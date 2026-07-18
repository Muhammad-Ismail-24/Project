"""
scrapers/wise_wheels.py (WiseWheels.com.pk) — v2.0 FULL REWRITE

ROOT CAUSE OF 0 RESULTS (v1):
  WiseWheels uses Next.js SSR with Cloudflare bot detection. When a data-center
  IP hits the /used-cars?... search page, Cloudflare serves a skeleton HTML shell
  — no listing cards at all, just the navbar and footer. Every card selector in
  v1 matched 0 elements → 0 results.

FIX — GOOGLE TRANSLATE PROXY (same technique as gari_pk.py):
  Route requests through translate.goog. Cloudflare does not block Google's
  crawlers. The translated HTML arrives with all listing cards intact.

  Original URL:
    https://wisewheels.com.pk/used-cars?price_from=0&page=1&make=toyota
  Proxy URL:
    https://wisewheels-com-pk.translate.goog/used-cars
      ?price_from=0&page=1&make=toyota
      &_x_tr_sl=auto&_x_tr_tl=en&_x_tr_hl=en&_x_tr_pto=wapp

CARD SELECTOR:
  WiseWheels renders listing cards as <div class="...listing-card..."> or
  <article> elements. From Google's indexed pages the data fields are:
    - Price: ₨68.5 lac  (rupee sign, NOT PKR/Rs.)
    - Mileage: 46000Km driven / 46000 KMs
    - City: Lahore
    - Year: 2022  (in spec row)
    - Date: "Last update: Nov 26th, 2025 at 00:38"
    - URL: /used-cars/01kv...-AD-65055  (ULID-based)

PRICE FIX:
  v1 regex looked for PKR/Rs. prefix only.
  v2 also matches ₨ (U+20A8) and bare "lac"/"lakh" amounts.

SOLD FILTER:
  Skip cards whose text contains "sold" (case-insensitive).

DEDUP:
  By listing_url to prevent proxy duplication artifacts.
"""
from bs4 import BeautifulSoup
import re
from models.car_schema import CarListing
from datetime import datetime, timezone

MAX_ORGANIC_CARDS = 40

STANDARD_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.google.com/",
}

# ₨ = U+20A8 RUPEE SIGN (used by WiseWheels), plus PKR/Rs. fallbacks
PRICE_RE = re.compile(
    r'(?:₨|PKR|Rs\.?)\s*[\d,\.]+\s*(?:Lac(?:s|hs?)?|Lakh?|Crore|CR)?'
    r'|[\d,\.]+\s*(?:Lac(?:s|hs?)?|Lakh?|Crore|CR)\b',
    re.I,
)

MONTH_MAP = {
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
    'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
}

KNOWN_CITIES_RE = re.compile(
    r'\b(Islamabad|Rawalpindi|Lahore|Karachi|Peshawar|Multan|Faisalabad|'
    r'Gujranwala|Sialkot|Quetta|Hyderabad|Bahawalpur|Sargodha|Gujrat|'
    r'Sahiwal|Abbottabad|Mardan|Jhelum|Attock|Wah)\b',
    re.I,
)


def _build_proxy_url(original_url: str) -> str:
    """
    Converts a wisewheels.com.pk URL to its Google Translate proxy equivalent.

    https://wisewheels.com.pk/used-cars?make=toyota&model=corolla&page=1
    →
    https://wisewheels-com-pk.translate.goog/used-cars
        ?make=toyota&model=corolla&page=1
        &_x_tr_sl=auto&_x_tr_tl=en&_x_tr_hl=en&_x_tr_pto=wapp
    """
    path_and_query = original_url.replace("https://wisewheels.com.pk", "")
    separator = "&" if "?" in path_and_query else "?"
    return (
        f"https://wisewheels-com-pk.translate.goog{path_and_query}"
        f"{separator}_x_tr_sl=auto&_x_tr_tl=en&_x_tr_hl=en&_x_tr_pto=wapp"
    )


def _normalize_price(raw: str) -> str:
    """
    Converts ₨68.5 lac → PKR 68.5 lac  so _clean_price() in the normalizer
    can parse it correctly (it handles the PKR prefix + lac multiplier).
    """
    # Replace rupee sign with PKR prefix
    normalized = re.sub(r'^₨\s*', 'PKR ', raw.strip())
    # Also fix bare Rs. prefix
    normalized = re.sub(r'^Rs\.?\s*', 'PKR ', normalized, flags=re.I)
    return normalized.strip()


