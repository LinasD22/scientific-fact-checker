"""
API endpoints for the fact checker plugin.
"""

from typing import Annotated
from api.utils.ai_calls import fact_preprocess
from fastapi import Body, APIRouter, HTTPException, status
from fastapi.responses import JSONResponse

from app.internal.api.services.fact_checker import FactCheckerService, create_fact_checker

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
    Full pipeline:
    1. Search Core API for relevant academic papers
    2. Search Pinecone for high-relevance snippets
    3. Use AI to fact-check snippets against the claim
    4. Return combined verdict
    """
    try:
        service = create_fact_checker()

        #TODO uncomment when we want to preprocess

        # preprocessing_json = fact_preprocess(claim)
        # if preprocessing_json["is_health_related"] == "false":
        if False:
            print("\n\n")
            print("This fact is not related to health.")
            print("\n\n")

            print(f"Justification:\n\t{preprocessing_json["justification"]}")

            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"detail": "Fact is not health related"},
            )
        else:

            result = service.check_claim(
                original_claim=claim,
                limit=LIMIT,
            )

            print(f"Agreement score: {result.agreement_score}")
            print(f"Summary:         {result.summary}")

            # print("\nIndividual results:")
            # for r in result.individual_results:
            #     score = f"[pinecone: {r['pinecone_score']:.3f}]" if r['pinecone_score'] else ""
            #     print(f"  {score} {r['source_title']}: {r['result']} (confidence: {r['confidence']})")
            #     print(f"Source snippet: {r['source_text']}")
            #     print(f"Explanation: { r['explanation']}")


        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "consensus": result.consensus,
                "final_verdict": result.final_verdict,
                "summary": result.summary,
                "agreement_score": result.agreement_score,
            },
        )

    except Exception as e:
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
    Check a claim against provided texts (no Core API or Pinecone search).
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