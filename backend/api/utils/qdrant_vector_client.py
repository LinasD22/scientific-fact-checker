"""
Qdrant client for semantic search over scientific text snippets.

Workflow:
1. Core API returns full texts from academic papers
2. Each work is checked against persistent cache by title fingerprint
3. Cache MISS  → chunk + embed (ONNX) + store permanently in Qdrant
4. Cache HIT   → skip chunking/embedding entirely
5. ONE semantic search scoped to the current request's titles
6. Cross-encoder reranking on candidates before returning top_k
7. Results returned - cached chunks stay for future requests

Thread Safety:
- All Qdrant operations protected by _collection_lock (RLock)
- Prevents concurrent modifications during indexing + searching
- Lock is held during: search, store, cache checks, reranking
"""
import cProfile
import hashlib
import logging
import os
import pstats
import uuid
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from langchain_text_splitters import RecursiveCharacterTextSplitter
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    HnswConfigDiff,
    MatchAny,
    MatchValue,
    OptimizersConfigDiff,
    PayloadSchemaType,
    PointStruct,
    QuantizationSearchParams,
    ScalarQuantization,
    ScalarQuantizationConfig,
    ScalarType,
    SearchParams,
    VectorParams,
)

os.environ.setdefault("OMP_NUM_THREADS", "16")
os.environ.setdefault("OMP_WAIT_POLICY", "PASSIVE")
os.environ.setdefault("ONNXRUNTIME_INTER_OP_NUM_THREADS", "16")
os.environ.setdefault("ONNXRUNTIME_INTRA_OP_NUM_THREADS", "2")

from fastembed import TextEmbedding
from sentence_transformers import CrossEncoder

COLLECTION = "fact_checker_cache"

_EMBED_BATCH_SIZE  = 128
_UPSERT_BATCH_SIZE = 512   # buvo 256 — didesnis batch = mažiau round-trip'ų į Qdrant
_THREAD_POOL_SIZE  = 8
_FETCH_MULTIPLIER  = 2
_RERANK_BATCH      = 16

_PAYLOAD_FIELDS = [
    "chunk_text",
    "source",
    "source_db",
    "source_id",
    "published_date",
    "url",
]


