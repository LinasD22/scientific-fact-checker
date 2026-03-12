"""
Core API client for searching academic papers.
Based on the provided example: https://api.core.ac.uk/v3/search/works
"""

import os
from typing import Any

import requests


class CoreAPIClient:
    """Client for interacting with the Core academic paper API."""
    
    BASE_URL = "https://api.core.ac.uk/v3"
    
    def __init__(self, api_key: str | None = None):
        """
        Initialize the Core API client.
        
        Args:
            api_key: API key for authentication. Defaults to env var CORE_API_KEY.
        """
        self.api_key = api_key or os.getenv("CORE_API_KEY", "")
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
    
    def search_works(
        self,
        query: str,
        limit: int = 3,
        extract: list[str] | None = None
    ) -> dict[str, Any]:
        """
        Search for academic works using the Core API.
        
        Args:
            query: Search query string (e.g., "obesity prevalence 2050")
            limit: Maximum number of results to return
            extract: List of fields to extract (default: title, abstract, fullText, downloadUrl)
        
        Returns:
            API response containing search results
        
        Raises:
            requests.HTTPError: If the API request fails
        """
        if extract is None:
            extract = ["title", "abstract", "fullText", "downloadUrl"]
        
        body = {
            "q": query,
            "limit": limit,
            "extract": extract
        }
        
        response = requests.post(
            f"{self.BASE_URL}/search/works",
            headers=self.headers,
            json=body,
            timeout=30
        )
        response.raise_for_status()
        
        return response.json()
    
    def get_work_details(self, work_id: int) -> dict[str, Any]:
        """
        Get detailed information about a specific work.
        
        Args:
            work_id: The Core work ID
        
        Returns:
            Work details from the API
        """
        response = requests.get(
            f"{self.BASE_URL}/works/{work_id}",
            headers=self.headers,
            timeout=30
        )
        response.raise_for_status()
        
        return response.json()
    
    def search_and_get_fulltext(
        self,
        query: str,
        limit: int = 3
    ) -> list[dict[str, Any]]:
        """
        Search for works and return results with full text.
        
        Args:
            query: Search query
            limit: Number of results
        
        Returns:
            List of works with title, publishedDate, abstract, and fullText
        """
        results = self.search_works(query=query, limit=limit)
        
        works = []
        for item in results.get("results", []):
            work = {
                "title": item.get("title"),
                "publishedDate": item.get("publishedDate"),
                "abstract": item.get("abstract"),
                "fullText": item.get("fullText"),
                "downloadUrl": item.get("downloadUrl")
            }
            works.append(work)
        
        return works
