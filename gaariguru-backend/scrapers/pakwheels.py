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


def _parse_age_days(item) -> int:
    """
    Extracts listing age in days from a PakWheels DOM card.

    PakWheels displays relative time like "2 days ago", "3 weeks ago".
    Strategy:
      1. Look for an element with a time/date-related class.
      2. Check the HTML <time> tag with datetime attribute (ISO format).
      3. Scan the full card text as broadest fallback.

    Returns:
      0   — posted today (minutes/hours/just now)
      N   — posted N days ago
      999 — could not detect age (normalizer scores this as stale = 0 pts)
    """
    # Strategy 1: class-name match
    time_el = item.find(class_=re.compile(r"(ago|date|time|posted|fresh|listing.?date)", re.I))

    # Strategy 2: <time> tag — prefer datetime attribute (ISO)
    if not time_el:
        time_el = item.find("time")

    time_text = ""
    if time_el:
        dt_attr = time_el.get("datetime", "")
        if dt_attr:
            from datetime import datetime, timezone
            try:
                posted = datetime.fromisoformat(dt_attr.replace("Z", "+00:00"))
                delta = datetime.now(timezone.utc) - posted
                return max(0, delta.days)
            except Exception:
                pass
        time_text = time_el.get_text(strip=True)

    # Strategy 3: full card text scan
    if not time_text:
        time_text = item.get_text(separator=" ")

    return _time_str_to_days(time_text)


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
            if not title_el:
                title_el = item.find('a', string=re.compile(r'\w+'))
            if not title_el:
                continue

            title = title_el.get_text(strip=True)
            if not title:
                continue

            a_tag = title_el if title_el.name == 'a' else title_el.find('a')
            if not a_tag:
                a_tag = item.find('a')

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
                age_days=_parse_age_days(item),
            ))
        except Exception:
            continue

    age_found = sum(1 for c in cars if c.age_days != 999)
    print(f"[PakWheels Scraper] Extracted {len(cars)} listings (Age: {age_found}/{len(cars)} parsed)")
    return cars