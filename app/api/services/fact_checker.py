from dataclasses import dataclass
from typing import Any

from api.utils.ai_calls import (
    AICallClient,
    ComparisonResult,
    FactCheckResponse,
    check_facts_with_ai,
)
from api.utils.core_api_client import CoreAPIClient


@dataclass
class FactCheckWork:
    """A single work from Core API prepared for fact-checking."""
    title: str
    published_date: str | None
    abstract: str | None
    full_text: str | None
    download_url: str | None


@dataclass
class FactCheckResult:
    """Final fact-check result combining all sources."""
    original_claim: str
    works_searched: int
    works_with_text: int
    individual_results: list[dict[str, Any]]
    sorted_results: list[dict[str, Any]]
    consensus: str | None
    final_verdict: str
    summary: str
    agreement_score: float


class FactCheckerService:
    """
    Main service that orchestrates the fact-checking workflow:
    1. Search Core API for relevant academic works
    2. Use AI to check each text against the original claim
    3. Use AI to compare results and provide final verdict
    """
    
    def __init__(
        self,
        core_api_key: str | None = None,
        ai_api_key: str | None = None,
        ai_base_url: str | None = None
    ):
        """
        Initialize the fact-checker service.
        
        Args:
            core_api_key: Core API key (defaults to env var)
            ai_api_key: AI API key (defaults to env var)
            ai_base_url: AI API base URL (defaults to env var)
        """
        self.core_client = CoreAPIClient(api_key=core_api_key)
        self.ai_client = AICallClient(api_key=ai_api_key, base_url=ai_base_url)
    
    def search_works(
        self,
        query: str,
        limit: int = 3
    ) -> list[FactCheckWork]:
        """
        Search for academic works using Core API.
        
        Args:
            query: Search query (e.g., "obesity prevalence 2050")
            limit: Number of results to fetch
        
        Returns:
            List of FactCheckWork objects
        """
        results = self.core_client.search_and_get_fulltext(query=query, limit=limit)
        
        works = []
        for item in results:
            works.append(FactCheckWork(
                title=item.get("title", "Untitled"),
                published_date=item.get("publishedDate"),
                abstract=item.get("abstract"),
                full_text=item.get("fullText"),
                download_url=item.get("downloadUrl")
            ))
        
        return works
    
    def check_claim(
        self,
        original_claim: str,
        query: str | None = None,
        limit: int = 3
    ) -> FactCheckResult:
        """
        Main method: Check a claim against academic papers.
        
        This method:
        1. Searches Core API for relevant works
        2. Uses AI to fact-check each work
        3. Uses AI to compare and get final verdict
        
        Args:
            original_claim: The fact/claim to verify
            query: Optional search query (defaults to original_claim)
            limit: Number of academic papers to search
        
        Returns:
            FactCheckResult with all details
        """
        search_query = query or original_claim
        
        # Step 1: Search Core API
        works = self.search_works(search_query, limit=limit)
        
        # Step 2: Prepare texts for AI fact-checking
        source_texts = []
        for work in works:
            # Prefer full text, fall back to abstract
            text = work.full_text or work.abstract or ""
            if text:
                source_texts.append({
                    "text": text,
                    "title": work.title,
                    "url": work.download_url,
                    "published_date": work.published_date
                })
        
        # Step 3: Run AI fact-checking
        individual_responses, comparison = check_facts_with_ai(
            original_claim=original_claim,
            source_texts=source_texts,
            ai_client=self.ai_client
        )
        
        # Step 4: Format individual results
        individual_results = []
        for i, res in enumerate(individual_responses):
            source = source_texts[i] if i < len(source_texts) else {}
            individual_results.append({
                "source_title": source.get("title", "Unknown"),
                "source_url": source.get("url"),
                "published_date": source.get("published_date"),
                "is_verified": res.is_verified,
                "confidence": res.confidence,
                "result": res.result.value,
                "explanation": res.explanation,
                "supporting_evidence": res.supporting_evidence,
                "contradicting_evidence": res.contradicting_evidence
            })
        
        # Step 5: Build final result
        return FactCheckResult(
            original_claim=original_claim,
            works_searched=len(works),
            works_with_text=len(source_texts),
            individual_results=individual_results,
            sorted_results=comparison.sorted_results,
            consensus=comparison.consensus.value if comparison.consensus else None,
            final_verdict=comparison.final_verdict.value,
            summary=comparison.summary,
            agreement_score=comparison.agreement_score
        )
    
    def check_claim_with_texts(
        self,
        original_claim: str,
        texts: list[dict[str, str]]
    ) -> FactCheckResult:
        """
        Check a claim against provided texts (without Core API search).
        
        Args:
            original_claim: The fact/claim to verify
            texts: List of dicts with 'text', 'title', and optional 'url'
        
        Returns:
            FactCheckResult with all details
        """
        # Run AI fact-checking directly
        _, comparison = check_facts_with_ai(
            original_claim=original_claim,
            source_texts=texts,
            ai_client=self.ai_client
        )
        
        # Format individual results
        individual_results = []
        for i, text_data in enumerate(texts):
            individual_results.append({
                "source_title": text_data.get("title", "Unknown"),
                "source_url": text_data.get("url"),
                "is_verified": False,
                "confidence": 0.0,
                "result": "unverifiable",
                "explanation": "Not checked",
                "supporting_evidence": [],
                "contradicting_evidence": []
            })
        
        return FactCheckResult(
            original_claim=original_claim,
            works_searched=len(texts),
            works_with_text=len(texts),
            individual_results=individual_results,
            sorted_results=comparison.sorted_results,
            consensus=comparison.consensus.value if comparison.consensus else None,
            final_verdict=comparison.final_verdict.value,
            summary=comparison.summary,
            agreement_score=comparison.agreement_score
        )


def create_fact_checker(
    core_api_key: str | None = None,
    ai_api_key: str | None = None,
    ai_base_url: str | None = None
) -> FactCheckerService:
    """
    Factory function to create a FactCheckerService instance.
    
    Args:
        core_api_key: Core API key
        ai_api_key: AI API key  
        ai_base_url: AI API base URL
    
    Returns:
        Configured FactCheckerService instance
    """
    return FactCheckerService(
        core_api_key=core_api_key,
        ai_api_key=ai_api_key,
        ai_base_url=ai_base_url
    )
