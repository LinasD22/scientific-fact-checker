"""
API endpoints for the fact checker plugin.
"""
import base64
import os
from typing import Annotated

from mistralai import Mistral

from api.utils.ai_calls import extract_individual_facts
from fastapi import Body, APIRouter, HTTPException, status, UploadFile, File

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

LIMIT=3
ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/jpg"}

def get_fact_checker() -> FactCheckerService:
    global _fact_checker
    if _fact_checker is None:
        _fact_checker = create_fact_checker()
    return _fact_checker

@router.post("/fact-check/ocr")
async def ocr_image(file: UploadFile = File(..., description="PNG or JPEG image to extract text from"),) -> JSONResponse:
    """
    Extract text from an uploaded PNG or JPEG image using Mistral OCR (mistral-ocr-latest).
    Returns the extracted text as a plain string ready to be used as a fact-check claim.
    """
    # ── Validate content type ──────────────────────────────────────────────────
    content_type = file.content_type or ""
    if content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type '{content_type}'. Only PNG and JPEG images are accepted.",
        )

    # ── Read & encode image ────────────────────────────────────────────────────
    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
    data_url = f"data:{content_type};base64,{image_b64}"

    # ── Call Mistral OCR ───────────────────────────────────────────────────────
    mistral_api_key = os.environ.get("MISTRAL_API_KEY")
    if not mistral_api_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="MISTRAL_API_KEY is not configured on the server.",
        )

    try:
        client = Mistral(api_key=mistral_api_key)
        ocr_response = client.ocr.process(
            model="mistral-ocr-latest",
            document={
                "type": "image_url",
                "image_url": data_url,
            },
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Mistral OCR request failed: {str(e)}",
        )

    # ── Collect text from all pages ────────────────────────────────────────────
    pages_text: list[str] = []
    for page in ocr_response.pages or []:
        page_text = (page.markdown or "").strip()
        if page_text:
            pages_text.append(page_text)

    extracted_text = "\n\n".join(pages_text).strip()

    if not extracted_text:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"text": "", "message": "No text could be extracted from the image."},
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"text": extracted_text},
    )



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
    2. For each claim:
       a. Search Core API for relevant academic papers
       b. Search Qdrant for high-relevance snippets
       c. Use AI to fact-check snippets against the claim
    3. Return results:
       - Backward compatible: first fact in top-level fields
       - New: all_results array with complete results for each fact
    Request JSON: `{"claim": "...", "user_id": null|123}` — pass `user_id` to store this run in `Query` for `/history` APIs.
    """
    try:
        claim = body.claim
        service = get_fact_checker()
        
        # ── Step 1: Extract individual facts from the provided text ──
        print(f"\n=== ORIGINAL WHOLE CLAIM: {claim} ===")
        print(f"\n=== Preprocessing: Extracting individual facts ===")
        facts_result = extract_individual_facts(claim)
        
        # Accommodate the new AI format (dicts with exact_quote) while falling back to strings if needed
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
        
        # ── Step 2: Fact-check each individual fact ──
        all_results = []
        
        for fact_idx, f_obj in enumerate(facts):
            individual_fact = f_obj["fact"]
            exact_quote = f_obj.get("exact_quote", individual_fact) # Grab the exact quote

            print(f"\n=== Checking fact {fact_idx + 1}/{len(facts)}: {individual_fact} ===")
            try:
                result = service.check_claim(
                    original_claim=individual_fact,
                    limit=LIMIT,
                )
                
                all_results.append({
                    "fact_index": fact_idx,
                    "original_fact": individual_fact,
                    "exact_quote": exact_quote, # <--- ADD THIS NEW FIELD
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

        if user_id is not None:
            _persist_query(user_id, claim, response_content)

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