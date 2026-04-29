from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from api.db.database import engine
from api.db.models import Query
from api.utils.auth_deps import get_required_user_id

router = APIRouter(
    prefix="/history",
    tags=["history"],
)

# TODO(team): Replace with `Query.final_verdict` or a defined aggregate (e.g. from all facts) when product agrees.
MOCK_FINAL_VERDICT: str = "unverifiable"


def get_session():
    with Session(engine) as session:
        yield session


@router.get("/user/{user_id}")
def get_user_history(
    user_id: int,
    session: Session = Depends(get_session),
    current_user_id: int = Depends(get_required_user_id),
):
    if current_user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access forbidden")
    # TODO: raise limit for pro plan
    statement = select(Query).where(Query.user_id == user_id).order_by(Query.claim_date.desc()).limit(3)
    results = session.exec(statement).all()
    if not results:
        return {"queries": []}
    return {
        "queries": [
            {
                "query_id": q.id,
                "claim": q.claim_text,
                # TODO(team): replace with q.final_verdict (or aggregate) per product spec
                "final_verdict": MOCK_FINAL_VERDICT,
                "claim_date": q.claim_date.isoformat() if q.claim_date is not None else None,
            }
            for q in results
        ],
    }


@router.get("/user/{user_id}/query/{query_id}")
def get_user_query_detail(
    user_id: int,
    query_id: int,
    session: Session = Depends(get_session),
    current_user_id: int = Depends(get_required_user_id),
):
    if current_user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access forbidden")
    statement = select(Query).where(Query.user_id == user_id, Query.id == query_id)
    result = session.exec(statement).first()
    if not result:
        raise HTTPException(status_code=404, detail="No query found for this user")
    data = result.result_json
    if not data:
        facts: list = []
    else:
        raw = data.get("facts") if data.get("facts") is not None else data.get("all_results")
        facts = raw if isinstance(raw, list) else []
    return {
        # TODO(team): replace with result.final_verdict (or aggregate) per product spec
        "final_verdict": MOCK_FINAL_VERDICT,
        "claim_date": result.claim_date.isoformat() if result.claim_date is not None else None,
        "claim": result.claim_text,
        "facts": facts,
    }
