"""
PubMed API client for searching academic papers.
Uses E-utilities (esearch) for finding article IDs and BioC-PMC for full-text content.
Based on the recommended approach from the user.
"""

import os
import time
import logging
from typing import Any
from functools import wraps
from typing import TypeVar
from pathlib import Path

import requests

import sys
sys.path.insert(0, str(Path(__file__).parent))
from query_cleaner import clean_query_for_pubmed

logger = logging.getLogger(__name__)

T = TypeVar('T')


def with_retry(max_retries: int = 3, initial_delay: float = 1.0, backoff_factor: float = 2.0):
    """Decorator for retrying failed API calls."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            delay = initial_delay
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except (requests.RequestException, requests.HTTPError) as e:
                    last_exception = e
                    if attempt < max_retries:
                        time.sleep(delay)
                        delay *= backoff_factor
                    else:
                        break
            if last_exception:
                raise last_exception
            return None
        return wrapper
    return decorator


class PubMedAPIClient:
    """Client for interacting with PubMed/PMC API."""

    ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    BIOC_PMC_URL = "https://www.ncbi.nlm.nih.gov/research/bionlp/RESTful/pmcoa.cgi"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("PUBMED_API_KEY", "")

    def _build_esearch_params(self, term: str, limit: int = 10) -> dict[str, Any]:
        """Build parameters for esearch API call. `term` is already fully constructed."""
        params = {
            "db": "pmc",
            "term": term,
            "retmode": "json",
            "retmax": limit,
            "sort": "relevance",
        }
        if self.api_key:
            params["api_key"] = self.api_key
        return params

    def _build_bioc_params(self, pmc_id: str) -> dict[str, Any]:
        """Build parameters for BioC-PMC API call."""
        if not pmc_id.startswith("PMC"):
            pmc_id = f"PMC{pmc_id}"
        params = {"format": "json"}
        if self.api_key:
            params["api_key"] = self.api_key
        return pmc_id, params

    @with_retry(max_retries=3, initial_delay=1.0, backoff_factor=2.0)
    def search_article_ids(
        self,
        query: str,
        limit: int = 10,
        use_mesh: bool = False,
    ) -> list[str]:
        """
        Step 1: Search for article IDs using esearch.

        Args:
            query:    Search query string, or a MeSH descriptor name when use_mesh=True.
            limit:    Maximum number of results to return.
            use_mesh: When True (bulk indexer path), wraps the query in a MeSH field tag
                      so PubMed matches the full concept tree rather than free text.
                      Also sorts by publication date (newest first) and skips stop-word
                      cleaning, since MeSH terms must be preserved verbatim.
                      Default False — behaviour identical to the original code.

        Returns:
            List of PMC IDs.
        """
        if use_mesh:
            # MeSH field tag: matches synonyms + all child concepts automatically.
            # Sorted newest-first so repeated runs pick up recent papers.
            # open access[filter] kept for BioC full-text compatibility.
            term = f'"{query}"[MeSH] AND open access[filter]'
            params = self._build_esearch_params(term, limit)
            params["sort"] = "pub_date"
            logger.info(f"PubMed MeSH search: {term}")
        else:
            # ── Original user-facing logic — unchanged ──────────────────────
            cleaned_query = clean_query_for_pubmed(query)
            term = f"{cleaned_query} AND open access[filter]"
            params = self._build_esearch_params(term, limit)
            logger.info(f"PubMed esearch found IDs for cleaned query: {cleaned_query}")
            if cleaned_query != query:
                logger.debug(f"Original query was: {query}")

        response = requests.get(self.ESEARCH_URL, params=params, timeout=30)
        response.raise_for_status()

        data = response.json()
        id_list = data.get("esearchresult", {}).get("idlist", [])
        logger.info(f"  → {len(id_list)} IDs returned")
        return id_list

    def _parse_bioc_document(self, document: dict[str, Any]) -> dict[str, Any]:
        """
        Parse a BioC-PMC document to extract relevant fields.
        """
        passages = document.get("passages", [])

        title = journal = published_date = authors = None

        for passage in passages:
            if passage.get("infons", {}).get("type") == "front":
                title = passage.get("text", "")
                journal = passage.get("infons", {}).get("journal")
                published_date = passage.get("infons", {}).get("year")
                authors_infons = passage.get("infons", {}).get("authors")
                if authors_infons:
                    authors = str(authors_infons)
                break

        abstract_parts = [
            p.get("text", "") for p in passages
            if p.get("infons", {}).get("type") == "abstract"
        ]
        body_parts = [
            p.get("text", "") for p in passages
            if p.get("infons", {}).get("type") == "paragraph"
        ]

        return {
            "title":          title,
            "journal":        journal,
            "published_date": published_date,
            "authors":        authors,
            "abstract":       " ".join(abstract_parts) if abstract_parts else None,
            "full_text":      " ".join(body_parts) if body_parts else None,
        }

    @with_retry(max_retries=3, initial_delay=1.0, backoff_factor=2.0)
    def fetch_article_content(self, pmc_id: str) -> dict[str, Any] | None:
        """
        Step 2: Fetch full article content using BioC-PMC API.

        Args:
            pmc_id: PMC ID (with or without "PMC" prefix)

        Returns:
            Dictionary with title, journal, published_date, abstract, full_text
        """
        if not pmc_id.startswith("PMC"):
            pmc_id = f"PMC{pmc_id}"

        url = f"{self.BIOC_PMC_URL}/BioC_json/{pmc_id}/unicode"
        params = {}
        if self.api_key:
            params["api_key"] = self.api_key

        response = requests.get(url, params=params, timeout=60)
        response.raise_for_status()

        data = response.json()
        if isinstance(data, list) and len(data) > 0:
            doc_data = data[0]
            if "documents" in doc_data and len(doc_data["documents"]) > 0:
                return self._parse_bioc_document(doc_data["documents"][0])

        logger.warning(f"Could not parse document for PMC ID: {pmc_id}")
        return None

    def search_and_get_fulltext(
        self,
        query: str,
        limit: int = 10
    ) -> list[dict[str, Any]]:
        """
        Complete search workflow: find IDs and fetch full text for each.
        (User-facing — unchanged from original.)
        """
        try:
            article_ids = self.search_article_ids(query, limit)
        except Exception as e:
            logger.error(f"PubMed esearch failed: {e}")
            return []

        if not article_ids:
            logger.info(f"No articles found for query: {query}")
            return []

        articles = []
        for pmc_id in article_ids:
            try:
                content = self.fetch_article_content(pmc_id)
                if content:
                    content["pmc_id"] = pmc_id
                    content["source"] = "pubmed"
                    articles.append(content)
            except Exception as e:
                logger.warning(f"Failed to fetch content for {pmc_id}: {e}")
                continue

        logger.info(f"Successfully retrieved {len(articles)} articles from PubMed")
        return articles


class PubMedSearchResult:
    """Data class for PubMed search results."""
    title: str
    published_date: str | None
    abstract: str | None
    full_text: str | None
    pmc_id: str
    source: str = "pubmed"