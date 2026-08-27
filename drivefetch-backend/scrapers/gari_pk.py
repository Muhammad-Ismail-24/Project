from core.logger import get_logger
logger = get_logger(__name__)
"""
scrapers/gari_pk.py

HACKER BYPASS: The Google Translate Proxy.
Since Gari.pk has strictly enforced Cloudflare JS Challenges against data
center IPs, we use Google's own servers to fetch the HTML for us.
Cloudflare never blocks Google.

DATE HANDLING (rewritten 2026-08-16)
------------------------------------
Gari.pk publishes the posting date in two places, and they always agree:

  1. Search results card — the LAST cell of `div#price-cat > div.div_feat`.
     Shows a relative age for recent ads ("1 day ago", "10 hours ago") and
     an absolute date once the ad is older than roughly three weeks
     ("Jul 19, 2022", "May 23, 2023", "Aug 10, 2026").

  2. Listing detail page — the "Date Posted" row of the spec table:
       <div class="inner-desc">
         <div class="desc1"><strong>Date Posted</strong></div>
         <div class="desc2">Aug 15, 2026</div>
       </div>

Verified equivalence: a card reading "17 days ago" resolves to the same day
as its detail page's "Jul 30, 2026". So the card is the primary source — it
costs no extra request — and the detail page is the fallback for the rare
card whose date cell is missing or unparseable.

WHAT CHANGED AND WHY
  - Date extraction now reads the specific `.div_feat` cells inside
    `#price-cat`, scanning from the last cell backwards. The old code swept
    every <span>/<p>/<div>/<td> in document order, so a title like
    "Suzuki Alto VXR 2 2015" could reach the absolute-date regex before the
    real date cell did. That only ever failed safely because strptime raised
    on the bogus month token "Vxr" — one alias table away from silently
    dating listings off their headline.
  - Undated cards now fall back to fetching the detail page and reading
    "Date Posted" directly. Bounded by GARI_DETAIL_LOOKUP_CAP and a
    semaphore so a broken card selector cannot turn one search into 40
    sequential page loads.
  - GARI_UNDATED_AGE_DAYS is gone. It wrote a fabricated 90 into age_days,
    which the search normaliser read as "89.9 days old, just barely fresh"
    while the recommendation normaliser (60-day limit) read as "stale, veto"
    with an invented reason. Undated now means UNKNOWN_AGE, and the
    normalisers decide what an unknown age is worth.
  - The 999 sentinel is gone everywhere; see scrapers/date_utils.py for why
    it was actively harmful (it collided with real ages over 998 days, which
    is exactly how July 2022 listings were scoring as "age unknown").
"""
import asyncio
import re

from bs4 import BeautifulSoup

from models.car_schema import CarListing
from scrapers.date_utils import (
    UNKNOWN_AGE,
    age_days_from_text,
    is_unknown_age,
)

MAX_CARDS = 40

# Detail-page fallback budget. Only undated cards trigger a lookup, and in
# practice almost every card carries its date, so this rarely fires at all.
GARI_DETAIL_LOOKUP_CAP = 12
GARI_DETAIL_CONCURRENCY = 4
GARI_DETAIL_TIMEOUT = 15

# Global semaphore: limits total concurrent outbound detail page fetches
# across all coroutines within this process.
GARI_DETAIL_SEMAPHORE = asyncio.Semaphore(GARI_DETAIL_CONCURRENCY)

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

# Matches the "Date Posted" spec row on a listing detail page.
DATE_POSTED_LABEL_RE = re.compile(r'date\s*posted', re.I)

# Text-level fallback for the same row, for when the markup shifts but the
# label survives: "Date Posted Aug 15, 2026".
DATE_POSTED_TEXT_RE = re.compile(
    r'date\s*posted\s*[:\-]?\s*'
    r'([A-Za-z]{3,9}\.?\s+\d{1,2},?\s+\d{4}'
    r'|\d{1,2}\s+[A-Za-z]{3,9}\.?,?\s+\d{4}'
    r'|\d{4}-\d{1,2}-\d{1,2})',
    re.I,
)


def _normalize_price_prefix(price: str) -> str:
    """Converts "Rs. 40 Lacs" → "PKR 40 Lacs" so the normalizer parses it."""
    return re.sub(r'^Rs\.?\s*', 'PKR ', price.strip(), flags=re.I)


def _proxy_url(url: str) -> str:
    """Rewrites a gari.pk URL to its Google Translate proxy equivalent."""
    path = url.replace("https://www.gari.pk", "").replace("http://www.gari.pk", "")
    return (
        f"https://www-gari-pk.translate.goog{path}"
        f"?_x_tr_sl=auto&_x_tr_tl=en&_x_tr_hl=en&_x_tr_pto=wapp"
    )


