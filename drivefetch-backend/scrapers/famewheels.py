from core.logger import get_logger
logger = get_logger(__name__)
"""
scrapers/famewheels.py

REBUILT 2026-08-16 — HTML parsing replaced by the site's own JSON API.

WHY
---
famewheels.com is a Next.js App Router site. Its /used-cars page server-renders
only MUI *skeleton loaders* — 15 `.MuiCard-root` placeholders with no text —
and hydrates the real listings client-side. The old scraper looked for
`.car-card` / `.listing` / `.col-md-4`, matched nothing, and returned [] every
time. (A `class~=card` selector does match, but only the empty skeletons, so
"found cards" here is a trap: they parse to blank titles.)

The RSC flight payload carries no listing data either. The page fetches from:

    GET https://bcknd.famewheels.com/newwebfilterpost?user_id=0&page=N

Response (Laravel paginator):
    {"posts": {"current_page", "data": [ {...} ], "last_page", "total", ...}}
    30 records per page, verified non-overlapping across pages.

FILTERING — none server-side
----------------------------
Only `body_type[]` narrows results. make / model / city / search parameters are
accepted and silently ignored (total stays at the unfiltered count), and
`makeName` triggers a Laravel 500. So this module pages through the newest
listings and filters on make/model in Python. Records are returned newest-first,
which is what we want anyway: the staleness veto would reject deep pages.

Per-record fields used here:
    post_title, makeName, modelName, yearName, feature_name (variant),
    price (int PKR), milage (int km — note the platform's spelling),
    city_name, cover + post_token (image), post_id, added_date / created_at

Image URL:   https://d2nn1d293raok6.cloudfront.net/public/posts/{post_token}/{cover}
Listing URL: https://www.famewheels.com/vehicle-details/{make}-{model}-{year}-for-sale-in-{city}/{post_id}
"""
import re
from urllib.parse import parse_qs, urlparse

from models.car_schema import CarListing
from scrapers.date_utils import age_days_from_timestamp, is_unknown_age

API_URL = "https://bcknd.famewheels.com/newwebfilterpost"
IMAGE_BASE = "https://d2nn1d293raok6.cloudfront.net/public/posts"
DETAIL_BASE = "https://www.famewheels.com/vehicle-details"

MAX_ORGANIC_CARDS = 35
REQUEST_TIMEOUT = 30

# The API has no make/model filter, so we walk the newest pages and match in
# Python. Three pages (~90 listings) is enough to find inventory for a common
# make/model without turning one search into a crawl.
MAX_PAGES = 3


# post_title is mostly unusable. On a sampled page, 26 of 30 records stored the
# literal placeholder string "title" (or null) instead of a headline, and the
# few real ones carry raw JSX artefacts: "Honda BR-V{' '}\n                2017".
# The structured makeName / modelName / yearName / feature_name fields are
# always populated and are the trustworthy source of identity.
_PLACEHOLDER_TITLES = {"", "title", "post title", "null", "none", "n/a", "-"}


def _clean_title(raw: str) -> str:
    """Strips JSX artefacts and collapses whitespace in a raw post_title."""
    text = (raw or "").replace("{' '}", " ").replace('{" "}', " ")
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def _is_placeholder(title: str) -> bool:
    return title.strip().lower() in _PLACEHOLDER_TITLES


def _compose_title(make: str, model: str, variant: str, year: str) -> str:
    """
    Builds a normalizer-friendly headline from the structured fields:
        "Toyota Corolla Cross 1.8 HEV X 2024"

    Sellers often repeat the make and model inside feature_name
    ("toyota Prado TX L Package 2.7"), so redundant leading tokens are dropped
    to keep the identity scorer from matching the same word twice.
    """
    parts = [p for p in (make.strip(), model.strip()) if p]

    variant = (variant or "").strip()
    if variant:
        lowered = variant.lower()
        for known in (make.lower(), model.lower()):
            if known and lowered.startswith(known):
                variant = variant[len(known):].strip(" -")
                lowered = variant.lower()
        # Drop a variant that is just a restatement of the model.
        if variant and variant.lower() not in (model.lower(), make.lower()):
            parts.append(variant)

    if year:
        parts.append(str(year).strip())

    return re.sub(r'\s+', ' ', " ".join(parts)).strip()


def _wanted_from_url(url: str) -> tuple[str, str, str]:
    """Pulls make / model / city out of the runner's famewheels URL."""
    query = parse_qs(urlparse(url).query)

    def one(key: str) -> str:
        vals = query.get(key) or []
        return (vals[0] or "").strip().lower().replace('-', ' ') if vals else ""

    return one("make"), one("model"), one("city")


