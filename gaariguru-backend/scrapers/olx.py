"""
scrapers/olx.py

REBUILT (this patch) against a confirmed, reverse-engineered field map of
OLX's real Algolia hit structure (see report.md). This replaces all the
previous guess-based extraction helpers with ground-truth field paths.

KEY CONFIRMED FACTS THAT CHANGE EVERYTHING:

1. PRICE: hit['price'] is a DECOY — it is always 0 for car listings.
   The real price lives at hit['extraFields']['price']. Every previous
   price-extraction attempt was searching the wrong top-level field.

2. IMAGE: there is no direct image URL field to read. The image must be
   CONSTRUCTED from an ID:
     photo_id = hit['coverPhoto']['externalID']
     image_url = f"https://images.olx.com.pk/thumbnails/{photo_id}-featureimage.webp"
   This is why every previous image-extraction attempt failed — it was
   looking for a ready-made URL string that doesn't exist in this shape.

3. YEAR / MILEAGE: also live under extraFields (extraFields.year,
   extraFields.mileage) as plain integers — no more list-of-pairs
   guessing needed.

4. CITY: hit['location'] is a list of location levels; level == 2 is
   the city.

5. LISTING URL: hit['slug'] + hit['externalID'] combine directly into
   https://www.olx.com.pk/item/{slug}-iid-{externalID} — no fallback
   guessing needed when both fields are present.

6. FEATURED ADS: the top-level hit['product'] field is literally the
   string "featured" when an ad is promoted/boosted, and absent
   otherwise. This is now the PRIMARY featured-ad signal, with the
   'activeProducts' boost-keyword check kept as a secondary signal.

CAUTION (per report.md): the 'make' filter value used in runner.py's
filter= query parameter is not always the plain make name — e.g. Honda's
real facet value is "cars-honda", not "honda". This scraper file does not
touch URL construction, but flag this for whoever next touches the OLX
filter= logic in runner.py — an incorrect make facet value there could
silently produce zero-result filters rather than an outright 404.
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


def _strip_filter_and_sort(url: str) -> str:
    """Fallback URL with filter=/sorting= removed, kept as a resilience
    net if the richer URL 404s for any reason."""
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


def _is_featured_ad(item: dict) -> bool:
    """
    CONFIRMED (report.md): the top-level 'product' field is literally the
    string "featured" when an ad is promoted, and absent for organic ads.
    This is now the primary signal. 'activeProducts' boost-keyword check
    kept as a secondary signal for schema variants.
    """
    if str(item.get("product", "")).lower() == "featured":
        return True

    active_products = item.get("activeProducts")
    if isinstance(active_products, dict) and active_products:
        boost_keywords = ("featured", "bump", "urgent", "top", "highlight", "premium")
        for k in active_products.keys():
            kl = str(k).lower()
            if "ad_limit" in kl:
                continue  # posting quota, not a ranking boost
            if any(kw in kl for kw in boost_keywords):
                return True

    return False


def _extract_from_hit(item: dict, fallback_url: str):
    """
    Extracts a single CarListing from a confirmed-shape OLX Algolia hit,
    using ground-truth field paths from report.md rather than guessing.
    Returns None if the hit has no usable title.
    """
    title = item.get("title", "")
    if not title:
        return None

    extra = item.get("extraFields") or {}

    # --- PRICE: hit['price'] is a decoy (always 0). Real price is here. ---
    price = extra.get("price", 0)

    # --- YEAR / MILEAGE: plain integers under extraFields ---
    year = extra.get("year", 0)
    mileage = extra.get("mileage", 0)

    # --- CITY: location is a list of levels; level == 2 is the city ---
    city = "Unknown"
    for loc in item.get("location", []) or []:
        if isinstance(loc, dict) and loc.get("level") == 2:
            city = loc.get("name", "Unknown")
            break

    # --- LISTING URL: slug + externalID combine directly ---
    slug = item.get("slug", "")
    external_id = item.get("externalID", "")
    if slug and external_id:
        listing_url = f"https://www.olx.com.pk/item/{slug}-iid-{external_id}"
    else:
        listing_url = fallback_url

    # --- IMAGE: constructed from coverPhoto's externalID ---
    image_url = ""
    cover = item.get("coverPhoto")
    if isinstance(cover, dict):
        photo_id = cover.get("externalID", "")
        if photo_id:
            image_url = f"https://images.olx.com.pk/thumbnails/{photo_id}-featureimage.webp"

    # Fallback: first entry in the photos[] array, same ID-based construction
    if not image_url:
        photos = item.get("photos") or []
        if isinstance(photos, list) and photos:
            first_photo = photos[0]
            if isinstance(first_photo, dict):
                photo_id = first_photo.get("externalID", "")
                if photo_id:
                    image_url = f"https://images.olx.com.pk/thumbnails/{photo_id}-featureimage.webp"
            elif isinstance(first_photo, str) and first_photo.startswith("http"):
                # Defensive: if a future schema variant provides a direct
                # URL string instead of an ID, use it as-is.
                image_url = first_photo

    return CarListing(
        title=title,
        price=str(price),
        mileage=str(mileage),
        city=city,
        year=str(year),
        listing_url=listing_url,
        image_url=image_url,
        platform="OLX",
    )


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
    # LAYER 1: window.state (confirmed primary source per report.md)
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
                    source = "window.state"
                    break
            except Exception:
                pass

        # __NEXT_DATA__ kept as a fallback source for schema variants
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
    # LAYER 2: Visual DOM Fallback (only if JSON layer found nothing)
    # ------------------------------------------------------------------ #
    if not hits:
        print(f"[OLX Scraper] ⚠ JSON state missing for {url}. Using Visual DOM Fallback (weaker extraction).")
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

                # Lazy-load resilient image extraction — real src is
                # often in data-src/data-original, not src, until the
                # browser actually scrolls the image into view.
                img_el = card.find("img")
                image_url = ""
                if img_el:
                    for attr in ("data-src", "data-original", "data-lazy-src", "src"):
                        val = img_el.get(attr, "").strip()
                        if val and val.startswith("http") and "placeholder" not in val.lower():
                            image_url = val
                            break

                cars.append(CarListing(
                    title=title, price=price, city=city, image_url=image_url,
                    platform="OLX", listing_url=link
                ))
            except Exception:
                continue

        print(f"[OLX Scraper] DOM fallback extracted {len(cars)} listings")
        return cars

    # ------------------------------------------------------------------ #
    # LAYER 3: Extract from confirmed-shape JSON hits
    #
    # FIX (critical): the featured-ad exclusion was found flagging ALL
    # hits as featured on real searches (confirmed via live logs — 24/24
    # hits skipped, 0 organic listings returned, on two separate
    # searches). The 'activeProducts' field is evidently present as
    # general metadata on most/all listings (many legitimate sellers use
    # bulk-posting packages), not a rare boost signal — so treating its
    # mere presence as "skip this" made the entire OLX scraper return
    # nothing. Safety net added: if excluding featured ads would leave
    # zero results, fall back to including them rather than returning
    # nothing. Degraded data (with some boosted ads mixed in) is far
    # better than silently contributing zero listings to every search.
    # ------------------------------------------------------------------ #
    print(f"[OLX Scraper] Using JSON source: {source} ({len(hits)} raw hits)")

    featured_items = []
    organic_items = []

    for item in hits:
        try:
            if _is_featured_ad(item):
                featured_items.append(item)
            else:
                organic_items.append(item)
        except Exception:
            continue

    # Prefer organic-first ordering, but if organic-only would leave us
    # with nothing, fall back to using ALL hits instead of zero.
    if organic_items:
        ordered_items = organic_items
        skipped_count = len(featured_items)
    else:
        print(
            f"[OLX Scraper] ⚠ All {len(featured_items)} hits were flagged featured — "
            f"this looks like an over-broad detection, not real data. "
            f"Falling back to including them rather than returning 0 listings."
        )
        ordered_items = featured_items
        skipped_count = 0

    image_missing_debug_dumped = False

    for item in ordered_items:
        if len(cars) >= MAX_ORGANIC_CARDS:
            break

        try:
            listing = _extract_from_hit(item, fallback_url=url)
            if listing is None:
                continue

            if not image_missing_debug_dumped and not listing.image_url:
                image_missing_debug_dumped = True
                print(
                    f"[OLX Scraper] ⚠ No image resolved for '{listing.title}'. "
                    f"coverPhoto={json.dumps(item.get('coverPhoto'), default=str)[:300]} "
                    f"photos[0]={json.dumps((item.get('photos') or [None])[0], default=str)[:300]}"
                )

            cars.append(listing)

        except Exception:
            continue

    if skipped_count > 0:
        print(f"[OLX Scraper] Skipped {skipped_count} featured/boosted ads (confirmed via 'product' field).")

    print(f"[OLX Scraper] Extracted {len(cars)} listings via {source}")
    return cars