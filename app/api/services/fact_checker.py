"""
FactCheckerService orchestrates the full fact-checking pipeline:
1. Search Core API for relevant academic papers
2. Search Pinecone for high-relevance snippets from those papers
3. Use AI to fact-check each snippet against the claim
4. Compare results and return final verdict
"""
import logging
import os
from dataclasses import dataclass
from typing import Any

from api.utils.ai_calls import AICallClient, FactCheckResponse, check_facts_with_ai
from api.utils.core_api_client import CoreAPIClient
from api.utils.pinecone_client import PineconeClient


@dataclass
class FactCheckWork:
    """A single work from Core API prepared for fact-checking."""
    title: str
    published_date: str | None
    abstract: str | None
    full_text: str | None
    download_url: str | None
    citation_count: int | None = None


@dataclass
class FactCheckResult:
    """Final fact-check result combining all sources."""
    original_claim: str
    works_searched: int
    works_with_text: int
    snippets_used: int
    individual_results: list[dict[str, Any]]
    sorted_results: list[dict[str, Any]]
    consensus: str | None
    final_verdict: str
    summary: str
    agreement_score: float


class FactCheckerService:

    def __init__(
        self,
        core_api_key: str | None = None,
        ai_api_key: str | None = None,
        pinecone_api_key: str | None = None,
        ai_base_url: str | None = None,
    ):
        self.core_client = CoreAPIClient(api_key=core_api_key)
        self.ai_client = AICallClient(api_key=ai_api_key, base_url=ai_base_url)
        self.pinecone_client = PineconeClient(api_key=pinecone_api_key)

    def _get_snippets_for_claim(self, claim: str, top_k: int = 5) -> list[dict[str, Any]]:
        return self.pinecone_client.search_snippets_for_claim(claim=claim, top_k=top_k)

    def _format_individual_results(
        self,
        individual_responses: list[FactCheckResponse],
        source_texts: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Format individual AI responses with their source texts."""
        individual_results = []
        for i, res in enumerate(individual_responses):
            source = source_texts[i] if i < len(source_texts) else {}
            individual_results.append({
                "source_title": source.get("title", "Unknown"),
                "source_url": source.get("url"),
                "citations": source.get("citations", []),
                "published_date": source.get("published_date"),
                "pinecone_score": source.get("score"),
                "source_text": source.get("text", ""),  # ← originalus tekstas
                "is_verified": res.is_verified,
                "confidence": res.confidence,
                "result": res.result.value,
                "explanation": res.explanation,
                "supporting_evidence": res.supporting_evidence,
                "contradicting_evidence": res.contradicting_evidence,
            })
        return individual_results

    def check_claim(
        self,
        original_claim: str,
        query: str | None = None,
        limit: int = 1,
    ) -> FactCheckResult:
        search_query = query or original_claim

        # Step 1: Search Core API
        raw_works = self.core_client.search_and_get_fulltext(query=search_query, limit=limit)
        works = [
            FactCheckWork(
                title=w.get("title", "Untitled"),
                published_date=w.get("publishedDate"),
                abstract=w.get("abstract"),
                full_text=w.get("fullText"),
                download_url=w.get("downloadUrl"),
                citation_count=w.get("citationCount"),
            )
            for w in raw_works
        ]
        works_with_text = [w for w in works if w.full_text or w.abstract]

        # Step 2: Chunk Core API texts and search Pinecone for best snippets
        works_for_pinecone = [
            {
                "text": w.full_text or w.abstract or "",
                "title": w.title,
                "citations": w.citation_count,
            }
            for w in works_with_text
        ]
        snippets = self.pinecone_client.search_snippets_from_texts(
            claim=original_claim,
            works=works_for_pinecone,
            top_k=6
        )

        # Step 3: Pinecone snippets or fallback to full texts
        if snippets:
            logging.warning("NAUDOJAMI SNIPPETS")
            source_texts = [
                {
                    "text": s["text"],
                    "title": s["title"],
                    "url": None,
                    "score": s["score"],
                    "citations": s.get("citations"),
                }
                for s in snippets
            ]
        else:
            logging.warning("NAUDOJAMI FULL TEXT")
            source_texts = []
            for work in works_with_text:
                text = work.full_text or work.abstract or ""
                if text:
                    source_texts.append({
                        "text": text,
                        "title": work.title,
                        "url": work.download_url,
                        "published_date": work.published_date,
                        "citations": work.citation_count,
                    })

        # Step 4: AI fact-checking
        individual_responses, comparison = check_facts_with_ai(
            original_claim=original_claim,
            source_texts=source_texts,
            ai_client=self.ai_client,
        )

        return FactCheckResult(
            original_claim=original_claim,
            works_searched=len(works),
            works_with_text=len(works_with_text),
            snippets_used=len(source_texts),
            individual_results=self._format_individual_results(individual_responses, source_texts),
            sorted_results=comparison.sorted_results,
            consensus=comparison.consensus.value if comparison.consensus else None,
            final_verdict=comparison.final_verdict.value,
            summary=comparison.summary,
            agreement_score=comparison.agreement_score,
        )

    def check_claim_with_texts(
        self,
        original_claim: str,
        texts: list[dict[str, str]],
    ) -> FactCheckResult:
        responses, comparison = check_facts_with_ai(
            original_claim=original_claim,
            source_texts=texts,
            ai_client=self.ai_client,
        )

        return FactCheckResult(
            original_claim=original_claim,
            works_searched=len(texts),
            works_with_text=len(texts),
            snippets_used=len(texts),
            individual_results=self._format_individual_results(responses, texts),
            sorted_results=comparison.sorted_results,
            consensus=comparison.consensus.value if comparison.consensus else None,
            final_verdict=comparison.final_verdict.value,
            summary=comparison.summary,
            agreement_score=comparison.agreement_score,
        )


def create_fact_checker(
    core_api_key: str | None = None,
    ai_api_key: str | None = None,
    pinecone_api_key: str | None = None,
    ai_base_url: str | None = None,
) -> FactCheckerService:
    return FactCheckerService(
        core_api_key=core_api_key,
        ai_api_key=ai_api_key,
        pinecone_api_key=pinecone_api_key,
        ai_base_url=ai_base_url,
    )