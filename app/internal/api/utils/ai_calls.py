"""
AI call methods for fact-checking.
Supports multiple providers via AI_PROVIDER env variable:
  - local    (default) - local LLM server via HTTP
  - openai             - OpenAI API
  - mistral            - Mistral API
  - gemini             - Google Gemini API
"""

import json
import logging
import os
from dataclasses import dataclass
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


# ── Provider implementations ──────────────────────────────────────────────────

def _call_local(system_prompt: str, user_prompt: str) -> str:
    base_url  = os.getenv("LOCAL_LLM_URL",      "http://localhost:8000")
    username  = os.getenv("LOCAL_LLM_USERNAME",  "admin")
    password  = os.getenv("LOCAL_LLM_PASSWORD",  "your_secure_password_here")
    model     = os.getenv("LOCAL_LLM_MODEL",     "heavy")

    response = requests.post(
        f"{base_url}/api/generate",
        auth=HTTPBasicAuth(username, password),
        json={"prompt": user_prompt, "system": system_prompt,
              "model": model, "max_tokens": 2000, "temperature": 0.2},
        timeout=120,
    )
    response.raise_for_status()
    return response.json()["response"]


def _call_openai(system_prompt: str, user_prompt: str) -> str:
    from openai import OpenAI
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))
    response = client.chat.completions.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        messages=[{"role": "system", "content": system_prompt},
                  {"role": "user",   "content": user_prompt}],
        temperature=0.2,
        max_tokens=2000,
    )
    return response.choices[0].message.content


def _call_mistral(system_prompt: str, user_prompt: str) -> str:
    from mistralai import Mistral
    client = Mistral(api_key=os.getenv("MISTRAL_API_KEY", ""))
    response = client.chat.complete(
        model=os.getenv("MISTRAL_MODEL", "mistral-large-latest"),
        messages=[{"role": "system", "content": system_prompt},
                  {"role": "user",   "content": user_prompt}],
        temperature=0.2,
        max_tokens=2000,
    )
    return response.choices[0].message.content


def _call_gemini(system_prompt: str, user_prompt: str) -> str:
    import google.generativeai as genai
    genai.configure(api_key=os.getenv("GEMINI_API_KEY", ""))
    client = genai.GenerativeModel(
        model_name=os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
        generation_config=genai.GenerationConfig(temperature=0.2, max_output_tokens=2000),
    )
    response = client.generate_content(f"{system_prompt}\n\n{user_prompt}")
    return response.text


_PROVIDERS = {
    "local":   _call_local,
    "openai":  _call_openai,
    "mistral": _call_mistral,
    "gemini":  _call_gemini,
}

# ── AICallClient ──────────────────────────────────────────────────────────────

class AICallClient:
    """Fact-checking AI client. Switch provider via AI_PROVIDER env variable."""

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
        sources_text = ""
        for i, source in enumerate(source_texts, 1):
            sources_text += f"\nSource {i} - {source.get('title', 'Unknown')}:\n{source.get('text', '')}\n"

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
            "result": "verified" or "partially_verified" or "false" or "unverifiable",
            "key_evidence": "Most important evidence from this source"
        }}
    ],
    "consensus": "verified" or "partially_verified" or "false" or "unverifiable" or "conflicting" or null,
    "final_verdict": "verified" or "partially_verified" or "false" or "unverifiable" or "conflicting",
    "summary": "Brief summary of findings across all sources",
    "agreement_score": 0.0-1.0
}}

sorted_results must be sorted by confidence (highest first)."""

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
    for r in result.get("individual_results", []):
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
        comparison = ComparisonResult(
            sorted_results=result.get("sorted_results", []),
            consensus=FactCheckResult(result["consensus"]) if result.get("consensus") else None,
            final_verdict=FactCheckResult(result.get("final_verdict", "unverifiable")),
            summary=result.get("summary", ""),
            agreement_score=float(result.get("agreement_score", 0.0)),
        )
    except (ValueError, KeyError) as e:
        comparison = ComparisonResult(
            sorted_results=[], consensus=None,
            final_verdict=FactCheckResult.UNVERIFIABLE,
            summary=f"Error parsing comparison: {str(e)}",
            agreement_score=0.0,
        )

    return responses, comparison