def _unproxy_url(url: str) -> str:
    """Rewrites a proxied link back to its canonical gari.pk form."""
    link = url.replace("https://www-gari-pk.translate.goog", "https://www.gari.pk")
    link = link.split("?_x_tr")[0]
    if not link.startswith('http'):
        link = 'https://www.gari.pk' + link
    return link


def _parse_card_age_days(item, debug: bool = False) -> int:
    """
    Reads the posting age from a Gari.pk search-result card.

    The date lives in the last cell of `div#price-cat > div.div_feat`. We scan
    those cells from the end backwards so a shifted column layout still finds
    it, and we never fall back to sweeping the whole card — the title and the
    spec values (year, engine cc, mileage) are full of digits that look
    date-shaped and have no business being read as a posting date.

    Returns UNKNOWN_AGE when the card carries no readable date.
    """
    spec_block = item.find(id='price-cat') or item
    cells = spec_block.find_all('div', class_='div_feat')

    for cell in reversed(cells):
        text = cell.get_text(strip=True)
        if not text or text == '-':
            continue
        age = age_days_from_text(text)
        if not is_unknown_age(age):
            if debug:
                logger.info(f"[Gari.pk Age] card cell {text!r} -> {age}d")
            return age

    # Markup drift guard: a dedicated date/posted element anywhere in the card.
    time_el = item.find(class_=re.compile(r'(posted|listing.?date|date|ago)', re.I))
    if time_el:
        age = age_days_from_text(time_el.get_text(strip=True))
        if not is_unknown_age(age):
            if debug:
                logger.info(f"[Gari.pk Age] class-matched element -> {age}d")
            return age

    if debug:
        cell_texts = [c.get_text(strip=True) for c in cells]
        logger.info(f"[Gari.pk Age] no date in card. Cells: {cell_texts}")

    return UNKNOWN_AGE


def parse_detail_age_days(html: str, debug: bool = False) -> int:
    """
    Reads "Date Posted" from a Gari.pk listing detail page.

    Primary path is the structured spec row:
        <div class="inner-desc">
          <div class="desc1"><strong>Date Posted</strong></div>
          <div class="desc2">Aug 15, 2026</div>
        </div>

    Falls back to a label-anchored text regex if that markup shifts.
    Returns UNKNOWN_AGE when the field is absent or unreadable.
    """
    if not html:
        return UNKNOWN_AGE

    soup = BeautifulSoup(html, 'html.parser')

    for row in soup.find_all('div', class_='inner-desc'):
        label_el = row.find('div', class_='desc1')
        if not label_el or not DATE_POSTED_LABEL_RE.search(label_el.get_text(strip=True)):
            continue
        value_el = row.find('div', class_='desc2')
        if not value_el:
            continue
        raw = value_el.get_text(strip=True)
        age = age_days_from_text(raw)
        if debug:
            logger.info(f"[Gari.pk Age] detail 'Date Posted' = {raw!r} -> {age}d")
        if not is_unknown_age(age):
            return age

    # Markup drift guard: label and value adjacent in the flattened text.
    match = DATE_POSTED_TEXT_RE.search(soup.get_text(separator=' ', strip=True))
    if match:
        age = age_days_from_text(match.group(1))
        if debug:
            logger.info(f"[Gari.pk Age] detail text fallback {match.group(1)!r} -> {age}d")
        if not is_unknown_age(age):
            return age

    return UNKNOWN_AGE


async def _fetch_detail_age(session, listing_url: str, semaphore) -> int:
    """Fetches one detail page through the proxy and returns its age in days."""
    if not listing_url:
        return UNKNOWN_AGE
    async with semaphore:
        try:
            response = await session.get(
                _proxy_url(listing_url), timeout=GARI_DETAIL_TIMEOUT
            )
        except Exception as e:
            logger.error(f"[Gari.pk Scraper] Detail fetch failed for {listing_url}: {e}", exc_info=True)
            return UNKNOWN_AGE
        if response.status_code != 200:
            logger.info(
                f"[Gari.pk Scraper] Detail HTTP {response.status_code} "
                f"for {listing_url}"
            )
            return UNKNOWN_AGE
        return parse_detail_age_days(response.text)


