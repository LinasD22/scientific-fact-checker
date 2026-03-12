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

import requests

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
        """
        Initialize the PubMed API client.
        
        Args:
            api_key: NCBI API key for higher rate limits. Defaults to env var PUBMED_API_KEY.
        """
        self.api_key = api_key or os.getenv("PUBMED_API_KEY", "")
    
    def _build_esearch_params(self, query: str, limit: int = 10) -> dict[str, Any]:
        """Build parameters for esearch API call."""
        params = {
            "db": "pmc",  # PubMed Central for full-text articles
            "term": f"{query} AND open access[filter]",
            "retmode": "json",
            "retmax": limit,
            "sort": "relevance"
        }
        if self.api_key:
            params["api_key"] = self.api_key
        return params
    
    def _build_bioc_params(self, pmc_id: str) -> dict[str, Any]:
        """Build parameters for BioC-PMC API call."""
        # PMC ID needs "PMC" prefix for BioC-PMC API
        if not pmc_id.startswith("PMC"):
            pmc_id = f"PMC{pmc_id}"
        
        params = {
            "format": "json"  # Request JSON format
        }
        if self.api_key:
            params["api_key"] = self.api_key
        return pmc_id, params
    
    @with_retry(max_retries=3, initial_delay=1.0, backoff_factor=2.0)
    def search_article_ids(self, query: str, limit: int = 10) -> list[str]:
        """
        Step 1: Search for article IDs using esearch.
        
        Args:
            query: Search query string (e.g., "vaccines AND autism")
            limit: Maximum number of results to return
        
        Returns:
            List of PMC IDs
        """
        params = self._build_esearch_params(query, limit)
        
        response = requests.get(
            self.ESEARCH_URL,
            params=params,
            timeout=30
        )
        response.raise_for_status()
        
        data = response.json()
        id_list = data.get("esearchresult", {}).get("idlist", [])
        
        logger.info(f"PubMed esearch found {len(id_list)} IDs for query: {query}")
        return id_list
    
    def _parse_bioc_document(self, document: dict[str, Any]) -> dict[str, Any]:
        """
        Parse a BioC-PMC document to extract relevant fields.
        
        Based on the user's guidance:
        - Title: passages with type "front"
        - Journal: infons.journal in front passage
        - Date: infons.year in front passage
        - Abstract: passages with type "abstract"
        - Body Text: passages with type "paragraph"
        """
        passages = document.get("passages", [])
        
        # Extract metadata from "front" passage
        title = None
        journal = None
        published_date = None
        
        for passage in passages:
            if passage.get("infons", {}).get("type") == "front":
                title = passage.get("text", "")
                journal = passage.get("infons", {}).get("journal")
                published_date = passage.get("infons", {}).get("year")
                break
        
        # Extract abstract
        abstract_parts = []
        for passage in passages:
            if passage.get("infons", {}).get("type") == "abstract":
                abstract_parts.append(passage.get("text", ""))
        
        abstract = " ".join(abstract_parts) if abstract_parts else None
        
        # Extract body text
        body_parts = []
        for passage in passages:
            if passage.get("infons", {}).get("type") == "paragraph":
                body_parts.append(passage.get("text", ""))
        
        full_text = " ".join(body_parts) if body_parts else None
        
        return {
            "title": title,
            "journal": journal,
            "published_date": published_date,
            "abstract": abstract,
            "full_text": full_text
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
        # Ensure PMC prefix
        if not pmc_id.startswith("PMC"):
            pmc_id = f"PMC{pmc_id}"
        
        url = f"{self.BIOC_PMC_URL}/BioC_json/{pmc_id}/unicode"
        
        params = {}
        if self.api_key:
            params["api_key"] = self.api_key
        
        response = requests.get(url, params=params, timeout=60)
        response.raise_for_status()
        
        data = response.json()
        
        # Parse the response - structure is [0].documents[0]
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
        
        Args:
            query: Search query
            limit: Number of articles to retrieve
        
        Returns:
            List of articles with title, publishedDate, abstract, and fullText
        """
        # Step 1: Get article IDs
        try:
            article_ids = self.search_article_ids(query, limit)
        except Exception as e:
            logger.error(f"PubMed esearch failed: {e}")
            return []
        
        if not article_ids:
            logger.info(f"No articles found for query: {query}")
            return []
        
        # Step 2: Fetch content for each ID
        articles = []
        for pmc_id in article_ids:
            try:
                content = self.fetch_article_content(pmc_id)
                if content:
                    # Add unique identifier for deduplication
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
