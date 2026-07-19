"""
scrapers/wise_wheels.py (WiseWheels.com.pk)

API INTERCEPTION REWRITE — DEBUG BUILD
Heavy instrumentation added to diagnose 0-listing root cause.

Known symptoms from logs:
  - API URL is hit successfully (no HTTP error printed)
  - Runner catches 'list' object has no attribute 'get' OUTSIDE this function
  - This means the crash is happening somewhere the runner passes `data` around,
    OR response.json() is returning a list and an old code path is calling .get() on it.

This build adds:
  1. Exact type() print before any interaction with `data`
  2. Raw 500-char JSON preview so we can see the actual envelope structure
  3. Full recursive key-map dump if data is a dict (up to 2 levels)
  4. Safe extraction with try/except around every .get() chain
  5. Per-item crash isolation with full traceback so no error is silently swallowed
  6. Final diagnostic summary line showing exactly how many items were found vs mapped vs skipped
"""
import json
import traceback
import urllib.parse
from models.car_schema import CarListing
from datetime import datetime, timezone

MAX_ORGANIC_CARDS = 40

STANDARD_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://wisewheels.com.pk/",
}


def _describe_structure(obj, prefix="", depth=0, max_depth=2):
    """
    Recursively prints the key/type structure of a dict or list
    up to max_depth levels. Helps map an unknown API envelope without
    printing the entire payload.
    """
    if depth > max_depth:
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, (dict, list)):
                print(f"[WiseWheels Structure]  {prefix}{k}: {type(v).__name__}(len={len(v)})")
                _describe_structure(v, prefix=prefix + "  ", depth=depth + 1, max_depth=max_depth)
            else:
                print(f"[WiseWheels Structure]  {prefix}{k}: {type(v).__name__} = {repr(v)[:80]}")
    elif isinstance(obj, list):
        print(f"[WiseWheels Structure]  {prefix}[list of {len(obj)} items]")
        if obj:
            print(f"[WiseWheels Structure]  {prefix}  [0] type: {type(obj[0]).__name__}")
            if isinstance(obj[0], dict):
                _describe_structure(obj[0], prefix=prefix + "    ", depth=depth + 1, max_depth=max_depth)


