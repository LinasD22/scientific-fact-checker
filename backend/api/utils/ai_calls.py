"""
AI call methods for fact-checking.
Supports multiple providers via AI_PROVIDER .env variable:
  - local    (default) - local LLM server via HTTP
  - openai             - OpenAI API
  - mistral            - Mistral API
  - gemini             - Google Gemini API
"""

import json
import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import requests
from requests.auth import HTTPBasicAuth


class FactCheckResult(Enum):
    VERIFIED = "verified"
    PARTIALLY_VERIFIED = "partially_verified"
    FALSE = "false"
    UNVERIFIABLE = "unverifiable"
    CONFLICTING = "conflicting"


@dataclass
class FactCheckResponse:
    is_verified: bool
    confidence: float
    result: FactCheckResult
    explanation: str
    supporting_evidence: list[str]
    contradicting_evidence: list[str]


@dataclass
class ComparisonResult:
    sorted_results: list[dict[str, Any]]
    consensus: FactCheckResult | None
    final_verdict: FactCheckResult
    summary: str
    agreement_score: float
    weighted_verdict: FactCheckResult | None = None  # Verdict from weighted aggregation
    source_reliability_scores: dict[str, float] = field(default_factory=dict)  # source title -> reliability rating


def _call_mistral(system_prompt: str, user_prompt: str) -> str:
    from mistralai import Mistral
    client = Mistral(api_key=os.getenv("MISTRAL_API_KEY", ""))
    response = client.chat.complete(
        model=os.getenv("MISTRAL_MODEL", "mistral-small-2506"),
        messages=[{"role": "system", "content": system_prompt},
                  {"role": "user",   "content": user_prompt}],
        temperature=0.2,
        max_tokens=2000,
    )
    raw_content = response.choices[0].message.content
    if isinstance(raw_content, list):
        return "".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in raw_content)
    return raw_content or ""


def _call_mistral_reasoning(system_prompt: str, user_prompt: str) -> str:
    """
    Mistral Small 4 su reasoning mode per raw HTTP (SDK dar nepalaiko reasoning_effort).
    reasoning_effort: "none" | "high"
    """
    api_key = os.getenv("MISTRAL_API_KEY", "")
    model = os.getenv("MISTRAL_REASONING_MODEL", "mistral-small-latest")
    reasoning_effort = os.getenv("MISTRAL_REASONING_EFFORT", "high")

    response = requests.post(
        "https://api.mistral.ai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            "temperature": 0.2,
            "max_tokens": 4000,
            "reasoning_effort": reasoning_effort,
        },
        timeout=120,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]

_PROVIDERS = {
    "mistral_reasoning":  _call_mistral_reasoning,
    "mistral": _call_mistral,
}

# ── AICallClient ──────────────────────────────────────────────────────────────

