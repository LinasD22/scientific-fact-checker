from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from api.db.database import engine
from api.db.models import Query

router = APIRouter(
    prefix="/history",
    tags=["history"]
)

# Dependency to get a database session
def get_session():
    with Session(engine) as session:
        yield session

@router.get("/user/{user_id}")
def get_user_history(user_id: int, session: Session = Depends(get_session)):
    # TODO right now we return max 3 we could increase this with pro plan
    statement = select(Query).where(Query.user_id == user_id).order_by(Query.query_date.desc()).limit(3)
    
    results = session.exec(statement).all()
    if not results:
        raise HTTPException(status_code=404, detail="No queries found for this user")
    else:
        return {
            "queries": [{
                "query_id": q.id,
                "claim": q.claim_text,
                "final_verdict": q.final_verdict,
                "claim_date": q.claim_date
            } for q in results],
        }

@router.get("/user/{user_id}/query/{query_id}")
def get_user_history(user_id: int, query_id: int, session: Session = Depends(get_session)):
    statement = select(Query).where(Query.user_id == user_id and Query.id == query_id)
    
    result = session.exec(statement).first()
    if not results:
        raise HTTPException(status_code=404, detail="No queries found for this user")
    else:

        return {
            "final_verdict": result.final_verdict,
            "claim_date": result.claim_date,
            "claim": result.claim_text,
            "facts": [fact for fact in result.result_json["facts"]]
        }