def _matches(item: dict, want_make: str, want_model: str) -> bool:
    """
    Client-side make/model gate.

    Deliberately permissive — it only has to cut the obvious noise, because
    normalizer.py runs a full identity score afterwards. Being too strict here
    would discard listings the normalizer would have accepted.
    """
    if want_make:
        make = (item.get("makeName") or "").lower()
        if want_make not in make and make not in want_make:
            return False

    if want_model:
        haystack = " ".join(str(item.get(k) or "") for k in
                            ("modelName", "post_title", "feature_name")).lower()
        # Match on the leading token so "corolla altis" still finds "Corolla".
        root = want_model.split()[0] if want_model.split() else want_model
        if root and root not in haystack:
            return False

    return True


def _build_listing(item: dict) -> CarListing | None:
    """Maps one API record onto a CarListing, or None when unusable."""
    make = (item.get("makeName") or "").strip()
    model = (item.get("modelName") or "").strip()
    year = str(item.get("yearName") or "").strip()
    variant = (item.get("feature_name") or "").strip()

    # The structured fields are the primary source — post_title is a
    # placeholder on the large majority of records (see _PLACEHOLDER_TITLES).
    title = _compose_title(make, model, variant, year)

    if not title:
        # No structured identity either; fall back to whatever the seller typed.
        raw = _clean_title(item.get("post_title"))
        title = "" if _is_placeholder(raw) else raw

    if not title or len(title) < 4:
        return None

    post_token = (item.get("post_token") or "").strip()
    cover = (item.get("cover") or "").strip()
    image_url = f"{IMAGE_BASE}/{post_token}/{cover}" if post_token and cover else ""

    city = (item.get("city_name") or "").strip() or "Unknown"

    post_id = item.get("post_id")
    if post_id:
        slug = re.sub(
            r'[^a-zA-Z0-9]+', '-',
            f"{make}-{model}-{year}-for-sale-in-{city}"
        ).strip('-')
        listing_url = f"{DETAIL_BASE}/{slug}/{post_id}"
    else:
        listing_url = "https://www.famewheels.com/used-cars"

    # added_date and created_at are both "YYYY-MM-DD HH:MM:SS" and agree;
    # added_date is the field the site itself displays.
    age_days = age_days_from_timestamp(
        item.get("added_date") or item.get("created_at")
    )

    return CarListing(
        title=title,
        price=item.get("price") or 0,
        mileage=item.get("milage") or 0,      # platform spells it "milage"
        city=city,
        year=year or 0,
        listing_url=listing_url,
        image_url=image_url,                  # never None — the model requires str
        platform="Famewheels",
        age_days=age_days,
    )


async def _fetch_page(session, page: int) -> list[dict]:
    """Returns one page of raw records, or [] on any failure."""
    try:
        response = await session.get(
            API_URL, params={"user_id": 0, "page": page}, timeout=REQUEST_TIMEOUT
        )
    except Exception as e:
        logger.error(f"[FameWheels Scraper] API request failed (page {page}, exc_info=True): {e}")
        return []

    if response.status_code != 200:
        logger.info(f"[FameWheels Scraper] API HTTP {response.status_code} (page {page})")
        return []

    try:
        payload = response.json()
    except Exception as e:
        logger.info(f"[FameWheels Scraper] API returned non-JSON (page {page}): {e}")
        return []

    posts = payload.get("posts")
    if isinstance(posts, dict):
        data = posts.get("data")
        return data if isinstance(data, list) else []
    if isinstance(posts, list):
        return posts

    logger.info(f"[FameWheels Scraper] Unexpected API shape, keys={list(payload)[:8]}")
    return []


async def scrape_famewheels(url: str, session) -> list[CarListing]:
    """Scrapes FameWheels through its public JSON API."""
    want_make, want_model, _want_city = _wanted_from_url(url)

    cars: list[CarListing] = []
    scanned = 0
    seen_ids: set = set()

    for page in range(1, MAX_PAGES + 1):
        records = await _fetch_page(session, page)
        if not records:
            break

        for item in records:
            if not isinstance(item, dict):
                continue
            post_id = item.get("post_id")
            if post_id in seen_ids:
                continue
            seen_ids.add(post_id)
            scanned += 1

            if not _matches(item, want_make, want_model):
                continue
            try:
                listing = _build_listing(item)
            except Exception as e:
                logger.info(f"[FameWheels Scraper] Skipped malformed record: {e}")
                continue
            if listing:
                cars.append(listing)

        if len(cars) >= MAX_ORGANIC_CARDS:
            break

    cars = cars[:MAX_ORGANIC_CARDS]
    age_found = sum(1 for c in cars if not is_unknown_age(c.age_days))
    logger.info(
        f"[FameWheels Scraper] Extracted {len(cars)} listings via API "
        f"(scanned {scanned} across {min(page, MAX_PAGES)} page(s), "
        f"filter make={want_make or '-'} model={want_model or '-'}). "
        f"Age: {age_found}/{len(cars)} parsed."
    )
    return cars