class AICallClient:
    """Fact-checking AI client. Switch provider via AI_PROVIDER .env variable."""

    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        self.provider = os.getenv("AI_PROVIDER", "local").lower()
        if self.provider not in _PROVIDERS:
            raise ValueError(f"Unknown AI_PROVIDER '{self.provider}'. "
                             f"Choose from: {list(_PROVIDERS)}")
        logging.info(f"AICallClient using provider: {self.provider}")

    def _call_ai(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        content = _PROVIDERS[self.provider](system_prompt, user_prompt).strip()

        # Strip markdown code blocks if present
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
            content = content.strip()

        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return {"raw_response": content}

    def check_all_facts(
        self,
        original_claim: str,
        source_texts: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Single combined call - fact-checks all sources and returns comparison."""
        # Truncate each source to stay under model context (e.g. Mistral 128k tokens)
        max_chars_per_source = int(os.getenv("AI_MAX_CHARS_PER_SOURCE", "30000"))
        sources_text = ""
        for i, source in enumerate(source_texts, 1):
            text = source.get("text", "") or ""
            if len(text) > max_chars_per_source:
                text = text[:max_chars_per_source] + "\n[...truncated]"
            sources_text += f"\nSource {i} - {source.get('title', 'Unknown')}:\n{text}\n"

        system_prompt = """You are a scientific fact-checking assistant.
Analyze claims against provided source texts and respond ONLY with valid JSON. No extra text."""

        user_prompt = f"""Claim to verify: "{original_claim}"
        
Sources:
{sources_text}

Respond ONLY with this JSON structure:
{{
    "individual_results": [
        {{
            "source": "Source title",
            "is_verified": true/false,
            "confidence": 0.0-1.0,
            "reliability": 0.0-1.0,
            "result": "verified" or "partially_verified" or "false" or "unverifiable" or "conflicting",
            "explanation": "Explanation using this source",
            "supporting_evidence": ["snippets that support the claim"],
            "contradicting_evidence": ["snippets that contradict the claim"]
        }}
    ],
    "sorted_results": [
        {{
            "source": "Source title",
            "confidence": 0.0-1.0,
            "reliability": 0.0-1.0,
            "result": "verified" or "partially_verified" or "false" or "unverifiable",
            "key_evidence": "Most important evidence from this source"
        }}
    ],
    "consensus": "verified" or "partially_verified" or "false" or "unverifiable" or "conflicting" or null,
    "final_verdict": "verified" or "partially_verified" or "false" or "unverifiable" or "conflicting",
    "summary": "Brief summary of findings across all sources",
    "agreement_score": 0.0 to 1.0 (1.0 = 100% all sources agree, 0.5 = 50% agree, 0.0 = complete disagreement)
}}

IMPORTANT GUIDELINES FOR RELIABILITY RATINGS:
- "reliability" (0.0-1.0) represents how trustworthy/authoritative this source is as evidence
- Consider: source quality, scientific rigor, publication status, peer-review, relevance to claim
- "confidence" (0.0-1.0) represents how confident you are in this source's verdict on the claim
- Confidence is independent of reliability: a reliable source might still be uncertain about a claim (low confidence)
- Only include sources with reliability >= 0.3 in the final aggregation (exclude very low-quality sources)

sorted_results must be sorted by reliability (highest first)."""

        return self._call_ai(system_prompt, user_prompt)


def fact_preprocess(
        original_claim: str,
) ->  dict[str, Any]:

    ai_client = AICallClient()

    expected_json = """
    {
        "is_health_related": "(true|false)",
        "justification": "(one to two sentence why do you think so)",
        "scientific paper names suggestions": [
            "one name for scientific paper",
            "second name for scientific paper",
            "third name for scientific paper",
        ]
    }
    """
    role="Hello imagine you are a critical classifier."

    prompt = (
        " I want you to classify this fact to either related with health or not (this will later be used for fact cheking with health service)"
        f". Strictly return a json:\n {expected_json} \n The fact to preprocess: {original_claim} \n"
    )
    # call ai
    json = ai_client._call_ai(role, prompt)

    print(json)
    # parse json
    return json


# ── Aggregation functions ─────────────────────────────────────────────────────

def _aggregate_source_verdicts(
    individual_results: list[dict[str, Any]],
    min_reliability_threshold: float = 0.3,
) -> tuple[FactCheckResult, float, dict[str, float]]:
    """
    Aggregate individual source verdicts using weighted averaging by reliability.
    
    Args:
        individual_results: List of results from each source with reliability ratings
        min_reliability_threshold: Minimum reliability score to include in aggregation (default 0.3)
    
    Returns:
        (aggregated_verdict, weighted_agreement_score)
    """
    if not individual_results:
        return FactCheckResult.UNVERIFIABLE, 0.0, {}
    
    # Filter sources by minimum reliability threshold
    reliable_sources = [
        r for r in individual_results
        if float(r.get("reliability", 0.0)) >= min_reliability_threshold
    ]
    
    if not reliable_sources:
        # If no sources meet threshold, use all sources with warning
        logging.warning(f"No sources met minimum reliability threshold {min_reliability_threshold}, using all sources")
        reliable_sources = individual_results
    
    # Map verdict strings to numeric values for weighted averaging
    verdict_map = {
        "verified": 1.0,
        "partially_verified": 0.5,
        "false": 0.0,
        "unverifiable": 0.25,  # Neutral middle ground
        "conflicting": 0.5,    # Treated as partially verified
    }
    
    total_weight = 0.0
    weighted_verdict_score = 0.0
    reliability_scores = {}
    
    for source in reliable_sources:
        result_str = source.get("result", "unverifiable")
        reliability = float(source.get("reliability", 0.5))
        
        # Use reliability as weight
        weight = reliability
        total_weight += weight
        
        # Get numeric value for verdict
        verdict_value = verdict_map.get(result_str, 0.25)
        weighted_verdict_score += verdict_value * weight
        
        # Store source reliability scores
        source_title = source.get("source", f"Source {len(reliability_scores)}")
        reliability_scores[source_title] = reliability
    
    # Calculate weighted average verdict
    if total_weight > 0:
        avg_verdict_score = weighted_verdict_score / total_weight
    else:
        avg_verdict_score = 0.25
    
    # Determine final verdict based on weighted average
    if avg_verdict_score >= 0.75:
        final_verdict = FactCheckResult.VERIFIED
    elif avg_verdict_score >= 0.6:
        final_verdict = FactCheckResult.PARTIALLY_VERIFIED
    elif avg_verdict_score <= 0.25:
        final_verdict = FactCheckResult.FALSE
    else:
        # 0.25 < score < 0.6
        final_verdict = FactCheckResult.UNVERIFIABLE
    
    # Calculate weighted agreement score
    # How much sources agree on the final verdict
    sources_supporting_verdict = sum(
        float(s.get("reliability", 0.0))
        for s in reliable_sources
        if verdict_map.get(s.get("result", "unverifiable"), 0.25) >= (avg_verdict_score - 0.1)
    )
    weighted_agreement = sources_supporting_verdict / total_weight if total_weight > 0 else 0.0
    
    return final_verdict, weighted_agreement, reliability_scores


# ── Main function ─────────────────────────────────────────────────────────────

def check_facts_with_ai(
    original_claim: str,
    source_texts: list[dict[str, Any]],
    ai_client: AICallClient | None = None,
) -> tuple[list[FactCheckResponse], ComparisonResult]:
    if ai_client is None:
        ai_client = AICallClient()

    if not source_texts:
        return [], ComparisonResult(
            sorted_results=[], consensus=None,
            final_verdict=FactCheckResult.UNVERIFIABLE,
            summary="No source texts provided.",
            agreement_score=0.0,
        )

    result = ai_client.check_all_facts(original_claim, source_texts)

    responses = []
    individual_results_raw = result.get("individual_results", [])
    
    for r in individual_results_raw:
        try:
            responses.append(FactCheckResponse(
                is_verified=r.get("is_verified", False),
                confidence=float(r.get("confidence", 0.0)),
                result=FactCheckResult(r.get("result", "unverifiable")),
                explanation=r.get("explanation", ""),
                supporting_evidence=r.get("supporting_evidence", []),
                contradicting_evidence=r.get("contradicting_evidence", []),
            ))
        except (ValueError, KeyError) as e:
            logging.warning(f"Error parsing individual result: {e}")
            responses.append(FactCheckResponse(
                is_verified=False, confidence=0.0,
                result=FactCheckResult.UNVERIFIABLE,
                explanation="Error parsing result",
                supporting_evidence=[], contradicting_evidence=[],
            ))

    try:
        # Perform aggregation-based verdict calculation
        aggregated_verdict, weighted_agreement, source_reliability_scores = _aggregate_source_verdicts(
            individual_results_raw,
            min_reliability_threshold=0.3,
        )
        
        # Use AI's consensus/final_verdict as fallback if aggregation fails
        ai_final_verdict = FactCheckResult(result.get("final_verdict", "unverifiable"))
        
        comparison = ComparisonResult(
            sorted_results=result.get("sorted_results", []),
            consensus=FactCheckResult(result["consensus"]) if result.get("consensus") else None,
            final_verdict=aggregated_verdict,  # Use aggregated verdict instead of AI's
            summary=result.get("summary", ""),
            agreement_score=weighted_agreement,  # Use weighted agreement score
            source_reliability_scores=source_reliability_scores,
            weighted_verdict=aggregated_verdict,
        )
    except (ValueError, KeyError) as e:
        logging.error(f"Error in aggregation: {e}")
        comparison = ComparisonResult(
            sorted_results=[], consensus=None,
            final_verdict=FactCheckResult.UNVERIFIABLE,
            summary=f"Error parsing comparison: {str(e)}",
            agreement_score=0.0,
            source_reliability_scores={},
        )

    return responses, comparison



