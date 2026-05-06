"""
FactCheckerService orchestrates the full fact-checking pipeline:
1. Search Core API and PubMed API for relevant academic papers (parallel)
2. Deduplicate results using unique identifiers
3. Search vector database for high-relevance snippets from those papers
4. Use AI to fact-check each snippet against the claim
5. Compare results and return final verdict
"""
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from api.utils.ai_calls import AICallClient, FactCheckResponse, check_facts_with_ai
from api.utils.core_api_client import CoreAPIClient
from api.utils.pubmed_api_client import PubMedAPIClient
from api.utils.qdrant_vector_client import QdrantVectorClient
from api.utils.synonym_expander import expand_query


@dataclass
class FactCheckWork:
    """A single work from Core API prepared for fact-checking."""
    title: str
    published_date: str | None
    abstract: str | None
    full_text: str | None
    download_url: str | None


@dataclass
class ArticleInfo:
    """Information about a scientific article used in fact-checking."""
    title: str
    published_date: str | None
    authors: str | None  # Author information if available
    source: str | None  # "core" or "pubmed"
    url: str | None
    index: int  # Index to link with individual_results


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
    articles_used: list[ArticleInfo]  # List of articles used for fact-checking


class FactCheckerService:

    def __init__(
        self,
        core_api_key: str | None = None,
        ai_api_key: str | None = None,
        ai_base_url: str | None = None,
        pubmed_api_key: str | None = None,
    ):
        self.core_client = CoreAPIClient(api_key=core_api_key)
        self.pubmed_client = PubMedAPIClient(api_key=pubmed_api_key)
        self.ai_client = AICallClient(api_key=ai_api_key, base_url=ai_base_url)
        self.vector_embed_client = QdrantVectorClient()


    def _search_core(self, query: str, limit: int) -> tuple[list[dict[str, Any]], str | None]:
        """Search Core API and return works with source identification."""
        try:
            raw_works = self.core_client.search_and_get_fulltext(query=query, limit=limit)
            works = []
            for w in raw_works:
                # Extract authors from various possible fields
                authors = None
                if w.get("authors"):
                    author_list = w.get("authors", [])
                    if isinstance(author_list, list):
                        authors = ", ".join([a.get("name", "") for a in author_list if a.get("name")])
                    elif isinstance(author_list, str):
                        authors = author_list
                elif w.get("creator"):
                    authors = w.get("creator")
                
                work = {
                    "title": w.get("title", "Untitled"),
                    "published_date": w.get("publishedDate"),
                    "authors": authors,
                    "abstract": w.get("abstract"),
                    "full_text": w.get("fullText"),
                    "download_url": w.get("downloadUrl"),
                    "source_id": w.get("id"),
                    "source": "core"
                }
                works.append(work)
            return works, None
        except Exception as e:
            logging.error(f"Core API search failed: {e}")
            return [], f"Core API: {str(e)}"

    def _search_pubmed(self, query: str, limit: int) -> tuple[list[dict[str, Any]], str | None]:
        """Search PubMed API and return works with source identification."""
        try:
            raw_works = self.pubmed_client.search_and_get_fulltext(query=query, limit=limit)
            works = []
            for w in raw_works:
                work = {
                    "title": w.get("title", "Untitled"),
                    "published_date": w.get("published_date"),
                    "authors": w.get("authors"),  # PubMed client should provide authors
                    "abstract": w.get("abstract"),
                    "full_text": w.get("full_text"),
                    "download_url": f"https://www.ncbi.nlm.nih.gov/pmc/articles/{w.get('pmc_id', '')}",
                    "source_id": w.get("pmc_id"),
                    "source": "pubmed"
                }
                works.append(work)
            return works, None
        except Exception as e:
            logging.error(f"PubMed API search failed: {e}")
            return [], f"PubMed API: {str(e)}"

    def _deduplicate_works(self, works_list: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
        """Deduplicate works based on unique identifiers."""
        unique_works = []
        seen_titles = set()
        
        for works in works_list:
            for work in works:
                title = work.get("title", "").lower().strip()
                if title in seen_titles:
                    continue
                unique_works.append(work)
                seen_titles.add(title)
        
        return unique_works

    def _get_years_ago(self, published_date: str | None) -> float | None:
        """Calculate years ago from published date. Returns None if date is invalid."""
        if not published_date:
            return None
        
        try:
            # Try parsing various date formats
            for fmt in ["%Y-%m-%d", "%Y-%m", "%Y"]:
                try:
                    pub_date = datetime.strptime(published_date[:10] if len(published_date) >= 10 else published_date, fmt)
                    break
                except ValueError:
                    continue
            else:
                return None
            
            # Use current time in UTC
            current_date = datetime.now(timezone.utc)
            
            # Handle naive dates (assume UTC)
            if pub_date.tzinfo is None:
                pub_date = pub_date.replace(tzinfo=timezone.utc)
            
            # Calculate years difference
            days_diff = (current_date - pub_date).days
            if days_diff < 0:
                return 0  # Future dates treated as 0 years ago
            
            return days_diff / 365.25
        except (ValueError, TypeError, OSError):
            return None

    def _prioritize_works_by_age(
        self, 
        works: list[dict[str, Any]], 
        target_count: int
    ) -> list[dict[str, Any]]:
        """Prioritize works by age: <2 years > <5 years > any.
        
        Args:
            works: List of works with published_date field
            target_count: Desired number of works to return
            
        Returns:
            Prioritized list of works
        """
        if not works or target_count <= 0:
            return []
        
        current_year = 2026  # Current year from environment
        
        # Categorize works by age
        less_than_2_years = []
        less_than_5_years = []
        older_or_unknown = []
        
        for work in works:
            years_ago = self._get_years_ago(work.get("published_date"))
            
            if years_ago is None:
                # Unknown date - put in fallback category
                older_or_unknown.append(work)
            elif years_ago < 2:
                less_than_2_years.append(work)
            elif years_ago < 5:
                less_than_5_years.append(work)
            else:
                older_or_unknown.append(work)
        
        # Build prioritized result
        prioritized = []
        
        # First, add all <2 year old papers
        prioritized.extend(less_than_2_years)
        
        # If we need more, add <5 year old papers
        if len(prioritized) < target_count:
            remaining_needed = target_count - len(prioritized)
            prioritized.extend(less_than_5_years[:remaining_needed])
        
        # If we still need more, add older/unknown papers
        if len(prioritized) < target_count:
            remaining_needed = target_count - len(prioritized)
            prioritized.extend(older_or_unknown[:remaining_needed])
        
        logging.info(
            f"Paper age prioritization: {len(less_than_2_years)} <2yo, "
            f"{len(less_than_5_years)} <5yo, {len(older_or_unknown)} older/unknown. "
            f"Returning {len(prioritized)} papers."
        )
        
        return prioritized

    def search_multiple_databases(
        self,
        query: str,
        limit_per_db: int = 10
    ) -> tuple[list[dict[str, Any]], list[str], str | None]:
        print(f"=== SEARCH MULTIPLE DATABASES ===")
        """Search both Core and PubMed databases in parallel.
        
        Uses expanded query for Core API (handles complex boolean queries),
        and original query for PubMed (simpler is better for their API).
        """
        databases_queried = []
        partial_failure = None
        
        # Expand query for Core (handles complex OR syntax well)
        expanded_query = expand_query(query)
        
        with ThreadPoolExecutor(max_workers=2) as executor:
            future_to_db = {
                executor.submit(self._search_core, expanded_query, limit_per_db): "core",
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
        
        unique_works = self._deduplicate_works(all_works)
        logging.info(f"Total unique works after deduplication: {len(unique_works)}")
        
        # Prioritize papers by age: <2 years > <5 years > any
        # Multiply limit by 2 to get enough candidates for prioritization
        prioritized_works = self._prioritize_works_by_age(
            works=unique_works, 
            target_count=limit_per_db * 2
        )
        
        return prioritized_works, databases_queried, partial_failure

    def _format_individual_results(
        self,
        individual_responses: list[FactCheckResponse],
        source_texts: list[dict[str, Any]],
        article_index_map: dict[str, int] | None = None,
    ) -> list[dict[str, Any]]:
        """Format individual AI responses with their source texts.
        
        Args:
            individual_responses: AI responses for each source
            source_texts: The source texts used
            article_index_map: Optional mapping from title to article index
        """
        individual_results = []
        for i, res in enumerate(individual_responses):
            source = source_texts[i] if i < len(source_texts) else {}
            source_title = source.get("title", "Unknown")
            
            result_dict = {
                "source_title": source_title,
                "source_url": source.get("url"),
                "published_date": source.get("published_date"),
                "qdrant_score": source.get("score"),
                "rerank_score": source.get("rerank_score"),  # May be None if not available
                "source_text": source.get("text", ""),  # ← originalus tekstas
                "is_verified": res.is_verified,
                "confidence": res.confidence,
                "result": res.result.value,
                "explanation": res.explanation,
                "supporting_evidence": res.supporting_evidence,
                "contradicting_evidence": res.contradicting_evidence,
            }
            
            # Add article index if mapping is provided
            if article_index_map and source_title in article_index_map:
                result_dict["article_index"] = article_index_map[source_title]
            
            individual_results.append(result_dict)
        return individual_results

    def check_claim(
        self,
        original_claim: str,
        query: str | None = None,
        limit: int = 10,
        global_search_threshold: float = 0.6,
        global_min_results: int = 5,
    ) -> FactCheckResult:
        search_query = query or original_claim

        logging.info(f"ALL PARAMETERS limit {limit} global search threshold {global_search_threshold} global min results {global_min_results}")

        # ── Step 1: Bandyk global Qdrant search (greita, be API calls) ──────────
        global_snippets = self.vector_embed_client.search_global(
            claim=original_claim,
            top_k=8,
            min_score=global_search_threshold,
        )

        if len(global_snippets) >= global_min_results:
            logging.info(
                f"Global search rado {len(global_snippets)} snippetų — "
                f"praleižiame API calls."
            )
            source_texts = [
                {
                    "text": s["text"],
                    "title": s["title"],
                    "url": s.get("url"),
                    "score": s["score"],
                    "published_date": s.get("published_date"),
                    "authors": s.get("authors"),
                }
                for s in global_snippets
            ]
            
            # Build articles_used from unique snippets (grouped by title)
            seen_titles = {}
            articles_used = []
            article_index = 0
            for snippet in global_snippets:
                title = snippet.get("title", "Unknown")
                if title.lower().strip() not in seen_titles:
                    seen_titles[title.lower().strip()] = article_index
                    articles_used.append(ArticleInfo(
                        title=title,
                        published_date=snippet.get("published_date"),
                        authors=snippet.get("authors"),
                        source=snippet.get("source_db", "unknown"),
                        url=snippet.get("url"),
                        index=article_index,
                    ))
                    article_index += 1
            
            # Create article_index_map for linking snippets to articles
            article_index_map = {title.lower().strip(): idx for title, idx in seen_titles.items()}
            
            # Grąžinam rezultatą be API calls
            individual_responses, comparison = check_facts_with_ai(
                original_claim=original_claim,
                source_texts=source_texts,
                ai_client=self.ai_client,
            )
            return FactCheckResult(
                original_claim=original_claim,
                works_searched=0,
                works_with_text=0,
                snippets_used=len(source_texts),
                individual_results=self._format_individual_results(
                    individual_responses, source_texts, article_index_map
                ),
                sorted_results=comparison.sorted_results,
                consensus=comparison.consensus.value if comparison.consensus else None,
                final_verdict=comparison.final_verdict.value,
                summary=comparison.summary,
                agreement_score=comparison.agreement_score,
                articles_used=articles_used,
            )

        logging.info(
            f"Global search rado tik {len(global_snippets)}, min result threshold {global_min_results} — "
            f"fallback į lazy indexing."
        )

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
            )
            for w in unique_works
        ]




        works_with_text = [w for w in works if w.full_text or w.abstract]
        logging.info(f"works: {len(works)}, works_with_text: {len(works_with_text)}")
        # Create lookup from unique_works to get metadata by title
        unique_works_lookup = {}
        for w in unique_works:
            title = w.get("title", "Untitled")
            unique_works_lookup[title.lower().strip()] = {
                "authors": w.get("authors"),
                "published_date": w.get("published_date"),
                "source": w.get("source", "unknown"),
                "url": w.get("download_url"),
            }

        works_for_qdrant = [
            {
                "text": w.full_text or w.abstract or "",
                "title": w.title,
            }
            for w in works_with_text
        ]
        
        # Step 2: Chunk, embed and search for best snippets using qdrant
        # Build metadata map for storing article info in Qdrant (with authors from unique_works)
        works_metadata = {}
        for w in works_with_text:
            title_key = w.title.lower().strip()
            work_meta = unique_works_lookup.get(title_key, {})
            works_metadata[w.title] = {
                "authors": work_meta.get("authors"),
                "published_date": w.published_date,
                "url": w.download_url,
            }
        
        snippets = self.vector_embed_client.search_snippets_from_texts(
            claim=original_claim,
            works=works_for_qdrant,
            top_k=5,
            works_metadata=works_metadata,
        )

        # Step 3: Qdrant snippets or fallback to full texts
        if snippets:
            logging.warning("NAUDOJAMI SNIPPETS")
            source_texts = []
            used_titles = set()  # Track which works actually provided snippets
            for s in snippets:
                title_key = s["title"].lower().strip()
                work_meta = unique_works_lookup.get(title_key, {})
                source_texts.append({
                    "text": s["text"],
                    "title": s["title"],
                    "url": work_meta.get("url"),  # Get URL from lookup
                    "score": s["score"],
                    "published_date": s.get("published_date"),
                    "authors": work_meta.get("authors"),
                })
                used_titles.add(title_key)
        else:
            logging.warning("NAUDOJAMI FULL TEXT")
            source_texts = []
            used_titles = set()
            for work in works_with_text:
                text = work.full_text or work.abstract or ""
                if text:
                    title_key = work.title.lower().strip()
                    work_meta = unique_works_lookup.get(title_key, {})
                    source_texts.append({
                        "text": text,
                        "title": work.title,
                        "url": work.download_url,
                        "published_date": work.published_date,
                        "authors": work_meta.get("authors"),
                    })
                    used_titles.add(title_key)

        if not source_texts:
            return FactCheckResult(
                original_claim=original_claim,
                works_searched=len(works),
                works_with_text=len(works_with_text),
                snippets_used=0,
                individual_results=[],
                sorted_results=[],
                consensus=None,
                final_verdict="unverifiable",
                summary="No source texts found from Core API or Qdrant for this claim.",
                agreement_score=0.0,
                articles_used=[],
            )

        # Step 4: Build articles_used ONLY from works that actually provided snippets
        articles_used = []
        seen_titles = {}
        for title_key in used_titles:
            work_meta = unique_works_lookup.get(title_key, {})
            articles_used.append(ArticleInfo(
                title=next((w.title for w in works_with_text if w.title.lower().strip() == title_key), title_key.title()),
                published_date=work_meta.get("published_date"),
                authors=work_meta.get("authors"),
                source=work_meta.get("source", "unknown"),
                url=work_meta.get("url"),
                index=len(articles_used),
            ))
            seen_titles[title_key] = len(articles_used) - 1
        
        # Create article_index_map for linking snippets to articles
        article_index_map = {title.lower().strip(): idx for title, idx in seen_titles.items()}

        # Step 5: AI fact-checking
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
            individual_results=self._format_individual_results(
                individual_responses, source_texts, article_index_map
            ),
            sorted_results=comparison.sorted_results,
            consensus=comparison.consensus.value if comparison.consensus else None,
            final_verdict=comparison.final_verdict.value,
            summary=comparison.summary,
            agreement_score=comparison.agreement_score,
            articles_used=articles_used,
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
            articles_used=[],  # No search-based articles for texts-only check
        )


def create_fact_checker(
    core_api_key: str | None = None,
    ai_api_key: str | None = None,
    ai_base_url: str | None = None,
    pubmed_api_key: str | None = None,
) -> FactCheckerService:
    return FactCheckerService(
        core_api_key=core_api_key,
        ai_api_key=ai_api_key,
        ai_base_url=ai_base_url,
        pubmed_api_key=pubmed_api_key,
    )