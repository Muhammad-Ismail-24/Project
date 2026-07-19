"""
scrapers/gari_pk.py

HACKER BYPASS: The Google Translate Proxy.
Since Gari.pk has strictly enforced Cloudflare JS Challenges against data
center IPs, we use Google's own servers to fetch the HTML for us.
Cloudflare never blocks Google.

FIXES (2026-07-19):
  OLD LISTING BLEED:
    Root cause: Gari.pk search result cards don't show the posting date —
    only the individual listing detail page does. The scraper was returning
    age_days=999 for all undated cards, and the normalizer treated 999 as
    "unknown" with a neutral middle score, letting 600+ day old cars through.

    Fix 1: Added DATE_RE which catches absolute date strings like
    "Oct 15, 2023" or "Sep 3, 2023" embedded anywhere in the card text
    (sometimes present in hidden elements, data attributes, or alt text).

    Fix 2: Added a GARI_MAX_AGE_DAYS cap (90 days). Any Gari.pk listing
    that returns age_days=999 (no date found on card) is treated as
    potentially stale and capped at 90 days for scoring purposes.
    This means undated listings score lower than fresh dated listings,
    preventing ancient cars from floating to the top.

    Fix 3: Broadened Strategy 2 to also scan <td> and <label> elements
    and increased the char limit to 60 to catch more date containers.

  WISEWHEELS DATE NOTE (separate file):
    WiseWheels age=0.0 is correct — those listings were just posted today.
    The created_at field is accurate. No fix needed there.
"""
from bs4 import BeautifulSoup
import re
import datetime
from models.car_schema import CarListing

MAX_CARDS = 40

# If a Gari.pk card has no detectable date, treat it as this many days old
# for scoring. High enough to deprioritize but not trigger the 14-day stale veto
# (which is reserved for listings WITH a confirmed old date).
GARI_UNDATED_AGE_DAYS = 90

# Known Pakistani cities for text-scan city detection
KNOWN_CITIES = (
    r'Islamabad|Rawalpindi|Lahore|Karachi|Peshawar|Multan|Faisalabad|'
    r'Gujranwala|Sialkot|Quetta|Hyderabad|Bahawalpur|Sargodha|Gujrat|'
    r'Sahiwal|Abbottabad|Mardan|Jhelum|Attock|Wah'
)
CITY_RE = re.compile(KNOWN_CITIES, re.I)

PRICE_RE = re.compile(
    r'(?:PKR|Rs\.?)\s*[\d,\.]+\s*(?:Lac(?:s|hs?)?|Lakh?|Crore|Million|CR)?'
    r'|[\d,\.]+\s*(?:Lac(?:s|hs?)?|Lakh?|Crore|Million|CR)\b',
    re.I
)

# Matches absolute dates like "Oct 15, 2023" or "15 Oct 2023" or "2023-10-15"
DATE_RE = re.compile(
    r'\b(?:'
    r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4}'  # Oct 15, 2023
    r'|\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?,?\s+\d{4}'  # 15 Oct 2023
    r'|\d{4}-\d{2}-\d{2}'                                                                   # 2023-10-15
    r'|\d{2}-\d{2}-\d{4}'                                                                   # 15-10-2023
    r')\b',
    re.I
)


def _normalize_price_prefix(price: str) -> str:
    """Converts "Rs. 40 Lacs" → "PKR 40 Lacs" so the normalizer parses it."""
    return re.sub(r'^Rs\.?\s*', 'PKR ', price.strip(), flags=re.I)


MONTH_MAP = {
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
    'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
    'january': 1, 'february': 2, 'march': 3, 'april': 4, 'june': 6,
    'july': 7, 'august': 8, 'september': 9, 'october': 10,
    'november': 11, 'december': 12,
}


