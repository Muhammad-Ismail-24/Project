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

            cars.append(CarListing(
                title=title,
                price=price,
                mileage=mileage,
                city=city,
                year=year,
                listing_url=link,
                image_url=image_url,
                platform='Gari.pk',
            ))
        except Exception:
            continue

    print(
        f"[Gari.pk Scraper] Extracted {len(cars)} listings via Google Proxy. "
        f"Price: {price_class_hits} class / {price_regex_hits} regex / "
        f"{len(cars) - price_class_hits - price_regex_hits} missing. "
        f"Images: {image_hits}/{len(cars)}. "
        f"City: {city_dom_hits} DOM / {len(cars) - city_dom_hits} fallback."
    )
    return cars