"""
scrapers/olx.py

FIX (this patch): The Broken Image Trap.
In the previous version, we followed the markdown report's advice to aggressively
construct the image URL using the photo ID and the suffix "-featureimage.webp". 
However, that suffix is obsolete and returns a 404 Not Found error from OLX's CDN. 
Because the code forcibly constructed that broken URL every single time, it ignored 
the perfectly valid native URL sitting right there in the JSON payload!

This patch:
1. Reverses the priority: It now hunts for the native, working `url` string 
   provided by the OLX API first.
2. If forced to construct a URL mathematically, it uses the correct modern 
   suffix (`-800x600.webp`).
3. Enhances the DOM fallback to grab lazy-loaded `data-src` images.
"""
from bs4 import BeautifulSoup
import re
import json
from urllib.parse import urlparse, urlunparse
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


def _format_img_url(url: str) -> str:
    url = str(url).strip()
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("/"):
        return "https://images.olx.com.pk" + url
    return url


def _extract_image(item: dict) -> str:
    # 1. Check primary coverPhoto / cover_photo object (Highest Priority)
    cover = item.get("coverPhoto") or item.get("cover_photo")
    if cover:
        if isinstance(cover, str) and cover.strip():
            return _format_img_url(cover)
        if isinstance(cover, dict):
            # Grab the native URL first before attempting to build one
            url = cover.get("url") or cover.get("big", {}).get("url") or _deep_find(cover, ["url", "src"])
            if url:
                return _format_img_url(url)
            # Only construct if native URL is missing
            photo_id = cover.get("externalID") or cover.get("id")
            if photo_id:
                return f"https://images.olx.com.pk/thumbnails/{photo_id}-800x600.webp"

    # 2. Check standard photos / images lists
    images = item.get("images") or item.get("photos") or []
    if isinstance(images, list) and len(images) > 0:
        first_img = images[0]
        if isinstance(first_img, str) and first_img.strip():
            return _format_img_url(first_img)
        if isinstance(first_img, dict):
            # Grab the native URL first
            url = first_img.get("url") or first_img.get("big", {}).get("url") or _deep_find(first_img, ["url", "src"])
            if url:
                return _format_img_url(url)
            # Only construct if native URL is missing
            photo_id = first_img.get("externalID") or first_img.get("id")
            if photo_id:
                return f"https://images.olx.com.pk/thumbnails/{photo_id}-800x600.webp"
                
    return ""


def _extract_price(item: dict) -> str:
    # Real price lives inside extraFields; top-level item['price'] is an intentional decoy 0
    extra = item.get("extraFields") or {}
    real_price = extra.get("price")
    if real_price not in (None, 0, "0", 0.0):
        return str(real_price)

    # Secondary contextual deep scan fallbacks
    for hint in ["display", "formatted", "label", "text", "amount", "value"]:
        val = _deep_find(extra, [hint])
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


def _is_featured_ad(item: dict) -> bool:
    active_products = item.get("activeProducts")
    if isinstance(active_products, dict) and active_products:
        boost_keywords = ("featured", "bump", "urgent", "top", "highlight", "premium")
        for product_key in active_products.keys():
            pk_lower = str(product_key).lower()
            if "ad_limit" in pk_lower:
                continue  
            if any(kw in pk_lower for kw in boost_keywords):
                return True

    if item.get("featured") is True or item.get("isFeatured") is True or item.get("is_featured") is True:
        return True
    promos = item.get("promotions") or item.get("applied_promotions")
    if isinstance(promos, list) and len(promos) > 0:
        return True
    pkg = item.get("package")
    if isinstance(pkg, dict) and (str(pkg.get("name", "")).lower() == "featured" or pkg.get("featured")):
        return True

    return False


def _strip_filter_and_sort(url: str) -> str:
    parsed = urlparse(url)
    query_pairs = [
        pair for pair in parsed.query.split("&")
        if pair and not pair.startswith("filter=") and not pair.startswith("sorting=")
    ]
    stripped_query = "&".join(query_pairs)
    return urlunparse(parsed._replace(query=stripped_query))


async def _fetch(session, url: str):
    try:
        response = await session.get(url, headers=STANDARD_HEADERS, timeout=20)
        return response.status_code, response.text
    except Exception as e:
        print(f"[OLX Scraper] Request failed: {e}")
        return None, None


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
        print(f"[OLX Scraper] ⚠ JSON State missing or empty for {url}. Falling back to Visual DOM extraction path!")
        cards = soup.find_all("li", attrs={"data-aut-id": "itemBox"})
        if not cards:
            cards = soup.find_all("li", attrs={"aria-label": "Listing"})
        if not cards:
            cards = soup.find_all("article")

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

                title_el = card.find(attrs={"data-aut-id": "itemTitle"}) or card.find("h2") or card.find("a")
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

                loc_el = card.find(attrs={"data-aut-id": "item-location"}) or card.find(attrs={"aria-label": "Location"})
                city = loc_el.get_text(strip=True) if loc_el else "Unknown"

                img_el = card.find("img")
                image_url = ""
                if img_el:
                    image_url = img_el.get("src") or img_el.get("data-src") or ""

                cars.append(CarListing(
                    title=title, price=price, city=city, image_url=image_url, platform="OLX", listing_url=link
                ))
            except Exception:
                continue
        return cars

    price_debug_dumped = False
    featured_skip_count = 0
    organic_count = 0

    for item in hits:
        if organic_count >= MAX_ORGANIC_CARDS:
            break

        try:
            if _is_featured_ad(item):
                featured_skip_count += 1
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

    if featured_skip_count > 0:
        print(f"[OLX Scraper] Skipped {featured_skip_count} featured/boosted ads (confirmed via activeProducts).")

    print(f"[OLX Scraper] Extracted {len(cars)} true organic listings via Next.js JSON")
    return cars