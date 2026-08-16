"""
scrapers/auto_deals.py

REBUILT 2026-08-16 — HTML parsing replaced by the site's own JSON API.

WHY
---
autodeals.pk is a client-rendered React SPA sitting behind Cloudflare. Every
URL returns the same ~2.4 KB shell — `<div id="root"></div>`, a bundle tag, and
a Cloudflare challenge-platform snippet. There is no server-rendered markup at
all, so the old BeautifulSoup card selectors matched nothing and this scraper
had been returning [] on every single search.

The React bundle calls a public REST API, which we query directly:

    GET https://api.autodeals.pk/flyers

AUTHENTICATION — the "API key" is the Origin header
---------------------------------------------------
Without an Origin header the API answers:

    403 {"message":"Forbidden: invalid API key"}

Sending `Origin: https://autodeals.pk` is sufficient; there is no token, and
none exists anywhere in the bundle. The gateway is doing origin-matching and
calling it an API key. Requests must therefore always carry _API_HEADERS.

Response:
    {"totalPages": int, "records": [ {...} ], "count": int, "sidePanelCounts", "limits"}

Query parameters (verified live):
    page       int    1-based
    pageSize   int
    category   str    "car"
    status     str    "active"
    search     str    free text — this is the make/model filter that works
    ct         str    city name, e.g. "Lahore"
    minP/maxP  int    price PKR
    minY/maxY  int    year
    sortBy     str    accepted but does not change ordering

    ⚠ mk / md — these expect NUMERIC make/model IDs. Passing a name
      ("mk=Toyota", "md=Corolla") does not error and does not filter: the
      backend hangs and the request times out after 75+ seconds. They are
      deliberately never sent by this module. Use `search` instead, which is
      fast (~1.3 s) and correctly narrows results.

Per-record fields used here:
    title, price (int PKR), modelYear, mileage (int km), city,
    images[].url (absolute S3 URLs), id, createdAt (ISO-8601)

Listing URL: https://autodeals.pk/used-cars/{title-slug}-{id}
(verified: the server prerenders the correct <title> and canonical for it)
"""
import re
from urllib.parse import parse_qs, urlparse

from models.car_schema import CarListing
from scrapers.date_utils import age_days_from_timestamp, is_unknown_age

API_URL = "https://api.autodeals.pk/flyers"
DETAIL_BASE = "https://autodeals.pk/used-cars/"

# The Origin header IS the credential — see module docstring.
_API_HEADERS = {
    "Origin":  "https://autodeals.pk",
    "Referer": "https://autodeals.pk/",
    "Accept":  "application/json, text/plain, */*",
}

MAX_ORGANIC_CARDS = 35
REQUEST_TIMEOUT = 30

# Path segments the runner encodes into the search URL, e.g.
#   /used-cars/search/-/ct_lahore/minP_0/maxP_5000000/searchStr_toyota-corolla
_SEGMENT_RE = re.compile(
    r'^(ct|rct|minP|maxP|minY|maxY|minM|maxM|searchStr|color|bodyT)_(.+)$'
)


def _slugify(text: str) -> str:
    return re.sub(r'[^a-z0-9]+', '-', (text or "").lower()).strip('-')


def _api_params_from_url(url: str) -> dict:
    """
    Translates the runner's autodeals.pk/used-cars/search/-/... URL into API
    parameters.

    The runner encodes filters as path segments (ct_lahore, minP_0,
    searchStr_toyota-corolla) with only `page` in the query string.
    """
    parsed = urlparse(url)
    params = {
        "category": "car",
        "status":   "active",
        "pageSize": MAX_ORGANIC_CARDS,
        "page":     1,
    }

    query = parse_qs(parsed.query)
    page_vals = query.get("page") or []
    if page_vals and str(page_vals[0]).isdigit():
        params["page"] = int(page_vals[0])

    numeric = {"minP", "maxP", "minY", "maxY", "minM", "maxM"}
    for segment in parsed.path.split('/'):
        match = _SEGMENT_RE.match(segment)
        if not match:
            continue
        key, value = match.group(1), match.group(2).strip()
        if not value:
            continue
        if key in numeric:
            if value.isdigit() and int(value) > 0:
                params[key] = int(value)
        elif key == "searchStr":
            # "toyota-corolla" (plus any trim slug the url_builder appended)
            # becomes a plain space-separated search phrase.
            params["search"] = value.replace('-', ' ').strip()
        else:
            params[key] = value.replace('-', ' ').strip()

    return params


def _build_listing(item: dict) -> CarListing | None:
    """Maps one API record onto a CarListing, or None when unusable."""
    title = (item.get("title") or "").strip()
    if not title or len(title) < 4:
        return None

    images = item.get("images") or []
    image_url = ""
    for img in images:
        if isinstance(img, dict):
            candidate = (img.get("url") or "").strip()
        elif isinstance(img, str):
            candidate = img.strip()
        else:
            continue
        if candidate.startswith("http"):
            image_url = candidate
            break

    ad_id = item.get("id")
    if ad_id:
        listing_url = f"{DETAIL_BASE}{_slugify(title)}-{ad_id}"
    else:
        listing_url = "https://autodeals.pk/used-cars"

    city = (item.get("city") or item.get("registerationCity") or "").strip() or "Unknown"

    return CarListing(
        title=title,
        price=item.get("price") or 0,
        mileage=item.get("mileage") or 0,
        city=city,
        year=item.get("modelYear") or 0,
        listing_url=listing_url,
        image_url=image_url,          # never None — the model requires str
        platform="AutoDeals",
        age_days=age_days_from_timestamp(item.get("createdAt")),
    )


async def scrape_auto_deals(url: str, session, search_filters: dict = None) -> list[CarListing]:
    """Scrapes AutoDeals through its public JSON API."""
    params = _api_params_from_url(url)

    try:
        response = await session.get(
            API_URL, params=params, headers=_API_HEADERS, timeout=REQUEST_TIMEOUT
        )
    except Exception as e:
        print(f"[AutoDeals Scraper] API request failed: {e}")
        return []

    if response.status_code == 403:
        # Almost certainly the Origin header was stripped or the gateway
        # tightened. Say so explicitly rather than reporting an empty search.
        print(
            "[AutoDeals Scraper] API HTTP 403 — origin rejected. "
            f"Body: {response.text[:120]}"
        )
        return []
    if response.status_code != 200:
        print(f"[AutoDeals Scraper] API HTTP {response.status_code} for params {params}")
        return []

    try:
        payload = response.json()
    except Exception as e:
        print(f"[AutoDeals Scraper] API returned non-JSON: {e}")
        return []

    records = payload.get("records")
    if not isinstance(records, list):
        print(f"[AutoDeals Scraper] Unexpected API shape, keys={list(payload)[:8]}")
        return []

    cars: list[CarListing] = []
    for item in records[:MAX_ORGANIC_CARDS]:
        if not isinstance(item, dict):
            continue
        try:
            listing = _build_listing(item)
        except Exception as e:
            print(f"[AutoDeals Scraper] Skipped malformed record: {e}")
            continue
        if listing:
            cars.append(listing)

    age_found = sum(1 for c in cars if not is_unknown_age(c.age_days))
    print(
        f"[AutoDeals Scraper] Extracted {len(cars)} listings via API "
        f"(matched {payload.get('count')} total). Age: {age_found}/{len(cars)} parsed."
    )
    return cars
