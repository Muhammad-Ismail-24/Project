"""
scrapers/olx.py

FIX (this patch): Broken links + zero price/year/mileage/city on OLX listings.

ROOT CAUSE:
  The previous parser only checked ONE shallow JSON key path for each field
  (e.g. item['price']['display']) and never used the ready-made 'url' field
  OLX's own JSON already provides. Real OLX payloads commonly nest fields
  one level deeper than assumed:
    - price   -> item['price']['value']['display']  (not item['price']['display'])
    - url     -> item['url']  (a ready relative path — was NEVER checked before!)
    - location-> item['location']['city']['name']    (dict, not always a list)
    - params  -> item['params'] (not just 'parameters'/'main_info'), each param
                 has value nested under param['value']['label'] / ['key']

Because the link was being manufactured from a slugified title + numeric id
instead of using the real 'url' field, "View Ad" pointed to URLs that don't
exist on OLX -> "not found" pages, exactly matching the reported symptom.

This patch:
  1. Tries item['url'] FIRST (the real, guaranteed-correct link) before ever
     falling back to manual slug/id reconstruction.
  2. Widens price/year/mileage/city extraction to check every known nesting
     shape, shallow AND deep, in priority order.
  3. Adds a one-time raw-JSON debug dump of the FIRST hit whenever price/year
     /mileage all come back empty, so any remaining shape mismatch can be
     diagnosed directly from your terminal logs instead of guessing again.
"""
from bs4 import BeautifulSoup
import re
import json
from models.car_schema import CarListing

MAX_ORGANIC_CARDS = 35

STANDARD_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.google.com/",
    "Cache-Control": "no-cache",
}


def _dig(d, *keys, default=None):
    """Safely walk a nested dict path, returning `default` if anything along
    the way is missing or not a dict. Avoids a wall of `.get().get().get()`."""
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
        if cur is None:
            return default
    return cur if cur is not None else default


def _extract_price(item: dict) -> str:
    """Checks every known OLX price shape, shallow to deep, in priority order."""
    candidates = [
        _dig(item, "price", "value", "display"),
        _dig(item, "price", "value", "converted_value"),
        _dig(item, "price", "value", "value"),
        _dig(item, "price", "display"),
        _dig(item, "price", "value"),
        item.get("price") if isinstance(item.get("price"), (str, int, float)) else None,
        _dig(item, "priceLabel"),
    ]
    for c in candidates:
        if c not in (None, "", 0, "0"):
            return str(c)
    return "0"


def _extract_location(item: dict) -> str:
    """Checks every known OLX location shape: dict-of-dicts, list-of-dicts, or flat."""
    # Shape A: location -> city -> name  (most common current shape)
    city = _dig(item, "location", "city", "name")
    if city:
        return city

    # Shape B: location -> district/city as plain string
    city = _dig(item, "location", "city")
    if isinstance(city, str) and city:
        return city

    # Shape C: locations as a list of dicts with a 'level' field (older shape)
    loc_list = item.get("locations")
    if isinstance(loc_list, list):
        for loc in loc_list:
            if isinstance(loc, dict) and loc.get("level") == 2:
                name = loc.get("name")
                if name:
                    return name
        for loc in loc_list:
            if isinstance(loc, dict) and loc.get("name"):
                return loc["name"]

    # Shape D: a flat 'location' string
    flat = item.get("location")
    if isinstance(flat, str) and flat:
        return flat

    return "Unknown"


def _extract_year_and_mileage(item: dict) -> tuple[str, str]:
    """Checks every known OLX params/attributes shape for Year and Mileage."""
    year, mileage = "0", "0"

    for container_key in ("params", "parameters", "main_info", "attributes", "specs"):
        container = item.get(container_key)
        if not isinstance(container, list):
            continue

        for p in container:
            if not isinstance(p, dict):
                continue

            key_name = str(
                p.get("key") or p.get("name") or p.get("id") or ""
            ).lower()

            value = (
                _dig(p, "value", "label")
                or _dig(p, "value", "key")
                or p.get("value")
                or p.get("value_name")
                or p.get("displayValue")
                or ""
            )
            value = str(value)

            if "year" in key_name and year == "0":
                year = value
            elif ("mileage" in key_name or "km" in key_name) and mileage == "0":
                mileage = value

        if year != "0" or mileage != "0":
            break

    return year, mileage


def _extract_link(item: dict, title: str, fallback_url: str) -> str:
    """
    CRITICAL FIX: try the real 'url' field OLX provides FIRST.
    Only fall back to manual slug/id reconstruction if it's genuinely absent.
    """
    raw_url = item.get("url") or _dig(item, "urls", "mobile") or _dig(item, "urls", "desktop")
    if raw_url:
        if raw_url.startswith("http"):
            return raw_url
        return "https://www.olx.com.pk" + (raw_url if raw_url.startswith("/") else f"/{raw_url}")

    raw_id = str(item.get("id") or item.get("objectID") or "")
    item_id = re.sub(r"\D", "", raw_id)
    raw_slug = (
        item.get("slug")
        or re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        or "vehicle"
    )
    if len(item_id) > 7:
        return f"https://www.olx.com.pk/item/{raw_slug}-iid-{item_id}"

    return fallback_url


