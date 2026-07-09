from datetime import datetime, timezone
from typing import Optional, List
from sqlmodel import SQLModel, Field, Relationship


class SearchQueryCache(SQLModel, table=True):
    """Database table to cache search queries to prevent duplicate scraping & appraisal calls."""
    id: Optional[int] = Field(default=None, primary_key=True)
    normalized_query: str = Field(index=True, unique=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Relationship to cached listings: One Search Query can have Many Car Listings
    listings: List["CachedCarListing"] = Relationship(
        back_populates="search_query", 
        sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )


class CachedCarListing(SQLModel, table=True):
    """Database table representing the fully evaluated car listings returned in searches."""
    id: str = Field(primary_key=True)
    search_id: int = Field(foreign_key="searchquerycache.id")
    
    title: str
    price: int
    mileage: int
    city: str
    year: int
    listing_url: str
    image_url: Optional[str] = Field(default=None, nullable=True)
    platform: str
    
    # Store red flags array as stringified JSON array
    red_flags_json: str
    liquidity_score: str
    justification: str

    # Relationship back to the cache query record
    search_query: SearchQueryCache = Relationship(back_populates="listings")
