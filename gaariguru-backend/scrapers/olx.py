"""
scrapers/olx.py

FIX: The "2 Weeks Old" Bug (The Featured Ad Trap). 
Even with sorting=desc-creation, OLX forces paid "Featured" ads to the 
very top of the JSON payload. These ads can be up to 30 days old.
The previous scraper was taking the first 35 items unconditionally, meaning
it filled its entire quota with stale featured ads and never reached the 
fresh organic ads below them.
This patch detects and skips all Featured/Promoted ads, guaranteeing that 
the 35 cars extracted are the absolute newest organic listings.
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
    if _depth > _max_depth or obj is None:
        return None

    if isinstance(obj, dict):
        for k, v in obj.items():
            kl = str(k).lower()
            if any(sub in kl for sub in key_substrings):
                if isinstance(v, (str, int, float)) and v not in ("", 0, "0", 0.0):
                    return v

        for k, v in obj.items():
            kl = str(k).lower()
            if any(sub in kl for sub in key_substrings) and isinstance(v, (dict, list)):
                found = _deep_find(v, key_substrings, _depth + 1, _max_depth)
                if found not in (None, "", 0, "0", 0.0):
                    return found

        for v in obj.values():
            found = _deep_find(v, key_substrings, _depth + 1, _max_depth)
            if found not in (None, "", 0, "0", 0.0):
                return found

    elif isinstance(obj, list):
        for entry in obj:
            found = _deep_find(entry, key_substrings, _depth + 1, _max_depth)
            if found not in (None, "", 0, "0", 0.0):
                return found

    return None

def _extract_image(item: dict) -> str:
    images = item.get("images") or item.get("photos") or []
    if isinstance(images, list) and len(images) > 0:
        first_img = images[0]
        if isinstance(first_img, dict):
            url = first_img.get("url") or first_img.get("big", {}).get("url")
            if url:
                return str(url)
            found = _deep_find(first_img, ["url", "src"])
            if found:
                return str(found)
    return ""

def _extract_price(item: dict) -> str:
    price_root = item.get("price")
    if price_root not in (None, 0, "0", 0.0):
        if isinstance(price_root, (str, int, float)):
            return str(price_root)
        if isinstance(price_root, dict):
            for hint in ["display", "formatted", "label", "text", "amount", "value"]:
                val = _deep_find(price_root, [hint])
                if val not in (None, "", 0, "0", 0.0):
                    return str(val)

    for k, v in item.items():
        kl = str(k).lower()
        if "price" in kl:
            if isinstance(v, (str, int, float)) and v not in ("", 0, "0", 0.0):
                return str(v)
            if isinstance(v, dict):
                found = _deep_find(v, ["display", "formatted", "value", "amount"])
                if found not in (None, "", 0, "0", 0.0):
                    return str(found)
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
        cards = soup.find_all("li", attrs={"data-aut-id": "itemBox"})
        if not cards:
            cards = soup.find_all("li", attrs={"aria-label": "Listing"})
        if not cards:
            cards = soup.find_all("article")

        for card in cards:
            if len(cars) >= MAX_ORGANIC_CARDS:
                break
            try:
                # Skip Featured Ads in DOM
                badge = card.find(attrs={"aria-label": "Featured"}) or \
                        card.find(attrs={"data-aut-id": "featured"}) or \
                        card.find(string=re.compile(r'Featured', re.I))
                if badge:
                    continue

                title_el = card.find(attrs={"data-aut-id": "itemTitle"}) or card.find("h2") or card.find("a")
                title = title_el.get_text(strip=True) if title_el else ""
                if not title: continue

                a_tag = card.find("a", href=True)
                link = ("https://www.olx.com.pk" + a_tag["href"] if a_tag and not a_tag["href"].startswith("http") else (a_tag["href"] if a_tag else url))

                price_el = card.find(attrs={"data-aut-id": "itemPrice"}) or card.find(class_=re.compile(r"price", re.I)) or card.find(attrs={"aria-label": "Price"})
                price = price_el.get_text(strip=True) if price_el else "0"

                loc_el = card.find(attrs={"data-aut-id": "item-location"}) or card.find(attrs={"aria-label": "Location"})
                city = loc_el.get_text(strip=True) if loc_el else "Unknown"

                img_el = card.find("img")
                image_url = img_el.get("src") if img_el else ""

                cars.append(CarListing(
                    title=title, price=price, city=city, image_url=image_url, platform="OLX", listing_url=link
                ))
            except Exception:
                continue
        return cars

    # NEW LOGIC: Filter out featured ads to guarantee true newest listings
    price_debug_dumped = False
    organic_count = 0

    for item in hits:
        if organic_count >= MAX_ORGANIC_CARDS:
            break
            
        try:
            # 1. Detect and Skip "Featured" / "Bumped" ads
            is_featured = (
                item.get("featured") is True or
                item.get("isFeatured") is True or
                item.get("is_featured") is True
            )
            
            # 2. Sometimes OLX hides the flag in a promotions array
            promos = item.get("promotions") or item.get("applied_promotions")
            if isinstance(promos, list) and len(promos) > 0:
                is_featured = True
                
            # 3. Check for package dict flags
            pkg = item.get("package")
            if isinstance(pkg, dict) and (pkg.get("name", "").lower() == "featured" or pkg.get("featured")):
                is_featured = True

            if is_featured:
                continue

            title = item.get("title", "")
            if not title:
                continue

            price = _extract_price(item)
            year, mileage = _extract_year_and_mileage(item)
            city = _extract_location(item)
            link = _extract_link(item, title, fallback_url=url)
            image_url = _extract_image(item)

            if not price_debug_dumped and price == "0":
                price_debug_dumped = True
                print(f"[OLX Scraper] ⚠ Price STILL '0' for '{title}'. Executed deep item scan.")

            cars.append(CarListing(
                title=title,
                price=price,
                mileage=mileage,
                city=city,
                year=year,
                image_url=image_url,
                listing_url=link,
                platform="OLX"
            ))
            
            organic_count += 1
            
        except Exception:
            continue

    print(f"[OLX Scraper] Extracted {len(cars)} true organic listings via Next.js JSON")
    return cars