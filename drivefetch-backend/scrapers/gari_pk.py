"""
scrapers/gari_pk.py  (was wise_wheels.py)

HACKER BYPASS: The Google Translate Proxy.
Since Gari.pk has strictly enforced Cloudflare JS Challenges against data
center IPs, we use Google's own servers to fetch the HTML for us.
Cloudflare never blocks Google.

PRICE FIX:
  Root cause of "PKR 0" on all Gari.pk listings:
    The class-based price selector fails when Google Translate renames classes.
  Fix: Add a PRICE_RE regex fallback that runs on text_content.

IMAGE FIX:
  Add _extract_image() with lazy-load resilience.

CITY FIX:
  Multi-strategy city extraction with search_filters fallback.

PRICE FORMAT FIX:
  Normalize the "Rs." prefix to "PKR " so the normalizer parses correctly.

AGE & SOLD FIX:
  - Docstring regex references updated to \\d to prevent SyntaxWarnings.
  - Sold filter now checks image src/alt tags and DOM classes for visual badges.
  - Age Strategy 2 now includes <div> tags with a strict 50-character limit 
    to successfully target <div class="desc2"> date elements.
  - Plural time parsing ('hours', 'minutes') fixed.
"""
from bs4 import BeautifulSoup
import re
from models.car_schema import CarListing

MAX_CARDS = 40

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


def _normalize_price_prefix(price: str) -> str:
    """Converts "Rs. 40 Lacs" → "PKR 40 Lacs" so the normalizer parses it correctly."""
    return re.sub(r'^Rs\.?\s*', 'PKR ', price.strip(), flags=re.I)


def _parse_age_days(item, debug: bool = False) -> int:
    """Extracts listing age in days from a Gari.pk card."""
    
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

    # Strategy 2: scan small inline elements (now includes 'div' to catch desc2)
    for tag in item.find_all(['span', 'p', 'small', 'li', 'div', 'td']):
        text = tag.get_text(strip=True)
        # Strict length check prevents parsing entire layout wrappers
        if not text or len(text) > 50:          
            continue
        result = _time_str_to_days(text)
        if result != 999:
            if debug:
                print(f"[Gari.pk Age DEBUG] Strategy 2 match in <{tag.name}>: {repr(text[:50])}")
            return result

    # Strategy 3: full card text as last resort
    full_text = item.get_text(separator=' ')
    if debug:
        print(f"[Gari.pk Age DEBUG] Strategy 3 full text (first 200): {repr(full_text[:200])}")
    result = _time_str_to_days(full_text)
    if result != 999:
        return result

    return 999


MONTH_MAP = {
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
    'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
    'january': 1, 'february': 2, 'march': 3, 'april': 4, 'june': 6,
    'july': 7, 'august': 8, 'september': 9, 'october': 10,
    'november': 11, 'december': 12,
}


def _time_str_to_days(text: str) -> int:
    import datetime

    t = text.lower().strip()
    today = datetime.date.today()

    # Absolute: Month Day, Year (e.g., Jul 28, 2023)
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

    # DD-MM-YYYY or YYYY-MM-DD
    m = re.search(r'(\d{4})-(\d{2})-(\d{2})', t)
    if m:
        try:
            posted = datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            return max(0, (today - posted).days)
        except ValueError:
            pass

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

    # Urdu partial-translation patterns
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


def _extract_city(item, fallback_city: str) -> str:
    """Multi-strategy city extraction."""
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

    for icon in item.find_all(['i', 'img'], class_=re.compile(r'(location|map|pin|place|geo)', re.I)):
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


def _extract_price(item, text_content: str) -> str:
    """Two-stage price extraction."""
    price_el = item.find(class_=re.compile(r'price', re.I))
    if price_el:
        raw = price_el.get_text(separator=' ', strip=True)
        if raw and raw.strip('0 ') != '':
            return raw

    m = PRICE_RE.search(text_content)
    if m:
        return m.group(0).strip()

    return '0'


def _extract_image(item) -> str:
    """Lazy-load resilient image extraction."""
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
            f"[Gari.pk Scraper] ❌ 0 card elements found via Google Proxy. "
            f"Raw HTML (first 1000 chars):\n{html[:1000]}"
        )
        return []

    cars = []
    city_dom_hits = 0
    price_class_hits = 0
    price_regex_hits = 0
    image_hits = 0
    age_found = 0

    for item in items[:MAX_CARDS]:
        try:
            text_content = item.get_text(separator=' ')

            # TASK 1: Filter SOLD listings (Text + Visual Badges)
            if re.search(r'\bsold\b', text_content, re.I):
                continue
            if item.find(class_=re.compile(r'sold', re.I)) or \
               item.find('img', src=re.compile(r'sold', re.I)) or \
               item.find('img', alt=re.compile(r'sold', re.I)):
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
            age_days = _parse_age_days(item, debug=False)
            if age_days != 999:
                age_found += 1

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
        f"Age: {age_found}/{len(cars)} parsed."
    )
    return cars