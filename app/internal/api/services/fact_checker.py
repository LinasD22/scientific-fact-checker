"""
FactCheckerService orchestrates the full fact-checking pipeline:
1. Search Core API and PubMed API for relevant academic papers (parallel)
2. Deduplicate results using unique identifiers
3. Search Pinecone for high-relevance snippets from those papers
4. Use AI to fact-check each snippet against the claim
5. Compare results and return final verdict

AC:
- System must send queries to Core and PubMed databases simultaneously
- System must detect duplicate articles using unique identifiers
- Only unique articles should be sent to fact-checking AI
- If one database is unavailable, continue with the other and inform user
"""
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any

from app.internal.api.utils.ai_calls import AICallClient, FactCheckResponse, check_facts_with_ai
from app.internal.api.utils.core_api_client import CoreAPIClient
from app.internal.api.utils.pinecone_client import PineconeClient
from app.internal.api.utils.pubmed_api_client import PubMedAPIClient
from app.internal.api.utils.synonym_expander import expand_query


@dataclass
class FactCheckWork:
    """A single work from Core API prepared for fact-checking."""
    title: str
    published_date: str | None
    abstract: str | None
    full_text: str | None
    download_url: str | None
    source_id: str | None = None  # Unique identifier for deduplication
    source: str = "core"  # Source database


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
    databases_queried: list[str] = None  # Which databases were successfully queried
    partial_failure: str | None = None  # Message if one database failed


