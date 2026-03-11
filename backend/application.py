import logging
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# nuskaito app/.env
sys.path.insert(0, str(Path(__file__).parent.parent))
load_dotenv(Path(__file__).parent / ".env")  # nuskaito app/.env

from fastapi import FastAPI
from api.controllers.fact_check import router as fact_check_router

# expose FastAPI application at module level so CLI can discover it
app = FastAPI(
    title="Scientific Fact Checker API",
    description="AI-powered fact-checking against academic papers",
    version="1.0.0"
)

# Include fact-check routes
app.include_router(fact_check_router, prefix="/api", tags=["fact-check"])

if __name__ == "__main__":
    # TODO remove and just call from terminal
    os.system(f"fastapi dev {str(Path(__file__).parent)}/application.py --host 127.0.0.1 --port 9000")