async def scrape_olx(url: str, session, search_filters: dict = None) -> list[CarListing]:
    """Scrapes OLX using a shared curl_cffi AsyncSession."""
    try:
        response = await session.get(url, headers=STANDARD_HEADERS, timeout=20)
        if response.status_code != 200:
            print(f"[OLX Scraper] HTTP {response.status_code} for {url}")
            return []
        html = response.text
    except Exception as e:
        print(f"[OLX Scraper] Request failed: {e}")
        return []

    if not html or len(html) < 500:
        print(f"[OLX Scraper] Response too short or empty for {url}")
        return []

    soup = BeautifulSoup(html, "html.parser")
    cars = []
    hits = []

    # ------------------------------------------------------------------ #
    # LAYER 1: JSON State Extraction
    # ------------------------------------------------------------------ #
    for s in soup.find_all("script"):
        content = s.string or ""
        if not content:
            continue

        match = re.search(r"window\.state\s*=\s*({.*?});\s*(?:window|$)", content, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(1))
                alg_hits = _dig(data, "algolia", "content", "hits", default=[])
                if alg_hits:
                    hits.extend(alg_hits)
                    break
            except Exception:
                pass

        if s.get("id") == "__NEXT_DATA__":
            try:
                data = json.loads(content)
                page_props = _dig(data, "props", "pageProps", default={})

                items_arr = _dig(page_props, "initialState", "listingSearch", "items", default=[])
                if items_arr:
                    hits.extend(items_arr)
                    break

                ad_list = _dig(page_props, "initialState", "listing", "adList", default=[])
                if ad_list:
                    hits.extend(ad_list)
                    break

                if not hits:
                    apollo = page_props.get("apolloState", {})
                    if apollo:
                        for k, v in apollo.items():
                            if not isinstance(v, dict):
                                continue
                            if v.get("__typename") != "Item" and not k.startswith("Item:"):
                                continue
                            if "title" not in v or "price" not in v:
                                continue
                            status = v.get("status", {})
                            if isinstance(status, dict) and status.get("display") not in (None, "ACTIVE"):
                                continue
                            if "id" not in v and k.startswith("Item:"):
                                v["id"] = k.split(":")[1]
                            hits.append(v)
                    if hits:
                        break

            except Exception:
                pass

    # ------------------------------------------------------------------ #
    # LAYER 2: Visual DOM Fallback
    # ------------------------------------------------------------------ #
    if not hits:
        print(f"[OLX Scraper] ⚠ JSON State missing for {url}. Attempting Visual DOM Fallback...")

        cards = soup.find_all("li", attrs={"data-aut-id": "itemBox"})
        if not cards:
            cards = soup.find_all("li", attrs={"aria-label": "Listing"})
        if not cards:
            cards = soup.find_all("article")

        if not cards:
            print(f"[OLX Scraper] ❌ DOM fallback also empty. Raw HTML (first 1000 chars):")
            print(html[:1000])
            return []

        for card in cards[:MAX_ORGANIC_CARDS]:
            try:
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

                loc_el = card.find(attrs={"data-aut-id": "item-location"}) or card.find(
                    attrs={"aria-label": "Location"}
                )
                city = loc_el.get_text(strip=True) if loc_el else "Unknown"

                cars.append(CarListing(
                    title=title, price=price, city=city, platform="OLX", listing_url=link
                ))
            except Exception:
                continue

        print(f"[OLX Scraper] DOM fallback extracted {len(cars)} listings")
        return cars

    # ------------------------------------------------------------------ #
    # LAYER 3: Parse hits from JSON state (hardened field extraction)
    # ------------------------------------------------------------------ #
    hits = hits[:MAX_ORGANIC_CARDS]

    debug_dumped = False

    for item in hits:
        try:
            title = item.get("title", "")
            if not title:
                continue

            price = _extract_price(item)
            year, mileage = _extract_year_and_mileage(item)
            city = _extract_location(item)
            link = _extract_link(item, title, fallback_url=url)

            if not debug_dumped and price == "0" and year == "0" and mileage == "0":
                debug_dumped = True
                print(f"[OLX Scraper] ⚠ All numeric fields empty for '{title}'. Raw item keys: {list(item.keys())}")
                print(f"[OLX Scraper] ⚠ Raw item sample (truncated): {json.dumps(item, default=str)[:800]}")

            cars.append(CarListing(
                title=title,
                price=price,
                mileage=mileage,
                city=city,
                year=year,
                listing_url=link,
                platform="OLX"
            ))
        except Exception:
            continue

    if not cars:
        print(f"[OLX Scraper] ❌ Parsed 0 listings from JSON hits. Raw HTML (first 1000 chars):")
        print(html[:1000])

    print(f"[OLX Scraper] Extracted {len(cars)} listings via Next.js JSON")
    return cars