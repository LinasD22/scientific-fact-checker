"""
Pinecone client for semantic search over scientific text snippets.

Workflow:
1. Core API returns full texts from academic papers
2. Texts are chunked locally using RecursiveCharacterTextSplitter
3. ALL chunks upserted into Pinecone in one pass (with unique session prefix)
4. ONE search_records() call returns most relevant snippets
5. ALL chunks deleted in one pass
"""
import logging
import os
import uuid
from typing import Any

from langchain_text_splitters import RecursiveCharacterTextSplitter
from pinecone import Pinecone


class PineconeClient:
    """Client for searching scientific text snippets in Pinecone."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("PINECONE_API_KEY", "")
        self.index_name = os.getenv("PINECONE_INDEX_NAME", "fact-checker")
        self.namespace = os.getenv("PINECONE_NAMESPACE", "pdf-vault")
        self.min_score = float(os.getenv("PINECONE_MIN_SCORE", "0.3"))
        self.chunk_size = int(os.getenv("PINECONE_CHUNK_SIZE", "800"))
        self.chunk_overlap = int(os.getenv("PINECONE_CHUNK_OVERLAP", "100"))

        self.pc = Pinecone(api_key=self.api_key)
        self.index = self.pc.Index(self.index_name)
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
        )

    # ── Chunking ──────────────────────────────────────────────────────────────

    def _chunk_texts(self, works: list[dict[str, Any]], session_id: str) -> list[dict[str, Any]]:
        """Chunk works into records ready for Pinecone upsert.
        session_id prefix ensures IDs are unique and easy to delete after search.
        """
        records = []
        for work_i, work in enumerate(works):
            text = work.get("text", "")
            title = work.get("title", "Unknown")
            if not text:
                continue

            citations = work.get("citations")
            chunks = self.splitter.split_text(text)
            for chunk_i, chunk in enumerate(chunks):
                records.append({
                    "id": f"{session_id}_{work_i}_{chunk_i}",
                    "chunk_text": chunk,
                    "source": title,
                    "citations": citations,
                })

        return records

    # ── Search existing index ─────────────────────────────────────────────────

    def search_snippets(
        self,
        query: str,
        top_k: int = 3,
        min_score: float | None = None,
        namespace: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search Pinecone index for snippets relevant to a query."""
        threshold = min_score if min_score is not None else self.min_score
        ns = namespace or self.namespace

        results = self.index.search_records(
            namespace=ns,
            query={
                "top_k": top_k * 3,  # daugiau kandidatų reranker'iui
                "inputs": {"text": query},
            },
            rerank={
                "model": "bge-reranker-v2-m3",
                "top_n": top_k * 2,  # reranker grąžina daugiau nei reikia, deduplikuosime
                "rank_fields": ["chunk_text"],
            },
        )

        seen_texts = set()
        snippets = []
        for hit in results.get("result", {}).get("hits", []):
            score = hit.get("_score", 0.0)
            fields = hit.get("fields", {})
            text = fields.get("chunk_text", "")

            if score < threshold:
                logging.warning(f"Hit score: {score:.3f} below threshold: {threshold} | {fields.get('source', '')}")
            elif text in seen_texts:
                logging.info(f"Skipping duplicate chunk | {fields.get('source', '')}")
            else:
                logging.info(f"Hit score: {score:.3f} | {fields.get('source', '')}")
                seen_texts.add(text)
                snippets.append({
                    "text": text,
                    "source": fields.get("source", "Unknown"),
                    "title": fields.get("source", "Unknown"),
                    "score": round(score, 4),
                    "citations": fields.get("citations"),
                })
                if len(snippets) >= top_k:
                    break

        return snippets

    # ── Search from raw texts (chunk + upsert + search + cleanup) ─────────────

    def search_snippets_from_texts(
        self,
        claim: str,
        works: list[dict[str, Any]],
        top_k: int = 3,
    ) -> list[dict[str, Any]]:
        """
        Chunk ALL provided texts, upsert everything at once, ONE search call,
        then delete everything. Much faster than per-segment approach.

        Uses a unique session_id prefix on all IDs so they can be safely
        identified and deleted without touching existing pdf-vault records.

        Args:
            claim: The fact/claim to search for
            works: List of dicts with 'text' and 'title'
            top_k: Number of snippets to return

        Returns:
            Most relevant snippets above min_score threshold
        """
        session_id = f"tmp_{uuid.uuid4().hex[:8]}"
        tmp_namespace = f"{self.namespace}_tmp"
        records = self._chunk_texts(works, session_id)

        if not records:
            return []

        record_ids = [r["id"] for r in records]
        logging.info(f"Session {session_id}: upserting {len(records)} chunks from {len(works)} work(s)")

        try:
            # Upsert all chunks in batches of 96
            for i in range(0, len(records), 96):
                self.index.upsert_records(
                    namespace=tmp_namespace,
                    records=records[i:i + 96],
                )

            # Single search call for all chunks
            snippets = self.search_snippets(query=claim, top_k=top_k, namespace=tmp_namespace)

        finally:
            # Delete all temporary records in batches of 1000
            for i in range(0, len(record_ids), 1000):
                self.index.delete(ids=record_ids[i:i + 1000], namespace=tmp_namespace)
            logging.info(f"Session {session_id}: deleted {len(record_ids)} chunks")

        return snippets

    # ── Convenience method ────────────────────────────────────────────────────

    def search_snippets_for_claim(
        self,
        claim: str,
        top_k: int = 3,
    ) -> list[dict[str, Any]]:
        """Search existing Pinecone index for snippets relevant to a claim."""
        return self.search_snippets(query=claim, top_k=top_k)