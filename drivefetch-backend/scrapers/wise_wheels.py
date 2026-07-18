"""
scrapers/wise_wheels.py (WiseWheels.com.pk)

REVERTING CLAUDE'S GOOGLE PROXY MISTAKE:
The Google Translate proxy strips out React/Mantine JavaScript, leaving a blank 
HTML skeleton. This version reverts to the native curl_cffi fetch (which works perfectly) 
and applies the true fix: DOM Bleed Container Isolation.

AGE FIX:
Includes the plural `s?` check to prevent fresh cars from scoring 999.
"""
from bs4 import BeautifulSoup
import re
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

    # --- Container Isolation (The DOM Bleed Fix) ---
    main_container = soup.find(['div', 'ul', 'section'], class_=re.compile(r'(search-results|listing-grid|row|ad-list)', re.I))
    search_root = main_container if main_container else soup

    items = search_root.find_all(['div', 'li', 'article'], class_=re.compile(r'(car-card|listing|col-md-[34]|col-lg-[34]|ad-container|search-item)', re.I))

    if not items:
        return []

    # --- Pre-Slice Filtering ---
    valid_items = []
    for el in items:
        class_str = " ".join(el.get('class', [])).lower()
        if 'nav' in class_str or 'menu' in class_str or 'widget' in class_str:
            continue
        valid_items.append(el)

    if len(valid_items) > MAX_ORGANIC_CARDS:
        valid_items = valid_items[:MAX_ORGANIC_CARDS]

    cars = []
    seen_urls = set()

    for item in valid_items:
        try:
            text_content = item.get_text(separator=' ')

            if re.search(r'\bsold\b', text_content, re.I):
                continue

            title_el = item.find(['h2', 'h3', 'h4'])
            if not title_el:
                title_el = item.find('a', string=re.compile(r'\w+'))
            title = title_el.get_text(strip=True) if title_el else ""
            if not title or len(title) < 4:
                continue

            a_tag = item.find('a', href=True)
            link = a_tag['href'] if a_tag else ""
            if link and not link.startswith('http'):
                link = 'https://wisewheels.com.pk' + (link if link.startswith('/') else '/' + link)

            if link in seen_urls:
                continue
            if link:
                seen_urls.add(link)

            price = '0'
            price_match = re.search(r'(PKR|Rs\.?|₨)\s*([\d,.]+)\s*(Lacs?|Crores?)?', text_content, re.I)
            if price_match:
                price = price_match.group(0).strip()
            else:
                price_el = item.find(class_=re.compile(r'price', re.I))
                if price_el:
                    price = price_el.get_text(strip=True)

            year = '0'
            year_match = re.search(r'\b(19[89]\d|20[0-2]\d)\b', text_content)
            if year_match:
                year = year_match.group(1)

            mileage = '0'
            mileage_match = re.search(r'\b([\d,]+)\s*KM\b', text_content, re.I)
            if mileage_match:
                mileage = mileage_match.group(1).replace(',', '')

            city = 'Unknown'
            city_el = item.find(class_=re.compile(r'(location|city|area)', re.I))
            if city_el:
                city = city_el.get_text(strip=True).split(',')[0].strip()
            else:
                text_lower = text_content.lower()
                for known_city in PAKISTANI_CITIES:
                    if known_city in text_lower:
                        city = known_city.title()
                        break

            # Use the robust age parser
            age_days = _time_str_to_days(text_content)

            image_url = ''
            img = item.find('img')
            if img:
                for attr in ('data-src', 'data-original', 'data-lazy-src', 'src'):
                    val = img.get(attr, '').strip()
                    if val and val.startswith('http') and 'placeholder' not in val.lower():
                        image_url = val
                        break

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