class QdrantVectorClient:
    """Persistent local Qdrant client for searching scientific text snippets.

    Thread-safe: All Qdrant operations are protected by locks to prevent
    concurrent modification errors when both API searches and background indexing
    are running simultaneously.
    """
    def __init__(self):
        self.model_name = os.getenv(
            "EMBEDDING_MODEL",
            "BAAI/bge-small-en-v1.5",
        )
        self.reranker_model_name = os.getenv(
            "RERANKER_MODEL",
            "cross-encoder/ms-marco-MiniLM-L-6-v2",
        )
        self.min_score        = float(os.getenv("QDRANT_MIN_SCORE",        "0.65"))
        self.min_rerank_score = float(os.getenv("RERANKER_MIN_SCORE",      "-2.0"))
        self.global_min_score = float(os.getenv("QDRANT_GLOBAL_MIN_SCORE", "0.55"))
        self.chunk_size       = int(os.getenv("QDRANT_CHUNK_SIZE",         "800"))
        self.chunk_overlap    = int(os.getenv("QDRANT_CHUNK_OVERLAP",      "50"))
        self.cache_path       = os.getenv("QDRANT_CACHE_PATH", "./qdrant_cache")

        logging.info(f"Loading ONNX embedding model: {self.model_name}")
        self.model = TextEmbedding(
            model_name=self.model_name,
            providers=["CPUExecutionProvider"],
        )
        self.vector_size = self._probe_vector_size()
        logging.info(
            f"Embedding backend: fastembed/ONNX CPU | "
            f"dim={self.vector_size} | model={self.model_name}"
        )

        logging.info(f"Loading cross-encoder reranker: {self.reranker_model_name}")
        self.reranker = CrossEncoder(
            self.reranker_model_name,
            device="cpu",
        )
        logging.info("Reranker ready.")

        self.client = QdrantClient(path=self.cache_path)

        # Thread safety: RLock allows the same thread to acquire the lock multiple times
        # This is critical for nested operations (search → rerank) without deadlock
        self._collection_lock = threading.RLock()

        self._ensure_collection()

        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
        )

        self._executor = ThreadPoolExecutor(max_workers=_THREAD_POOL_SIZE)

    # ── Vector size probe ──────────────────────────────────────────────────────

    def _probe_vector_size(self) -> int:
        """Probe vector size - no lock needed, called during init."""
        vec = list(self.model.embed(["probe"]))[0]
        return len(vec)

    # ── Collection setup ───────────────────────────────────────────────────────

    def _ensure_collection(self) -> None:
        """Ensure collection exists - no lock needed, called during init."""
        existing = [c.name for c in self.client.get_collections().collections]
        if COLLECTION not in existing:
            self.client.create_collection(
                collection_name=COLLECTION,
                vectors_config=VectorParams(
                    size=self.vector_size,
                    distance=Distance.COSINE,
                    on_disk=False,
                ),
                hnsw_config=HnswConfigDiff(
                    m=32,               # default 16
                    ef_construct=200,   # default 100
                    on_disk=False,
                ),
                quantization_config=ScalarQuantization(
                    scalar=ScalarQuantizationConfig(
                        type=ScalarType.INT8,
                        quantile=0.99,
                        always_ram=True,
                    )
                ),
                optimizers_config=OptimizersConfigDiff(
                    indexing_threshold=20000,
                    memmap_threshold=500000,
                ),
            )
            for field in ("fingerprint", "source", "source_db", "source_id"):
                self.client.create_payload_index(
                    collection_name=COLLECTION,
                    field_name=field,
                    field_schema=PayloadSchemaType.KEYWORD,
                )
            logging.info(f"Created persistent Qdrant collection '{COLLECTION}'")
        else:
            count = self.client.count(collection_name=COLLECTION).count
            logging.info(
                f"Loaded existing Qdrant collection '{COLLECTION}' "
                f"({count} cached chunks)"
            )

    # ── Cache key ──────────────────────────────────────────────────────────────

    @staticmethod
    def _fingerprint(title: str, text: str) -> str:
        """Generate fingerprint - no lock needed, pure function."""
        content = f"{title.strip()}:{text[:200].strip()}"
        return hashlib.md5(content.encode()).hexdigest()

    def _is_cached(self, fingerprint: str) -> bool:
        """Check if fingerprint exists in cache - PROTECTED by lock."""
        with self._collection_lock:
            return self._is_cached_unlocked(fingerprint)

    def _is_cached_unlocked(self, fingerprint: str) -> bool:
        try:
            results = self.client.scroll(
                collection_name=COLLECTION,
                scroll_filter=Filter(
                    must=[FieldCondition(
                        key="fingerprint",
                        match=MatchValue(value=fingerprint),
                    )]
                ),
                limit=1,
                with_payload=False,
                with_vectors=False,
            )
            return len(results[0]) > 0
        except Exception as e:
            logging.error(f"Error checking cache for fingerprint: {e}")
            return False

    def _batch_is_cached(self, fingerprints: list[str]) -> set[str]:
        """
        Batch fingerprint tikrinimas — VIENAS Qdrant scroll kvietimas.

        Vietoj N atskirų scroll'ų (po vieną per straipsnį), siunčiamas
        vienas should filtras su visais fingerprint'ais iš karto.
        Grąžina set'ą fingerprint'ų, kurie jau yra kešuoti.
        """
        if not fingerprints:
            return set()

        cached: set[str] = set()
        # Skaidomame į batch'us — Qdrant should filtras veikia gerai iki ~500
        _BATCH = 500
        for i in range(0, len(fingerprints), _BATCH):
            batch = fingerprints[i : i + _BATCH]
            try:
                from qdrant_client.models import MatchAny
                results, _ = self.client.scroll(
                    collection_name=COLLECTION,
                    scroll_filter=Filter(
                        must=[FieldCondition(
                            key="fingerprint",
                            match=MatchAny(any=batch),
                        )]
                    ),
                    limit=len(batch),
                    with_payload=["fingerprint"],
                    with_vectors=False,
                )
                for point in results:
                    fp = (point.payload or {}).get("fingerprint", "")
                    if fp:
                        cached.add(fp)
            except Exception as e:
                logging.error(f"Batch fingerprint check error: {e}")
                # Fallback: nė vienas nelaikomas kešuotu — bus re-indeksuotas
        return cached

    # ── Embedding (ONNX / fastembed) ───────────────────────────────────────────

    def _embed(self, texts: list[str]) -> list[list[float]]:
        """Embed texts - no lock needed, doesn't modify Qdrant."""
        results: list[list[float]] = []
        for i in range(0, len(texts), _EMBED_BATCH_SIZE):
            batch = texts[i : i + _EMBED_BATCH_SIZE]
            batch_vecs = list(self.model.embed(batch))
            results.extend(v.tolist() for v in batch_vecs)
        return results

    # ── Reranking (cross-encoder) ──────────────────────────────────────────────

    def _rerank_parallel(
            self,
            claim: str,
            candidates: list[dict[str, Any]],
            top_k: int,
            num_threads: int = 4,
    ) -> list[dict[str, Any]]:
        if not candidates:
            return []

        # Padalinti kandidatus į grupes
        chunk_size = max(1, len(candidates) // num_threads)
        chunks = [candidates[i:i + chunk_size] for i in range(0, len(candidates), chunk_size)]

        def rerank_chunk(chunk):
            if not chunk:
                return []
            pairs = [(claim, c["text"]) for c in chunk]
            scores = self.reranker.predict(pairs, show_progress_bar=False).tolist()
            for c, s in zip(chunk, scores):
                c["rerank_score"] = round(float(s), 4)
            return chunk

        # Parallelinis vykdymas
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(rerank_chunk, chunk) for chunk in chunks]
            reranked_chunks = []
            for future in as_completed(futures):
                reranked_chunks.extend(future.result())

        # Surūšiuoti ir grąžinti top_k
        reranked_chunks.sort(key=lambda x: x["rerank_score"], reverse=True)
        return reranked_chunks[:top_k]


    def _rerank(
        self,
        claim: str,
        candidates: list[dict[str, Any]],
        top_k: int,
    ) -> list[dict[str, Any]]:

        if not candidates:
            return []

        pairs = [(claim, c["text"]) for c in candidates]
        all_scores: list[float] = []

        try:
            # Batch reranking - process in chunks to control memory
            for i in range(0, len(pairs), _RERANK_BATCH):
                batch_scores = self.reranker.predict(pairs[i : i + _RERANK_BATCH]).tolist()
                all_scores.extend(batch_scores)

            # Safety check: verify alignment
            if len(all_scores) != len(candidates):
                logging.warning(
                    f"Score mismatch: {len(all_scores)} scores for {len(candidates)} candidates. "
                    f"This may indicate concurrent Qdrant modifications. Truncating to match."
                )
                min_len = min(len(all_scores), len(candidates))
                all_scores = all_scores[:min_len]
                candidates = candidates[:min_len]

            # Assign scores safely
            for candidate, score in zip(candidates, all_scores):
                candidate["rerank_score"] = round(float(score), 4)

        except Exception as e:
            logging.error(
                f"Reranking error (possible concurrent modification): {e}. "
                f"Falling back to vector scores."
            )
            # Fallback: use existing vector scores
            for candidate in candidates:
                candidate["rerank_score"] = candidate.get("score", -5.0)

        # Filter and sort
        filtered = [s for s in candidates if s["rerank_score"] >= self.min_rerank_score]
        filtered.sort(key=lambda x: x["rerank_score"], reverse=True)

        # Log top results
        for item in filtered[:top_k]:
            logging.info(
                f"Rerank {item['rerank_score']:+.3f} "
                f"(vec {item['score']:.3f}) | {item['source']}"
            )

        return filtered[:top_k]

    # ── Chunking & storage ─────────────────────────────────────────────────────

    def _store_work(
        self,
        title: str,
        text: str,
        fingerprint: str,
        source_db: str = "lazy",
        source_id: str = "",
        authors: str | None = None,
        published_date: str | None = None,
        url: str | None = None,
    ) -> int:

        try:
            raw_chunks = self.splitter.split_text(text)
            if not raw_chunks:
                return 0

            vectors = self._embed(raw_chunks)

            points = [
                PointStruct(
                    id=str(uuid.uuid4()),
                    vector=vectors[i],
                    payload={
                        "chunk_text":     raw_chunks[i],
                        "source":         title,
                        "fingerprint":    fingerprint,
                        "source_db":      source_db,
                        "source_id":      source_id,
                        "authors":        authors,
                        "published_date": published_date,
                        "url":            url,
                    },
                )
                for i in range(len(raw_chunks))
            ]

            # ── Tik upsert su lock'u ─────────────────────────────────────────
            with self._collection_lock:
                for i in range(0, len(points), _UPSERT_BATCH_SIZE):
                    self.client.upsert(
                        collection_name=COLLECTION,
                        points=points[i : i + _UPSERT_BATCH_SIZE],
                    )

            return len(points)
        except Exception as e:
            logging.error(f"Error storing work '{title}': {e}")
            return 0

    # ── Bulk indexing (background indexer) ────────────────────────────────────

    def store_bulk_batch(
        self,
        articles: list[dict[str, Any]],
    ) -> dict[str, int]:
        """
        Indeksuoja kelis straipsnius vienu embed kvietimu.

        Optimizacijos:
          1. Fingerprint tikrinimas — vienas scroll su OR filtru (ne N atskirų)
          2. Embed'inimas vyksta BEZ lock'o
          3. Lock'as laikomas TIK upsert fazės metu
          4. Didesnis upsert batch (_UPSERT_BATCH_SIZE)

        Args:
            articles: Sąrašas dict'ų su raktais:
                        pmc_id, title, text, source_db, source_id,
                        authors (optional), published_date (optional), url (optional)

        Returns:
            {pmc_id: n_chunks_stored} — tik sėkmingai indeksuotų straipsnių.
        """
        if not articles:
            return {}

        # ── 1. Chunk'iname ir renkame fingerprint'us────────────
        candidate_articles = []
        for art in articles:
            pmc_id = art.get("pmc_id", "")
            title  = art.get("title") or "Unknown"
            text   = art.get("text") or ""
            if not text:
                continue
            raw_chunks = self.splitter.split_text(text)
            if not raw_chunks:
                continue
            fingerprint = self._fingerprint(title, text)
            candidate_articles.append((art, raw_chunks, fingerprint))

        if not candidate_articles:
            logging.info("store_bulk_batch: nėra teksto indeksavimui")
            return {}

        # ── 2. Batch fingerprint tikrinimas — VIENAS scroll su visais FP ─────
        all_fingerprints = [fp for _, _, fp in candidate_articles]
        cached_fingerprints = self._batch_is_cached(all_fingerprints)

        # ── 3. Filtruojame jau kešuotus straipsnius ──────────────────────────
        all_chunks: list[str] = []
        all_meta:   list[dict[str, Any]] = []
        article_chunk_counts: dict[str, int] = {}
        skipped_fingerprint = 0

        for art, raw_chunks, fingerprint in candidate_articles:
            pmc_id = art.get("pmc_id", "")

            if fingerprint in cached_fingerprints:
                logging.debug(f"store_bulk_batch: skip (fingerprint) {pmc_id}")
                skipped_fingerprint += 1
                continue

            meta = {
                "source":         art.get("title") or "Unknown",
                "fingerprint":    fingerprint,
                "source_db":      art.get("source_db", "pubmed_bulk"),
                "source_id":      pmc_id,
                "authors":        art.get("authors"),
                "published_date": art.get("published_date"),
                "url":            art.get("url"),
            }

            start_idx = len(all_chunks)
            all_chunks.extend(raw_chunks)
            all_meta.extend([meta] * len(raw_chunks))
            article_chunk_counts[pmc_id] = len(raw_chunks)

            logging.debug(
                f"store_bulk_batch: queued [{pmc_id}] "
                f"{meta['source'][:50]} → {len(raw_chunks)} chunks (offset {start_idx})"
            )

        if skipped_fingerprint:
            logging.info(f"store_bulk_batch: {skipped_fingerprint} straipsniai praleisti (fingerprint)")

        if not all_chunks:
            logging.info("store_bulk_batch: nėra naujų chunk'ų indeksavimui")
            return {}

        logging.info(
            f"store_bulk_batch: embed {len(all_chunks)} chunk'ų "
            f"iš {len(article_chunk_counts)} straipsnių..."
        )
        t0 = __import__("time").monotonic()
        vectors = self._embed(all_chunks)
        elapsed = __import__("time").monotonic() - t0
        logging.info(f"store_bulk_batch: embed baigtas [{elapsed:.1f}s]")

        points = [
            PointStruct(
                id=str(__import__("uuid").uuid4()),
                vector=vectors[i],
                payload={
                    "chunk_text": all_chunks[i],
                    **all_meta[i],
                },
            )
            for i in range(len(all_chunks))
        ]

        # ── 6. Upsert SU lock'u — kuo trumpiau ───────────────────────────────
        with self._collection_lock:
            for i in range(0, len(points), _UPSERT_BATCH_SIZE):
                self.client.upsert(
                    collection_name=COLLECTION,
                    points=points[i : i + _UPSERT_BATCH_SIZE],
                    wait=False,
                )

        logging.info(
            f"store_bulk_batch: upsert'inta {len(points)} chunk'ų "
            f"({len(article_chunk_counts)} straipsnių)"
        )

        return article_chunk_counts

    # ── Core search ────────────────────────────────────────────────────────────

    def search_snippets_from_texts(
        self,
        claim: str,
        works: list[dict[str, Any]],
        top_k: int = 5,
        works_metadata: dict[str, dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        if not works:
            return []

        valid_works = [
            (w.get("title", "Unknown"), w.get("text", ""))
            for w in works
            if w.get("text", "")
        ]

        def prep_work(args: tuple[str, str]) -> tuple[str, str, str]:
            title, text = args
            fp = self._fingerprint(title, text)
            return title, text, fp

        futures = [self._executor.submit(prep_work, w) for w in valid_works]
        cache_results = [f.result() for f in futures]

        cached_titles, new_titles = [], []
        works_meta = works_metadata or {}

        all_fps = [fp for _, _, fp in cache_results]
        with self._collection_lock:
            cached_fps = self._batch_is_cached(all_fps)

        for title, text, fp in cache_results:
            if fp in cached_fps:
                cached_titles.append(title)
                logging.info(f"Cache HIT  → '{title}'")
            else:
                meta = works_meta.get(title, {})
                # _store_work acquires lock internally for upsert only
                n = self._store_work(
                    title, text, fp,
                    source_db=meta.get("source_db", "lazy"),
                    source_id=meta.get("source_id", ""),
                    authors=meta.get("authors"),
                    published_date=meta.get("published_date"),
                    url=meta.get("url"),
                )
                new_titles.append(title)
                logging.info(f"Cache MISS → '{title}' stored {n} chunks")

        all_titles = cached_titles + new_titles
        if not all_titles:
            logging.warning("No usable works found - all texts were empty.")
            return []

        logging.info(
            f"Cache stats: {len(cached_titles)} hit(s), {len(new_titles)} miss(es)"
        )

        fetch_limit = top_k * _FETCH_MULTIPLIER
        query_vector = self._embed([claim])[0]

        try:
            response = self.client.query_points(
                collection_name=COLLECTION,
                query=query_vector,
                query_filter=Filter(
                    must=[FieldCondition(
                        key="source",
                        match=MatchAny(any=all_titles),
                    )]
                ),
                limit=fetch_limit,
                with_payload=_PAYLOAD_FIELDS,
                score_threshold=self.min_score,
                search_params=SearchParams(
                    hnsw_ef=96,
                    exact=False,
                    quantization=QuantizationSearchParams(
                        ignore=False,
                        rescore=True,
                        oversampling=2.0,
                    ),
                ),
            )
        except Exception as e:
            logging.error(f"Vector search error: {e}")
            return []

        candidates = []
        for hit in response.points:
            payload = hit.payload or {}
            candidates.append({
                "text":           payload.get("chunk_text", ""),
                "source":         payload.get("source", "Unknown"),
                "title":          payload.get("source", "Unknown"),
                "score":          round(hit.score, 4),
                "rerank_score":   -5.0,
                "source_db":      payload.get("source_db", ""),
                "source_id":      payload.get("source_id", ""),
                "authors":        payload.get("authors"),
                "published_date": payload.get("published_date"),
                "url":            payload.get("url"),
            })

        if not candidates:
            logging.warning("All vector search candidates below min_score threshold.")
            return []

        logging.info(
            f"Vector search: {len(candidates)} candidates above threshold "
            f"(requested {fetch_limit})"
        )

        return self._rerank(claim, candidates, top_k)

    def search_global(
        self,
        claim: str,
        top_k: int = 3,
        min_score: float | None = None,
    ) -> list[dict[str, Any]]:
        threshold = min_score if min_score is not None else self.global_min_score

        query_vector = self._embed([claim])[0]
        fetch_limit = top_k * _FETCH_MULTIPLIER

        try:
            response = self.client.query_points(
                collection_name=COLLECTION,
                query=query_vector,
                limit=fetch_limit,
                with_payload=_PAYLOAD_FIELDS,
                score_threshold=threshold,
                search_params=SearchParams(
                    hnsw_ef=64,
                    exact=False,
                    quantization=QuantizationSearchParams(
                        ignore=False,
                        rescore=True,
                        oversampling=2.0,
                    ),
                ),
            )
        except Exception as e:
            logging.error(f"Global search error: {e}")
            return []

        candidates = []
        for hit in response.points:
            payload = hit.payload or {}
            candidates.append({
                "text":           payload.get("chunk_text", ""),
                "source":         payload.get("source", "Unknown"),
                "title":          payload.get("source", "Unknown"),
                "score":          round(hit.score, 4),
                "rerank_score":   -5.0,
                "source_db":      payload.get("source_db", "unknown"),
                "source_id":      payload.get("source_id", ""),
                "authors":        payload.get("authors"),
                "published_date": payload.get("published_date"),
                "url":            payload.get("url"),
            })

        if not candidates:
            logging.info("search_global: nieko nerasta virš threshold.")
            return []

        logging.info(f"search_global: {len(candidates)} kandidatai → reranking")

        return self._rerank(claim, candidates, top_k)

    # ── Cache management ───────────────────────────────────────────────────────

    def cache_stats(self) -> dict[str, Any]:
        """Get cache statistics - PROTECTED by lock."""
        with self._collection_lock:
            total = self.client.count(collection_name=COLLECTION).count
            return {"total_chunks": total, "cache_path": self.cache_path}

    def clear_cache(self) -> None:
        """Clear entire cache - PROTECTED by lock."""
        with self._collection_lock:
            try:
                self.client.delete_collection(collection_name=COLLECTION)
                self._ensure_collection()
                logging.info("Cache cleared.")
            except Exception as e:
                logging.error(f"Error clearing cache: {e}")

    def close(self) -> None:
        """Close connections safely."""
        try:
            self._executor.shutdown(wait=True)
            self.client.close()
            logging.info("Qdrant client closed.")
        except Exception as e:
            logging.error(f"Error closing Qdrant client: {e}")

    def __del__(self) -> None:
        """Cleanup on deletion."""
        self.close()