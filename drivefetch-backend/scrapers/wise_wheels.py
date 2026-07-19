"""
scrapers/wise_wheels.py (WiseWheels.com.pk)

API INTERCEPTION — PRODUCTION BUILD

Root cause (diagnosed 2026-07-19):
  The WiseWheels API returns each listing with a `thumbnail` field
  (a direct S3 URL) rather than an `images[]` or `media[]` array.
  The old code searched for those arrays, found nothing, resolved
  image_url to '', passed `image_url or None` → None to CarListing,
  and Pydantic rejected it (image_url requires str, not NoneType).

  Fix: read `item['thumbnail']` directly.
  Fallback chain: thumbnail → '' (never None, keeps Pydantic happy).

Also confirmed from debug logs:
  - Envelope: {"dealer": null, "data": [...], "pagination": {...}}
  - city is a plain string (not a nested dict)
  - url field contains a ready-made relative path
  - price is already an integer (no lac conversion needed)
  - created_at is ISO 8601 with microseconds + Z suffix
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


async def scrape_wise_wheels(url: str, session, search_filters: dict = None) -> list[CarListing]:

    # Transform frontend search URL → backend API endpoint
    api_url = url.replace(
        "https://wisewheels.com.pk/used-cars",
        "https://api.wisewheels.com.pk/client/v1/used-cars/search"
    )

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

    print(f"[WiseWheels API] Fetched {len(items)} raw items.")

    cars = []

    for item in items[:MAX_ORGANIC_CARDS]:
        try:
            # ── Title ──────────────────────────────────────────────────────────
            title = (
                item.get("title") or
                item.get("title_full") or
                f"{item.get('make', '')} {item.get('model', '')}".strip() or
                "Unknown"
            )

            # ── Price ──────────────────────────────────────────────────────────
            # Already an integer in rupees (e.g. 4600000). Skip lac conversion.
            price_raw = item.get("price") or item.get("price_pkr") or 0
            price = str(price_raw)

            # ── Year & Mileage ─────────────────────────────────────────────────
            year = str(item.get("year") or item.get("model_year") or "0")
            mileage = str(item.get("mileage") or item.get("milage") or "0")

            # ── City ───────────────────────────────────────────────────────────
            # city is a plain string in this API (e.g. "Lahore")
            city_raw = item.get("city") or item.get("registered_city") or "Unknown"
            city = city_raw if isinstance(city_raw, str) else city_raw.get("name", "Unknown")

            # ── Listing URL ────────────────────────────────────────────────────
            # `url` field is already a valid relative path: /used-cars/slug-AD-id
            relative_url = item.get("url", "")
            if relative_url:
                link = f"https://wisewheels.com.pk{relative_url}"
            else:
                slug = item.get("slug", "")
                ad_id = str(item.get("id") or item.get("ad_id") or "")
                link = f"https://wisewheels.com.pk/used-cars/{slug}-AD-{ad_id}" if slug else url

            # ── Image URL ──────────────────────────────────────────────────────
            # The API provides `thumbnail` as a direct S3 URL — use it.
            # No images[] or media[] array exists in this response.
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

    print(f"[WiseWheels Scraper] Extracted {len(cars)} formatted listings from API.")
    return cars