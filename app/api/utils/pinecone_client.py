"""
Pinecone client for semantic search over scientific text snippets.

Workflow:
1. Core API returns full texts from academic papers
2. Texts are chunked and upserted into Pinecone (via upload script)
3. This client searches Pinecone for snippets most relevant to a claim
4. Only snippets above PINECONE_MIN_SCORE threshold are returned
"""
import logging
import os
from typing import Any

from pinecone import Pinecone

class PineconeClient:
    """Client for searching scientific text snippets in Pinecone."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("PINECONE_API_KEY", "")
        self.index_name = os.getenv("PINECONE_INDEX_NAME", "fact-checker")
        self.namespace = os.getenv("PINECONE_NAMESPACE", "pdf-vault")
        self.min_score = float(os.getenv("PINECONE_MIN_SCORE", "0.3"))

        self.pc = Pinecone(api_key=self.api_key)
        self.index = self.pc.Index(self.index_name)

    def search_snippets(
        self,
        query: str,
        top_k: int = 3,
        min_score: float | None = None,
    ) -> list[dict[str, Any]]:
        """
        Search Pinecone for text snippets relevant to a query/claim.

        Args:
            query: The claim or search query to find relevant snippets for
            top_k: Number of top results to retrieve before score filtering
            min_score: Minimum similarity score (overrides env var if provided)

        Returns:
            List of snippets with text, source, and score - filtered by min_score
        """
        threshold = min_score if min_score is not None else self.min_score



        results = self.index.search_records(
            namespace=self.namespace,
            query={
                "top_k": top_k,
                "inputs": {"text": query},
            },
            rerank={
                "model": "bge-reranker-v2-m3",
                "top_n": top_k,
                "rank_fields": ["chunk_text"],
            },
        )

        snippets = []
        for hit in results.get("result", {}).get("hits", []):
            if hit.get('_score') < threshold:
                logging.warning(f"Hit score: {hit.get('_score')} | threshold: {threshold}")
            else:
                logging.info(f"Hit score: {hit.get('_score')} | threshold: {threshold}")

            score = hit.get("_score", 0.0)
            if score >= threshold:
                fields = hit.get("fields", {})
                snippets.append({
                    "text": fields.get("chunk_text", ""),
                    "source": fields.get("source", "Unknown"),
                    "title": fields.get("title", fields.get("source", "Unknown")),
                    "score": round(score, 4),
                })

        return snippets

    def search_snippets_for_claim(
        self,
        claim: str,
        top_k: int = 3,
    ) -> list[dict[str, Any]]:
        """
        Convenience method - searches for snippets relevant to a specific claim.

        Args:
            claim: The fact/claim to find evidence for
            top_k: Number of candidates before score filtering

        Returns:
            High-relevance snippets to use for fact-checking
        """
        return self.search_snippets(query=claim, top_k=top_k)
