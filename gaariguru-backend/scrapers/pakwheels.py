"""
scrapers/pakwheels.py

Migrated from Playwright to curl_cffi.
Accepts a curl_cffi AsyncSession and fetches HTML directly.
"""
from bs4 import BeautifulSoup
import re
from models.car_schema import CarListing

MAX_ORGANIC_CARDS = 40


def _extract_price(item) -> str:
    """
    Strict DOM Element Targeting.
    Targets the specific div.price-details node first.
    Returns the FULL raw text so the Normalizer can detect Lacs/Crore.
    """
    price_el = item.find('div', class_=re.compile(r'price-details|generic-green', re.I))
    if price_el:
        raw = price_el.get_text(separator=' ', strip=True)
        if raw:
            return raw
    return '0'


def _extract_image(item) -> str:
    """
    Lazy-load resilient image extraction.
    Checks data-src / data-original first; falls back to src.
    """
    img = item.find('img')
    if img:
        for attr in ('data-src', 'data-original', 'data-lazy-src', 'src'):
            val = img.get(attr, '').strip()
            if val and val.startswith('http') and 'placeholder' not in val.lower():
                return val
    return ''


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


def _parse_age_days(item, debug: bool = False) -> int:
    """
    Extracts listing age in days from a PakWheels DOM card.

    PakWheels displays relative time like "2 days ago", "3 weeks ago".

    Strategy:
      1. <time> tag with a datetime attribute — most precise (ISO timestamp).
      2. Class-name match for date/time/posted elements.
      3. Per-element regex scan — tests each tag's text individually for a
         relative-time pattern. This is MUCH safer than dumping the full card
         text into _time_str_to_days, which was hitting mileage strings like
         "45,000 km" or year numbers and returning 999 silently every time.
      4. Debug dump so you can see what the card contains when all else fails.

    Returns:
      0   — posted today (minutes/hours/just now)
      N   — posted N days ago
      999 — could not detect age (normalizer scores this as stale = 0 pts)
    """
    from datetime import datetime, timezone

    # Strategy 1: <time datetime="..."> — ISO timestamp, most accurate
    time_tag = item.find("time")
    if time_tag:
        dt_attr = time_tag.get("datetime", "")
        if dt_attr:
            try:
                posted = datetime.fromisoformat(dt_attr.replace("Z", "+00:00"))
                delta = datetime.now(timezone.utc) - posted
                return max(0, delta.days)
            except Exception:
                pass
        # No datetime attr — try the text of the tag itself
        result = _time_str_to_days(time_tag.get_text(strip=True))
        if result != 999:
            return result

    # Strategy 2: class-name match for known date-carrier elements
    time_el = item.find(class_=re.compile(
        r"(ago|date|time|posted|fresh|listing.?date|added|updated|when)", re.I
    ))
    if time_el:
        result = _time_str_to_days(time_el.get_text(strip=True))
        if result != 999:
            return result

    # Strategy 3: walk every element and test its text individually.
    # We avoid dumping the full card text because mileage strings like
    # "45,000 km" and year strings like "2016" contain numbers that the
    # regex can misinterpret — scanning per-element isolates only real
    # time phrases.
    TIME_PATTERN = re.compile(
        r'\b(\d+\s*(?:minute|min|hour|hr|day|week|month|year)s?\s*ago'
        r'|just now|today|yesterday|moments?\s*ago)\b',
        re.I
    )
    for el in item.find_all(True):
        text = el.get_text(strip=True)
        if TIME_PATTERN.search(text):
            result = _time_str_to_days(text)
            if result != 999:
                return result

    # Strategy 4: debug dump — prints card snippet when all strategies miss
    if debug:
        snippet = item.get_text(separator=' ', strip=True)[:300]
        print(f"[PakWheels DEBUG] No date found. Card text: {snippet}")

    return 999  # unparseable — treated as stale = 0 pts by normalizer scorer


async def scrape_pakwheels(url: str, session) -> list[CarListing]:
    """Scrapes PakWheels using a shared curl_cffi AsyncSession."""
    try:
        response = await session.get(url, timeout=20)
        if response.status_code != 200:
            print(f"[PakWheels Scraper] HTTP {response.status_code} for {url}")
            return []
        html = response.text
    except Exception as e:
        print(f"[PakWheels Scraper] Request failed: {e}")
        return []

    if not html or len(html) < 500:
        return []

    soup = BeautifulSoup(html, 'html.parser')
    cars = []

    items = soup.find_all('li', class_=re.compile(r'classified-listing', re.I))
    if not items:
        items = soup.find_all('div', class_=re.compile(r'ad-container', re.I))

    if len(items) > MAX_ORGANIC_CARDS:
        items = items[:MAX_ORGANIC_CARDS]

    for item in items:
        try:
            # --- Title ---
            title_el = item.find(['h2', 'h3', 'h4'])
            a_tag = None
            if title_el:
                a_tag = title_el if title_el.name == 'a' else title_el.find('a')
            if not a_tag:
                a_tag = item.find('a', string=re.compile(r'\w+'))

            title = a_tag.get_text(strip=True) if a_tag else (title_el.get_text(strip=True) if title_el else "")
            if not title:
                continue

            link = a_tag.get('href', '').strip() if a_tag else url
            if link and not link.startswith('http'):
                link = 'https://www.pakwheels.com' + link

            # --- Price ---
            price = _extract_price(item)

            # --- Year & Mileage ---
            year, mileage = '0', '0'
            text_content = item.get_text(separator=' ')

            year_match = re.search(r'\b(19[89]\d|20[0-2]\d)\b', text_content)
            if year_match:
                year = year_match.group(1)

            mileage_match = re.search(r'\b([\d,]+)\s*km\b', text_content, re.I)
            if mileage_match:
                mileage = mileage_match.group(1).replace(',', '')

            # --- City ---
            city_text = 'Unknown'
            city_ul = item.find('ul', class_=re.compile(r'search-vehicle-info\b', re.I))
            if city_ul:
                li = city_ul.find('li')
                if li:
                    extracted_text = li.get_text(strip=True)
                    if extracted_text and not extracted_text.isdigit():
                        if not re.search(r'(km|cc|petrol|diesel|hybrid|automatic|manual)', extracted_text, re.I):
                            city_text = extracted_text

            # --- Image ---
            image_url = _extract_image(item)

            cars.append(CarListing(
                title=title,
                price=price,
                mileage=mileage,
                city=city_text,
                year=year,
                listing_url=link,
                image_url=image_url,
                platform='PakWheels',
                age_days=_parse_age_days(item, debug=(len(cars) == 0)),
            ))
        except Exception:
            continue

    age_found = sum(1 for c in cars if c.age_days != 999)
    print(f"[PakWheels Scraper] Extracted {len(cars)} listings (Age: {age_found}/{len(cars)} parsed)")
    return cars