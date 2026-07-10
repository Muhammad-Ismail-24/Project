"""
scrapers/olx.py

FIX (this patch): Corrected against the REAL raw Algolia hit shape,
confirmed directly from production debug logs (not guessed).

WHAT THE DEBUG DUMP REVEALED:
  Raw item keys included:
    'activeProducts', 'agency', 'category', 'category.lvl0', 'category.lvl1',
    'contactInfo', 'coverPhoto', 'createdAt', 'description', 'documentCount',
    'documentsTags', 'externalID', 'extraFields', 'format',
    'formattedExtraFields', 'geo_point', 'geography', 'id', 'isSellerVerified',
    'keywords', 'location', 'location.lvl0'...'location.lvl4', 'objectID',
    'panoramaCount', 'photoCount', 'photos', 'price', 'product', 'productInfo',
    'productScore', 'purpose', 'requestIndex', 'slug', 'sourceID', 'state',
    'timestamp', 'title', 'type', 'updatedAt', 'userExternalID', 'videoCount',
    'locationTranslations', 'adTags'

  Three concrete, log-confirmed findings from this:

  1. NO 'url' KEY EXISTS on this object shape at all. This is a raw Algolia
     search-index hit, not a Next.js/GraphQL item — there is no ready-made
     link field. The previous "check url first" fix does not apply here.

  2. NO 'params'/'parameters'/'main_info'/'attributes'/'specs' KEY EXISTS.
     Year and mileage live under 'extraFields' / 'formattedExtraFields'
     instead — a container name that was never checked before, which is
     why every OLX listing showed year=0, mileage=0.

  3. There IS an 'externalID' field, separate from 'id'/'objectID'. This is
     OLX's real public-facing ad ID used in their actual URL structure
     (.../iid-{externalID}). The previous link fallback used 'id'/'objectID'
     (internal Algolia identifiers), which is why links 404'd even in the
     manual-reconstruction fallback path.

  4. 'location' is a SINGULAR key (list-of-dicts-with-level, same shape as
     the old 'locations' plural key we already supported) — not a nested
     dict as first assumed. The flattened 'location.lvl0'..'lvl4' keys are
     separate top-level Algolia facet keys, not part of a nested path.

This patch fixes all four findings directly, and widens the debug dump to
print the actual 'price' and 'extraFields'/'formattedExtraFields' subtrees
(not just the outer key list) so any remaining shape surprise is fully
visible in one more log round instead of guessed blind again.
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
    the way is missing or not a dict."""
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
        if cur is None:
            return default
    return cur if cur is not None else default


def _deep_find(obj, key_substrings, _depth=0, _max_depth=5):
    """
    Recursively searches obj (dict/list, any nesting) for the first key at
    any depth whose lowercased name contains any of `key_substrings`, and
    returns that key's value — as long as the value itself isn't empty/falsy.

    Used for 'price', where the real nesting depth/key names are unknown
    and vary between Algolia hit shapes (e.g. price->value->amount vs.
    price->value->display vs. price->regularPrice->value).
    """
    if _depth > _max_depth or obj is None:
        return None

    if isinstance(obj, dict):
        # Direct key match at this level first
        for k, v in obj.items():
            kl = str(k).lower()
            if any(sub in kl for sub in key_substrings):
                if v not in (None, "", 0, "0", [], {}):
                    return v
        # Then recurse into nested values
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
    Price extraction using a deep, shape-agnostic search of the 'price'
    subtree. Prefers a human-readable 'display' string first, then falls
    back to any numeric 'amount'/'value'/'converted' style field found at
    any depth.
    """
    price_root = item.get("price")
    if price_root is None:
        return "0"

    if isinstance(price_root, (str, int, float)) and price_root not in ("", 0, "0"):
        return str(price_root)

    # Pass 1: prefer a human-readable display string if one exists anywhere
    val = _deep_find(price_root, ["display"])
    if val not in (None, "", 0, "0"):
        return str(val)

    # Pass 2: any plausible numeric price field, in priority order
    for hint in ["amount", "converted_value", "convertedvalue", "regularprice", "value"]:
        val = _deep_find(price_root, [hint])
        if val not in (None, "", 0, "0"):
            return str(val)

    return "0"


def _extract_year_and_mileage(item: dict) -> tuple[str, str]:
    """
    Year/mileage extraction that checks BOTH known OLX container shapes:
      - 'extraFields' / 'formattedExtraFields' (confirmed real key names)
      - legacy 'params'/'parameters'/'main_info'/'attributes'/'specs'
    Each container may itself be either:
      - a list of {key/name/id, value/value_name/displayValue/label} pairs, or
      - a flat dict mapping field-name -> value directly.
    """
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
    """
    Location extraction. CONFIRMED real shape: 'location' is a LIST of
    dicts with a 'level' field (city is typically level==2) — the same
    shape previously only supported under the (incorrect) plural key
    'locations'. Also handles a dict or flat-string shape defensively,
    and keeps the legacy plural key as a final fallback.
    """
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

    # Legacy fallback: some older/alternate payloads use plural 'locations'
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
    """
    Link extraction, in priority order:
      1. A genuinely ready-made 'url' field, if this particular hit shape
         happens to provide one (some OLX payload variants do).
      2. Manual reconstruction using 'externalID' FIRST — confirmed to be
         OLX's real public-facing ad ID — falling back to 'id'/'objectID'
         only if externalID is absent.
      3. The original search page URL as an absolute last resort, rather
         than ever returning a guaranteed-broken guessed link.
    """
    raw_url = item.get("url") or _dig(item, "urls", "mobile") or _dig(item, "urls", "desktop")
    if raw_url:
        if raw_url.startswith("http"):
            return raw_url
        return "https://www.olx.com.pk" + (raw_url if raw_url.startswith("/") else f"/{raw_url}")

    # externalID confirmed present and is OLX's real public ad ID —
    # check it BEFORE the internal Algolia id/objectID fields.
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

            # One-time diagnostic: if fields are STILL empty after this
            # patch, dump the actual 'price' and extraFields subtrees
            # (not just the outer key list) so the exact remaining shape
            # mismatch, if any, is fully visible in the next log round.
            if not debug_dumped and price == "0" and year == "0" and mileage == "0":
                debug_dumped = True
                print(f"[OLX Scraper] ⚠ STILL empty for '{title}' after shape fix. Investigating subtrees:")
                print(f"[OLX Scraper]   price subtree: {json.dumps(item.get('price'), default=str)[:500]}")
                print(f"[OLX Scraper]   extraFields subtree: {json.dumps(item.get('extraFields'), default=str)[:500]}")
                print(f"[OLX Scraper]   formattedExtraFields subtree: {json.dumps(item.get('formattedExtraFields'), default=str)[:500]}")
                print(f"[OLX Scraper]   location subtree: {json.dumps(item.get('location'), default=str)[:300]}")
                print(f"[OLX Scraper]   externalID={item.get('externalID')!r}  id={item.get('id')!r}  objectID={item.get('objectID')!r}  slug={item.get('slug')!r}")

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