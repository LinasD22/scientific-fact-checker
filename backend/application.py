import logging
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware

# nuskaito app/.env
sys.path.insert(0, str(Path(__file__).parent.parent))
env_path = Path(__file__).parent / ".env"

if env_path.exists():
    load_dotenv(dotenv_path=env_path, override=True)
    print(f"application.py Success: Loaded .env from {env_path}")
else:
    print(f"application.py Error: Could not find .env at {env_path}")


from fastapi import FastAPI
from api.controllers.fact_check import router as fact_check_router

# expose FastAPI application at module level so CLI can discover it
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)-8s %(name)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)


app = FastAPI(
    title="Scientific Fact Checker API",
    description="AI-powered fact-checking against academic papers",
    version="1.0.0"
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
    "chrome-extension://bemiflplbncbfocohghkahmaacmgnpho",
    "http://localhost:*",
    "https://api.healthfactchecker.site",
    "https://healthfactchecker.site"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)
# Include fact-check routes
app.include_router(fact_check_router, prefix="/api", tags=["fact-check"])

# Database setup
from api.db.database import engine
from sqlmodel import SQLModel
from api.db import models 

def create_db_and_tables():
    SQLModel.metadata.create_all(engine)

@app.on_event("startup")
def on_startup():
    create_db_and_tables()

# Include authentication routes
from api.controllers import auth
app.include_router(auth.router)


from api.controllers import history
app.include_router(history.router)

if __name__ == "__main__":
    os.system(f"fastapi dev {str(Path(__file__).parent)}/application.py --host 0.0.0.0 --port 8000") #8080