async def _backfill_ages_from_detail_pages(session, cars: list[CarListing]) -> int:
    """
    Fills in age_days for cards that had no readable date, by reading
    "Date Posted" off each listing's detail page.

    Capped at GARI_DETAIL_LOOKUP_CAP lookups so a card-selector regression
    cannot turn one search into dozens of extra page loads. Returns the
    number of ages successfully recovered.
    """
    pending = [c for c in cars if is_unknown_age(c.age_days) and c.listing_url]
    if not pending:
        return 0

    targets = pending[:GARI_DETAIL_LOOKUP_CAP]
    if len(pending) > len(targets):
        logger.info(
            f"[Gari.pk Scraper] {len(pending)} undated cards, "
            f"fetching detail pages for the first {len(targets)}."
        )

    results = await asyncio.gather(
        *(_fetch_detail_age(session, c.listing_url, GARI_DETAIL_SEMAPHORE) for c in targets),
        return_exceptions=True,
    )

    recovered = 0
    for car, age in zip(targets, results):
        if isinstance(age, Exception) or is_unknown_age(age):
            continue
        car.age_days = age
        recovered += 1

    return recovered


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


def parse_gari_cards(html: str, searched_city: str = 'Unknown',
                     debug: bool = False, stats: dict = None) -> list[CarListing]:
    """
    Parses Gari.pk search-result HTML into CarListings.

    Split out from scrape_gari_pk so the card and date logic can be exercised
    against saved fixtures without a live request. Pass `stats` to collect the
    per-field extraction counters used in the scraper's summary log line.
    """
    counters = stats if stats is not None else {}
    counters.setdefault('price_class', 0)
    counters.setdefault('price_regex', 0)
    counters.setdefault('city_dom', 0)
    counters.setdefault('image', 0)
    soup = BeautifulSoup(html, 'html.parser')

    items = soup.find_all('div', class_=re.compile(r'car-item', re.I))
    if not items:
        items = soup.find_all('div', class_=re.compile(r'search[_-]?item', re.I))
    if not items:
        items = soup.find_all('div', class_=re.compile(r'block_ss', re.I))
    if not items:
        items = soup.find_all('div', class_=re.compile(r'\bcard\b', re.I))

    if not items:
        logger.info(
            f"[Gari.pk Scraper] 0 card elements found via Google Proxy. "
            f"Raw HTML (first 1000 chars):\n{html[:1000]}"
        )
        return []

    cars = []
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
            link = _unproxy_url(a_tag['href']) if a_tag else ""

            # --- Price ---
            price_el = item.find(class_=re.compile(r'price', re.I))
            raw_price = price_el.get_text(separator=' ', strip=True) if price_el else ''
            if raw_price and raw_price.strip('0 ') != '':
                price = _normalize_price_prefix(raw_price)
                counters['price_class'] += 1
            else:
                m = PRICE_RE.search(text_content)
                if m:
                    price = _normalize_price_prefix(m.group(0).strip())
                    counters['price_regex'] += 1
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
                counters['city_dom'] += 1

            # --- Image ---
            # Must be "" and never None: CarListing.image_url is a plain `str`,
            # so passing None raises a pydantic ValidationError that the
            # except-continue below would swallow — silently dropping every
            # image-less card instead of keeping the listing without a photo.
            image_url = _extract_image(item) or ""
            if image_url:
                counters['image'] += 1

            # --- Age ---
            # UNKNOWN_AGE here is honest, not a scoring hint. Undated cards get
            # a detail-page lookup in scrape_gari_pk; whatever is still unknown
            # after that is handed to the normalisers as unknown, and they sink
            # it below every dated listing.
            age_days = _parse_card_age_days(item, debug=debug)

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

    return cars


async def scrape_gari_pk(
    url: str,
    session,
    search_filters: dict = None
) -> list[CarListing]:
    """Fetches Gari.pk via the Google Translate proxy."""
    filters = search_filters or {}
    searched_city = filters.get('city', '').replace('-', ' ').title() or 'Unknown'

    try:
        response = await session.get(_proxy_url(url), timeout=15)
        if response.status_code != 200:
            logger.info(f"[Gari.pk Scraper] Google Proxy HTTP {response.status_code}")
            return []
        html = response.text
    except Exception as e:
        logger.info(f"[Gari.pk Scraper] Proxy connection error: {e}")
        return []

    stats = {}
    cars = parse_gari_cards(html, searched_city=searched_city, stats=stats)
    if not cars:
        return []

    from_card = sum(1 for c in cars if not is_unknown_age(c.age_days))
    recovered = await _backfill_ages_from_detail_pages(session, cars)
    still_unknown = sum(1 for c in cars if is_unknown_age(c.age_days))

    logger.info(
        f"[Gari.pk Scraper] Extracted {len(cars)} listings via Google Proxy. "
        f"Price: {stats['price_class']} class / {stats['price_regex']} regex / "
        f"{len(cars) - stats['price_class'] - stats['price_regex']} missing. "
        f"Images: {stats['image']}/{len(cars)}. "
        f"City: {stats['city_dom']} DOM / {len(cars) - stats['city_dom']} fallback. "
        f"Age: {from_card} from card, {recovered} from detail page, "
        f"{still_unknown} unknown."
    )
    return cars
