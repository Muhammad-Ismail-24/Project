"""
scrapers/olx.py

REBUILT against confirmed OLX Algolia hit structure.

IMAGE FIX:
  The CDN URL reconstruction from coverPhoto.externalID has been proven
  broken across 5+ tested URL patterns. 
  The fix maps <img> tags directly from the rendered HTML DOM to their 
  corresponding JSON hits using the exact external listing ID (-iid-).
  This guarantees 1-to-1 mapping and eliminates incorrect photo rendering.

KEY CONFIRMED FIELD PATHS (OLX Algolia hit):
  - Price:   hit['extraFields']['price']     (hit['price'] is always 0)
  - Year:    hit['extraFields']['year']
  - Mileage: hit['extraFields']['mileage']
  - City:    hit['location'] list, item where level == 2
  - URL:     https://www.olx.com.pk/item/{slug}-iid-{externalID}
  - Image:   <img> tag from DOM card matching the same ID
"""
from bs4 import BeautifulSoup
import re
import json
from urllib.parse import urlparse, urlunparse
from models.car_schema import CarListing

MAX_ORGANIC_CARDS = 35

STANDARD_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.google.com/",
    "Cache-Control": "no-cache",
}


# ------------------------------------------------------------------ #
# HELPERS
# ------------------------------------------------------------------ #

def _dig(d, *keys, default=None):
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
        if cur is None:
            return default
    return cur if cur is not None else default


def _strip_filter_and_sort(url: str) -> str:
    """Return a fallback URL with filter=/sorting= stripped out."""
    parsed = urlparse(url)
    query_pairs = [
        pair for pair in parsed.query.split("&")
        if pair
        and not pair.startswith("filter=")
        and not pair.startswith("sorting=")
    ]
    return urlunparse(parsed._replace(query="&".join(query_pairs)))


def _is_featured_ad(item: dict) -> bool:
    """
    Primary signal: top-level 'product' field == 'featured'.
    Secondary: 'activeProducts' contains a boost keyword.
    """
    if str(item.get("product", "")).lower() == "featured":
        return True

    active_products = item.get("activeProducts")
    if isinstance(active_products, dict) and active_products:
        boost_keywords = ("featured", "bump", "urgent", "top", "highlight", "premium")
        for k in active_products.keys():
            kl = str(k).lower()
            if "ad_limit" in kl:
                continue
            if any(kw in kl for kw in boost_keywords):
                return True

    return False


def _scrape_dom_images(soup: BeautifulSoup) -> dict:
    """
    Builds { listing_id: image_url } from <img> tags inside actual listing cards.
    Maps by exact unique ID instead of title to prevent collisions.
    """
    image_map = {}

    cards = soup.find_all("li", attrs={"data-aut-id": "itemBox"})
    if not cards:
        cards = soup.find_all("li", attrs={"aria-label": "Listing"})
    if not cards:
        cards = soup.find_all("article")

    for card in cards:
        try:
            # Extract unique ID from the href instead of the title
            a_tag = card.find("a", href=True)
            if not a_tag:
                continue
            
            href = a_tag["href"]
            match = re.search(r'-iid-(\d+)', href)
            if not match:
                continue
            
            listing_id = match.group(1)

            img_el = card.find("img")
            if not img_el:
                continue

            image_url = ""
            for attr in ("data-src", "data-original", "data-lazy-src", "src"):
                val = img_el.get(attr, "").strip()
                if val and val.startswith("http") and "placeholder" not in val.lower():
                    image_url = val
                    break

            if image_url:
                image_map[listing_id] = image_url

        except Exception:
            continue

    return image_map


