import os
from pathlib import Path
from dotenv import load_dotenv
from sqlmodel import create_engine, Session, SQLModel, Field

env_path = Path(__file__).resolve().parent.parent.parent.parent / 'database'/'.env'

if env_path.exists():
    load_dotenv(dotenv_path=env_path, override=True)
    print(f"database.py Success: Loaded .env from {env_path}")
else:
    print(f"database.py Error: Could not find .env at {env_path}")


# Build URL using your .env variables
user = os.getenv("DB_USER")
password = os.getenv("DB_PASSWORD")
host = os.getenv("DB_HOST", "localhost")
port = os.getenv("DB_PORT", "3306")
db_name = os.getenv("DB_NAME")

DATABASE_URL = f"mysql+mysqlconnector://{user}:{password}@{host}:{port}/{db_name}"

# echo=False for production, True for debugging SQL commands
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

def get_session():
    with Session(engine) as session:
        yield session