def _parse_date_to_age(text: str) -> int:
    """
    WiseWheels date format: "Last update: Nov 26th, 2025 at 00:38"
    Also handles: "Feb 13th, 2025 at 15:07", relative ("2 days ago"), etc.

    Returns age in days, or 999 if unparseable.
    """
    today = datetime.now(tz=timezone.utc).date()
    t = text.lower().strip()

    # "Last update: Nov 26th, 2025 at 00:38"  or  "Nov 26th, 2025 at 00:38"
    # Covers ordinals: 1st 2nd 3rd 4th ... 31st
    m = re.search(
        r'([a-z]{3,9})\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})',
        t
    )
    if m:
        mon_str = m.group(1)[:3]
        month_num = MONTH_MAP.get(mon_str)
        if month_num:
            try:
                posted = datetime(int(m.group(3)), month_num, int(m.group(2))).date()
                return max(0, (today - posted).days)
            except ValueError:
                pass

    # Same-day
    if re.search(r'\b(minute|min|hour|hr|just now|today|moments?)\b', t):
        return 0

    if 'yesterday' in t:
        return 1

    m2 = re.search(r'(\d+)\s*day', t)
    if m2:
        return int(m2.group(1))

    m2 = re.search(r'(\d+)\s*week', t)
    if m2:
        return int(m2.group(1)) * 7

    m2 = re.search(r'(\d+)\s*month', t)
    if m2:
        return int(m2.group(1)) * 30

    m2 = re.search(r'(\d+)\s*year', t)
    if m2:
        return int(m2.group(1)) * 365

    return 999


def _find_cards(soup: BeautifulSoup) -> list:
    """
    Multi-strategy card selector for WiseWheels (post-proxy HTML).

    WiseWheels uses Tailwind CSS — class names are utility strings, not
    semantic. We target the listing container by its structural signature:
    presence of a price element (₨ or PKR) and a year (4-digit number).

    Strategy order (most specific → most permissive):
      1. <article> tags (WiseWheels listing cards are often <article>)
      2. <div> or <li> with href pattern matching /used-cars/ULID-AD-N
      3. Any block element containing a price signal (₨ or PKR/Rs.)
    """
    # S1: article tags — common for listing cards in Next.js apps
    cards = soup.find_all("article")
    if cards:
        return cards

    # S2: Any block element that contains a /used-cars/...-AD-... link
    # This matches the ULID-based URL pattern WiseWheels uses
    AD_HREF_RE = re.compile(r'/used-cars/[a-z0-9]+-AD-\d+', re.I)
    seen_parents = set()
    ad_cards = []
    for a in soup.find_all("a", href=AD_HREF_RE):
        # Walk up to the nearest block-level parent that's a card container
        parent = a.parent
        for _ in range(5):
            if parent is None:
                break
            tag = getattr(parent, 'name', None)
            if tag in ('div', 'li', 'section'):
                pid = id(parent)
                if pid not in seen_parents:
                    seen_parents.add(pid)
                    ad_cards.append(parent)
                break
            parent = parent.parent
    if ad_cards:
        return ad_cards

    # S3: Any element that holds a price signal (₨ / PKR)
    price_signal = re.compile(r'₨|PKR|Rs\.?\s*[\d]', re.I)
    price_blocks = []
    for el in soup.find_all(['div', 'li', 'section']):
        text = el.get_text()
        if price_signal.search(text):
            # Keep only leaf-ish blocks (not the entire page body)
            children_with_price = [
                c for c in el.find_all(['div', 'li', 'section'])
                if price_signal.search(c.get_text())
            ]
            if not children_with_price:
                price_blocks.append(el)
    return price_blocks


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
        if any(skip in lower for skip in ('placeholder', 'blank', '1x1', 'logo', 'icon')):
            continue
        return val
    return ''


def _clean_proxy_url(url: str) -> str:
    """
    Strips Google Translate proxy artifacts from a listing URL.
    translate.goog rewrites hrefs like:
      /used-cars/01kv...-AD-65055?_x_tr_sl=auto&...
    We want:
      https://wisewheels.com.pk/used-cars/01kv...-AD-65055
    """
    # Remove translate.goog host prefix if it crept in
    url = url.replace("https://wisewheels-com-pk.translate.goog", "https://wisewheels.com.pk")
    # Strip translate query params
    url = re.sub(r'[?&]_x_tr[^&]*', '', url).rstrip('?&')
    if url.startswith('/'):
        url = 'https://wisewheels.com.pk' + url
    return url


