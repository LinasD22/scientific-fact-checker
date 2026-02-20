"""
AI call methods for fact-checking.
Uses AI to verify facts against source texts and compare results.
"""

import json
import os
from dataclasses import dataclass
from enum import Enum
from typing import Any

import requests


class FactCheckResult(Enum):
    """Possible fact-check verification results."""
    VERIFIED = "verified"
    PARTIALLY_VERIFIED = "partially_verified"
    FALSE = "false"
    UNVERIFIABLE = "unverifiable"
    CONFLICTING = "conflicting"


@dataclass
class FactCheckResponse:
    """Response from a single fact-check operation."""
    is_verified: bool
    confidence: float  # 0.0 to 1.0
    result: FactCheckResult
    explanation: str
    supporting_evidence: list[str]
    contradicting_evidence: list[str]


@dataclass
class ComparisonResult:
    """Result from comparing multiple fact-checks."""
    sorted_results: list[dict[str, Any]]  # Sorted by confidence
    consensus: FactCheckResult | None
    final_verdict: FactCheckResult
    summary: str
    agreement_score: float  # 0.0 to 1.0


class AICallClient:
    """Client for making AI calls to fact-check texts."""
    
    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        """
        Initialize the AI call client.
        
        Args:
            api_key: API key for AI service. Defaults to env var AI_API_KEY.
            base_url: Base URL for AI API. Defaults to a standard endpoint.
        """
        self.api_key = api_key or os.getenv("AI_API_KEY", "")
        self.base_url = base_url or os.getenv("AI_BASE_URL", "https://api.openai.com/v1")
    
    def _call_ai(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        """
        Make a generic AI API call.
        
        Args:
            system_prompt: System instruction for the AI
            user_prompt: User query/prompt
        
        Returns:
            Parsed JSON response from the AI
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "gpt-4",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.3,
            "max_tokens": 1000
        }
        
        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=60
        )
        response.raise_for_status()
        
        result = response.json()
        content = result["choices"][0]["message"]["content"]
        
        # Try to parse as JSON
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            # Return as text if not JSON
            return {"raw_response": content}
    
    def check_fact(
        self,
        original_claim: str,
        source_text: str,
        source_title: str | None = None
    ) -> FactCheckResponse:
        """
        Check a single fact against a source text.
        
        Args:
            original_claim: The claim/fact to verify
            source_text: The source text to check against
            source_title: Optional title of the source
        
        Returns:
            FactCheckResponse with verification details
        """
        system_prompt = """You are a fact-checking assistant. Your role is to verify claims 
against provided source texts. Analyze the text carefully and determine if the claim 
is supported, contradicted, or cannot be verified by the text."""
        
        source_info = f"Source: {source_title}\n\n" if source_title else ""
        user_prompt = f"""Original Claim to Verify:
"{original_claim}"

{source_info}Source Text:
{source_text}

Please analyze the claim against the source text and provide your fact-check result 
in JSON format with the following structure:
{{
    "is_verified": true/false,
    "confidence": 0.0-1.0,
    "result": "verified"/"partially_verified"/"false"/"unverifiable"/"conflicting",
    "explanation": "Detailed explanation of your reasoning",
    "supporting_evidence": ["List of text snippets that support the claim"],
    "contradicting_evidence": ["List of text snippets that contradict the claim"]
}}"""
        
        result = self._call_ai(system_prompt, user_prompt)
        
        # Parse the result into a FactCheckResponse
        try:
            return FactCheckResponse(
                is_verified=result.get("is_verified", False),
                confidence=result.get("confidence", 0.0),
                result=FactCheckResult(result.get("result", "unverifiable")),
                explanation=result.get("explanation", ""),
                supporting_evidence=result.get("supporting_evidence", []),
                contradicting_evidence=result.get("contradicting_evidence", [])
            )
        except (ValueError, KeyError) as e:
            # Handle parsing errors gracefully
            return FactCheckResponse(
                is_verified=False,
                confidence=0.0,
                result=FactCheckResult.UNVERIFIABLE,
                explanation=f"Error parsing result: {str(e)}",
                supporting_evidence=[],
                contradicting_evidence=[]
            )
    
    def compare_and_sort_results(
        self,
        original_claim: str,
        fact_check_results: list[dict[str, Any]]
    ) -> ComparisonResult:
        """
        Compare multiple fact-check results, sort them, and generate a final verdict.
        
        Args:
            original_claim: The original claim being verified
            fact_check_results: List of fact-check results from different sources
        
        Returns:
            ComparisonResult with sorted results and final verdict
        """
        system_prompt = """You are an expert at comparing and synthesizing multiple 
fact-check results. Your task is to analyze multiple verifications of the same 
claim from different sources, determine consensus, and provide a final verdict."""
        
        results_json = json.dumps(fact_check_results, indent=2)
        user_prompt = f"""Original Claim:
"{original_claim}"

Fact-Check Results from Multiple Sources:
{results_json}

Please analyze these results and provide a comparison in JSON format:
{{
    "sorted_results": [
        {{
            "source": "source identifier",
            "confidence": 0.0-1.0,
            "result": "verified"/"partially_verified"/"false"/"unverifiable",
            "key_evidence": "Most important evidence"
        }}
    ],
    "consensus": "verified"/"partially_verified"/"false"/"unverifiable"/"conflicting"/null,
    "final_verdict": "verified"/"partially_verified"/"false"/"unverifiable"/"conflicting",
    "summary": "Brief summary of the comparison and final conclusion",
    "agreement_score": 0.0-1.0
}}

Sort results by confidence score (highest first)."""
        
        result = self._call_ai(system_prompt, user_prompt)
        
        try:
            return ComparisonResult(
                sorted_results=result.get("sorted_results", []),
                consensus=FactCheckResult(result["consensus"]) if result.get("consensus") else None,
                final_verdict=FactCheckResult(result.get("final_verdict", "unverifiable")),
                summary=result.get("summary", ""),
                agreement_score=result.get("agreement_score", 0.0)
            )
        except (ValueError, KeyError) as e:
            # Handle parsing errors
            return ComparisonResult(
                sorted_results=fact_check_results,
                consensus=None,
                final_verdict=FactCheckResult.UNVERIFIABLE,
                summary=f"Error comparing results: {str(e)}",
                agreement_score=0.0
            )


def check_facts_with_ai(
    original_claim: str,
    source_texts: list[dict[str, Any]],
    ai_client: AICallClient | None = None
) -> tuple[list[FactCheckResponse], ComparisonResult]:
    """
    Main function to check a claim against multiple texts and get final result.
    
    Args:
        original_claim: The claim to verify
        source_texts: List of dicts with 'text', 'title', and optionally 'url'
        ai_client: Optional AICallClient instance
    
    Returns:
        Tuple of (individual results, comparison result)
    """
    if ai_client is None:
        ai_client = AICallClient()
    
    # Step 1: Check each text individually
    individual_results = []
    for source in source_texts:
        text = source.get("text", "")
        title = source.get("title", source.get("url", "Unknown"))
        
        if text:  # Only check if there's actual text
            result = ai_client.check_fact(original_claim, text, title)
            individual_results.append({
                "source": title,
                "is_verified": result.is_verified,
                "confidence": result.confidence,
                "result": result.result.value,
                "explanation": result.explanation,
                "supporting_evidence": result.supporting_evidence,
                "contradicting_evidence": result.contradicting_evidence
            })
    
    # Step 2: Compare and get final verdict
    comparison = ai_client.compare_and_sort_results(original_claim, individual_results)
    
    # Convert back to FactCheckResponse objects for the first part
    responses = []
    for res in individual_results:
        responses.append(FactCheckResponse(
            is_verified=res["is_verified"],
            confidence=res["confidence"],
            result=FactCheckResult(res["result"]),
            explanation=res["explanation"],
            supporting_evidence=res["supporting_evidence"],
            contradicting_evidence=res["contradicting_evidence"]
        ))
    
    return responses, comparison
