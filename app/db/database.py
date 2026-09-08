"""
Database connection setup.
Reads DATABASE_URL from .env (postgresql://ecommerce_user:ecommerce_pass@localhost:5433/ecommerce_db)
"""
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set. Check your .env file.")

# pool_pre_ping avoids stale-connection errors after Docker restarts
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """
    FastAPI-style dependency generator.
    Usage in tools.py / main.py:
        db = next(get_db())
        ... or via Depends(get_db) once FastAPI is wired in (Step 8).
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