def _time_str_to_days(text: str) -> int:
    t = text.lower().strip()
    today = datetime.date.today()

    # Absolute: Month Day, Year (e.g., Oct 15, 2023)
    date_match = re.search(r'([a-z]{3,9})\s+(\d{1,2}),?\s+(\d{4})', t)
    if date_match:
        try:
            month_str = date_match.group(1)[:3].capitalize()
            clean_date = f"{month_str} {date_match.group(2)}, {date_match.group(3)}"
            posted = datetime.datetime.strptime(clean_date, "%b %d, %Y").date()
            return max(0, (today - posted).days)
        except Exception:
            pass

    # Absolute: Day Month Year (e.g., 28 Jul 2023)
    dmy_match = re.search(r'(\d{1,2})\s+([a-z]{3,9}),?\s+(\d{4})', t)
    if dmy_match:
        try:
            month_str = dmy_match.group(2)[:3].capitalize()
            clean_date = f"{month_str} {dmy_match.group(1)}, {dmy_match.group(3)}"
            posted = datetime.datetime.strptime(clean_date, "%b %d, %Y").date()
            return max(0, (today - posted).days)
        except Exception:
            pass

    # YYYY-MM-DD
    m = re.search(r'(\d{4})-(\d{2})-(\d{2})', t)
    if m:
        try:
            posted = datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            return max(0, (today - posted).days)
        except ValueError:
            pass

    # DD-MM-YYYY
    m = re.search(r'(\d{2})-(\d{2})-(\d{4})', t)
    if m:
        try:
            posted = datetime.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            return max(0, (today - posted).days)
        except ValueError:
            pass

    # Relative English
    m = re.search(r'(?:about\s+)?(\d+)\s*day', t)
    if m:
        return int(m.group(1))

    m = re.search(r'(?:about\s+)?(\d+)\s*week', t)
    if m:
        return int(m.group(1)) * 7

    m = re.search(r'(?:about\s+)?(\d+)\s*month', t)
    if m:
        return int(m.group(1)) * 30

    m = re.search(r'(?:about\s+)?(\d+)\s*year', t)
    if m:
        return int(m.group(1)) * 365

    # Urdu relative
    m = re.search(r'(\d+)\s*دن', t)
    if m:
        return int(m.group(1))
    m = re.search(r'(\d+)\s*ہفتے', t)
    if m:
        return int(m.group(1)) * 7
    m = re.search(r'(\d+)\s*مہینے', t)
    if m:
        return int(m.group(1)) * 30
    m = re.search(r'(\d+)\s*سال', t)
    if m:
        return int(m.group(1)) * 365

    # Same-day signals
    if re.search(r'\b(minute|min|hour|hr|just now|today|moments?)s?\b|ابھی|گھنٹ|منٹ', t):
        return 0

    if 'yesterday' in t or 'کل' in t:
        return 1

    return 999


def _parse_age_days(item, debug: bool = False) -> int:
    """
    Extracts listing age in days from a Gari.pk card.

    Strategy order:
      1. Dedicated date/time CSS class element
      2. Small inline elements (span, p, small, li, div, td, label) < 60 chars
      3. Data attributes and alt text (catches hidden date metadata)
      4. Full card text scan (last resort — picks up "Oct 15, 2023" style dates)

    Returns 999 if no date found. Caller should treat 999 as undated
    and apply GARI_UNDATED_AGE_DAYS as the scoring fallback.
    """
    # Strategy 1: dedicated time/date element
    time_el = item.find(
        class_=re.compile(r'(ago|date|time|posted|fresh|listing.?date|new|updated)', re.I)
    )
    if not time_el:
        time_el = item.find('time')

    time_text = time_el.get_text(strip=True) if time_el else ''
    if time_text:
        result = _time_str_to_days(time_text)
        if result != 999:
            return result

    # Strategy 2: scan small inline elements
    for tag in item.find_all(['span', 'p', 'small', 'li', 'div', 'td', 'label']):
        text = tag.get_text(strip=True)
        if not text or len(text) > 60:
            continue
        result = _time_str_to_days(text)
        if result != 999:
            if debug:
                print(f"[Gari.pk Age DEBUG] Strategy 2 match in <{tag.name}>: {repr(text[:60])}")
            return result

    # Strategy 3: scan data-* attributes and img alt text for hidden date metadata
    for tag in item.find_all(True):
        for attr_name, attr_val in tag.attrs.items():
            if not isinstance(attr_val, str):
                continue
            if DATE_RE.search(attr_val):
                result = _time_str_to_days(attr_val)
                if result != 999:
                    if debug:
                        print(f"[Gari.pk Age DEBUG] Strategy 3 attr match [{attr_name}]: {repr(attr_val[:60])}")
                    return result

    # Strategy 4: full card text — catches "Date Posted: Oct 15, 2023" style
    full_text = item.get_text(separator=' ')
    if debug:
        print(f"[Gari.pk Age DEBUG] Strategy 4 full text (first 300): {repr(full_text[:300])}")
    result = _time_str_to_days(full_text)
    if result != 999:
        return result

    return 999


def _extract_city(item, fallback_city: str) -> str:
    city_el = item.find(class_=re.compile(r'(location|city|area)', re.I))
    if city_el:
        text = city_el.get_text(strip=True).split(',')[0].strip()
        if text and len(text) > 2:
            return text

    for tag in item.find_all(['li', 'span']):
        text = tag.get_text(strip=True)
        m = CITY_RE.search(text)
        if m and len(text) < 60:
            return m.group(0).capitalize()

    for icon in item.find_all(
        ['i', 'img'],
        class_=re.compile(r'(location|map|pin|place|geo)', re.I)
    ):
        parent = icon.parent
        if parent:
            text = parent.get_text(strip=True).split(',')[0].strip()
            m = CITY_RE.search(text)
            if m:
                return m.group(0).capitalize()

    full_text = item.get_text(separator=' ')
    m = CITY_RE.search(full_text)
    if m:
        return m.group(0).capitalize()

    return fallback_city


def _extract_image(item) -> str:
    img = item.find('img')
    if not img:
        return ''

    for attr in ('data-src', 'data-original', 'data-lazy-src', 'src'):
        val = (img.get(attr) or '').strip()
        if not val:
            continue
        if not val.startswith('http'):
            continue
        lower = val.lower()
        if 'placeholder' in lower or 'blank' in lower or '1x1' in lower or 'logo' in lower:
            continue
        return val

    return ''


