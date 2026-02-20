"""
API endpoints for the fact checker pugin.
"""

from typing import Annotated

from fastapi import Body, FastAPI, HTTPException, status
from fastapi.responses import JSONResponse

from api.services.fact_checker import FactCheckerService, create_fact_checker


# Create the FastAPI app
app = FastAPI(
    title="Scientific Fact Checker API",
    description="AI-powered fact-checking against academic papers",
    version="1.0.0"
)

# Global service instance (can be overridden with custom keys)
_fact_checker: FactCheckerService | None = None


def get_fact_checker() -> FactCheckerService:
    """Get or create the fact-checker service instance."""
    global _fact_checker
    if _fact_checker is None:
        _fact_checker = create_fact_checker()
    return _fact_checker


@app.post("/fact-check/search")
async def fact_check_with_search(
    claim: Annotated[str, Body(description="The fact/claim to verify")],
    query: Annotated[str | None, Body(description="Search query for Core API")] = None,
    limit: Annotated[int, Body(description="Number of papers to search", ge=1, le=10)] = 3,
    core_api_key: Annotated[str | None, Body(description="Override Core API key")] = None,
    ai_api_key: Annotated[str | None, Body(description="Override AI API key")] = None,
) -> JSONResponse:
    """
    Check a claim by searching academic papers and using AI for fact-checking.
    
    This endpoint:
    1. Searches Core API for relevant academic works
    2. Uses AI to check each work against the claim
    3. Compares results and provides a final verdict
    """
    try:
        # Create service with optional custom keys
        if core_api_key or ai_api_key:
            service = create_fact_checker(
                core_api_key=core_api_key,
                ai_api_key=ai_api_key
            )
        else:
            service = get_fact_checker()
        
        # Run fact-check
        result = service.check_claim(
            original_claim=claim,
            query=query,
            limit=limit
        )
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "original_claim": result.original_claim,
                "works_searched": result.works_searched,
                "works_with_text": result.works_with_text,
                "individual_results": result.individual_results,
                "sorted_results": result.sorted_results,
                "consensus": result.consensus,
                "final_verdict": result.final_verdict,
                "summary": result.summary,
                "agreement_score": result.agreement_score
            }
        )
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Fact-check failed: {str(e)}"
        )


@app.post("/fact-check/texts")
async def fact_check_with_texts(
    claim: Annotated[str, Body(description="The fact/claim to verify")],
    texts: Annotated[
        list[dict[str, str]],
        Body(description="List of texts to check with 'text', 'title', and optional 'url'")
    ],
    ai_api_key: Annotated[str | None, Body(description="Override AI API key")] = None,
) -> JSONResponse:
    """
    Check a claim against provided texts without searching.
    
    Use this endpoint when you have texts already and just need
    AI fact-checking without the Core API search.
    """
    try:
        # Create service with optional custom key
        if ai_api_key:
            service = create_fact_checker(ai_api_key=ai_api_key)
        else:
            service = get_fact_checker()
        
        # Run fact-check with provided texts
        result = service.check_claim_with_texts(
            original_claim=claim,
            texts=texts
        )
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "original_claim": result.original_claim,
                "works_searched": result.works_searched,
                "works_with_text": result.works_with_text,
                "individual_results": result.individual_results,
                "sorted_results": result.sorted_results,
                "consensus": result.consensus,
                "final_verdict": result.final_verdict,
                "summary": result.summary,
                "agreement_score": result.agreement_score
            }
        )
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Fact-check failed: {str(e)}"
        )


@app.get("/health")
async def health_check() -> JSONResponse:
    """Health check endpoint."""
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"status": "healthy"}
    )
