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
"""
import hashlib
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from langchain_text_splitters import RecursiveCharacterTextSplitter
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchAny,
    MatchValue,
    PayloadSchemaType,
    PointStruct,
    VectorParams,
)

os.environ.setdefault("OMP_NUM_THREADS", "16")
os.environ.setdefault("OMP_WAIT_POLICY", "PASSIVE")   # avoid busy-wait on idle cores
os.environ.setdefault("ONNXRUNTIME_INTER_OP_NUM_THREADS", "16")
os.environ.setdefault("ONNXRUNTIME_INTRA_OP_NUM_THREADS", "2")

from fastembed import TextEmbedding  # noqa: E402  (must come after .env vars)
from sentence_transformers import CrossEncoder  # noqa: E402

COLLECTION = "fact_checker_cache"

# Ryzen 9950X batch optimum: large enough to saturate ONNX threads,
# small enough to avoid memory pressure on long academic texts.
_EMBED_BATCH_SIZE  = 128
_UPSERT_BATCH_SIZE = 256   # Qdrant local file — larger batch = fewer syscalls
_THREAD_POOL_SIZE  = 8     # for parallel _is_cached scroll lookups

# Reranking: fetch more candidates from Qdrant so the cross-encoder
# has enough material to reorder before we cut to top_k.
_FETCH_MULTIPLIER = 4   # fetch top_k * 4 candidates for reranking

# ------ Reikia cargo ir rustc iš: https://rustup.rs/
class QdrantVectorClient:
    """Persistent local Qdrant client for searching scientific text snippets.

    Chunks and embeddings are cached on disk by title fingerprint.
    Subsequent requests for the same paper skip chunking and embedding entirely.

    Embedding backend: fastembed (ONNX Runtime) — ~3-5x faster than
    sentence-transformers on CPU, no GPU required.

    Reranking backend: cross-encoder/ms-marco-MiniLM-L-6-v2 — lightweight
    cross-encoder that re-scores (claim, chunk) pairs for higher precision.
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
        self.min_score     = float(os.getenv("QDRANT_MIN_SCORE",      "0.3"))
        self.min_rerank_score = float(os.getenv("RERANKER_MIN_SCORE", "-5.0"))
        self.chunk_size    = int(os.getenv("QDRANT_CHUNK_SIZE",       "800"))
        self.chunk_overlap = int(os.getenv("QDRANT_CHUNK_OVERLAP",    "50"))
        self.cache_path    = os.getenv("QDRANT_CACHE_PATH", "./qdrant_cache")

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
            # MiniLM-L-6 fits comfortably in RAM; no GPU needed
            device="cpu",
        )
        logging.info("Reranker ready.")

        self.client = QdrantClient(path=self.cache_path)
        self._ensure_collection()

        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
        )

        # Reusable thread pool for parallel cache lookups
        self._executor = ThreadPoolExecutor(max_workers=_THREAD_POOL_SIZE)

    # ── Vector size probe ──────────────────────────────────────────────────────

    def _probe_vector_size(self) -> int:
        """Embed a single token to discover the model's output dimension."""
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
                ),
            )
            self.client.create_payload_index(
                collection_name=COLLECTION,
                field_name="fingerprint",
                field_schema=PayloadSchemaType.KEYWORD,
            )
            self.client.create_payload_index(
                collection_name=COLLECTION,
                field_name="source",
                field_schema=PayloadSchemaType.KEYWORD,
            )
            self.client.create_payload_index(
                collection_name=COLLECTION,
                field_name="source_db",
                field_schema=PayloadSchemaType.KEYWORD,
            )
            self.client.create_payload_index(
                collection_name=COLLECTION,
                field_name="source_id",
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
        content = f"{title.strip()}:{text[:200].strip()}"
        return hashlib.md5(content.encode()).hexdigest()

    def _is_cached(self, fingerprint: str) -> bool:
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

    # ── Embedding (ONNX / fastembed) ───────────────────────────────────────────

    def _embed(self, texts: list[str]) -> list[list[float]]:
        """
        Embed a list of texts using fastembed (ONNX Runtime).

        fastembed.embed() is a generator — we batch internally to control
        memory on large chunk lists while keeping ONNX threads saturated.
        """
        results: list[list[float]] = []
        for i in range(0, len(texts), _EMBED_BATCH_SIZE):
            batch = texts[i : i + _EMBED_BATCH_SIZE]
            batch_vecs = list(self.model.embed(batch))
            results.extend(v.tolist() for v in batch_vecs)
        return results

    # ── Reranking (cross-encoder) ──────────────────────────────────────────────

    def _rerank(
        self,
        claim: str,
        candidates: list[dict[str, Any]],
        top_k: int,
    ) -> list[dict[str, Any]]:
        """
        Score each (claim, chunk_text) pair with the cross-encoder,
        filter by min_rerank_score, sort descending, return top_k.

        Cross-encoder scores are raw logits (unbounded floats) — higher = better.
        -5.0 default min_rerank_score drops clearly irrelevant chunks while
        keeping borderline ones that passed the vector search threshold.
        """
        if not candidates:
            return []

        pairs = [(claim, c["text"]) for c in candidates]
        scores: list[float] = self.reranker.predict(pairs).tolist()

        # Attach rerank score to each candidate
        # Update rerank scores (they were initialized with default -5.0)
        for candidate, score in zip(candidates, scores):
            candidate["rerank_score"] = round(score, 4)
        scored = candidates

        # Filter low-quality results, then sort best-first
        filtered = [s for s in scored if s["rerank_score"] >= self.min_rerank_score]
        filtered.sort(key=lambda x: x["rerank_score"], reverse=True)

        for item in filtered[:top_k]:
            logging.info(
                f"Rerank {item['rerank_score']:+.3f} "
                f"(vec {item['score']:.3f}) | {item['source']}"
            )

        return filtered[:top_k]

    # ── Chunking & storage ─────────────────────────────────────────────────────

    def _store_work(self, title: str, text: str, fingerprint: str,
                    source_db: str = "lazy", source_id: str = "") -> int:
        raw_chunks = self.splitter.split_text(text)
        if not raw_chunks:
            return 0

        vectors = self._embed(raw_chunks)

        offset = self.client.count(collection_name=COLLECTION).count
        points = [
            PointStruct(
                id=offset + i,
                vector=vectors[i],
                payload={
                    "chunk_text": raw_chunks[i],
                    "source": title,
                    "fingerprint": fingerprint,
                    "source_db": source_db,
                    "source_id": source_id,
                }
            )
            for i in range(len(raw_chunks))
        ]

        # Larger batches → fewer Qdrant file-system round-trips
        for i in range(0, len(points), _UPSERT_BATCH_SIZE):
            self.client.upsert(
                collection_name=COLLECTION,
                points=points[i : i + _UPSERT_BATCH_SIZE],
            )

        return len(points)

    # ── Core search ────────────────────────────────────────────────────────────

    def search_snippets_from_texts(
        self,
        claim: str,
        works: list[dict[str, Any]],
        top_k: int = 20,
    ) -> list[dict[str, Any]]:
        """
        For each work: serve from cache or chunk+embed+store.
        Cache lookups run in parallel via ThreadPoolExecutor.
        Then:
          1. Vector search → top_k * _RERANK_FETCH_MULTIPLIER candidates
          2. Cross-encoder reranking → top_k final results
        """
        if not works:
            return []

        # ── Parallel cache lookup ──────────────────────────────────────────────
        valid_works = [
            (w.get("title", "Unknown"), w.get("text", ""))
            for w in works
            if w.get("text", "")
        ]

        def check_work(args: tuple[str, str]) -> tuple[str, str, str, bool]:
            title, text = args
            fp = self._fingerprint(title, text)
            return title, text, fp, self._is_cached(fp)

        futures = [self._executor.submit(check_work, w) for w in valid_works]
        cache_results = [f.result() for f in futures]

        cached_titles, new_titles = [], []
        for title, text, fp, is_hit in cache_results:
            if is_hit:
                cached_titles.append(title)
                logging.info(f"Cache HIT  → '{title}'")
            else:
                n = self._store_work(title, text, fp, source_db="lazy")
                new_titles.append(title)
                logging.info(f"Cache MISS → '{title}' stored {n} chunks")

        all_titles = cached_titles + new_titles
        if not all_titles:
            logging.warning("No usable works found - all texts were empty.")
            return []

        logging.info(
            f"Cache stats: {len(cached_titles)} hit(s), {len(new_titles)} miss(es)"
        )

        # ── Stage 1: vector search — fetch more candidates for reranker ────────
        fetch_limit = top_k * _FETCH_MULTIPLIER
        query_vector = self._embed([claim])[0]
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
            with_payload=True,
        )

        # Build candidates list, applying vector score threshold
        candidates = []
        for hit in response.points:
            score   = hit.score
            payload = hit.payload or {}
            if score < self.min_score:
                logging.warning(
                    f"Vec score {score:.3f} below threshold {self.min_score} "
                    f"| {payload.get('source', '')}"
                )
                continue
            candidates.append({
                "text":        payload.get("chunk_text", ""),
                "source":      payload.get("source", "Unknown"),
                "title":       payload.get("source", "Unknown"),
                "score":       round(score, 4),
                "rerank_score": -5.0,  # Default rerank score (will be updated later)
            })

        if not candidates:
            logging.warning("All vector search candidates below min_score threshold.")
            return []

        logging.info(
            f"Vector search: {len(candidates)} candidates above threshold "
            f"(requested {fetch_limit})"
        )

        # ── Stage 2: cross-encoder reranking ───────────────────────────────────
        return self._rerank(claim, candidates, top_k)

    def search_global(
            self,
            claim: str,
            top_k: int = 3,
            min_score: float = 0.45,
    ) -> list[dict[str, Any]]:
        """
        Ieško per VISĄ kolekciją be title filtro.
        Naudojama kai turima daug embedded dokumentų.
        """
        query_vector = self._embed([claim])[0]
        fetch_limit = top_k * _FETCH_MULTIPLIER

        response = self.client.query_points(
            collection_name=COLLECTION,
            query=query_vector,
            limit=fetch_limit,
            with_payload=True,
            score_threshold=min_score,
        )

        candidates = []
        for hit in response.points:
            payload = hit.payload or {}
            candidates.append({
                "text": payload.get("chunk_text", ""),
                "source": payload.get("source", "Unknown"),
                "title": payload.get("source", "Unknown"),
                "score": round(hit.score, 4),
                "source_db": payload.get("source_db", "unknown"),
                "source_id": payload.get("source_id", ""),
            })

        if not candidates:
            logging.info("search_global: nieko nerasta virš threshold.")
            return []

        logging.info(f"search_global: {len(candidates)} kandidatai → reranking")
        return self._rerank(claim, candidates, top_k)

    # ── Cache management ───────────────────────────────────────────────────────

    def cache_stats(self) -> dict[str, Any]:
        total = self.client.count(collection_name=COLLECTION).count
        return {"total_chunks": total, "cache_path": self.cache_path}

    def clear_cache(self) -> None:
        self.client.delete_collection(collection_name=COLLECTION)
        self._ensure_collection()
        logging.info("Cache cleared.")

    def close(self) -> None:
        try:
            self._executor.shutdown(wait=False)
            self.client.close()
        except Exception:
            pass

    def __del__(self) -> None:
        self.close()