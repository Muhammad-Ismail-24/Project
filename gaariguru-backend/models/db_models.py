from datetime import datetime, timezone
from typing import Optional, List
from sqlmodel import SQLModel, Field, Relationship
from sqlalchemy import UniqueConstraint


class SearchQueryCache(SQLModel, table=True):
    """Database table to cache search queries to prevent duplicate scraping & appraisal calls."""
    id: Optional[int] = Field(default=None, primary_key=True)
    normalized_query: str = Field(index=True, unique=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

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

    red_flags_json: str
    liquidity_score: str
    justification: str

    search_query: SearchQueryCache = Relationship(back_populates="listings")


class User(SQLModel, table=True):
    """Database table representing authenticated users."""
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True)
    name: Optional[str] = Field(default=None)
    picture: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Configurable AI assistant name — user sets this in Settings.
    # Default "GaariGuru Expert" is used until user changes it.
    agent_name: str = Field(default="GaariGuru Expert")

    saved_listings: List["SavedListing"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )
    chat_messages: List["ChatMessage"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )


class SavedListing(SQLModel, table=True):
    """Database table representing a car listing saved by a user."""
    __table_args__ = (UniqueConstraint("user_id", "listing_id", name="uq_user_listing"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    listing_id: str = Field(index=True)
    platform: str
    title: str
    saved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    user_id: int = Field(foreign_key="user.id", index=True)
    user: Optional[User] = Relationship(back_populates="saved_listings")


class ChatMessage(SQLModel, table=True):
    """
    Persistent chat history for logged-in users.

    One row per message turn. Guests never write here — their
    conversation exists only in React state for the session.

    role: "user" | "assistant"
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    role: str                          # "user" | "assistant"
    content: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    user: Optional[User] = Relationship(back_populates="chat_messages")