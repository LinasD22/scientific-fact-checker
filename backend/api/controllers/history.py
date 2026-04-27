from fastapi import APIRouter, Depends
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
    statement = select(Query).where(Query.user_id == user_id).order_by(Query.query_date.desc()).limit(3)
    results = session.exec(statement).all()
    if not results:
        raise HTTPException(status_code=404, detail="No queries found for this user")
    else:
        return {
            "queries": [results.query_text for results in results]
            }   