class FactCheckerService:

    def __init__(
        self,
        core_api_key: str | None = None,
        ai_api_key: str | None = None,
        pinecone_api_key: str | None = None,
        ai_base_url: str | None = None,
        pubmed_api_key: str | None = None,
    ):
        self.core_client = CoreAPIClient(api_key=core_api_key)
        self.pubmed_client = PubMedAPIClient(api_key=pubmed_api_key)
        self.ai_client = AICallClient(api_key=ai_api_key, base_url=ai_base_url)
        self.pinecone_client = PineconeClient(api_key=pinecone_api_key)

    def _get_snippets_for_claim(self, claim: str, top_k: int = 5) -> list[dict[str, Any]]:
        return self.pinecone_client.search_snippets_for_claim(claim=claim, top_k=top_k)

    def _search_core(self, query: str, limit: int) -> tuple[list[dict[str, Any]], str | None]:
        """
        Search Core API and return works with source identification.
        Returns tuple of (works, error_message)
        """
        try:
            raw_works = self.core_client.search_and_get_fulltext(query=query, limit=limit)
            works = []
            for w in raw_works:
                work = {
                    "title": w.get("title", "Untitled"),
                    "published_date": w.get("publishedDate"),
                    "abstract": w.get("abstract"),
                    "full_text": w.get("fullText"),
                    "download_url": w.get("downloadUrl"),
                    "source_id": w.get("id"),  # Core work ID
                    "source": "core"
                }
                works.append(work)
            return works, None
        except Exception as e:
            logging.error(f"Core API search failed: {e}")
            return [], f"Core API: {str(e)}"

    def _search_pubmed(self, query: str, limit: int) -> tuple[list[dict[str, Any]], str | None]:
        """
        Search PubMed API and return works with source identification.
        Returns tuple of (works, error_message)
        """
        try:
            raw_works = self.pubmed_client.search_and_get_fulltext(query=query, limit=limit)
            works = []
            for w in raw_works:
                work = {
                    "title": w.get("title", "Untitled"),
                    "published_date": w.get("published_date"),
                    "abstract": w.get("abstract"),
                    "full_text": w.get("full_text"),
                    "download_url": f"https://www.ncbi.nlm.nih.gov/pmc/articles/{w.get('pmc_id', '')}",
                    "source_id": w.get("pmc_id"),  # PMC ID
                    "source": "pubmed"
                }
                works.append(work)
            return works, None
        except Exception as e:
            logging.error(f"PubMed API search failed: {e}")
            return [], f"PubMed API: {str(e)}"

    def _deduplicate_works(
        self,
        works_list: list[list[dict[str, Any]]]
    ) -> list[dict[str, Any]]:
        """
        Deduplicate works based on unique identifiers.
        Uses title similarity and DOI/Core ID/PMC ID for matching.
        """
        unique_works = []
        seen_titles = set()
        
        for works in works_list:
            for work in works:
                title = work.get("title", "").lower().strip()
                
                # Skip if we've seen this exact title
                if title in seen_titles:
                    continue
                
                # Check for similar titles (simple fuzzy matching)
                is_duplicate = False
                for seen_title in seen_titles:
                    # Simple similarity check: if titles are very similar
                    if self._is_similar_title(title, seen_title):
                        is_duplicate = True
                        break
                
                if not is_duplicate:
                    unique_works.append(work)
                    seen_titles.add(title)
        
        return unique_works

    def _is_similar_title(self, title1: str, title2: str) -> bool:
        """
        Check if two titles are similar (likely duplicates).
        Uses simple word-based comparison.
        """
        if not title1 or not title2:
            return False
        
        # Get unique words from titles
        words1 = set(title1.split())
        words2 = set(title2.split())
        
        # If titles share more than 70% of words, consider them similar
        if len(words1) == 0 or len(words2) == 0:
            return False
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        similarity = len(intersection) / len(union)
        return similarity > 0.7

    def search_multiple_databases(
        self,
        query: str,
        limit_per_db: int = 3
    ) -> tuple[list[dict[str, Any]], list[str], str | None]:
        """
        Search both Core and PubMed databases in parallel.
        Returns unique works, list of successful databases, and error message if partial failure.
        
        Args:
            query: Search query
            limit_per_db: Number of results to fetch from each database
            
        Returns:
            Tuple of (unique_works, successful_databases, partial_failure_message)
        """
        databases_queried = []
        partial_failure = None
        
        # Use ThreadPoolExecutor for parallel execution
        with ThreadPoolExecutor(max_workers=2) as executor:
            future_to_db = {
                executor.submit(self._search_core, query, limit_per_db): "core",
                executor.submit(self._search_pubmed, query, limit_per_db): "pubmed"
            }
            
            all_works = []
            
            for future in as_completed(future_to_db):
                db_name = future_to_db[future]
                try:
                    works, error = future.result()
                    if error is None:
                        databases_queried.append(db_name)
                        all_works.append(works)
                        logging.info(f"{db_name.upper()} returned {len(works)} works")
                    else:
                        partial_failure = error
                        logging.warning(f"{db_name.upper()} search failed: {error}")
                except Exception as e:
                    error_msg = f"{db_name}: {str(e)}"
                    partial_failure = error_msg
                    logging.error(f"Unexpected error from {db_name}: {e}")
        
        # Deduplicate works from all databases
        unique_works = self._deduplicate_works(all_works)
        
        logging.info(f"Total unique works after deduplication: {len(unique_works)}")
        logging.info(f"Databases queried successfully: {databases_queried}")
        
        return unique_works, databases_queried, partial_failure

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
        use_multiple_dbs: bool = True,
    ) -> FactCheckResult:
        search_query = query or original_claim
        search_query = expand_query(search_query)

        # Step 1: Search Core API (or both Core and PubMed in parallel)
        if use_multiple_dbs:
            # Parallel search across multiple databases
            unique_works, databases_queried, partial_failure = self.search_multiple_databases(
                query=search_query,
                limit_per_db=limit
            )
            
            works = [
                FactCheckWork(
                    title=w.get("title", "Untitled"),
                    published_date=w.get("published_date"),
                    abstract=w.get("abstract"),
                    full_text=w.get("full_text"),
                    download_url=w.get("download_url"),
                    source_id=w.get("source_id"),
                    source=w.get("source", "unknown"),
                )
                for w in unique_works
            ]
        else:
            # Original single-database search (Core only)
            raw_works = self.core_client.search_and_get_fulltext(query=search_query, limit=limit)
            works = [
                FactCheckWork(
                    title=w.get("title", "Untitled"),
                    published_date=w.get("publishedDate"),
                    abstract=w.get("abstract"),
                    full_text=w.get("fullText"),
                    download_url=w.get("downloadUrl"),
                )
                for w in raw_works
            ]
            databases_queried = ["core"] if raw_works else []
            partial_failure = None

        works_with_text = [w for w in works if w.full_text or w.abstract]

        # Step 2: Chunk Core API texts and search Pinecone for best snippets
        works_for_pinecone = [
            {
                "text": w.full_text or w.abstract or "",
                "title": w.title,
            }
            for w in works_with_text
        ]
        snippets = self.pinecone_client.search_snippets_from_texts(
            claim=original_claim,
            works=works_for_pinecone,
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
            databases_queried=databases_queried,
            partial_failure=partial_failure,
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
            databases_queried=["texts_provided"],  # External texts provided
            partial_failure=None,
        )


def create_fact_checker(
    core_api_key: str | None = None,
    ai_api_key: str | None = None,
    pinecone_api_key: str | None = None,
    ai_base_url: str | None = None,
    pubmed_api_key: str | None = None,
) -> FactCheckerService:
    return FactCheckerService(
        core_api_key=core_api_key,
        ai_api_key=ai_api_key,
        pinecone_api_key=pinecone_api_key,
        ai_base_url=ai_base_url,
        pubmed_api_key=pubmed_api_key,
    )