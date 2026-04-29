"""
Create one user (same rules as POST /auth/register) without the HTTP server.

From repo root:
  PYTHONPATH=backend python database/register_one_user.py

Env (optional):
  REGISTER_EMAIL, REGISTER_PASSWORD, FIRST_NAME, LAST_NAME

Also loads backend/.env so JWT/SECRET and bcrypt work.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "backend"))

from dotenv import load_dotenv

load_dotenv(_REPO / "database" / ".env", override=True)
load_dotenv(_REPO / "backend" / ".env", override=False)

from sqlmodel import Session, select

from api.db.database import engine
from api.db.models import Auth, User
from api.utils.password_security import hash_password


def main() -> None:
    email = os.getenv("REGISTER_EMAIL", "dev.user@factchecker.local")
    password = os.getenv("REGISTER_PASSWORD", "DevPass2026!")
    first = os.getenv("FIRST_NAME", "Dev")
    last = os.getenv("LAST_NAME", "User")

    with Session(engine) as session:
        existing = session.exec(select(Auth).where(Auth.email == email)).first()
        if existing:
            print(f"User already exists: {email} — skipping.")
            u = session.exec(select(User).where(User.email == email)).first()
            if u and u.id is not None:
                print(f"user_id={u.id}")
            return

        auth = Auth(email=email, password=hash_password(password))
        session.add(auth)
        session.flush()
        user = User(
            first_name=first,
            last_name=last,
            email=email,
            auth_email=auth.email,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        print(f"Registered: {email}  user_id={user.id}")


if __name__ == "__main__":
    main()