async def scrape_wise_wheels(
    url: str,
    session,
    search_filters: dict = None
) -> list[CarListing]:
    """
    Scrapes WiseWheels.com.pk via the Google Translate proxy.

    The proxy bypasses Cloudflare bot detection (identical technique to
    scrape_gari_pk) and returns fully-rendered listing HTML.
    """
    filters = search_filters or {}
    searched_city = (filters.get('city', '') or '').replace('-', ' ').title() or 'Unknown'

    proxy_url = _build_proxy_url(url)

    try:
        response = await session.get(proxy_url, headers=STANDARD_HEADERS, timeout=18)
        if response.status_code != 200:
            print(f"[WiseWheels] Proxy HTTP {response.status_code} for {url}")
            return []
        html = response.text
    except Exception as e:
        print(f"[WiseWheels] Proxy connection error: {e}")
        return []

    if not html or len(html) < 500:
        print(f"[WiseWheels] Response too short for {url}")
        return []

    # Cloudflare JS-challenge detection (shouldn't fire via Google Translate)
    if 'cf-browser-verification' in html or 'challenges.cloudflare.com' in html:
        print(f"[WiseWheels] Cloudflare challenge slipped through proxy — skipping.")
        return []

    soup = BeautifulSoup(html, 'html.parser')
    items = _find_cards(soup)

    if not items:
        print(
            f"[WiseWheels] ⚠ 0 card elements found via proxy.\n"
            f"  Raw HTML (first 1000):\n{html[:1000]}"
        )
        return []

    cars: list[CarListing] = []
    seen_urls: set[str] = set()
    price_hit = price_miss = img_hit = age_hit = 0

    for item in items[:MAX_ORGANIC_CARDS]:
        try:
            text_content = item.get_text(separator=' ')

            # Skip sold listings
            if re.search(r'\bsold\b', text_content, re.I):
                continue
            if item.find(class_=re.compile(r'sold', re.I)):
                continue

            # --- Title ---
            title_el = (
                item.find(['h2', 'h3', 'h4', 'h5'])
                or item.find('a', string=re.compile(r'\w{3,}'))
            )
            title = title_el.get_text(strip=True) if title_el else ''
            if not title or len(title) < 4:
                continue

            # --- Link ---
            # Prefer links matching the WiseWheels ULID-AD pattern
            AD_HREF_RE = re.compile(r'/used-cars/[a-z0-9]+-AD-\d+', re.I)
            link_el = item.find('a', href=AD_HREF_RE) or item.find('a', href=True)
            raw_href = link_el['href'] if link_el else ''
            link = _clean_proxy_url(raw_href) if raw_href else url

            if link in seen_urls:
                continue
            if link and link != url:
                seen_urls.add(link)

            # --- Price ---
            # Try price element first, then regex over full text
            price_raw = ''
            price_el = item.find(class_=re.compile(r'price', re.I))
            if price_el:
                candidate = price_el.get_text(separator=' ', strip=True)
                if PRICE_RE.search(candidate):
                    price_raw = candidate
            if not price_raw:
                m = PRICE_RE.search(text_content)
                if m:
                    price_raw = m.group(0)

            if price_raw:
                price = _normalize_price(price_raw)
                price_hit += 1
            else:
                price = '0'
                price_miss += 1

            # --- Year ---
            year_m = re.search(r'\b(19[89]\d|20[0-2]\d)\b', text_content)
            year = year_m.group(1) if year_m else '0'

            # --- Mileage ---
            # WiseWheels shows "46000Km driven" or "46000 KMs"
            mileage_m = re.search(r'\b([\d,]+)\s*[Kk][Mm]', text_content)
            mileage = mileage_m.group(1).replace(',', '') if mileage_m else '0'

            # --- City ---
            city = searched_city
            city_el = item.find(class_=re.compile(r'(location|city|area)', re.I))
            if city_el:
                extracted = city_el.get_text(strip=True).split(',')[0].strip()
                if extracted and len(extracted) > 2:
                    city = extracted
            else:
                city_m = KNOWN_CITIES_RE.search(text_content)
                if city_m:
                    city = city_m.group(1).capitalize()

            # --- Age ---
            # Look for "Last update:" date text or relative time strings
            age_days = 999
            # Dedicated date/time elements
            date_el = item.find(
                class_=re.compile(r'(date|time|ago|posted|update|fresh)', re.I)
            ) or item.find('time')
            if date_el:
                age_days = _parse_date_to_age(date_el.get_text(strip=True))

            # Scan short inline elements if dedicated element missed
            if age_days == 999:
                for tag in item.find_all(['span', 'p', 'small', 'div', 'li']):
                    text = tag.get_text(strip=True)
                    if not text or len(text) > 80:
                        continue
                    # Must contain a date/time signal
                    if re.search(
                        r'(last update|posted|ago|today|yesterday|jan|feb|mar|apr|may|jun|'
                        r'jul|aug|sep|oct|nov|dec|\d+\s*day|\d+\s*week|\d+\s*month)',
                        text, re.I
                    ):
                        candidate = _parse_date_to_age(text)
                        if candidate != 999:
                            age_days = candidate
                            break

            if age_days != 999:
                age_hit += 1

            # --- Image ---
            image_url = _extract_image(item) or None
            if image_url:
                img_hit += 1

            # Guard: only drop if BOTH price AND year are unknown AND no link
            # (navbar links have no price+year+distinctive-url)
            ad_url_m = re.search(r'/used-cars/[a-z0-9]+-AD-\d+', link, re.I)
            if price == '0' and year == '0' and not ad_url_m:
                continue

            cars.append(CarListing(
                title=title,
                price=price,
                mileage=mileage,
                city=city,
                year=year,
                listing_url=link,
                image_url=image_url,
                platform='WiseWheels',
                age_days=age_days,
            ))
        except Exception:
            continue

    total = len(cars)
    print(
        f"[WiseWheels] Extracted {total} listings via Google Proxy. "
        f"Price: {price_hit} found / {price_miss} missing. "
        f"Images: {img_hit}/{total}. Age: {age_hit}/{total} parsed."
    )
    return cars