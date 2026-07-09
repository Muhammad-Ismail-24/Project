from pydantic import BaseModel, Field
from typing import Optional, Union
from datetime import datetime, timezone
from uuid import uuid4

class CarListing(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    title: str
    price: Union[int, str]
    mileage: Union[int, str]
    city: str
    year: Union[int, str]
    listing_url: str
    image_url: str = ""
    platform: str
    age_days: int = Field(default=0)
    scraped_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