async def scrape_wise_wheels(url: str, session, search_filters: dict = None) -> list[CarListing]:

    # ── Step 1: Build API URL ──────────────────────────────────────────────────
    api_url = url.replace(
        "https://wisewheels.com.pk/used-cars",
        "https://api.wisewheels.com.pk/client/v1/used-cars/search"
    )
    print(f"[WiseWheels API] Intercepting: {api_url}")

    # ── Step 2: HTTP request ───────────────────────────────────────────────────
    try:
        response = await session.get(api_url, headers=STANDARD_HEADERS, timeout=15)
        print(f"[WiseWheels DEBUG] HTTP status: {response.status_code}")
        print(f"[WiseWheels DEBUG] Response Content-Type: {response.headers.get('content-type', 'NOT SET')}")

        if response.status_code != 200:
            print(f"[WiseWheels ❌] API HTTP Error: {response.status_code}")
            print(f"[WiseWheels DEBUG] Response body (first 500 chars): {response.text[:500]}")
            return []

        raw_text = response.text
        print(f"[WiseWheels DEBUG] Raw response length: {len(raw_text)} chars")
        print(f"[WiseWheels DEBUG] First 500 chars of raw JSON:\n{raw_text[:500]}\n{'─'*60}")

        data = response.json()

    except Exception as e:
        print(f"[WiseWheels ❌] HTTP/JSON parse failed: {e}")
        traceback.print_exc()
        return []

    # ── Step 3: Diagnose the top-level data shape ──────────────────────────────
    print(f"[WiseWheels DEBUG] Top-level type of `data`: {type(data).__name__}")

    if isinstance(data, list):
        print(f"[WiseWheels DEBUG] data IS a raw list. Length: {len(data)}")
        if data:
            print(f"[WiseWheels DEBUG] First element type: {type(data[0]).__name__}")
            if isinstance(data[0], dict):
                print(f"[WiseWheels DEBUG] First element keys: {list(data[0].keys())}")

    elif isinstance(data, dict):
        print(f"[WiseWheels DEBUG] data IS a dict. Top-level keys: {list(data.keys())}")
        print("[WiseWheels DEBUG] Full structure map (2 levels deep):")
        _describe_structure(data)

    else:
        print(f"[WiseWheels DEBUG] data is an unexpected type: {type(data)} — value: {repr(data)[:200]}")

    # ── Step 4: Safe item extraction (covers every known envelope pattern) ─────
    try:
        items = []

        if isinstance(data, list):
            # API returned a bare array — direct use
            items = data
            print(f"[WiseWheels DEBUG] Extraction path: bare list → {len(items)} items")

        elif isinstance(data, dict):
            # Try the most common nested patterns, log which one matched
            if isinstance(data.get('data'), dict) and isinstance(data['data'].get('items'), list):
                items = data['data']['items']
                print(f"[WiseWheels DEBUG] Extraction path: data.data.items → {len(items)} items")

            elif isinstance(data.get('data'), list):
                items = data['data']
                print(f"[WiseWheels DEBUG] Extraction path: data.data (list) → {len(items)} items")

            elif isinstance(data.get('items'), list):
                items = data['items']
                print(f"[WiseWheels DEBUG] Extraction path: data.items → {len(items)} items")

            elif isinstance(data.get('result'), list):
                items = data['result']
                print(f"[WiseWheels DEBUG] Extraction path: data.result → {len(items)} items")

            elif isinstance(data.get('listings'), list):
                items = data['listings']
                print(f"[WiseWheels DEBUG] Extraction path: data.listings → {len(items)} items")

            elif isinstance(data.get('cars'), list):
                items = data['cars']
                print(f"[WiseWheels DEBUG] Extraction path: data.cars → {len(items)} items")

            else:
                # Nothing matched — print all values' types to find the list
                print("[WiseWheels DEBUG] No known extraction path matched. Scanning all values for a list:")
                for k, v in data.items():
                    print(f"[WiseWheels DEBUG]   key='{k}' type={type(v).__name__} len={len(v) if hasattr(v, '__len__') else 'N/A'}")
                    if isinstance(v, list) and v:
                        print(f"[WiseWheels DEBUG]   ↳ Candidate! Using data['{k}'] as items.")
                        items = v
                        break

        else:
            print(f"[WiseWheels ❌] Unhandled data type: {type(data)}")
            return []

    except Exception as e:
        print(f"[WiseWheels ❌] Item extraction block crashed: {e}")
        traceback.print_exc()
        return []

    # ── Step 5: Validate items list ────────────────────────────────────────────
    if not items:
        print(f"[WiseWheels ❌] Extraction yielded 0 items after all path attempts.")
        # Print the full raw JSON (capped at 2000 chars) for manual inspection
        try:
            pretty = json.dumps(data, indent=2)[:2000]
            print(f"[WiseWheels DEBUG] Full payload preview (capped 2000 chars):\n{pretty}")
        except Exception:
            pass
        return []

    print(f"[WiseWheels API] Successfully fetched {len(items)} raw JSON items.")

    # ── Step 6: Schema discovery on first item ─────────────────────────────────
    if items and isinstance(items[0], dict):
        print(f"[WiseWheels Schema] First item keys: {list(items[0].keys())}")
        # Print the full first item so we know every field available
        try:
            print(f"[WiseWheels Schema] First item (full):\n{json.dumps(items[0], indent=2, default=str)[:1500]}")
        except Exception:
            print(f"[WiseWheels Schema] First item (repr): {repr(items[0])[:800]}")

    # ── Step 7: Map items → CarListing ────────────────────────────────────────
    cars = []
    skipped_no_data = 0
    skipped_crash = 0

    for idx, item in enumerate(items[:MAX_ORGANIC_CARDS]):
        try:
            if not isinstance(item, dict):
                print(f"[WiseWheels DEBUG] Item #{idx} is not a dict — type: {type(item).__name__}, skipping.")
                skipped_crash += 1
                continue

            # Title
            title = item.get('title') or item.get('name')
            if not title:
                make_raw = item.get('make', '')
                model_raw = item.get('model', '')
                variant_raw = item.get('variant', '')

                make = make_raw.get('name', '') if isinstance(make_raw, dict) else str(make_raw)
                model = model_raw.get('name', '') if isinstance(model_raw, dict) else str(model_raw)
                variant = variant_raw.get('name', '') if isinstance(variant_raw, dict) else str(variant_raw)
                title = f"{make} {model} {variant}".strip()

            if not title:
                print(f"[WiseWheels DEBUG] Item #{idx}: could not derive title, keys={list(item.keys())}")

            # Price
            price_raw = item.get('price') or item.get('price_pkr') or item.get('asking_price') or '0'
            price = str(price_raw)

            # Year & Mileage
            year = str(item.get('year') or item.get('model_year') or '0')
            mileage = str(item.get('mileage') or item.get('milage') or item.get('odometer') or '0')

            # City
            city = "Unknown"
            city_raw = item.get('city') or item.get('location')
            if isinstance(city_raw, dict):
                city = city_raw.get('name') or city_raw.get('title') or 'Unknown'
            elif isinstance(city_raw, str):
                city = city_raw

            # Listing URL
            slug = item.get('slug', '')
            ad_id = str(item.get('id') or item.get('ad_id') or item.get('listing_id') or '')

            if slug and ad_id:
                link = f"https://wisewheels.com.pk/used-cars/{slug}-AD-{ad_id}"
            elif slug:
                link = f"https://wisewheels.com.pk/used-cars/{slug}"
            else:
                link = item.get('url') or item.get('listing_url') or url

            # Image URL
            image_url = ''
            images = item.get('images') or item.get('media') or item.get('photos') or []
            if isinstance(images, list) and images:
                first_img = images[0]
                if isinstance(first_img, dict):
                    path = (
                        first_img.get('url') or
                        first_img.get('path') or
                        first_img.get('image_url') or
                        first_img.get('src') or ''
                    )
                    if path and not path.startswith('http'):
                        image_url = f"https://s3.ap-southeast-2.amazonaws.com/media.wisewheels/{path}"
                    else:
                        image_url = path
                elif isinstance(first_img, str):
                    image_url = first_img
            elif isinstance(images, str):
                image_url = images

            # Log image result for first 3 items to verify extraction
            if idx < 3:
                print(f"[WiseWheels DEBUG] Item #{idx} image_url resolved to: {image_url!r}")

            # Age
            age_days = 999
            created_at = item.get('created_at') or item.get('createdAt') or item.get('updated_at')
            if created_at:
                try:
                    dt_str = str(created_at).replace('Z', '+00:00')
                    dt = datetime.fromisoformat(dt_str)
                    delta = datetime.now(timezone.utc) - dt
                    age_days = max(0, delta.days)
                except Exception as age_err:
                    print(f"[WiseWheels DEBUG] Item #{idx} age parse failed for value={created_at!r}: {age_err}")

            # Skip bare skeletons with no useful data
            if price == '0' and year == '0':
                skipped_no_data += 1
                continue

            cars.append(CarListing(
                title=title or "Unknown",
                price=price,
                mileage=mileage,
                city=city,
                year=year,
                listing_url=link,
                image_url=image_url or None,
                platform='WiseWheels',
                age_days=age_days,
            ))

        except Exception as e:
            print(f"[WiseWheels ❌] Item #{idx} mapping crashed: {e}")
            traceback.print_exc()
            skipped_crash += 1
            continue

    # ── Step 8: Final diagnostic summary ──────────────────────────────────────
    print(
        f"[WiseWheels Scraper] Done. "
        f"raw={len(items)} | mapped={len(cars)} | "
        f"skipped_no_data={skipped_no_data} | skipped_crash={skipped_crash}"
    )
    return cars