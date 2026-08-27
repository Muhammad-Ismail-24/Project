from core.logger import get_logger
logger = get_logger(__name__)
"""
scrapers/drive_pk.py

REBUILT 2026-08-16 — HTML parsing replaced by the site's own JSON API.

WHY
---
Drive.pk is an Angular single-page app. The server ships a 830 KB shell whose
only listing content is a `<script id="ng-state" type="application/json">`
TransferState blob; there are no `.car-card` / `.listing` / `.col-md-4`
elements anywhere in it. The old BeautifulSoup selectors matched exactly zero
nodes, so this scraper had been silently returning [] on every search.

That TransferState blob turned out to be a cached copy of a public, unauthenticated
REST call, so we skip the HTML entirely and query the API directly:

    GET https://api.drivepk.com/cars

Response:
    {"message": ..., "data": [ {...}, ... ], "pagination": {"page","limit","total","totalPages","hasNext","hasPrev"}}

Query parameters (verified live against the running API):
    page       int    1-based
    limit      int    honoured up to at least 100
    brands     str    make name,  e.g. "Toyota"      (alias: brand)
    models     str    model name, e.g. "Corolla"     (alias: model)
    cities     str    city name,  e.g. "Lahore"      (alias: city)
    minPrice / maxPrice   int PKR
    minYear  / maxYear    int

    NOT supported: q / search / keyword — the API accepts them and silently
    ignores them (result total is unchanged), so free-text must never be
    relied on for filtering.

Per-record fields used here:
    title, price (int PKR), year, mileage (int km), location.city,
    images[] (absolute CDN URLs), slug, createdAt / liveAt (ISO-8601)

Listing URL: https://www.drivepk.com/cars/classified/{slug}

The runner still builds a drivepk.com/cars/list?... URL, so this module parses
that URL's query string and maps it onto the API. runner.py needs no changes.
"""
import re
from urllib.parse import parse_qs, urlparse, unquote_plus

from models.car_schema import CarListing
from scrapers.date_utils import age_days_from_timestamp, is_unknown_age

API_URL = "https://api.drivepk.com/cars"
DETAIL_BASE = "https://www.drivepk.com/cars/classified/"

MAX_ORGANIC_CARDS = 35
REQUEST_TIMEOUT = 25


def _first_token(value: str) -> str:
    """
    Reduces a model query to its leading token.

    url_builder.build_platform_search_url() appends a resolved trim slug onto
    the `q` parameter ("corolla%20altis-grande"), and the API's `models` filter
    will not match that compound string. Taking the leading token biases toward
    over-fetching ("Corolla" also returns "Corolla Cross") rather than
    under-fetching — the normalizer's identity scoring rejects the extras,
    whereas a listing never fetched can never be recovered.
    """
    cleaned = unquote_plus(value or "").strip()
    if not cleaned:
        return ""
    return re.split(r'[\s+]+', cleaned)[0].strip()


def _api_params_from_url(url: str) -> dict:
    """Translates the runner's drivepk.com/cars/list URL into API parameters."""
    query = parse_qs(urlparse(url).query)

    def one(key: str) -> str:
        vals = query.get(key) or []
        return (vals[0] or "").strip() if vals else ""

    params = {
        "page":  one("page") or 1,
        "limit": MAX_ORGANIC_CARDS,
    }

    brands = one("brands")
    if brands:
        params["brands"] = brands

    model = _first_token(one("q"))
    if model:
        params["models"] = model

    cities = one("cities")
    if cities:
        params["cities"] = cities

    for src, dst in (("minPrice", "minPrice"), ("maxPrice", "maxPrice"),
                     ("minYear", "minYear"), ("maxYear", "maxYear")):
        raw = one(src)
        if raw.isdigit() and int(raw) > 0:
            params[dst] = int(raw)

    return params


def _build_listing(item: dict) -> CarListing | None:
    """Maps one API record onto a CarListing, or None when unusable."""
    title = (item.get("title") or "").strip()
    if not title or len(title) < 4:
        return None

    brand = (item.get("brand") or {}).get("name") or ""
    if brand and brand.lower() not in title.lower():
        # Several sellers omit the make from the headline ("Corolla Gli 2017").
        # The normalizer vetoes on make-not-in-title, so prepend the structured
        # brand rather than lose a legitimate match to a lazy title.
        title = f"{brand} {title}".strip()

    location = item.get("location") or item.get("currentLocation") or {}
    city = (location.get("city") or "").strip() or "Unknown"

    images = item.get("images") or []
    image_url = ""
    for img in images:
        if isinstance(img, str) and img.startswith("http"):
            image_url = img
            break

    slug = (item.get("slug") or "").strip()
    listing_url = DETAIL_BASE + slug if slug else "https://www.drivepk.com/cars/list"

    # createdAt is when the ad was posted; liveAt is when it went visible.
    # Prefer createdAt and fall back to liveAt, matching how the site itself
    # orders and labels its inventory.
    age_days = age_days_from_timestamp(item.get("createdAt") or item.get("liveAt"))

    return CarListing(
        title=title,
        price=item.get("price") or 0,
        mileage=item.get("mileage") or 0,
        city=city,
        year=item.get("year") or 0,
        listing_url=listing_url,
        image_url=image_url,          # never None — the model requires str
        platform="Drive.pk",
        age_days=age_days,
    )


async def scrape_drive_pk(url: str, session, search_filters: dict = None) -> list[CarListing]:
    """Scrapes Drive.pk through its public JSON API."""
    params = _api_params_from_url(url)

    try:
        response = await session.get(API_URL, params=params, timeout=REQUEST_TIMEOUT)
    except Exception as e:
        logger.error(f"[Drive.pk Scraper] API request failed: {e}", exc_info=True)
        return []

    if response.status_code != 200:
        logger.info(f"[Drive.pk Scraper] API HTTP {response.status_code} for params {params}")
        return []

    try:
        payload = response.json()
    except Exception as e:
        logger.info(f"[Drive.pk Scraper] API returned non-JSON: {e}")
        return []

    records = payload.get("data")
    if not isinstance(records, list):
        logger.info(f"[Drive.pk Scraper] Unexpected API shape, keys={list(payload)[:8]}")
        return []

    cars: list[CarListing] = []
    for item in records[:MAX_ORGANIC_CARDS]:
        if not isinstance(item, dict):
            continue
        try:
            listing = _build_listing(item)
        except Exception as e:
            logger.info(f"[Drive.pk Scraper] Skipped malformed record: {e}")
            continue
        if listing:
            cars.append(listing)

    age_found = sum(1 for c in cars if not is_unknown_age(c.age_days))
    total = (payload.get("pagination") or {}).get("total")
    logger.info(
        f"[Drive.pk Scraper] Extracted {len(cars)} listings via API "
        f"(matched {total} total). Age: {age_found}/{len(cars)} parsed."
    )
    return cars
