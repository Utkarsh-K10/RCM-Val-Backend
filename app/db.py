# db.py
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# --- Configuration and Engine Setup ---

DATABASE_URL = os.getenv("DATABASE_URL")

# Check if the environment variable is set
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is not set.")

# Ensure SSL mode is required, important for hosted databases like Supabase
if "sslmode" not in DATABASE_URL:
    # Append sslmode=require to the URL
    if "?" in DATABASE_URL:
        DATABASE_URL += "&sslmode=require"
    else:
        DATABASE_URL += "?sslmode=require"

# Create SQLAlchemy engine with connection pool settings
# These settings are beneficial for use with Supabase's pooler (Supavisor)
engine = create_engine(
    url=DATABASE_URL,
    pool_pre_ping=True,  # auto-reconnect if dropped
    pool_size=5,         # small pool (Supabase free tier has connection limits)
    max_overflow=2
)

# --- Session and Dependency Setup ---

# SessionLocal class is used to produce new Session objects
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for declarative models
Base = declarative_base()

def get_db():
    """
    FastAPI Dependency: Provides a database session for each request.
    It closes the session automatically after the request is finished.
    """
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()

