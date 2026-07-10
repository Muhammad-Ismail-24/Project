"""
scrapers/olx.py

FIX (this patch): Price still returning 0 while year/mileage/city/link now
all work correctly (confirmed via live screenshot — real OLX ad opened
successfully showing "Rs 40 Lacs", 2015, correct city, but frontend showed
"PKR 0").

TWO ROOT CAUSES FOUND:

1. THE DEBUG DUMP NEVER FIRED FOR THIS CASE.
   The previous debug trigger only fired when price, year, AND mileage were
   ALL three simultaneously "0". Since year/mileage/city were fixed last
   patch, that three-way condition stopped being true — so the diagnostic
   dump silently never printed for the remaining price-only failure. This
   patch decouples the price debug trigger so it fires independently.

2. A REAL BUG IN `_deep_find()`.
   When `_deep_find` found a key whose name matched (e.g. a key literally
   named "value"), but that key's VALUE was itself another nested dict
   (not the final number), the old code returned that nested dict object
   directly — instead of continuing to recurse INTO it for the actual
   scalar leaf value. This meant a shape like:
     "price": {"value": {"value": 4000000, "currency": "PKR"}}
   would match the outer "value" key, see its value is a non-empty dict,
   and incorrectly treat the dict itself as "found" rather than digging
   one level deeper for the real number 4000000.

   Fixed: `_deep_find` now only accepts a match if the value at that key
   is a scalar (str/int/float). If the matching key's value is itself a
   dict/list, it explicitly recurses into THAT substructure next before
   falling back to a generic full-tree scan.
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
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
        if cur is None:
            return default
    return cur if cur is not None else default


def _deep_find(obj, key_substrings, _depth=0, _max_depth=6):
    """
    Recursively searches obj (dict/list, any nesting) for a key at any depth
    whose lowercased name contains any of `key_substrings`.

    FIXED BEHAVIOR: a match only counts if that key's value is itself a
    scalar (str/int/float). If the matching key's value is a nested
    dict/list instead, we recurse INTO that specific substructure next
    (higher priority than unrelated sibling keys), rather than incorrectly
    returning the container object itself as if it were the answer.
    """
    if _depth > _max_depth or obj is None:
        return None

    if isinstance(obj, dict):
        # Priority 1: a matching key whose value is already a scalar leaf.
        for k, v in obj.items():
            kl = str(k).lower()
            if any(sub in kl for sub in key_substrings):
                if isinstance(v, (str, int, float)) and v not in ("", 0, "0"):
                    return v

        # Priority 2: a matching key whose value is a nested dict/list —
        # recurse specifically into it before scanning unrelated siblings.
        for k, v in obj.items():
            kl = str(k).lower()
            if any(sub in kl for sub in key_substrings) and isinstance(v, (dict, list)):
                found = _deep_find(v, key_substrings, _depth + 1, _max_depth)
                if found not in (None, "", 0, "0"):
                    return found

        # Priority 3: generic recursive scan through every value regardless
        # of key name, as a final fallback.
        for v in obj.values():
            found = _deep_find(v, key_substrings, _depth + 1, _max_depth)
            if found not in (None, "", 0, "0"):
                return found

    elif isinstance(obj, list):
        for entry in obj:
            found = _deep_find(entry, key_substrings, _depth + 1, _max_depth)
            if found not in (None, "", 0, "0"):
                return found

    return None


def _extract_price(item: dict) -> str:
    """
    Price extraction using the fixed, shape-agnostic deep search.
    Tries human-readable display/formatted text first, then falls back to
    any plausible numeric field, at any nesting depth.
    """
    price_root = item.get("price")
    if price_root is None:
        return "0"

    if isinstance(price_root, (str, int, float)) and price_root not in ("", 0, "0"):
        return str(price_root)

    # Pass 1: prefer a human-readable display/formatted string
    for hint in ["display", "formatted", "label", "text"]:
        val = _deep_find(price_root, [hint])
        if val not in (None, "", 0, "0"):
            return str(val)

    # Pass 2: any plausible numeric price field, in priority order
    for hint in ["amount", "raw", "converted_value", "convertedvalue", "regularprice", "value"]:
        val = _deep_find(price_root, [hint])
        if val not in (None, "", 0, "0"):
            return str(val)

    return "0"


def _extract_year_and_mileage(item: dict) -> tuple[str, str]:
    year, mileage = "0", "0"
    container_keys = (
        "extraFields", "formattedExtraFields",
        "params", "parameters", "main_info", "attributes", "specs",
    )
    for container_key in container_keys:
        container = item.get(container_key)
        if not container:
            continue

        if isinstance(container, list):
            for p in container:
                if not isinstance(p, dict):
                    continue
                key_name = str(p.get("key") or p.get("name") or p.get("id") or "").lower()
                value = (
                    _dig(p, "value", "label")
                    or _dig(p, "value", "key")
                    or p.get("value")
                    or p.get("value_name")
                    or p.get("displayValue")
                    or p.get("label")
                    or ""
                )
                value = str(value)
                if "year" in key_name and year == "0":
                    year = value
                elif ("mileage" in key_name or "km" in key_name or "odometer" in key_name) and mileage == "0":
                    mileage = value

        elif isinstance(container, dict):
            for k, v in container.items():
                kl = str(k).lower()
                if "year" in kl and year == "0":
                    year = str(v)
                elif ("mileage" in kl or "km" in kl or "odometer" in kl) and mileage == "0":
                    mileage = str(v)

        if year != "0" or mileage != "0":
            break

    return year, mileage


def _extract_location(item: dict) -> str:
    loc = item.get("location")

    if isinstance(loc, dict):
        name = _dig(loc, "city", "name")
        if name:
            return name
        city_str = loc.get("city")
        if isinstance(city_str, str) and city_str:
            return city_str

    if isinstance(loc, list):
        for entry in loc:
            if isinstance(entry, dict) and entry.get("level") == 2:
                name = entry.get("name")
                if name:
                    return name
        for entry in loc:
            if isinstance(entry, dict) and entry.get("name"):
                return entry["name"]

    if isinstance(loc, str) and loc:
        return loc

    loc_list = item.get("locations")
    if isinstance(loc_list, list):
        for entry in loc_list:
            if isinstance(entry, dict) and entry.get("level") == 2:
                name = entry.get("name")
                if name:
                    return name
        for entry in loc_list:
            if isinstance(entry, dict) and entry.get("name"):
                return entry["name"]

    return "Unknown"


def _extract_link(item: dict, title: str, fallback_url: str) -> str:
    raw_url = item.get("url") or _dig(item, "urls", "mobile") or _dig(item, "urls", "desktop")
    if raw_url:
        if raw_url.startswith("http"):
            return raw_url
        return "https://www.olx.com.pk" + (raw_url if raw_url.startswith("/") else f"/{raw_url}")

    raw_id = str(item.get("externalID") or item.get("id") or item.get("objectID") or "")
    item_id = re.sub(r"\D", "", raw_id)

    raw_slug = (
        item.get("slug")
        or re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        or "vehicle"
    )

    if len(item_id) >= 6:
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

    hits = hits[:MAX_ORGANIC_CARDS]

    # Separate, INDEPENDENT one-time debug triggers per field — this is the
    # key fix so a price-only failure is no longer masked by year/mileage
    # having already succeeded.
    price_debug_dumped = False

    for item in hits:
        try:
            title = item.get("title", "")
            if not title:
                continue

            price = _extract_price(item)
            year, mileage = _extract_year_and_mileage(item)
            city = _extract_location(item)
            link = _extract_link(item, title, fallback_url=url)

            if not price_debug_dumped and price == "0":
                price_debug_dumped = True
                print(f"[OLX Scraper] ⚠ Price STILL '0' for '{title}'. Raw price subtree:")
                print(f"[OLX Scraper]   {json.dumps(item.get('price'), default=str)[:1200]}")

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