"""
scrapers/wise_wheels.py (WiseWheels.com.pk)

MANTINE UI / NEXT.JS DOM TARGETING:
This scraper has been precision-mapped to WiseWheels' Next.js frontend.
- Targets specific Tailwind utility classes (e.g., shadow-card, line-clamp-1).
- Extracts Year, Mileage, and City from un-labeled spans using index positioning
  (0 = Year, 1 = Mileage, 5 = Location).
- Decodes high-res S3 image URLs trapped behind Next.js /_next/image?url= routing.
- Uses strict <h3> and <h5> selectors for Title and Date parsing.
"""
from bs4 import BeautifulSoup
import re
import urllib.parse
from models.car_schema import CarListing
from datetime import datetime

MAX_ORGANIC_CARDS = 40

STANDARD_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.google.com/",
}

PAKISTANI_CITIES = [
    "islamabad", "rawalpindi", "lahore", "karachi", "peshawar",
    "multan", "faisalabad", "gujranwala", "sialkot", "quetta",
    "hyderabad", "bahawalpur", "sargodha", "sahiwal", "mardan",
    "abbottabad", "gujrat", "jhelum", "wah cantt", "taxila",
]

def _time_str_to_days(text: str) -> int:
    t = text.lower()
    if re.search(r"\b(minute|min|hour|hr|just now|today|moments?)s?\b", t):
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
    return 999


async def scrape_wise_wheels(url: str, session, search_filters: dict = None) -> list[CarListing]:
    try:
        response = await session.get(url, headers=STANDARD_HEADERS, timeout=15)
        if response.status_code != 200:
            print(f"[WiseWheels Scraper] HTTP {response.status_code} for {url}")
            return []
        html = response.text
    except Exception as e:
        print(f"[WiseWheels Scraper] Request failed: {e}")
        return []

    if not html or len(html) < 500:
        return []

    soup = BeautifulSoup(html, 'html.parser')

    # --- Container Isolation ---
    # Target the Tailwind flexbox wrapper specific to the search grid
    main_container = soup.find('div', class_=re.compile(r'gap-\[1rem\]', re.I))
    search_root = main_container if main_container else soup

    # --- Card Wrapper Selector ---
    # Target the specific Mantine interactive div card 
    items = search_root.find_all('div', class_=re.compile(r'shadow-card', re.I))

    if not items:
        return []

    if len(items) > MAX_ORGANIC_CARDS:
        items = items[:MAX_ORGANIC_CARDS]

    cars = []
    seen_urls = set()

    for item in items:
        try:
            text_content = item.get_text(separator=' ')

            if re.search(r'\bsold\b', text_content, re.I):
                continue

            # --- Title ---
            title_el = item.find('h3', class_=re.compile(r'line-clamp-1', re.I))
            title = title_el.get_text(strip=True) if title_el else ""
            if not title or len(title) < 4:
                continue

            # --- Link ---
            a_tag = item.find('a', href=re.compile(r'/used-cars/', re.I))
            link = a_tag['href'] if a_tag else ""
            if link and not link.startswith('http'):
                link = 'https://wisewheels.com.pk' + link

            if link in seen_urls:
                continue
            if link:
                seen_urls.add(link)

            # --- Price ---
            price = '0'
            price_span = item.find('span', string=re.compile(r'PKR|Rs|₨', re.I))
            if price_span:
                price = price_span.get_text(strip=True)

            # --- Specs (Year, Mileage, City via Index Positioning) ---
            year = '0'
            mileage = '0'
            city = 'Unknown'
            
            # Locate the flex container holding the SVG-divided specs
            spec_wrapper = item.find('div', class_=re.compile(r'text-muted-foreground|gap-2', re.I))
            if spec_wrapper:
                spans = spec_wrapper.find_all('span')
                if len(spans) >= 6:
                    year = spans[0].get_text(strip=True)
                    
                    # Clean the mileage string (e.g. "45000 KM")
                    raw_mileage = spans[1].get_text(strip=True)
                    mileage = re.sub(r'[^\d]', '', raw_mileage)
                    
                    city = spans[5].get_text(strip=True)
                elif len(spans) > 0:
                    # Failsafe fallback if lengths vary
                    year_match = re.search(r'\b(19[89]\d|20[0-2]\d)\b', text_content)
                    if year_match: year = year_match.group(1)
                    
                    mileage_match = re.search(r'\b([\d,]+)\s*KM\b', text_content, re.I)
                    if mileage_match: mileage = mileage_match.group(1).replace(',', '')

            # --- Date/Time Posted ---
            age_days = 999
            date_el = item.find('h5', class_=re.compile(r'text-\[8px\]', re.I))
            if date_el:
                age_days = _time_str_to_days(date_el.get_text(strip=True))

            # --- Image (Next.js Optimization Decoder) ---
            image_url = ''
            img = item.find('img')
            if img:
                src = img.get('src', '')
                if '/_next/image?url=' in src:
                    # Unquote the high-res S3 parameter from the Next.js routing
                    match = re.search(r'url=([^&]+)', src)
                    if match:
                        image_url = urllib.parse.unquote(match.group(1))
                else:
                    image_url = src

            if price == '0' and year == '0':
                continue
            
            cars.append(CarListing(
                title=title,
                price=price,
                mileage=mileage,
                city=city,
                year=year,
                listing_url=link or url,
                image_url=image_url,
                platform='WiseWheels',
                age_days=age_days,
            ))
        except Exception:
            continue

    print(f"[WiseWheels Scraper] Extracted {len(cars)} listings")
    return cars