from pydantic import BaseModel, Field
from typing import Optional, Union
from datetime import datetime, timezone
from uuid import uuid4

from scrapers.date_utils import UNKNOWN_AGE


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
    # Days since the listing was posted. UNKNOWN_AGE (-1) means the scraper
    # could not determine it — test with date_utils.is_unknown_age(), never
    # against a magic number.
    #
    # The default is UNKNOWN_AGE, not 0. A scraper that never sets this field
    # is saying "I don't know", and 0 means "posted today". Conflating the two
    # let every dateless Drive.pk / AutoDeals / FameWheels listing present
    # itself to the normalisers as same-day fresh inventory.
    age_days: int = Field(default=UNKNOWN_AGE)
    scraped_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    matched_target: str = ""