def _parse_age_days(item) -> int:
    """
    Extracts listing age in days from an OLX DOM card.

    OLX displays relative time like "2 days ago", "1 week ago", "just now".
    Strategy:
      1. Look for an element with a time/date-related class or data-aut-id.
      2. Also check the HTML <time> tag (OLX sometimes uses it with datetime attr).
      3. Scan the full card text as broadest fallback.

    Returns:
      0   — posted today (minutes/hours/just now)
      N   — posted N days ago
      999 — could not detect age (normalizer scores this as stale = 0 pts)
    """
    # Strategy 1: data-aut-id attribute (OLX-specific)
    time_el = item.find(attrs={"data-aut-id": re.compile(r"(date|time|posted|ago)", re.I)})

    # Strategy 2: class-name match
    if not time_el:
        time_el = item.find(class_=re.compile(r"(ago|date|time|posted|fresh|listing.?date)", re.I))

    # Strategy 3: <time> HTML tag — check datetime attribute first
    if not time_el:
        time_el = item.find("time")

    time_text = ""
    if time_el:
        # If <time datetime="..."> is present, prefer that (ISO format)
        dt_attr = time_el.get("datetime", "")
        if dt_attr:
            from datetime import datetime, timezone
            try:
                posted = datetime.fromisoformat(dt_attr.replace("Z", "+00:00"))
                delta = datetime.now(timezone.utc) - posted
                return max(0, delta.days)
            except Exception:
                pass
        time_text = time_el.get_text(strip=True)

    # Strategy 4: full card text scan
    if not time_text:
        time_text = item.get_text(separator=" ")

    return _time_str_to_days(time_text)


def _time_str_to_days(text: str) -> int:
    """Converts a relative time string to an integer day count."""
    t = text.lower()

    if re.search(r"\b(minute|min|hour|hr|just now|today|moments?)\b", t):
        return 0
    if "yesterday" in t:
        return 1

    m = re.search(r"(\d+)\s*day", t)
    if m:
        return int(m.group(1))

    m = re.search(r"(\d+)\s*week", t)
    if m:
        return int(m.group(1)) * 7

    m = re.search(r"(\d+)\s*month", t)
    if m:
        return int(m.group(1)) * 30

    m = re.search(r"(\d+)\s*year", t)
    if m:
        return int(m.group(1)) * 365

    return 999  # unparseable → treated as stale by normalizer scorer


async def _fetch(session, url: str):
    try:
        response = await session.get(url, headers=STANDARD_HEADERS, timeout=20)
        return response.status_code, response.text
    except Exception as e:
        print(f"[OLX Scraper] Request failed: {e}")
        return None, None


def _extract_from_hit(item: dict, fallback_url: str, image_map: dict) -> CarListing | None:
    """
    Extracts a CarListing from one OLX Algolia hit.

    IMAGE STRATEGY (in priority order):
      1. Exact ID DOM lookup — always works when the page rendered properly.
      2. CDN reconstruction from coverPhoto.externalID — kept as last resort
         even though it has consistently failed, costs nothing to try.
      3. Empty string if both fail — better than crashing.
    """
    title = item.get("title", "")
    if not title:
        return None

    extra = item.get("extraFields") or {}

    # Price: real field is extraFields.price (hit['price'] is always 0)
    price = extra.get("price", 0)

    # Year and mileage: plain integers under extraFields
    year = extra.get("year", 0)
    mileage = extra.get("mileage", 0)

    # City: location list, level == 2 is the city
    city = "Unknown"
    for loc in item.get("location", []) or []:
        if isinstance(loc, dict) and loc.get("level") == 2:
            city = loc.get("name", "Unknown")
            break

    # Listing URL
    slug = item.get("slug", "")
    external_id = str(item.get("externalID", ""))
    
    if slug and external_id:
        listing_url = f"https://www.olx.com.pk/item/{slug}-iid-{external_id}"
    else:
        listing_url = fallback_url

    # ------------------------------------------------------------------ #
    # IMAGE: Exact ID DOM lookup first, CDN reconstruction as last resort
    # ------------------------------------------------------------------ #
    image_url = image_map.get(external_id, "")

    if not image_url:
        # Last-resort CDN reconstruction (consistently failed in testing,
        # but costs nothing to attempt)
        cover = item.get("coverPhoto")
        if isinstance(cover, dict):
            photo_id = cover.get("externalID", "")
            if photo_id:
                image_url = f"https://images.olx.com.pk/thumbnails/{photo_id}-featureimage.webp"

        if not image_url:
            photos = item.get("photos") or []
            if isinstance(photos, list) and photos:
                first = photos[0]
                if isinstance(first, dict):
                    photo_id = first.get("externalID", "")
                    if photo_id:
                        image_url = f"https://images.olx.com.pk/thumbnails/{photo_id}-featureimage.webp"
                elif isinstance(first, str) and first.startswith("http"):
                    image_url = first

    # Age in days — OLX JSON hits carry a unix timestamp in 'createdAt'
    age_days = 999
    created_at = item.get("createdAt") or item.get("date") or item.get("activated_at")
    if created_at:
        try:
            from datetime import datetime, timezone
            posted = datetime.fromtimestamp(int(created_at), tz=timezone.utc)
            delta = datetime.now(timezone.utc) - posted
            age_days = max(0, delta.days)
        except Exception:
            age_days = 999

    return CarListing(
        title=title,
        price=str(price),
        mileage=str(mileage),
        city=city,
        year=str(year),
        listing_url=listing_url,
        image_url=image_url or None,
        platform="OLX",
        age_days=age_days,
    )


