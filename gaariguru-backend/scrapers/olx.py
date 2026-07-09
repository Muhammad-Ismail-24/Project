"""
scrapers/olx.py

Migrated from Playwright to curl_cffi.
Accepts a curl_cffi AsyncSession and fetches the OLX page directly.
Extracts listings from the embedded __NEXT_DATA__ / window.state JSON.

FIXES (July 2026):
  - Added STANDARD_HEADERS to every request to prevent 403 blocks.
  - All JSON extraction paths hardened with deeper key traversal.
  - DOM fallback updated for current OLX card structure (li[data-aut-id="itemBox"]).
  - Debug logging: prints first 1000 chars of HTML when 0 listings are extracted.
"""
from bs4 import BeautifulSoup
import re
import json
from models.car_schema import CarListing

MAX_ORGANIC_CARDS = 35

# Standard browser headers injected on every request.
# These prevent the server from flagging the request as a bot (HTTP 403).
STANDARD_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.google.com/",
    "Cache-Control": "no-cache",
}


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

    soup = BeautifulSoup(html, 'html.parser')
    cars = []
    hits = []

    # ------------------------------------------------------------------ #
    # LAYER 1: JSON State Extraction
    # OLX embeds ALL listing data in one of two script tags. We try both.
    # ------------------------------------------------------------------ #
    for s in soup.find_all('script'):
        content = s.string or ''
        if not content:
            continue

        # --- Path A: window.state (older OLX Next.js builds) ---
        match = re.search(r'window\.state\s*=\s*({.*?});\s*(?:window|$)', content, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(1))
                alg_hits = (
                    data.get('algolia', {})
                        .get('content', {})
                        .get('hits', [])
                )
                if alg_hits:
                    hits.extend(alg_hits)
                    break
            except Exception:
                pass

        # --- Path B: __NEXT_DATA__ (current OLX builds) ---
        if s.get('id') == '__NEXT_DATA__':
            try:
                data = json.loads(content)
                page_props = data.get("props", {}).get("pageProps", {})

                # Sub-path B1: initialState → listingSearch → items
                items_arr = (
                    page_props.get("initialState", {})
                               .get("listingSearch", {})
                               .get("items", [])
                )
                if items_arr:
                    hits.extend(items_arr)
                    break

                # Sub-path B2: initialState → listing → adList (alternate key)
                ad_list = (
                    page_props.get("initialState", {})
                               .get("listing", {})
                               .get("adList", [])
                )
                if ad_list:
                    hits.extend(ad_list)
                    break

                # Sub-path B3: apolloState — walk all keys for Item objects
                if not hits:
                    apollo = page_props.get("apolloState", {})
                    if apollo:
                        for k, v in apollo.items():
                            if not isinstance(v, dict):
                                continue
                            if v.get('__typename') != 'Item' and not k.startswith('Item:'):
                                continue
                            if "title" not in v or "price" not in v:
                                continue
                            status = v.get('status', {})
                            if isinstance(status, dict) and status.get('display') not in (None, 'ACTIVE'):
                                continue
                            if 'id' not in v and k.startswith('Item:'):
                                v['id'] = k.split(':')[1]
                            hits.append(v)
                    if hits:
                        break

            except Exception:
                pass

    # ------------------------------------------------------------------ #
    # LAYER 2: Visual DOM Fallback
    # Used when JSON state is missing/empty (e.g. Cloudflare-lite pages).
    # ------------------------------------------------------------------ #
    if not hits:
        print(f"[OLX Scraper] ⚠ JSON State missing for {url}. Attempting Visual DOM Fallback...")

        # Current OLX card selector (li with data-aut-id="itemBox")
        cards = soup.find_all('li', attrs={'data-aut-id': 'itemBox'})
        # Legacy fallback: aria-label="Listing"
        if not cards:
            cards = soup.find_all('li', attrs={'aria-label': 'Listing'})
        # Broadest fallback: any article tag
        if not cards:
            cards = soup.find_all('article')

        if not cards:
            # --- CRITICAL DEBUG: print raw HTML snippet for selector diagnosis ---
            print(f"[OLX Scraper] ❌ DOM fallback also empty. Raw HTML (first 1000 chars):")
            print(html[:1000])
            return []

        for card in cards[:MAX_ORGANIC_CARDS]:
            try:
                # Title
                title_el = (
                    card.find(attrs={'data-aut-id': 'itemTitle'})
                    or card.find('h2')
                    or card.find('a')
                )
                title = title_el.get_text(strip=True) if title_el else ""
                if not title:
                    continue

                # Link
                a_tag = card.find('a', href=True)
                link = ('https://www.olx.com.pk' + a_tag['href']
                        if a_tag and not a_tag['href'].startswith('http')
                        else (a_tag['href'] if a_tag else url))

                # Price
                price_el = (
                    card.find(attrs={'data-aut-id': 'itemPrice'})
                    or card.find(class_=re.compile(r'price', re.I))
                    or card.find(attrs={'aria-label': 'Price'})
                )
                price = price_el.get_text(strip=True) if price_el else '0'

                cars.append(CarListing(
                    title=title, price=price, platform='OLX', listing_url=link
                ))
            except Exception:
                continue

        print(f"[OLX Scraper] DOM fallback extracted {len(cars)} listings")
        return cars

    # ------------------------------------------------------------------ #
    # LAYER 3: Parse hits from JSON state
    # ------------------------------------------------------------------ #
    hits = hits[:MAX_ORGANIC_CARDS]
    for item in hits:
        try:
            title = item.get('title', '')
            if not title:
                continue

            # --- Price ---
            raw_price = item.get('price', {})
            if isinstance(raw_price, dict):
                price = str(
                    raw_price.get('display')
                    or raw_price.get('value')
                    or raw_price.get('regularPrice')
                    or '0'
                )
            else:
                price = str(raw_price or '0')

            # --- Year & Mileage from parameters array ---
            params = item.get('parameters', []) or item.get('main_info', []) or []
            year = '0'
            mileage = '0'
            for p in (params if isinstance(params, list) else []):
                if not isinstance(p, dict):
                    continue
                k = str(p.get('key') or p.get('name') or '').lower()
                v = str(
                    p.get('value')
                    or p.get('value_name')
                    or p.get('displayValue')
                    or ''
                )
                if 'year' in k:
                    year = v
                elif 'mileage' in k or 'km' in k:
                    mileage = v

            # --- City ---
            city = 'Unknown'
            loc_data = item.get('locations') or item.get('location')
            if isinstance(loc_data, list):
                for loc in loc_data:
                    if isinstance(loc, dict) and loc.get('level') == 2:
                        city = loc.get('name', 'Unknown')
                        break
            elif isinstance(loc_data, dict):
                city = loc_data.get('name', 'Unknown')

            # --- URL ---
            raw_id = str(item.get('id') or item.get('objectID') or '')
            item_id = re.sub(r'\D', '', raw_id)
            raw_slug = (
                item.get('slug')
                or re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')
                or 'vehicle'
            )
            link = (
                f"https://www.olx.com.pk/item/{raw_slug}-iid-{item_id}"
                if len(item_id) > 7
                else url
            )

            cars.append(CarListing(
                title=title,
                price=price,
                mileage=mileage,
                city=city,
                year=year,
                listing_url=link,
                platform='OLX'
            ))
        except Exception:
            continue

    if not cars:
        # --- CRITICAL DEBUG: print raw HTML snippet for selector diagnosis ---
        print(f"[OLX Scraper] ❌ Parsed 0 listings from JSON hits. Raw HTML (first 1000 chars):")
        print(html[:1000])

    print(f"[OLX Scraper] Extracted {len(cars)} listings via Next.js JSON")
    return cars