async def scrape_gari_pk(
    url: str,
    session,
    search_filters: dict = None
) -> list[CarListing]:
    """Fetches Gari.pk via the Google Translate proxy."""
    filters = search_filters or {}
    searched_city = filters.get('city', '').replace('-', ' ').title() or 'Unknown'

    path = url.replace("https://www.gari.pk", "")
    proxy_url = (
        f"https://www-gari-pk.translate.goog{path}"
        f"?_x_tr_sl=auto&_x_tr_tl=en&_x_tr_hl=en&_x_tr_pto=wapp"
    )

    try:
        response = await session.get(proxy_url, timeout=15)
        if response.status_code != 200:
            print(f"[Gari.pk Scraper] Google Proxy HTTP {response.status_code}")
            return []
        html = response.text
    except Exception as e:
        print(f"[Gari.pk Scraper] Proxy connection error: {e}")
        return []

    soup = BeautifulSoup(html, 'html.parser')

    items = soup.find_all('div', class_=re.compile(r'car-item', re.I))
    if not items:
        items = soup.find_all('div', class_=re.compile(r'search[_-]?item', re.I))
    if not items:
        items = soup.find_all('div', class_=re.compile(r'block_ss', re.I))
    if not items:
        items = soup.find_all('div', class_=re.compile(r'\bcard\b', re.I))

    if not items:
        print(
            f"[Gari.pk Scraper] 0 card elements found via Google Proxy. "
            f"Raw HTML (first 1000 chars):\n{html[:1000]}"
        )
        return []

    cars = []
    city_dom_hits  = 0
    price_class_hits = 0
    price_regex_hits = 0
    image_hits     = 0
    age_found      = 0
    age_undated    = 0

    for item in items[:MAX_CARDS]:
        try:
            text_content = item.get_text(separator=' ')

            # Filter SOLD listings
            if re.search(r'\bsold\b', text_content, re.I):
                continue
            if (item.find(class_=re.compile(r'sold', re.I)) or
                    item.find('img', src=re.compile(r'sold', re.I)) or
                    item.find('img', alt=re.compile(r'sold', re.I))):
                continue

            # --- Title ---
            title_el = (
                item.find(['h2', 'h3', 'h4', 'h5'])
                or item.find('a', string=re.compile(r'\w+'))
            )
            title = title_el.get_text(strip=True) if title_el else ""
            if not title or len(title) < 4:
                continue

            # --- Link ---
            a_tag = item.find('a', href=True)
            link = a_tag['href'] if a_tag else ""
            if link:
                link = link.replace(
                    "https://www-gari-pk.translate.goog",
                    "https://www.gari.pk"
                )
                link = link.split("?_x_tr")[0]
                if not link.startswith('http'):
                    link = 'https://www.gari.pk' + link

            # --- Price ---
            price_el = item.find(class_=re.compile(r'price', re.I))
            raw_price = price_el.get_text(separator=' ', strip=True) if price_el else ''
            if raw_price and raw_price.strip('0 ') != '':
                price = _normalize_price_prefix(raw_price)
                price_class_hits += 1
            else:
                m = PRICE_RE.search(text_content)
                if m:
                    price = _normalize_price_prefix(m.group(0).strip())
                    price_regex_hits += 1
                else:
                    price = '0'

            # --- Year ---
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
            city = _extract_city(item, fallback_city=searched_city)
            if city != searched_city:
                city_dom_hits += 1

            # --- Image ---
            image_url = _extract_image(item) or None
            if image_url:
                image_hits += 1

            # --- Age ---
            # age_days=999 means no date found on the card.
            # We replace 999 with GARI_UNDATED_AGE_DAYS so these listings:
            #   (a) don't get vetoed by the stale-listing rule (that needs a real date)
            #   (b) score lower than fresh dated listings
            #   (c) can still appear if there's nothing better
            age_days = _parse_age_days(item, debug=False)
            if age_days != 999:
                age_found += 1
            else:
                age_undated += 1
                age_days = GARI_UNDATED_AGE_DAYS

            cars.append(CarListing(
                title=title,
                price=price,
                mileage=mileage,
                city=city,
                year=year,
                listing_url=link,
                image_url=image_url,
                platform='Gari.pk',
                age_days=age_days,
            ))
        except Exception:
            continue

    print(
        f"[Gari.pk Scraper] Extracted {len(cars)} listings via Google Proxy. "
        f"Price: {price_class_hits} class / {price_regex_hits} regex / "
        f"{len(cars) - price_class_hits - price_regex_hits} missing. "
        f"Images: {image_hits}/{len(cars)}. "
        f"City: {city_dom_hits} DOM / {len(cars) - city_dom_hits} fallback. "
        f"Age: {age_found}/{len(cars)} parsed, {age_undated} undated→{GARI_UNDATED_AGE_DAYS}d."
    )
    return cars