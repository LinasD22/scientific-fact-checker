from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from backend.api.db.database import SessionLocal, engine
from backend.api.models.fact_check import FactCheck # Import your model

# This line tells SQLAlchemy to actually go to the remote server 
# and create the tables if they don't exist yet.
FactCheck.metadata.create_all(bind=engine)

app = FastAPI()

# The Dependency to get a database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()