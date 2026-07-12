"""
scrapers/gari_pk.py  (was wise_wheels.py)

HACKER BYPASS: The Google Translate Proxy.
Since Gari.pk has strictly enforced Cloudflare JS Challenges against data
center IPs, we use Google's own servers to fetch the HTML for us.
Cloudflare never blocks Google.

CITY FIX (this patch):
  Root cause of "city=Unknown" veto that was killing all 30 extracted listings:
    1. The DOM city selector (class_ matching "location|city|area") doesn't
       match Gari.pk's real HTML. The city is typically in a <span> or <li>
       adjacent to a map-pin icon, not in an element whose CLASS is literally
       "location", "city", or "area". The Google Translate proxy also strips
       or renames some classes, making this even less reliable.
    2. When the DOM lookup failed, the fallback was hardcoded to 'Unknown',
       which caused the normalizer's city veto to immediately drop the listing.

  Two-part fix:
    A. BROADEN DOM SELECTORS: try 6+ different city extraction strategies
       in priority order, each targeting a different HTML pattern Gari.pk
       uses across its pages.
    B. GUARANTEED CITY FALLBACK: if all DOM strategies fail, use the city
       from search_filters (which is always the city the user searched for).
       This is logically sound — if the user searched "Islamabad", all
       results on this Islamabad search page ARE in Islamabad, even if the
       DOM label is missing. 'Unknown' is never a correct fallback here.
"""
from bs4 import BeautifulSoup
import re
from models.car_schema import CarListing

MAX_CARDS = 40

# Known Pakistani cities — used as a regex anchor for text-scan city detection
KNOWN_CITIES = (
    r'Islamabad|Rawalpindi|Lahore|Karachi|Peshawar|Multan|Faisalabad|'
    r'Gujranwala|Sialkot|Quetta|Hyderabad|Bahawalpur|Sargodha|Gujrat|'
    r'Sahiwal|Abbottabad|Mardan|Jhelum|Attock|Wah'
)
CITY_RE = re.compile(KNOWN_CITIES, re.I)


def _extract_city(item, fallback_city: str) -> str:
    """
    Tries multiple strategies to extract city text from a Gari.pk card.
    Returns the first non-empty match, or fallback_city if all fail.

    Strategy priority:
      1. Element with class containing 'location', 'city', or 'area'
         (classic selector — works on some Gari.pk page variants)
      2. <li> or <span> containing a known Pakistani city name
         (structure-agnostic, catches city labels inside icon+text pairs)
      3. <i> or <img> tag with a location-icon class sibling scan
         (catches Font Awesome / custom icon patterns: <i class="fa-map-marker">City</i>)
      4. Full text scan for a known city name anywhere in the card
         (broadest possible fallback — should always match if city is mentioned)
      5. search_filters city (the city the user searched for)
         (guaranteed last resort — logically correct since results ARE from that city)
    """
    # --- Strategy 1: class-name match ---
    city_el = item.find(class_=re.compile(r'(location|city|area)', re.I))
    if city_el:
        text = city_el.get_text(strip=True).split(',')[0].strip()
        if text and len(text) > 2:
            return text

    # --- Strategy 2: <li> or <span> containing a known Pakistani city name ---
    for tag in item.find_all(['li', 'span']):
        text = tag.get_text(strip=True)
        m = CITY_RE.search(text)
        if m and len(text) < 60:   # short text = dedicated label, not a description
            return m.group(0).capitalize()

    # --- Strategy 3: icon sibling scan ---
    # Gari.pk uses patterns like <i class="icon-location"></i> followed by city text,
    # or wraps both in a parent <span>/<div>. Check parent's text after the icon.
    for icon in item.find_all(['i', 'img'], class_=re.compile(r'(location|map|pin|place|geo)', re.I)):
        parent = icon.parent
        if parent:
            text = parent.get_text(strip=True).split(',')[0].strip()
            m = CITY_RE.search(text)
            if m:
                return m.group(0).capitalize()

    # --- Strategy 4: full card text scan for any known city ---
    full_text = item.get_text(separator=' ')
    m = CITY_RE.search(full_text)
    if m:
        return m.group(0).capitalize()

    # --- Strategy 5: guaranteed fallback — use the searched city ---
    return fallback_city


async def scrape_gari_pk(
    url: str,
    session,
    search_filters: dict = None
) -> list[CarListing]:
    """
    Fetches Gari.pk via the Google Translate proxy (bypasses Cloudflare),
    then parses the returned HTML for car listings.
    """
    # Extract the city the user searched for — used as the guaranteed fallback
    # if DOM city extraction fails for any individual card.
    filters = search_filters or {}
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
    # Step 2: Parse HTML
    # ------------------------------------------------------------------ #
    soup = BeautifulSoup(html, 'html.parser')

    # Card selectors in priority order
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
    city_dom_hits = 0   # track how often DOM extraction succeeds vs fallback

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
                # Clean Google Translate URL rewriting
                link = link.replace(
                    "https://www-gari-pk.translate.goog",
                    "https://www.gari.pk"
                )
                link = link.split("?_x_tr")[0]   # strip translate parameters
                if not link.startswith('http'):
                    link = 'https://www.gari.pk' + link

            # --- Price ---
            price_el = item.find(class_=re.compile(r'price', re.I))
            price = price_el.get_text(strip=True) if price_el else '0'

            # --- Text content (used for regex fallbacks) ---
            text_content = item.get_text(separator=' ')

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

            cars.append(CarListing(
                title=title,
                price=price,
                mileage=mileage,
                city=city,
                year=year,
                listing_url=link,
                platform='Gari.pk',
            ))
        except Exception:
            continue

    fallback_used = len(cars) - city_dom_hits
    print(
        f"[Gari.pk Scraper] Extracted {len(cars)} listings via Google Proxy. "
        f"City: {city_dom_hits} from DOM, {fallback_used} from search_filters fallback."
    )
    return cars