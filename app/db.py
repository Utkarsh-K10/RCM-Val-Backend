from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import os

DATABASE_URL = os.getenv("DATABASE_URL")

# Ensure SSL mode is required (important for Supabase / Railway)
if DATABASE_URL and "sslmode" not in DATABASE_URL:
    if "?" in DATABASE_URL:
        DATABASE_URL += "&sslmode=require"
    else:
        DATABASE_URL += "?sslmode=require"

# Create SQLAlchemy engine with health checks
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,        # auto-reconnect if dropped
    pool_size=5,               # small pool (Supabase free tier has connection limits)
    max_overflow=2
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    """Dependency for FastAPI routes"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