# ------------------------------------------------------------------ #
# MAIN SCRAPER
# ------------------------------------------------------------------ #

async def scrape_olx(url: str, session, search_filters: dict = None) -> list[CarListing]:
    status_code, html = await _fetch(session, url)

    if status_code == 404:
        fallback_url = _strip_filter_and_sort(url)
        if fallback_url != url:
            print(f"[OLX Scraper] ⚠ 404 on rich URL. Retrying stripped fallback: {fallback_url}")
            status_code, html = await _fetch(session, fallback_url)

    if status_code != 200:
        print(f"[OLX Scraper] HTTP {status_code} for {url}")
        return []

    if not html or len(html) < 500:
        return []

    soup = BeautifulSoup(html, "html.parser")
    cars = []
    hits = []
    source = None

    # ------------------------------------------------------------------ #
    # BUILD DOM IMAGE MAP FIRST — before we process JSON hits
    # This scans the actual rendered <img> tags in the HTML once, builds
    # a lookup table, and then every hit in Layer 3 uses it for free.
    # ------------------------------------------------------------------ #
    image_map = _scrape_dom_images(soup)
    print(f"[OLX Scraper] DOM image map: {len(image_map)} entries scraped from HTML cards.")

    # ------------------------------------------------------------------ #
    # LAYER 1: JSON State Extraction
    # ------------------------------------------------------------------ #
    for s in soup.find_all("script"):
        content = s.string or ""
        if not content:
            continue

        # Path A: window.state
        match = re.search(r"window\.state\s*=\s*({.*?});\s*(?:window|$)", content, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(1))
                alg_hits = _dig(data, "algolia", "content", "hits", default=[])
                if alg_hits:
                    hits.extend(alg_hits)
                    source = "window.state"
                    break
            except Exception:
                pass

        # Path B: __NEXT_DATA__
        if s.get("id") == "__NEXT_DATA__":
            try:
                data = json.loads(content)
                page_props = _dig(data, "props", "pageProps", default={})

                items_arr = _dig(page_props, "initialState", "listingSearch", "items", default=[])
                if items_arr:
                    hits.extend(items_arr)
                    source = "__NEXT_DATA__.listingSearch"
                    break

                ad_list = _dig(page_props, "initialState", "listing", "adList", default=[])
                if ad_list:
                    hits.extend(ad_list)
                    source = "__NEXT_DATA__.adList"
                    break

            except Exception:
                pass

    # ------------------------------------------------------------------ #
    # LAYER 2: Visual DOM Fallback (when JSON found nothing)
    # ------------------------------------------------------------------ #
    if not hits:
        print(
            f"[OLX Scraper] ⚠ JSON state missing for {url}. "
            f"Using Visual DOM Fallback."
        )
        cards = soup.find_all("li", attrs={"data-aut-id": "itemBox"})
        if not cards:
            cards = soup.find_all("li", attrs={"aria-label": "Listing"})
        if not cards:
            cards = soup.find_all("article")

        if not cards:
            print(f"[OLX Scraper] ❌ DOM fallback also empty. Raw HTML (first 1000 chars):\n{html[:1000]}")
            return []

        for card in cards:
            if len(cars) >= MAX_ORGANIC_CARDS:
                break
            try:
                badge = (
                    card.find(attrs={"aria-label": "Featured"})
                    or card.find(attrs={"data-aut-id": "featured"})
                    or card.find(string=re.compile(r"Featured", re.I))
                )
                if badge:
                    continue

                title_el = (
                    card.find(attrs={"data-aut-id": "itemTitle"})
                    or card.find("h2")
                    or card.find("a")
                )
                title = title_el.get_text(strip=True) if title_el else ""
                if not title:
                    continue

                a_tag = card.find("a", href=True)
                link = (
                    "https://www.olx.com.pk" + a_tag["href"]
                    if a_tag and not a_tag["href"].startswith("http")
                    else (a_tag["href"] if a_tag else url)
                )

                price_el = (
                    card.find(attrs={"data-aut-id": "itemPrice"})
                    or card.find(class_=re.compile(r"price", re.I))
                    or card.find(attrs={"aria-label": "Price"})
                )
                price = price_el.get_text(strip=True) if price_el else "0"

                loc_el = (
                    card.find(attrs={"data-aut-id": "item-location"})
                    or card.find(attrs={"aria-label": "Location"})
                )
                city = loc_el.get_text(strip=True) if loc_el else "Unknown"

                # ID Extraction for exact map lookup
                listing_id = ""
                match = re.search(r'-iid-(\d+)', link)
                if match:
                    listing_id = match.group(1)

                image_url = image_map.get(listing_id, "")

                cars.append(CarListing(
                    title=title,
                    price=price,
                    city=city,
                    image_url=image_url or None,
                    platform="OLX",
                    listing_url=link,
                    age_days=_parse_age_days(card),
                ))
            except Exception:
                continue

        print(f"[OLX Scraper] DOM fallback extracted {len(cars)} listings")
        return cars

    # ------------------------------------------------------------------ #
    # LAYER 3: Parse hits from confirmed-shape JSON
    # ------------------------------------------------------------------ #
    print(f"[OLX Scraper] Using JSON source: {source} ({len(hits)} raw hits)")

    featured_items = []
    organic_items = []
    for item in hits:
        try:
            (featured_items if _is_featured_ad(item) else organic_items).append(item)
        except Exception:
            continue

    # Prefer organic-only, but if that would give 0 results (over-broad
    # featured detection), fall back to all hits rather than returning nothing
    if organic_items:
        ordered_items = organic_items
        skipped_count = len(featured_items)
    else:
        print(
            f"[OLX Scraper] ⚠ All {len(featured_items)} hits flagged as featured — "
            f"looks like over-broad detection. Including them rather than returning 0."
        )
        ordered_items = featured_items
        skipped_count = 0

    for item in ordered_items:
        if len(cars) >= MAX_ORGANIC_CARDS:
            break
        try:
            # image_map is passed in — _extract_from_hit does the DOM
            # lookup internally, with CDN reconstruction as last resort
            listing = _extract_from_hit(item, fallback_url=url, image_map=image_map)
            if listing:
                cars.append(listing)
        except Exception:
            continue

    if skipped_count > 0:
        print(f"[OLX Scraper] Skipped {skipped_count} featured/boosted ads.")

    # Debug: report image and age hit rates
    with_images = sum(1 for c in cars if c.image_url)
    age_found = sum(1 for c in cars if c.age_days != 999)
    print(
        f"[OLX Scraper] Extracted {len(cars)} listings via {source} "
        f"({with_images}/{len(cars)} with images, "
        f"Age: {age_found}/{len(cars)} parsed)."
    )

    if not cars:
        print(f"[OLX Scraper] ❌ 0 listings. Raw HTML (first 1000 chars):\n{html[:1000]}")

    return cars