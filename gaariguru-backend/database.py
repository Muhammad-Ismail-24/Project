import os
from sqlmodel import SQLModel, create_engine, Session
from agents.config import settings

# 1. Retrieve URL from settings, fallback to os.getenv, then default to local SQLite
raw_url = getattr(
    settings, 
    "database_url", 
    getattr(settings, "DATABASE_URL", os.getenv("DATABASE_URL", "sqlite:///./gaariguru.db"))
)

# 2. Crucial fix for SQLAlchemy: enforce 'postgresql://' over legacy 'postgres://'
if raw_url and raw_url.startswith("postgres://"):
    DATABASE_URL = raw_url.replace("postgres://", "postgresql://", 1)
else:
    DATABASE_URL = raw_url

# 3. Connect arguments check for SQLite threading configurations
connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False

# Instantiate the SQLAlchemy/SQLModel database engine
engine = create_engine(DATABASE_URL, echo=False, connect_args=connect_args)

def create_db_and_tables():
    """Initializes the database schema by generating all declared SQLModel tables."""
    from models.db_models import SearchQueryCache, CachedCarListing
    SQLModel.metadata.create_all(engine)

def get_session():
    """FastAPI dependency yielding a database session context."""
    with Session(engine) as session:
        yield session