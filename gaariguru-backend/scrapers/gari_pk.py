"""
scrapers/gari_pk.py  (was wise_wheels.py)

HACKER BYPASS: The Google Translate Proxy.
Since Gari.pk has strictly enforced Cloudflare JS Challenges against data
center IPs, we use Google's own servers to fetch the HTML for us.
Cloudflare never blocks Google.

PRICE FIX (this patch):
  Root cause of "PKR 0" on all Gari.pk listings:
    The class-based price selector (class_=re.compile(r'price')) fails when
    Google Translate renames or restructures the price element's class.
    The price text IS present in the card's text_content (confirmed — mileage
    and year regex work fine on the same string), but the class lookup returns
    None or an element with just "0".

  Fix: Add a PRICE_RE regex fallback that runs on text_content, identical
  in philosophy to how year and mileage are already extracted. The regex
  covers every Pakistani price format observed in production:
    - "PKR 28 Lac"  /  "PKR 28.5 Lacs"  /  "PKR 28.5 Lakh"
    - "Rs. 45.5 Lacs"
    - "PKR 2,200,000"  (raw numeric)
    - "14 Lac"  (no currency prefix)
  The class-based selector is kept as the first attempt; regex kicks in
  only when the selector returns '0' or nothing.

IMAGE FIX (this patch):
  The previous scraper had zero image extraction code — images were simply
  never populated, causing every Gari.pk card to show "No Image Provided".

  Fix: Add _extract_image() with lazy-load resilience:
    - Checks data-src / data-original / data-lazy-src before falling back to src
    - Skips placeholder/blank/1x1 URLs
    - Google Translate proxy preserves <img> tags and their src attributes
      intact (Google only rewrites <a href> and injects <font> for text).

CITY FIX (from previous patch, retained):
  Multi-strategy city extraction with search_filters fallback so
  city is never 'Unknown'.

PRICE FORMAT FIX (this patch):
  Root cause of "PKR 32,000" instead of "PKR 3,200,000":
    Gari.pk shows prices as "Rs. 32 Lacs". The normalizer's _clean_price()
    strips all non-digit/dot characters from the string. On "rs. 32 lacs"
    this produces ".32" (the dot in "Rs." survives the strip), which
    float(".32") = 0.32, then × 100,000 = 32,000 instead of 3,200,000.

    The normalizer works correctly for "PKR 32 Lacs" — that dot doesn't exist.
    Fix: normalize the "Rs." prefix to "PKR" in the scraper before returning,
    so the normalizer always receives the format it handles correctly.
    One regex substitution: r'^Rs\\.?\\s*' → 'PKR '.
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

# Pakistani price formats — covers every variant seen in production
# Examples matched:
#   "PKR 28 Lac", "PKR 28.5 Lacs", "PKR 28.5 Lakh", "Rs. 45.5 Lacs",
#   "PKR 2,200,000", "14 Lac", "2.8 Crore"
PRICE_RE = re.compile(
    r'(?:PKR|Rs\.?)\s*[\d,\.]+\s*(?:Lac(?:s|hs?)?|Lakh?|Crore|Million|CR)?'
    r'|[\d,\.]+\s*(?:Lac(?:s|hs?)?|Lakh?|Crore|Million|CR)\b',
    re.I
)


def _normalize_price_prefix(price: str) -> str:
    """
    Converts "Rs. 40 Lacs" → "PKR 40 Lacs" so the normalizer parses it correctly.

    The normalizer's _clean_price strips all non-digit/dot chars. "Rs. 40" becomes
    ".40" → float 0.4 → × 100,000 = 40,000 (wrong). "PKR 40" becomes "40" → 40.0
    → × 100,000 = 4,000,000 (correct). This one substitution fixes all Rs. variants:
    "Rs. 40", "Rs 40", "Rs.40" all become "PKR 40".
    """
    return re.sub(r'^Rs\.?\s*', 'PKR ', price.strip(), flags=re.I)


def _parse_age_days(item, debug: bool = False) -> int:
    """
    Extracts listing age in days from a Gari.pk card.

    FIX (this patch): Previous version returned 999 (stale) for 0/30 cards
    on some searches (e.g. "Suzuki Every"). Three root causes found:

    1. Google Translate renders Urdu time strings INCONSISTENTLY across
       searches — sometimes "2 days ago" (full English), sometimes "2 دن"
       (Urdu days word without translation), sometimes an ABSOLUTE date
       like "12 July 2025" or "Jul 12" instead of a relative string at
       all. The old code only handled relative English strings.

    2. Pakistani platforms (Gari.pk AND PakWheels confirmed) use the word
       "about" before the number: "about 6 hours ago", "about 2 days ago".
       The old regex r'(\d+)\s*day' required the digit to come first, so
       "about 2 days" never matched.

    3. Strategy 2 (full card text scan) was picking up spec text numbers
       (engine cc, horsepower, mileage figures) BEFORE the date string
       because it scanned the entire concatenated card text without any
       preference ordering.

    Fix strategy:
    - Add 'about' tolerance to all relative-time patterns.
    - Add Urdu partial-translation patterns (دن, ہفتے, مہینے, سال).
    - Add absolute-date parsing (12 July / Jul 12 / DD-MM-YYYY).
    - Prioritize the dedicated date element (Strategy 1) over full-text
      scan (Strategy 2) to avoid spec-text number collisions.
    - Add per-card debug output (enabled via debug=True) so future
      failures show the exact text being fed to the parser.
    """
    # Strategy 1: dedicated time/date element (fastest and most precise)
    time_el = item.find(
        class_=re.compile(r'(ago|date|time|posted|fresh|listing.?date|new|updated)', re.I)
    )
    if not time_el:
        time_el = item.find('time')

    time_text = time_el.get_text(strip=True) if time_el else ''

    if debug and time_text:
        print(f"[Gari.pk Age DEBUG] Strategy 1 text: {repr(time_text[:80])}")

    if time_text:
        result = _time_str_to_days(time_text)
        if result != 999:
            return result

    # Strategy 2: scan only small inline elements (spans/li/p) — avoids
    # collisions with spec text in the larger card body.
    for tag in item.find_all(['span', 'p', 'small', 'li']):
        text = tag.get_text(strip=True)
        if len(text) > 60:          # skip long spec-text blobs
            continue
        result = _time_str_to_days(text)
        if result != 999:
            if debug:
                print(f"[Gari.pk Age DEBUG] Strategy 2 match in <{tag.name}>: {repr(text[:60])}")
            return result

    # Strategy 3: full card text as last resort
    full_text = item.get_text(separator=' ')
    if debug:
        print(f"[Gari.pk Age DEBUG] Strategy 3 full text (first 200): {repr(full_text[:200])}")
    result = _time_str_to_days(full_text)
    if result != 999:
        return result

    if debug:
        print(f"[Gari.pk Age DEBUG] All strategies failed — returning 999 (stale fallback)")
    return 999


MONTH_MAP = {
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
    'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
    'january': 1, 'february': 2, 'march': 3, 'april': 4, 'june': 6,
    'july': 7, 'august': 8, 'september': 9, 'october': 10,
    'november': 11, 'december': 12,
}


def _time_str_to_days(text: str) -> int:
    """
    Converts a relative OR absolute time string to an integer day count.

    FIX (this patch):
    - 'about' tolerance: r'(?:about\s+)?(\d+)\s*unit' so "about 2 days"
      matches the same as "2 days".
    - Urdu partial-translation patterns: دن (days), ہفتے (weeks),
      مہینے (months), سال (years), پہلے (ago).
    - Absolute date parsing: "12 July", "Jul 12", "12-07-2025",
      "2025-07-12" — computes days-since-posted from today's date.
    - Keeps all original relative English patterns intact.
    """
    import datetime

    t = text.lower().strip()

    # --- Same-day signals ---
    if re.search(r'\b(minute|min|hour|hr|just now|today|moments?|ابھی|گھنٹ|منٹ)\b', t):
        return 0

    if 'yesterday' in t or 'کل' in t:
        return 1

    # --- Relative English (with optional 'about' prefix) ---
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

    # --- Urdu partial-translation patterns ---
    # دن = days, ہفتے = weeks, مہینے = months, سال = years, پہلے = ago
    m = re.search(r'(\d+)\s*دن', text)       # Urdu "days"
    if m:
        return int(m.group(1))

    m = re.search(r'(\d+)\s*ہفتے', text)     # Urdu "weeks"
    if m:
        return int(m.group(1)) * 7

    m = re.search(r'(\d+)\s*مہینے', text)    # Urdu "months"
    if m:
        return int(m.group(1)) * 30

    m = re.search(r'(\d+)\s*سال', text)      # Urdu "years"
    if m:
        return int(m.group(1)) * 365

    # --- Absolute date parsing ---
    # Formats: "12 July 2025", "12 July", "Jul 12", "12-07-2025", "2025-07-12"
    today = datetime.date.today()

    # "12 July 2025" or "12 July"
    m = re.search(
        r'(\d{1,2})\s+(january|february|march|april|may|june|july|august|'
        r'september|october|november|december|jan|feb|mar|apr|jun|jul|aug|'
        r'sep|oct|nov|dec)(?:\s+(\d{4}))?',
        t
    )
    if m:
        day = int(m.group(1))
        month = MONTH_MAP.get(m.group(2), 0)
        year = int(m.group(3)) if m.group(3) else today.year
        if month > 0:
            try:
                posted = datetime.date(year, month, day)
                diff = (today - posted).days
                return max(0, diff)
            except ValueError:
                pass

    # "July 12" or "Jul 12"
    m = re.search(
        r'(january|february|march|april|may|june|july|august|'
        r'september|october|november|december|jan|feb|mar|apr|jun|jul|aug|'
        r'sep|oct|nov|dec)\s+(\d{1,2})(?:,?\s*(\d{4}))?',
        t
    )
    if m:
        month = MONTH_MAP.get(m.group(1), 0)
        day = int(m.group(2))
        year = int(m.group(3)) if m.group(3) else today.year
        if month > 0:
            try:
                posted = datetime.date(year, month, day)
                diff = (today - posted).days
                return max(0, diff)
            except ValueError:
                pass

    # "DD-MM-YYYY" or "YYYY-MM-DD"
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

    return 999  # unparseable → treated as stale by scorer


def _extract_city(item, fallback_city: str) -> str:
    """
    Multi-strategy city extraction. Falls back to searched city (never 'Unknown').
    Strategy order:
      1. Class-name match ('location', 'city', 'area')
      2. <li>/<span> containing a known Pakistani city name
      3. Icon sibling scan (Font Awesome / custom map-pin icons)
      4. Full card text scan for any known city name
      5. search_filters city (guaranteed fallback)
    """
    # Strategy 1: class-name match
    city_el = item.find(class_=re.compile(r'(location|city|area)', re.I))
    if city_el:
        text = city_el.get_text(strip=True).split(',')[0].strip()
        if text and len(text) > 2:
            return text

    # Strategy 2: <li>/<span> containing a known city name
    for tag in item.find_all(['li', 'span']):
        text = tag.get_text(strip=True)
        m = CITY_RE.search(text)
        if m and len(text) < 60:
            return m.group(0).capitalize()

    # Strategy 3: icon sibling scan
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

    # Strategy 4: full text scan
    full_text = item.get_text(separator=' ')
    m = CITY_RE.search(full_text)
    if m:
        return m.group(0).capitalize()

    # Strategy 5: guaranteed fallback
    return fallback_city


def _extract_price(item, text_content: str) -> str:
    """
    Two-stage price extraction:
      Stage 1: class-based selector (fast, accurate when class survives proxy)
      Stage 2: PRICE_RE regex on full card text (resilient fallback)
    Returns '0' only if both stages fail.
    """
    # Stage 1: class-based
    price_el = item.find(class_=re.compile(r'price', re.I))
    if price_el:
        raw = price_el.get_text(separator=' ', strip=True)
        # Reject '0', empty, or pure-digit-zero values
        if raw and raw.strip('0 ') != '':
            return raw

    # Stage 2: regex on full text
    m = PRICE_RE.search(text_content)
    if m:
        return m.group(0).strip()

    return '0'


def _extract_image(item) -> str:
    """
    Lazy-load resilient image extraction.
    Google Translate proxy preserves <img> tags and their src attributes intact.
    Checks data-src / data-original / data-lazy-src before falling back to src.
    Skips placeholder / blank / 1x1 pixel URLs.
    """
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
    """
    Fetches Gari.pk via the Google Translate proxy (bypasses Cloudflare),
    then parses the returned HTML for car listings.
    """
    filters = search_filters or {}
    # City the user searched for — guaranteed fallback so city is never 'Unknown'
    searched_city = filters.get('city', '').replace('-', ' ').title() or 'Unknown'

    # ------------------------------------------------------------------ #
    # Step 1: Transform Gari.pk URL → Google Translate proxy URL
    # ------------------------------------------------------------------ #
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

    # ------------------------------------------------------------------ #
    # Step 2: Parse HTML — card selectors in priority order
    # ------------------------------------------------------------------ #
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

    # ------------------------------------------------------------------ #
    # Step 3: Extract fields from each card
    # ------------------------------------------------------------------ #
    cars = []
    city_dom_hits = 0
    price_class_hits = 0
    price_regex_hits = 0
    image_hits = 0
    age_found = 0       # how many cards had a parseable date

    for item in items[:MAX_CARDS]:
        try:
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

            # --- Text content (shared by price / year / mileage regex) ---
            text_content = item.get_text(separator=' ')

            # --- Price (two-stage, with Rs. → PKR normalization) ---
            # Stage 1: class selector
            price_el = item.find(class_=re.compile(r'price', re.I))
            raw_price = price_el.get_text(separator=' ', strip=True) if price_el else ''
            if raw_price and raw_price.strip('0 ') != '':
                price = _normalize_price_prefix(raw_price)
                price_class_hits += 1
            else:
                # Stage 2: regex on full card text
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

            # --- City (multi-strategy with guaranteed fallback) ---
            city = _extract_city(item, fallback_city=searched_city)
            if city != searched_city:
                city_dom_hits += 1

            # --- Image ---
            image_url = _extract_image(item) or None
            if image_url:
                image_hits += 1

            # --- Age (days since posted) ---
            # debug=True on first 3 cards to confirm which strategy fires
            # after the fix — remove once age parsing is confirmed working.
            age_days = _parse_age_days(item, debug=(len(cars) < 3))
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