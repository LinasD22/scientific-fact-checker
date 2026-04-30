"""
API endpoints for the fact checker plugin.
"""

import asyncio
import logging
from typing import Annotated
from api.utils.ai_calls import extract_individual_facts, translate_to_english, translate_from_english
from fastapi import Body, APIRouter, HTTPException, status
from fastapi.responses import JSONResponse
from datetime import date, datetime, timezone
from typing import Annotated, Any

from pydantic import BaseModel, Field
from fastapi import APIRouter, Body, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlmodel import Session

from api.db.database import engine
from api.db.models import Query
from api.enums import FactCheckResult
from api.utils.ai_calls import extract_individual_facts
from api.services.fact_checker import FactCheckerService, create_fact_checker
from api.utils.auth_deps import get_optional_user_id


def _verdict_to_enum(v: str | None) -> FactCheckResult | None:
    if v is None:
        return None
    try:
        return FactCheckResult(v)
    except ValueError:
        return None


def _first_successful_verdict(all_results: list[dict[str, Any]]) -> FactCheckResult | None:
    for r in all_results:
        if "error" in r:
            continue
        if r.get("final_verdict") is not None:
            return _verdict_to_enum(r["final_verdict"])
    return None


def _persist_query(user_id: int, claim: str, response_content: dict[str, Any]) -> None:
    """Store full response in Query.result_json; first non-error fact verdict in Query.final_verdict."""
    all_results = response_content.get("all_results") or []
    stored_json = {**response_content, "facts": all_results, "saved_at": datetime.now(timezone.utc).isoformat()}
    verdict = _first_successful_verdict(all_results)
    with Session(engine) as session:
        row = Query(
            claim_text=claim[:255],
            claim_date=date.today(),
            result_json=stored_json,
            final_verdict=verdict,
            user_id=user_id,
        )
        session.add(row)
        session.commit()

router = APIRouter()

_fact_checker: FactCheckerService | None = None

LIMIT = 3


def get_fact_checker() -> FactCheckerService:
    global _fact_checker
    if _fact_checker is None:
        _fact_checker = create_fact_checker()
    return _fact_checker


class FactCheckSearchBody(BaseModel):
    claim: str = Field(..., description="The fact/claim to verify")


