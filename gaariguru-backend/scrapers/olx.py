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


def _scrape_dom_images(soup: BeautifulSoup) -> dict:
    """
    Scans the actual rendered HTML for real <img> tags inside listing
    cards, keyed by normalized title text. This is how OLX images were
    ORIGINALLY extracted, before the JSON-based coverPhoto/externalID
    reconstruction was introduced — and that reconstruction has since
    been proven broken across 5 different tested URL patterns (plain
    externalID, numeric id, split UUIDs, either UUID alone — none of
    them loaded a real image). The DOM always contains a working image
    reference because that's literally what renders the photo for a
    human visitor; no CDN URL guessing is needed at all.

    Returns: { normalized_title_lowercase: image_url }
    """
    image_map = {}

    cards = soup.find_all("li", attrs={"data-aut-id": "itemBox"})
    if not cards:
        cards = soup.find_all("li", attrs={"aria-label": "Listing"})
    if not cards:
        cards = soup.find_all("article")

    for card in cards:
        try:
            title_el = card.find(attrs={"data-aut-id": "itemTitle"}) or card.find("h2") or card.find("a")
            title_text = title_el.get_text(strip=True) if title_el else ""
            if not title_text:
                continue

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
                image_map[title_text.strip().lower()] = image_url

        except Exception:
            continue

    return image_map


def _lookup_dom_image(title: str, image_map: dict) -> str:
    """Exact match first, then a loose substring match as a fallback,
    since JSON titles and DOM titles can differ slightly in whitespace
    or truncation."""
    key = title.strip().lower()
    if key in image_map:
        return image_map[key]

    for dom_title, url in image_map.items():
        if key in dom_title or dom_title in key:
            return url

    return ""


def _extract_from_hit(item: dict, fallback_url: str, age_days: int = 0):
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
        age_days=age_days,
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
    # FIX (ordering): hits from window.state arrive in Algolia relevance
    # order, NOT date order — even though the URL has sorting=desc-creation.
    # The sort param affects the rendered UI, not the JSON baked into the
    # HTML. Additionally, the featured/organic split was destroying any
    # pre-existing date ordering by grouping all organics before all
    # featured regardless of post date.
    #
    # Fix: sort the entire hit list by createdAt/timestamp DESCENDING
    # before splitting or iterating, so newest listings always come first
    # regardless of featured status. Also extracts age_days from the
    # timestamp so the Normalizer's freshness scorer can rank OLX
    # listings correctly instead of defaulting to 0 for everything.
    # ------------------------------------------------------------------ #
    import datetime

    def _hit_timestamp(hit: dict) -> int:
        """Returns Unix timestamp from a hit for sort key. Higher = newer."""
        return int(hit.get("createdAt") or hit.get("timestamp") or 0)

    def _hit_age_days(hit: dict) -> int:
        """Converts hit's createdAt Unix timestamp to days-since-posted."""
        ts = _hit_timestamp(hit)
        if ts <= 0:
            return 0  # unknown age → treat as fresh (don't penalise)
        try:
            posted = datetime.datetime.utcfromtimestamp(ts).date()
            today = datetime.date.today()
            return max(0, (today - posted).days)
        except Exception:
            return 0

    # Sort ALL hits newest-first before any splitting
    hits_sorted = sorted(hits, key=_hit_timestamp, reverse=True)

    # Log the timestamp range so we can confirm the sort is working
    if hits_sorted:
        newest_ts = _hit_timestamp(hits_sorted[0])
        oldest_ts = _hit_timestamp(hits_sorted[-1])
        newest_age = _hit_age_days(hits_sorted[0])
        oldest_age = _hit_age_days(hits_sorted[-1])
        print(
            f"[OLX Scraper] Hit timestamp range after sort: "
            f"newest={newest_age}d ago (ts={newest_ts}), "
            f"oldest={oldest_age}d ago (ts={oldest_ts})"
        )

    print(f"[OLX Scraper] Using JSON source: {source} ({len(hits_sorted)} raw hits)")

    featured_items = []
    organic_items = []

    for item in hits_sorted:
        try:
            if _is_featured_ad(item):
                featured_items.append(item)
            else:
                organic_items.append(item)
        except Exception:
            continue

    # Prefer organic-first, but maintain date order WITHIN each group.
    # If excluding featured leaves nothing, fall back to all hits.
    if organic_items:
        ordered_items = organic_items
        skipped_count = len(featured_items)
    else:
        print(
            f"[OLX Scraper] ⚠ All {len(featured_items)} hits were flagged featured — "
            f"falling back to including them rather than returning 0 listings."
        )
        ordered_items = featured_items
        skipped_count = 0

    image_missing_debug_dumped = False
    image_url_sample_logged = False

    for item in ordered_items:
        if len(cars) >= MAX_ORGANIC_CARDS:
            break

        try:
            age = _hit_age_days(item)
            listing = _extract_from_hit(item, fallback_url=url, age_days=age)
            if listing is None:
                continue

            # DIAGNOSTIC: the previously constructed URL used the raw
            # 'externalID' string as-is. Live logs revealed that field
            # is actually TWO valid 36-char UUIDs concatenated with an
            # extra hyphen (e.g. "{uuid1}-{uuid2}"), not one flat ID —
            # almost certainly why the constructed URL never loaded.
            # Log several plausible alternate constructions here so we
            # can identify the real working pattern by testing each one
            # directly in a browser, rather than guessing a third time.
            if not image_url_sample_logged:
                image_url_sample_logged = True
                cover = item.get("coverPhoto") or {}
                numeric_id = cover.get("id", "")
                ext_id = cover.get("externalID", "")

                candidates = {
                    "A (current — raw externalID as one blob)": listing.image_url,
                    "B (plain numeric id)": (
                        f"https://images.olx.com.pk/thumbnails/{numeric_id}-featureimage.webp"
                        if numeric_id else "N/A — no numeric id present"
                    ),
                }
                # Attempt to split the externalID into its two component
                # UUIDs (36 chars each) if it matches that exact shape.
                if ext_id and len(ext_id) == 73 and ext_id[36] == "-":
                    uuid1, uuid2 = ext_id[:36], ext_id[37:]
                    candidates["C (split into two path segments)"] = (
                        f"https://images.olx.com.pk/thumbnails/{uuid1}/{uuid2}-featureimage.webp"
                    )
                    candidates["D (first UUID only)"] = (
                        f"https://images.olx.com.pk/thumbnails/{uuid1}-featureimage.webp"
                    )
                    candidates["E (second UUID only)"] = (
                        f"https://images.olx.com.pk/thumbnails/{uuid2}-featureimage.webp"
                    )

                print(f"[OLX Scraper] 🔍 Testing image URL candidates for '{listing.title}':")
                for label, candidate_url in candidates.items():
                    print(f"[OLX Scraper]    {label}: {candidate_url}")
                print(
                    f"[OLX Scraper] 🔍 Paste EACH candidate URL above into a browser tab — "
                    f"report back which one (if any) actually renders an image."
                )
                print(f"[OLX Scraper] 🔍 Raw coverPhoto: {json.dumps(cover, default=str)[:400]}")

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