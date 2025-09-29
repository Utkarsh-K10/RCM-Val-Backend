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
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()

