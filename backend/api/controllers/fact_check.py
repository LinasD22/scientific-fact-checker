"""
API endpoints for the fact checker plugin.
"""

from typing import Annotated
from api.utils.ai_calls import extract_individual_facts
from fastapi import Body, APIRouter, HTTPException, status
from fastapi.responses import JSONResponse

from api.services.fact_checker import FactCheckerService, create_fact_checker

router = APIRouter()

_fact_checker: FactCheckerService | None = None

LIMIT=3

def get_fact_checker() -> FactCheckerService:
    global _fact_checker
    if _fact_checker is None:
        _fact_checker = create_fact_checker()
    return _fact_checker


@router.post("/fact-check/search")
async def fact_check_with_search(
    claim: Annotated[str, Body(embed=True, description="The fact/claim to verify")],
) -> JSONResponse:
    """
    Full pipeline with preprocessing:
    1. Preprocess: Break text into individual factual claims using Mistral
    2. For each claim:
       a. Search Core API for relevant academic papers
       b. Search Qdrant for high-relevance snippets
       c. Use AI to fact-check snippets against the claim
    3. Return results:
       - Backward compatible: first fact in top-level fields
       - New: all_results array with complete results for each fact
    """
    try:
        service = get_fact_checker()
        
        # ── Step 1: Extract individual facts from the provided text ──
        print(f"\n=== ORIGINAL WHOLE CLAIM: {claim} ===")
        print(f"\n=== Preprocessing: Extracting individual facts ===")
        facts_result = extract_individual_facts(claim)
        print(f"\n=== FACT RESULTS COUNT AFTER EXTRACTING ===")
        print(f"{len(facts_result)} facts")
        facts = facts_result.get("facts", [claim])  # Fallback to original if extraction fails
        
        if not facts:
            facts = [claim]  # Ensure we have at least one fact
        
        print(f"Extracted {len(facts)} fact(s) to check:")
        for i, fact in enumerate(facts, 1):
            print(f"  {i}. {fact}")
        
        # ── Step 2: Fact-check each individual fact ──
        all_results = []
        
        for fact_idx, individual_fact in enumerate(facts):
            print(f"\n=== Checking fact {fact_idx + 1}/{len(facts)}: {individual_fact} ===")
            try:
                result = service.check_claim(
                    original_claim=individual_fact,
                    limit=LIMIT,
                )
                
                all_results.append({
                    "fact_index": fact_idx,
                    "original_fact": individual_fact,
                    "consensus": result.consensus,
                    "final_verdict": result.final_verdict,
                    "summary": result.summary,
                    "agreement_score": result.agreement_score,
                    "individual_results": result.individual_results,
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
                })
                
                print(f"Verdict: {result.final_verdict} (confidence: {result.agreement_score:.2f})")
                
            except Exception as e:
                print(f"Error checking fact {fact_idx + 1}: {str(e)}")
                all_results.append({
                    "fact_index": fact_idx,
                    "original_fact": individual_fact,
                    "error": str(e),
                })
        
        # ── Step 3: Return results ──
        # Backward compatible: first fact in top-level fields
        # Frontend-ready: all_results array with complete results
        first_result = all_results[0] if all_results else {}
        
        response_content = {
            "total_facts_extracted": len(facts),
            "facts_checked": len([r for r in all_results if "error" not in r]),
            "current_fact_index": 0,  # Frontend placeholder
            "current_fact": facts[0] if facts else claim,
            # === BACKWARD COMPATIBLE (first fact only) ===
            "consensus": first_result.get("consensus"),
            "final_verdict": first_result.get("final_verdict"),
            "summary": first_result.get("summary"),
            "agreement_score": first_result.get("agreement_score"),
            "individual_results": first_result.get("individual_results", []),
            "articles_used": first_result.get("articles_used", []),
            # === NEW: ALL RESULTS ===
            "all_results": all_results,
        }
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=response_content,
        )

    except Exception as e:
        import traceback
        import logging
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