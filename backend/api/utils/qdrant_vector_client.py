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
import hashlib
import json
import logging
import os
import time
import uuid
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
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

from MeshParser import log

#os.environ.setdefault("OMP_NUM_THREADS", "16")
os.environ.setdefault("OMP_WAIT_POLICY", "PASSIVE")
#os.environ.setdefault("ONNXRUNTIME_INTER_OP_NUM_THREADS", "16")
#os.environ.setdefault("ONNXRUNTIME_INTRA_OP_NUM_THREADS", "2")

from fastembed import TextEmbedding, SparseTextEmbedding
from rank_bm25 import BM25Okapi
from sentence_transformers import CrossEncoder

COLLECTION = "fact_checker_cache"

_EMBED_BATCH_SIZE  = 1024
_UPSERT_BATCH_SIZE = 1024
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
        self.min_rerank_score = float(os.getenv("RERANKER_MIN_SCORE",      "-4.0"))
        self.global_min_score = float(os.getenv("QDRANT_GLOBAL_MIN_SCORE", "0.55"))
        self.chunk_size       = int(os.getenv("QDRANT_CHUNK_SIZE",         "800"))
        self.chunk_overlap    = int(os.getenv("QDRANT_CHUNK_OVERLAP",      "50"))
        self.cache_path       = os.getenv("QDRANT_CACHE_PATH", "./qdrant_cache")

        logging.info(f"Loading ONNX embedding model: {self.model_name}")
        self.model = TextEmbedding(
            model_name=self.model_name,
            providers=["CPUExecutionProvider"],
            cuda=False,
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
            backend="onnx",
        )
        logging.info("Reranker ready.")

        self.splade_model_name = os.getenv(
            "SPLADE_MODEL",
            "prithivida/Splade_PP_en_v1",
        )
        logging.info(f"Loading SPLADE sparse model: {self.splade_model_name}")
        self.splade_model = SparseTextEmbedding(
            model_name=self.splade_model_name,
            providers=["CPUExecutionProvider"],
        )
        logging.info("SPLADE model ready.")

        qdrant_url = os.getenv("QDRANT_URL")
        if qdrant_url:
            self.client = QdrantClient(url=qdrant_url)
            logging.info(f"Qdrant: serverio režimas → {qdrant_url}")
        else:
            self.client = QdrantClient(path=self.cache_path)
            logging.info(f"Qdrant: lokalus failų režimas → {self.cache_path}")

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
        vec = list(self.model.embed(["probe"]))[0]
        return len(vec)

    # ── Collection setup ───────────────────────────────────────────────────────

    def _ensure_collection(self) -> None:
        existing = [c.name for c in self.client.get_collections().collections]
        if COLLECTION not in existing:
            self.client.create_collection(
                collection_name=COLLECTION,
                vectors_config=VectorParams(
                    size=self.vector_size,
                    distance=Distance.COSINE,
                    on_disk=True,
                ),
                hnsw_config=HnswConfigDiff(
                    m=16,
                    ef_construct=32,
                    on_disk=True,
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
                    memmap_threshold=10000,
                ),
                on_disk_payload=True,
            )
            for field in ("fingerprint", "source", "source_db", "source_id"):
                self.client.create_payload_index(
                    collection_name=COLLECTION,
                    field_name=field,
                    field_schema=PayloadSchemaType.KEYWORD,
                )
            logging.info(f"Created persistent Qdrant collection '{COLLECTION}'")

            config_dict = self.client.get_collection(COLLECTION).config.dict() # Konvertuojame i žodyna
            print(json.dumps(config_dict, indent=2))
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
        Grąžina set'ą fingerprint'ų, kurie jau yra kešuoti.
        """
        if not fingerprints:
            return set()

        cached: set[str] = set()
        _BATCH = 200
        for i in range(0, len(fingerprints), _BATCH):
            batch = fingerprints[i : i + _BATCH]
            try:
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

    def embed_articles_bulk(
        self,
        articles: list[dict[str, Any]],
    ) -> tuple[list[str], list[list[float]], list[dict], dict[str, int]]:
        log.info(f"EMBED STARTING: {articles[0].get('pmc_id', 'unknown')} at {time.time()}")
        """
        Atlieka tik chunk'inimą ir embedding'ą (be upsert).
        Grąžina:
            - chunks: sąrašas chunk'ų tekstų
            - vectors: sąrašas vektorių
            - payloads: sąrašas payload'ų (metaduomenų)
            - article_chunk_counts: {pmc_id: chunk_count}
        """
        if not articles:
            return [], [], [], {}

        # 1. Chunk'inimas ir fingerprintų generavimas
        candidate_articles = []
        for art in articles:
            pmc_id = art.get("pmc_id", "")
            title = art.get("title") or "Unknown"
            text = art.get("text") or ""
            if not text:
                continue
            raw_chunks = self.splitter.split_text(text)
            if not raw_chunks:
                continue
            fingerprint = self._fingerprint(title, text)
            candidate_articles.append((art, raw_chunks, fingerprint))

        if not candidate_articles:
            logging.info("embed_articles_bulk: nėra teksto indeksavimui")
            return [], [], [], {}

        # 2. Batch fingerprint tikrinimas — VIENAS scroll su visais FP
        all_fingerprints = [fp for _, _, fp in candidate_articles]
        cached_fingerprints = self._batch_is_cached(all_fingerprints)

        # 3. Filtruojame jau kešuotus straipsnius
        all_chunks: list[str] = []
        all_meta: list[dict[str, Any]] = []
        article_chunk_counts: dict[str, int] = {}
        skipped_fingerprint = 0

        for art, raw_chunks, fingerprint in candidate_articles:
            pmc_id = art.get("pmc_id", "")

            if fingerprint in cached_fingerprints:
                logging.debug(f"embed_articles_bulk: skip (fingerprint) {pmc_id}")
                skipped_fingerprint += 1
                continue

            meta = {
                "chunk_text": "",  # placeholder, bus užpildyta vėliau
                "source": art.get("title") or "Unknown",
                "fingerprint": fingerprint,
                "source_db": art.get("source_db", "pubmed_bulk"),
                "source_id": pmc_id,
                "authors": art.get("authors"),
                "published_date": art.get("published_date"),
                "url": art.get("url"),
            }

            all_chunks.extend(raw_chunks)
            all_meta.extend([meta.copy() for _ in raw_chunks])
            article_chunk_counts[pmc_id] = len(raw_chunks)

            logging.debug(
                f"embed_articles_bulk: queued [{pmc_id}] "
                f"{meta['source'][:50]} → {len(raw_chunks)} chunks"
            )

        if skipped_fingerprint:
            logging.info(f"embed_articles_bulk: {skipped_fingerprint} straipsniai praleisti (fingerprint)")

        if not all_chunks:
            logging.info("embed_articles_bulk: nėra naujų chunk'ų indeksavimui")
            return [], [], [], {}

        # 4. Embedding
        logging.info(
            f"embed_articles_bulk: embed {len(all_chunks)} chunk'ų "
            f"iš {len(article_chunk_counts)} straipsnių..."
        )
        t0 = __import__("time").monotonic()
        vectors = self._embed(all_chunks)
        elapsed = __import__("time").monotonic() - t0
        logging.info(f"embed_articles_bulk: embed baigtas [{elapsed:.1f}s]")

        # 5. Užpildome chunk_text payload'uose
        for i, chunk in enumerate(all_chunks):
            all_meta[i]["chunk_text"] = chunk

        log.info(f"EMBED FINISHED: took {elapsed:.1f}s")
        return all_chunks, vectors, all_meta, article_chunk_counts

    def upsert_points(
        self,
        chunks: list[str],
        vectors: list[list[float]],
        payloads: list[dict[str, Any]],
    ) -> None:
        """
        Įrašo jau sugeneruotus vektorius į Qdrant (su lock'u).

        Args:
            chunks: Sąrašas chunk'ų tekstų (naudojamas log'ams)
            vectors: Sąrašas vektorių
            payloads: Sąrašas payload'ų
        """
        if not chunks or not vectors or not payloads:
            logging.warning("upsert_points: tuščiai duomenys")
            return

        if len(chunks) != len(vectors) or len(chunks) != len(payloads):
            logging.error(f"upsert_points: dydžių nesutapimas: chunks={len(chunks)}, vectors={len(vectors)}, payloads={len(payloads)}")
            return

        points = [
            PointStruct(
                id=str(uuid.uuid4()),
                vector=vectors[i],
                payload=payloads[i],
            )
            for i in range(len(chunks))
        ]

        with self._collection_lock:
            for i in range(0, len(points), _UPSERT_BATCH_SIZE):
                self.client.upsert(
                    collection_name=COLLECTION,
                    points=points[i : i + _UPSERT_BATCH_SIZE],
                    wait=False,
                )

        logging.info(f"upsert_points: upsert'inta {len(points)} chunk'ų")

    def store_bulk_batch(
        self,
        articles: list[dict[str, Any]],
    ) -> dict[str, int]:
        """
        Indeksuoja kelis straipsnius vienu embed kvietimu (sinchroniškai).

        Šis metodas paliktas dėl API suderinamumo. Naujam kodui rekomenduojama
        naudoti embed_articles_bulk() + upsert_points() atskirai.
        """
        chunks, vectors, payloads, article_chunk_counts = self.embed_articles_bulk(articles)
        if chunks:
            self.upsert_points(chunks, vectors, payloads)
        return article_chunk_counts

    def get_all_pmc_ids(self) -> set[str]:
        """
        Nuskaito visus source_id (pmc_id) iš Qdrant.

        Returns:
            Set'as unikalių PMC ID
        """
        indexed: set[str] = set()
        offset = None
        batch_num = 0
        BATCH_SIZE = 10_000

        with self._collection_lock:
            while True:
                try:
                    results, next_offset = self.client.scroll(
                        collection_name=COLLECTION,
                        scroll_filter=Filter(must=[
                            FieldCondition(key="source_db", match=MatchValue(value="pubmed_bulk"))
                        ]),
                        limit=BATCH_SIZE,
                        offset=offset,
                        with_payload=["source_id"],
                        with_vectors=False,
                    )
                except Exception as e:
                    logging.warning(f"Klaida skaitant Qdrant: {e}")
                    break

                for point in results:
                    sid = (point.payload or {}).get("source_id", "")
                    if sid:
                        indexed.add(sid)

                batch_num += 1
                if batch_num % 10 == 0:
                    logging.info(f"  ... nuskaityta {len(indexed)} ID ({batch_num} batchų)")

                if next_offset is None:
                    break
                offset = next_offset

        return indexed

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

        new_articles_to_embed: list[dict] = []

        for title, text, fp in cache_results:
            if fp in cached_fps:
                cached_titles.append(title)
                logging.info(f"Cache HIT  → '{title}'")
            else:
                meta = works_meta.get(title, {})
                new_articles_to_embed.append({
                    "title": title,
                    "text": text,
                    "pmc_id": meta.get("source_id", ""),
                    "source_db": meta.get("source_db", "lazy"),
                    "authors": meta.get("authors"),
                    "published_date": meta.get("published_date"),
                    "url": meta.get("url"),
                })
                new_titles.append(title)
                logging.info(f"Cache MISS → '{title}' (queued for batch embed)")

        # Batch embed visi nauji straipsniai vienu ONNX kvietimu
        if new_articles_to_embed:
            logging.info(f"Batch embedding {len(new_articles_to_embed)} naujų straipsnių...")
            chunks, vectors, payloads, _ = self.embed_articles_bulk(new_articles_to_embed)
            if chunks:
                self.upsert_points(chunks, vectors, payloads)
                logging.info(f"Batch embed baigtas: {len(chunks)} chunks iš {len(new_articles_to_embed)} straipsnių")

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

    # ── BM25 helpers ───────────────────────────────────────────────────────────

    _BM25_STOPWORDS: frozenset[str] = frozenset({
        "the", "a", "an", "of", "in", "is", "to", "and", "or", "with",
        "was", "were", "are", "be", "been", "this", "that", "for", "from",
        "by", "at", "as", "on", "it", "its", "not", "we", "our", "their",
        "these", "those", "also", "but", "had", "has", "have", "which",
        "that", "than", "can", "may", "who", "when", "where", "into",
    })

    @staticmethod
    def _tokenize_with_bigrams(text: str, stopwords: frozenset[str] = _BM25_STOPWORDS) -> list[str]:
        """
        Unigrams + bigrams po stopwords filtracijos.

        "blood pressure medication" →
            ["blood", "pressure", "medication", "blood_pressure", "pressure_medication"]

        Bigrams pagerina medicininiams terminams:
        "blood_pressure", "clinical_trial", "placebo_controlled" ir pan.
        """
        tokens = [t for t in text.lower().split() if t not in stopwords]
        bigrams = [f"{tokens[i]}_{tokens[i + 1]}" for i in range(len(tokens) - 1)]
        return tokens + bigrams

    @staticmethod
    def _prf_expand(
        claim: str,
        first_pass_chunks: list[dict[str, Any]],
        top_n_docs: int = 3,
        top_n_terms: int = 6,
        stopwords: frozenset[str] = _BM25_STOPWORDS,
    ) -> str:
        """
        Pseudo Relevance Feedback — išplečia query terminais iš top BM25 chunk'ų.

        Prielaida: PMC/CORE jau grąžino relevantius straipsnius, todėl
        top chunk'ai yra pakankamai patikimi terminų šaltiniai.

        Args:
            claim:              Originalus teiginys
            first_pass_chunks:  BM25 pirmo pass'o rezultatai (surūšiuoti pagal score)
            top_n_docs:         Iš kiek top chunk'ų rinkti terminus
            top_n_terms:        Kiek expansion terminų pridėti
            stopwords:          Filtruojami žodžiai

        Returns:
            Išplėstas query string'as
        """
        import re
        from collections import Counter

        top_texts = " ".join(c["text"] for c in first_pass_chunks[:top_n_docs])
        words = re.findall(r'\b[a-zA-Z]{4,}\b', top_texts.lower())
        words = [w for w in words if w not in stopwords]

        claim_tokens = set(claim.lower().split())
        term_counts = Counter(w for w in words if w not in claim_tokens)

        expansion_terms = [t for t, _ in term_counts.most_common(top_n_terms)]
        if not expansion_terms:
            return claim

        expanded = f"{claim} {' '.join(expansion_terms)}"
        logging.info(f"PRF expansion: [{', '.join(expansion_terms)}]")
        return expanded

    def search_snippets_bm25(
        self,
        claim: str,
        works: list[dict[str, Any]],
        top_k: int = 5,
        works_metadata: dict[str, dict[str, Any]] | None = None,
        rerank_candidates: int = 30,
        prf_first_pass: int = 10,
        prf_min_chunks: int = 3,
    ) -> list[dict[str, Any]]:
        """
        BM25 + bigrams + PRF (Pseudo Relevance Feedback) + cross-encoder reranking.

        Pipeline:
          1. Chunk'iname visus works
          2. BM25 pirmas pass (bigrams) — renkame PRF kandidatus
          3. PRF — išplečiame query terminais iš top chunk'ų
          4. BM25 antras pass su išplėstu query
          5. Cross-encoder reranking

        Args:
            claim:             Teiginys / query
            works:             [{"title": ..., "text": ...}]
            top_k:             Kiek geriausių snippet'ų grąžinti
            works_metadata:    {title: {"published_date", "url", "authors", ...}}
            rerank_candidates: Kiek BM25 kandidatų perduoti reranker'iui
            prf_first_pass:    Kiek top chunk'ų naudoti PRF terminų rinkimui
            prf_min_chunks:    Minimalus chunk'ų skaičius PRF aktyvavimui
        """
        if not works:
            return []

        works_meta = works_metadata or {}

        # Chunk'iname visus works
        all_chunks: list[dict[str, Any]] = []
        for work in works:
            title = work.get("title", "Unknown")
            text  = work.get("text", "")
            if not text:
                continue
            meta = works_meta.get(title, {})
            for chunk in self.splitter.split_text(text):
                all_chunks.append({
                    "text":           chunk,
                    "title":          title,
                    "source":         title,
                    "score":          0.0,
                    "rerank_score":   -5.0,
                    "published_date": meta.get("published_date"),
                    "url":            meta.get("url"),
                    "authors":        meta.get("authors"),
                    "source_db":      meta.get("source_db", "lazy"),
                    "source_id":      meta.get("source_id", ""),
                })

        if not all_chunks:
            logging.warning("search_snippets_bm25: nėra chunk'ų iš works")
            return []

        # Tokenizuojame corpus su bigrams
        tokenized_corpus = [self._tokenize_with_bigrams(c["text"]) for c in all_chunks]
        bm25 = BM25Okapi(tokenized_corpus)

        # ── Pass 1: PRF terminų rinkimas ────────────────────────────────────────
        first_tokens = self._tokenize_with_bigrams(claim)
        first_scores  = bm25.get_scores(first_tokens)

        first_indices = sorted(
            range(len(first_scores)),
            key=lambda i: first_scores[i],
            reverse=True,
        )
        first_pass_chunks = [
            all_chunks[i]
            for i in first_indices[:prf_first_pass]
            if first_scores[i] > 0
        ]

        # ── PRF expansion ───────────────────────────────────────────────────────
        if len(first_pass_chunks) >= prf_min_chunks:
            expanded_claim = self._prf_expand(claim, first_pass_chunks)
        else:
            expanded_claim = claim
            logging.info(
                f"search_snippets_bm25: PRF praleistas "
                f"(tik {len(first_pass_chunks)} chunk'ų < min {prf_min_chunks})"
            )

        # ── Pass 2: galutinis BM25 scoring su išplėstu query ───────────────────

        final_tokens = self._tokenize_with_bigrams(expanded_claim)
        final_scores  = bm25.get_scores(final_tokens)

        top_indices = sorted(
            range(len(final_scores)),
            key=lambda i: final_scores[i],
            reverse=True,
        )[:rerank_candidates]

        candidates = []
        for i in top_indices:
            if final_scores[i] <= 0:
                break
            chunk = dict(all_chunks[i])
            chunk["score"] = round(float(final_scores[i]), 4)
            candidates.append(chunk)

        if not candidates:
            logging.warning("search_snippets_bm25: visi BM25 scores == 0 (query terminai nerasti)")
            return []

        logging.info(
            f"search_snippets_bm25: {len(all_chunks)} chunks → "
            f"{len(candidates)} BM25 kandidatai → reranking"
        )

        return self._rerank(claim, candidates, top_k)

    def search_global(
        self,
        claim: str,
        top_k: int = 3,
        min_score: float | None = None,
    ) -> list[dict[str, Any]]:
        logging.info(f"--search_global START {claim} : {datetime.now().strftime("%H:%M:%S.%f")} ")
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