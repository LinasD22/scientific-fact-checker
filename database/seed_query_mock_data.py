"""
Insert mock Query rows into fact_checker_db (MySQL).

Run from repository root:
  PYTHONPATH=backend python database/seed_query_mock_data.py

Requires database/.env (DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, DB_NAME).

Does not create users (avoids bcrypt in this script). Uses the first row in `User`, or
`SEED_USER_ID` from the environment, or exit with a short message.
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

# repo_root / backend on path
_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "backend"))

from dotenv import load_dotenv

# DB credentials from database/.env
load_dotenv(_REPO / "database" / ".env", override=True)

import os

from sqlmodel import Session, select

from api.db.database import engine
from api.db.models import Query, User
from api.enums import FactCheckResult


def _result_payload(claim: str, verdict: str, n_facts: int) -> dict:
    """Shape similar to fact_check persistence + history `facts` key."""
    facts = [
        {
            "fact_index": i,
            "original_fact": claim[:200] if i == 0 else f"Sub-claim {i + 1} related to the main topic.",
            "consensus": verdict,
            "final_verdict": verdict,
            "summary": (
                "Sources largely support this statement; two systematic reviews and a cohort study "
                "align on the main effect, with minor caveats on generalizability."
            )[:500],
            "agreement_score": 0.72 + i * 0.05,
            "individual_results": [
                {
                    "source_title": "Lancet Public Health 2022",
                    "result": "verified" if verdict == "verified" else "partially_verified",
                    "reliability": 0.88,
                    "confidence": 0.81,
                }
            ],
            "articles_used": [
                {
                    "title": "Systematic review of trial evidence",
                    "published_date": "2023-04-12",
                    "authors": "Smith J, Lee K",
                    "source": "core",
                    "url": "https://example.org/paper/1001",
                    "index": 0,
                }
            ],
        }
        for i in range(n_facts)
    ]
    base = {
        "total_facts_extracted": n_facts,
        "facts_checked": n_facts,
        "current_fact_index": 0,
        "current_fact": claim[:200],
        "consensus": verdict,
        "final_verdict": verdict,
        "summary": facts[0]["summary"] if facts else "",
        "agreement_score": facts[0].get("agreement_score", 0.0) if facts else 0.0,
        "individual_results": facts[0].get("individual_results", []) if facts else [],
        "articles_used": facts[0].get("articles_used", []) if facts else [],
        "all_results": facts,
        "facts": facts,
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }
    return base


MOCK_CLAIMS: list[tuple[str, FactCheckResult, int, date]] = [
    (
        "COVID-19 mRNA vaccines reduce risk of severe disease in adults 65+ according to multiple RCTs.",
        FactCheckResult.VERIFIED,
        2,
        date(2026, 1, 14),
    ),
    (
        "Eight weeks of moderate aerobic training improves VO2 max in previously sedentary adults.",
        FactCheckResult.PARTIALLY_VERIFIED,
        1,
        date(2026, 2, 3),
    ),
    (
        "Megadoses of vitamin C prevent the common cold in the general population.",
        FactCheckResult.UNVERIFIABLE,
        3,
        date(2026, 2, 20),
    ),
    (
        "Statins lower LDL cholesterol; effect size varies by baseline risk and statin type.",
        FactCheckResult.VERIFIED,
        1,
        date(2026, 3, 1),
    ),
]


def _resolve_user_id(session: Session) -> int:
    override = os.getenv("SEED_USER_ID")
    if override is not None and override.isdigit():
        u = session.get(User, int(override))
        if u is None:
            raise SystemExit(f"No User with Id={override}. Set SEED_USER_ID to a valid user id.")
        return int(override)
    first = session.exec(select(User).limit(1)).first()
    if first and first.id is not None:
        return first.id
    raise SystemExit(
        "No users in the database. Register one user via POST /auth/register, then run:\n"
        "  SEED_USER_ID=1 python database/seed_query_mock_data.py"
    )


def main() -> None:
    with Session(engine) as session:
        user_id = _resolve_user_id(session)
        for claim, verdict, n_facts, cdate in MOCK_CLAIMS:
            if len(claim) > 255:
                claim = claim[:255]
            payload = _result_payload(claim, verdict.value, n_facts)
            row = Query(
                claim_text=claim,
                claim_date=cdate,
                result_json=payload,
                final_verdict=verdict,
                user_id=user_id,
            )
            session.add(row)
        session.commit()

    print(f"Inserted {len(MOCK_CLAIMS)} Query row(s) for user_id={user_id}.")


if __name__ == "__main__":
    main()
