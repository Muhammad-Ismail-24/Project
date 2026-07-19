"""
scrapers/wise_wheels.py (WiseWheels.com.pk)

API INTERCEPTION — v2 PRODUCTION BUILD

Fixes applied 2026-07-19:
  1. image_url: read `thumbnail` directly (flat S3 URL in API response).
     Old code searched for images[]/media[] which don't exist → None → Pydantic crash.

  2. City post-filter: WiseWheels API returns nationwide results regardless of
     city_id parameter (confirmed from logs — city_id=257 returned Lahore listings).
     Solution: after extraction, filter by requested city using the `city` string
     in each item. Accepts both exact match and the twin-city expansion
     ("Islamabad and Rawalpindi" → accept Islamabad OR Rawalpindi).

  3. price is already full rupees integer (e.g. 4600000) — no lac conversion needed.

  4. `url` field is a ready-made relative path — just prepend domain.
"""
from models.car_schema import CarListing
from datetime import datetime, timezone

MAX_ORGANIC_CARDS = 40

STANDARD_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://wisewheels.com.pk/",
}

# Maps twin-city search strings → list of city names to accept
# Keeps WiseWheels city post-filter in sync with orchestrator twin-city logic
TWIN_CITY_MAP = {
    "islamabad and rawalpindi": ["islamabad", "rawalpindi"],
    "rawalpindi and islamabad": ["islamabad", "rawalpindi"],
    "lahore":                   ["lahore"],
    "karachi":                  ["karachi"],
    "islamabad":                ["islamabad"],
    "rawalpindi":               ["rawalpindi"],
}


def _city_matches(item_city: str, requested_city: str) -> bool:
    """
    Returns True if the listing's city is acceptable for the requested city.
    requested_city comes from the runner (lowercased search string).
    item_city comes directly from the API response.
    """
    if not requested_city:
        return True  # no city filter requested

    item_city_lower = item_city.lower().strip()
    requested_lower = requested_city.lower().strip()

    # Check twin-city map first
    accepted = TWIN_CITY_MAP.get(requested_lower)
    if accepted:
        return item_city_lower in accepted

    # Fallback: simple substring match
    return requested_lower in item_city_lower or item_city_lower in requested_lower


async def scrape_wise_wheels(url: str, session, search_filters: dict = None) -> list[CarListing]:

    # Transform frontend search URL → backend API endpoint
    api_url = url.replace(
        "https://wisewheels.com.pk/used-cars",
        "https://api.wisewheels.com.pk/client/v1/used-cars/search"
    )

    # Extract requested city from search_filters for post-filtering
    requested_city = ""
    if search_filters:
        requested_city = (search_filters.get("city") or "").strip()

    try:
        print(f"[WiseWheels API] Intercepting: {api_url}")
        response = await session.get(api_url, headers=STANDARD_HEADERS, timeout=15)

        if response.status_code != 200:
            print(f"[WiseWheels ❌] HTTP {response.status_code} for {api_url}")
            return []

        data = response.json()

    except Exception as e:
        print(f"[WiseWheels ❌] Request/parse failed: {e}")
        return []

    # Envelope: {"dealer": null, "data": [...20 items...], "pagination": {...}}
    if not isinstance(data, dict):
        print(f"[WiseWheels ❌] Unexpected top-level type: {type(data).__name__}")
        return []

    items = data.get("data", [])

    if not isinstance(items, list) or not items:
        print(f"[WiseWheels ❌] No items in response. Keys: {list(data.keys())}")
        return []

    cars = []
    skipped_city = 0

    for item in items[:MAX_ORGANIC_CARDS]:
        try:
            # ── City ───────────────────────────────────────────────────────────
            # city is a plain string in the API (e.g. "Lahore", "Islamabad")
            city_raw = item.get("city") or item.get("registered_city") or "Unknown"
            city = city_raw if isinstance(city_raw, str) else city_raw.get("name", "Unknown")

            # Post-filter: WiseWheels API ignores city_id — filter manually
            if requested_city and not _city_matches(city, requested_city):
                skipped_city += 1
                continue

            # ── Title ──────────────────────────────────────────────────────────
            title = (
                item.get("title") or
                item.get("title_full") or
                f"{item.get('make', '')} {item.get('model', '')}".strip() or
                "Unknown"
            )

            # ── Price ──────────────────────────────────────────────────────────
            # Already an integer in rupees (e.g. 4600000). No lac conversion.
            price_raw = item.get("price") or item.get("price_pkr") or 0
            price = str(price_raw)

            # ── Year & Mileage ─────────────────────────────────────────────────
            year = str(item.get("year") or item.get("model_year") or "0")
            mileage = str(item.get("mileage") or item.get("milage") or "0")

            # ── Listing URL ────────────────────────────────────────────────────
            # `url` field is a ready-made relative path: /used-cars/slug-AD-id
            relative_url = item.get("url", "")
            if relative_url:
                link = f"https://wisewheels.com.pk{relative_url}"
            else:
                slug = item.get("slug", "")
                ad_id = str(item.get("id") or item.get("ad_id") or "")
                link = f"https://wisewheels.com.pk/used-cars/{slug}-AD-{ad_id}" if slug else url

            # ── Image URL ──────────────────────────────────────────────────────
            # API provides `thumbnail` as a direct full S3 URL.
            # No images[]/media[] array exists in the search response.
            image_url = item.get("thumbnail") or ""

            # ── Age ────────────────────────────────────────────────────────────
            age_days = 999
            created_at = item.get("created_at") or item.get("updated_at")
            if created_at:
                try:
                    dt = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
                    age_days = max(0, (datetime.now(timezone.utc) - dt).days)
                except Exception:
                    pass

            # Skip bare skeletons with no useful data
            if price == "0" and year == "0":
                continue

            cars.append(CarListing(
                title=title,
                price=price,
                mileage=mileage,
                city=city,
                year=year,
                listing_url=link,
                image_url=image_url,   # always str, never None
                platform="WiseWheels",
                age_days=age_days,
            ))

        except Exception as e:
            print(f"[WiseWheels Mapping Error] {e}")
            continue

    print(
        f"[WiseWheels Scraper] Extracted {len(cars)} formatted listings from API. "
        f"(city-filtered: {skipped_city} skipped)"
    )
    return cars