@router.post("/fact-check/search")
async def fact_check_with_search(
    body: FactCheckSearchBody,
    user_id: int | None = Depends(get_optional_user_id),
) -> JSONResponse:
    """
    Full pipeline with preprocessing:
    1. Preprocess: Break text into individual factual claims using Mistral
    2. For each claim (IN PARALLEL):
        a. Search Core API for relevant academic papers
        b. Search Qdrant for high-relevance snippets
        c. Use AI to fact-check snippets against the claim
    3. Return results:
       - Backward compatible: first fact in top-level fields
       - New: all_results array with complete results for each fact
    """
    try:
        claim = body.claim
        service = get_fact_checker()
        LIMIT = 5 # Or your preferred limit
        
        # ── Step 1: Extract individual facts from the provided text ──
        print(f"\n=== ORIGINAL WHOLE CLAIM: {claim} ===")
        print(f"\n=== Preprocessing: Extracting individual facts ===")
        facts_result = extract_individual_facts(claim)
        
        # Accommodate the new AI format (dicts with exact_quote) while falling back to strings
        raw_facts = facts_result.get("facts", [claim]) 
        facts = []
        for f in raw_facts:
            if isinstance(f, dict):
                facts.append(f)
            else:
                # Fallback if the AI just returns a string
                facts.append({"fact": f, "exact_quote": f})
        
        print(f"Extracted {len(facts)} fact(s) to check:")
        for i, f_obj in enumerate(facts, 1):
            print(f"  {i}. {f_obj['fact']} (Quote: {f_obj.get('exact_quote', 'N/A')})")
        
        # ── Step 1b: Translate non-English facts to English ──
        print(f"\n=== Translating facts to English (if needed) ===")
        facts_to_check = []  # English facts for fact-checking
        original_facts_metadata = []  # Metadata for the response
        
        for i, f_obj in enumerate(facts, 1):
            fact_text = f_obj["fact"]
            exact_quote = f_obj.get("exact_quote", fact_text)
            
            translation_result = translate_to_english(fact_text)
            translated_text = translation_result["translated"]
            was_translated = translation_result["was_translated"]
            detected_lang = translation_result.get("detected_language", "unknown")
            
            facts_to_check.append(translated_text)
            original_facts_metadata.append({
                "original": fact_text,
                "exact_quote": exact_quote,
                "translated": translated_text,
                "was_translated": was_translated,
                "detected_language": detected_lang,
            })
            
            if was_translated:
                print(f"  Fact {i}: [{detected_lang} -> en] {fact_text}")
            else:
                print(f"  Fact {i}: [en] {fact_text}")

        # ── Step 2: Fact-check each individual fact IN PARALLEL ──
        print(f"\n=== Starting parallel fact-checking for {len(facts_to_check)} facts ===")
        
        async def check_fact_async(fact_idx: int, fact_to_check: str, metadata: dict):
            """Wrapper to run blocking check_claim in thread pool."""
            loop = asyncio.get_event_loop()
            try:
                result = await loop.run_in_executor(
                    None, 
                    service.check_claim,
                    fact_to_check,
                    None, 
                    LIMIT,
                )
                
                # Build individual_results with Lithuanian explanations
                individual_results = result.individual_results
                summary_lithuanian = None
                
                # Always translate summary to Lithuanian
                if result.summary:
                    try:
                        summary_translation = await loop.run_in_executor(
                            None,
                            lambda txt=result.summary: translate_from_english(txt, "lithuanian")
                        )
                        summary_lithuanian = summary_translation.get("translated")
                    except Exception as e:
                        logging.warning(f"Failed to translate summary to Lithuanian: {e}")
                
                # Translate explanations in individual_results to Lithuanian
                translated_individuals = []
                for ind_res in individual_results:
                    ind_copy = ind_res.copy()
                    explanation = ind_res.get("explanation", "")
                    if explanation:
                        try:
                            translation = await loop.run_in_executor(
                                None,
                                lambda txt=explanation: translate_from_english(txt, "lithuanian")
                            )
                            ind_copy["explanation_lithuanian"] = translation.get("translated")
                        except Exception as e:
                            logging.warning(f"Failed to translate explanation to Lithuanian: {e}")
                            ind_copy["explanation_lithuanian"] = None
                    else:
                        ind_copy["explanation_lithuanian"] = None
                    translated_individuals.append(ind_copy)

                return {
                    "fact_index": fact_idx,
                    "original_fact": metadata["original"],
                    "exact_quote": metadata["exact_quote"],
                    "translated_fact": metadata.get("translated"),
                    "was_translated": metadata.get("was_translated", False),
                    "detected_language": metadata.get("detected_language"),
                    "consensus": result.consensus,
                    "final_verdict": result.final_verdict,
                    "summary": result.summary,
                    "summary_lithuanian": summary_lithuanian,
                    "agreement_score": result.agreement_score,
                    "individual_results": translated_individuals,
                    "articles_used": [
                        {
                            "title": article.title,
                            "published_date": article.published_date,
                            "authors": article.authors,
                            "source": article.source,
                            "url": article.url,
                            "index": article.index,
                        }
                        for article in result.articles_used
                    ],
                }
            except Exception as e:
                print(f"✗ Error checking fact {fact_idx + 1}: {str(e)}")
                return {
                    "fact_index": fact_idx,
                    "original_fact": metadata["original"],
                    "exact_quote": metadata["exact_quote"],
                    "error": str(e),
                }

        # Run all checks in parallel
        all_results = await asyncio.gather(
            *[check_fact_async(i, facts_to_check[i], original_facts_metadata[i])
              for i in range(len(facts_to_check))]
        )
        
        # ── Step 3: Return results ──
        first_result = all_results[0] if all_results else {}
        first_metadata = original_facts_metadata[0] if original_facts_metadata else {}
        
        response_content = {
            "total_facts_extracted": len(facts),
            "facts_checked": len([r for r in all_results if "error" not in r]),
            "current_fact_index": 0,
            "current_fact": first_metadata.get("original", claim),
            # === BACKWARD COMPATIBLE ===
            "consensus": first_result.get("consensus"),
            "final_verdict": first_result.get("final_verdict"),
            "summary": first_result.get("summary"),
            "summary_lithuanian": first_result.get("summary_lithuanian"),
            "agreement_score": first_result.get("agreement_score"),
            "individual_results": first_result.get("individual_results", []),
            "articles_used": first_result.get("articles_used", []),
            # === NEW: ALL RESULTS ===
            "all_results": all_results,
        }

        if user_id is not None:
            _persist_query(user_id, claim, response_content)
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=response_content,
        )

    except Exception as e:
        import traceback
        logging.error(f"Fact-check search failed: {e}\n{traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Fact-check failed: {str(e)}",
        )

@router.post("/fact-check/texts")
async def fact_check_with_texts(
    claim: Annotated[str, Body(description="The fact/claim to verify")],
    texts: Annotated[
        list[dict[str, str]],
        Body(description="List of texts with 'text', 'title', and optional 'url'"),
    ],
    ai_api_key: Annotated[str | None, Body(description="Override AI API key")] = None,
) -> JSONResponse:
    """
    Check a claim against provided texts (no Core API or Qdrant search).
    """
    try:
        service = (
            create_fact_checker(ai_api_key=ai_api_key)
            if ai_api_key
            else get_fact_checker()
        )

        result = service.check_claim_with_texts(
            original_claim=claim,
            texts=texts,
        )

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "original_claim": result.original_claim,
                "works_searched": result.works_searched,
                "works_with_text": result.works_with_text,
                "snippets_used": result.snippets_used,
                "individual_results": result.individual_results,
                "sorted_results": result.sorted_results,
                "consensus": result.consensus,
                "final_verdict": result.final_verdict,
                "summary": result.summary,
                "agreement_score": result.agreement_score,
                "articles_used": [],  # No articles for texts-only check
            },
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Fact-check failed: {str(e)}",
        )


@router.get("/health")
async def health_check() -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"status": "healthy"},
    )