"""
scrapers/wise_wheels.py (Gari.pk)

Uses curl_cffi to hit Gari.pk's hidden AJAX endpoint directly.
Impersonates Chrome to bypass their TLS fingerprint checks.

FIXES (July 2026):
  - Added STANDARD_HEADERS to the priming GET request (was missing, causing 403).
  - Added AJAX_HEADERS with full browser context (Origin, Referer, XHR flag, Content-Type).
  - Cookie jar is now explicitly shared between the priming GET and the POST
    by using the same AsyncSession instance for both calls (was already correct,
    but the GET lacked headers so the server rejected it before setting cookies).
  - Payload builder hardened: filters out empty string parts to avoid "c_make_0|"
    with an empty value, which caused Gari.pk to return 0 results silently.
  - BeautifulSoup selectors broadened with re.compile() partial matches to
    survive future minor class name changes.
  - DEBUG: If 0 listings are extracted, prints the first 1000 chars of raw HTML
    so the selector can be diagnosed without re-running the full pipeline.
"""
from bs4 import BeautifulSoup
import re
from curl_cffi.requests import AsyncSession
from models.car_schema import CarListing

MAX_CARDS = 40

# Standard browser headers for the cookie-priming GET.
# Without these, Gari.pk's CDN/WAF immediately returns 403.
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
    "Upgrade-Insecure-Requests": "1",
}

# Separate headers for the AJAX POST.
# The server validates that XHR requests come from within the site (Origin + Referer).
AJAX_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "X-Requested-With": "XMLHttpRequest",
    "Origin": "https://www.gari.pk",
    "Referer": "https://www.gari.pk/",
    "Cache-Control": "no-cache",
}


async def scrape_wise_wheels(
    url: str,
    session=None,
    search_filters: dict = None
) -> list[CarListing]:
    """
    Scrapes Gari.pk via their AJAX search endpoint using curl_cffi.

    Strategy:
      1. Prime a fresh AsyncSession with a GET to the homepage. This causes
         the server to set its session/CSRF cookies in the cookie jar.
      2. POST to the AJAX endpoint with those cookies attached automatically.
         Gari.pk validates that the POST comes from an active browser session.
    """
    make  = (search_filters or {}).get('make',  '').lower().replace("-", "").strip()
    model = (search_filters or {}).get('model', '').lower().replace("-", "").strip()

    # Build the search_param payload.
    # Only add non-empty values — an empty make/model filter returns garbage.
    param_parts = []
    if make:
        param_parts.append(f"c_make_0|{make}")
    if model:
        param_parts.append(f"c_model_0|{model}")

    # Gari.pk AJAX requires at least one filter; fall back to a broad "cars" search.
    if param_parts:
        payload_str = "cars_mini/" + ",".join(param_parts) + "/"
    else:
        payload_str = "cars_mini/"

    ajax_url = "https://www.gari.pk/search-car-ajax.php"

    try:
        # Always use a DEDICATED session for Gari.pk.
        # The shared pipeline session carries cookies from other domains which
        # can confuse Gari.pk's WAF. A clean session + homepage prime is safer.
        async with AsyncSession(impersonate="chrome120") as gari_session:

            # --- Step 1: Cookie priming GET ---
            prime_resp = await gari_session.get(
                "https://www.gari.pk/",
                headers=STANDARD_HEADERS,
                timeout=15
            )
            if prime_resp.status_code not in (200, 301, 302):
                print(
                    f"[Gari.pk Scraper] Homepage prime failed with "
                    f"HTTP {prime_resp.status_code}. Aborting."
                )
                return []

            # --- Step 2: AJAX POST with cookies from Step 1 ---
            resp = await gari_session.post(
                ajax_url,
                data={"search_param": payload_str},
                headers=AJAX_HEADERS,
                timeout=15
            )

            if resp.status_code != 200:
                print(
                    f"[Gari.pk Scraper] AJAX POST failed with "
                    f"HTTP {resp.status_code} (payload: {payload_str!r})"
                )
                return []

            html = resp.text
            if not html or len(html) < 100:
                print(
                    f"[Gari.pk Scraper] AJAX response too short "
                    f"({len(html) if html else 0} chars). "
                    f"Payload was: {payload_str!r}"
                )
                return []

    except Exception as e:
        print(f"[Gari.pk Scraper] Connection error: {e}")
        return []

    # ------------------------------------------------------------------ #
    # HTML Parsing — partial class matches to survive minor class renames
    # ------------------------------------------------------------------ #
    soup = BeautifulSoup(html, 'html.parser')

    # Try multiple known selectors in priority order
    items = soup.find_all('div', class_=re.compile(r'block_ss', re.I))
    if not items:
        items = soup.find_all('div', class_=re.compile(r'search[_-]?item', re.I))
    if not items:
        items = soup.find_all('div', class_=re.compile(r'car[_-]?item', re.I))
    if not items:
        # Broadest fallback: any div with a link and a price inside
        items = soup.find_all('div', class_=re.compile(r'(listing|result|card)', re.I))

    if not items:
        # --- CRITICAL DEBUG ---
        print(
            f"[Gari.pk Scraper] ❌ 0 card elements found. "
            f"Raw HTML (first 1000 chars):\n{html[:1000]}"
        )
        return []

    cars = []
    for item in items[:MAX_CARDS]:
        try:
            # --- Title ---
            title_el = (
                item.find(['h2', 'h3', 'h4'])
                or item.find('a', string=re.compile(r'\w+'))
            )
            title = title_el.get_text(strip=True) if title_el else ""
            if not title or len(title) < 4:
                continue

            # --- Link ---
            a_tag = item.find('a', href=True)
            link = a_tag['href'] if a_tag else ""
            if link and not link.startswith('http'):
                link = 'https://www.gari.pk' + link

            # --- Price ---
            price_el = item.find(class_=re.compile(r'price', re.I))
            price = price_el.get_text(strip=True) if price_el else '0'

            # --- Year ---
            text_content = item.get_text(separator=' ')
            year = '0'
            year_match = re.search(r'\b(19[89]\d|20[0-2]\d)\b', text_content)
            if year_match:
                year = year_match.group(1)

            # --- Mileage ---
            mileage = '0'
            mileage_match = re.search(r'\b([\d,]+)\s*km\b', text_content, re.I)
            if mileage_match:
                mileage = mileage_match.group(1).replace(',', '')

            # --- City ---
            city = 'Unknown'
            city_el = item.find(class_=re.compile(r'(location|city|area)', re.I))
            if city_el:
                city = city_el.get_text(strip=True).split(',')[0].strip()

            cars.append(CarListing(
                title=title,
                price=price,
                mileage=mileage,
                city=city,
                year=year,
                listing_url=link,
                platform='Gari.pk'
            ))
        except Exception:
            continue

    if not cars:
        # --- CRITICAL DEBUG: selectors matched elements but parsing failed ---
        print(
            f"[Gari.pk Scraper] ❌ Found {len(items)} card elements but parsed "
            f"0 listings. Raw HTML (first 1000 chars):\n{html[:1000]}"
        )

    print(f"[Gari.pk Scraper] Extracted {len(cars)} listings.")
    return cars