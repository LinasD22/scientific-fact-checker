from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from api.db.database import engine
from api.db.models import Query

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
def get_user_history(user_id: int, session: Session = Depends(get_session)):
    # TODO: raise limit for pro plan
    statement = select(Query).where(Query.user_id == user_id).order_by(Query.claim_date.desc()).limit(3)
    results = session.exec(statement).all()
    if not results:
        raise HTTPException(status_code=404, detail="No queries found for this user")
    return {
        "queries": [
            {
                "query_id": q.id,
                "claim": q.claim_text,
                "final_verdict": MOCK_FINAL_VERDICT,  # TODO(team): was q.final_verdict
                "claim_date": str(q.claim_date) if q.claim_date is not None else None,
            }
            for q in results
        ],
    }


@router.get("/user/{user_id}/query/{query_id}")
def get_user_query_detail(user_id: int, query_id: int, session: Session = Depends(get_session)):
    statement = select(Query).where(Query.user_id == user_id, Query.id == query_id)
    result = session.exec(statement).first()
    if not result:
        raise HTTPException(status_code=404, detail="No query found for this user")
    data = result.result_json
    if not data:
        facts: list = []
    else:
        facts = data.get("facts") or data.get("all_results") or []
    return {
        "final_verdict": MOCK_FINAL_VERDICT,  # TODO(team): was result.final_verdict or aggregate
        "claim_date": str(result.claim_date) if result.claim_date is not None else None,
        "claim": result.claim_text,
        "facts": facts,
    }
