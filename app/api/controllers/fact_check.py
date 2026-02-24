"""
API endpoints for the fact checker plugin.
"""

from typing import Annotated

from fastapi import Body, APIRouter, HTTPException, status, FastAPI
from fastapi.responses import JSONResponse

from api.services.fact_checker import FactCheckerService, create_fact_checker

app = FastAPI(
    title="Scientific Fact Checker API",
    description="AI-powered fact-checking against academic papers",
    version="1.0.0"
)

_fact_checker: FactCheckerService | None = None


def get_fact_checker() -> FactCheckerService:
    global _fact_checker
    if _fact_checker is None:
        _fact_checker = create_fact_checker()
    return _fact_checker


@router.post("/fact-check/search")
async def fact_check_with_search(
    claim: Annotated[str, Body(description="The fact/claim to verify")],
    query: Annotated[str | None, Body(description="Search query for Core API")] = None,
    limit: Annotated[int, Body(description="Number of papers to search", ge=1, le=10)] = 3,
    core_api_key: Annotated[str | None, Body(description="Override Core API key")] = None,
    ai_api_key: Annotated[str | None, Body(description="Override AI API key")] = None,
) -> JSONResponse:
    """
    Full pipeline:
    1. Search Core API for relevant academic papers
    2. Search Pinecone for high-relevance snippets
    3. Use AI to fact-check snippets against the claim
    4. Return combined verdict
    """
    try:
        service = (
            create_fact_checker(core_api_key=core_api_key, ai_api_key=ai_api_key)
            if core_api_key or ai_api_key
            else get_fact_checker()
        )

        result = service.check_claim(
            original_claim=claim,
            query=query,
            limit=limit,
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
