from sqlmodel import SQLModel, create_engine, Session
from agents.config import settings

# Retrieve database URL from global configurations dynamically
DATABASE_URL = getattr(
    settings, 
    "database_url", 
    getattr(settings, "DATABASE_URL", "sqlite:///./gaariguru.db")
)

# Connect arguments check for SQLite threading configurations
connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False

# Instantiate the SQLAlchemy/SQLModel database engine
engine = create_engine(DATABASE_URL, echo=False, connect_args=connect_args)

def create_db_and_tables():
    """Initializes the database schema by generating all declared SQLModel tables."""
    # Import models here to ensure they are registered on the SQLModel metadata before table creation
    from models.db_models import SearchQueryCache, CachedCarListing
    SQLModel.metadata.create_all(engine)

def get_session():
    """FastAPI dependency yielding a database session context."""
    with Session(engine) as session:
        yield session
