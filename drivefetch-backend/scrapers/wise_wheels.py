"""
scrapers/wise_wheels.py (WiseWheels.com.pk)

Brand new scraper for the WiseWheels platform.
Uses curl_cffi AsyncSession for TLS-fingerprinted requests.
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

# Common Pakistani cities for regex-based city extraction fallback
PAKISTANI_CITIES = [
    "islamabad", "rawalpindi", "lahore", "karachi", "peshawar",
    "multan", "faisalabad", "gujranwala", "sialkot", "quetta",
    "hyderabad", "bahawalpur", "sargodha", "sahiwal", "mardan",
    "abbottabad", "gujrat", "jhelum", "wah cantt", "taxila",
]


async def scrape_wise_wheels(url: str, session, search_filters: dict = None) -> list[CarListing]:
    """
    Scrapes WiseWheels.com.pk using a shared curl_cffi AsyncSession.
    Uses defensive regex extraction to handle dynamic DOM structures.
    """
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
        print(f"[WiseWheels Scraper] Response too short or empty for {url}")
        return []

    soup = BeautifulSoup(html, 'html.parser')

    # --- Find listing containers using a broad selector ---
    items = soup.find_all('div', class_=re.compile(r'(listing|car-card|item|col-|card)', re.I))

    if not items:
        print(f"[WiseWheels Scraper] ⚠ 0 card elements found for {url}")
        return []

    if len(items) > MAX_ORGANIC_CARDS:
        items = items[:MAX_ORGANIC_CARDS]

    cars = []
    seen_urls = set()  # For deduplication by listing_url

    for item in items:
        try:
            text_content = item.get_text(separator=' ')

            # TASK 1: Filter SOLD listings
            if re.search(r'\bsold\b', text_content, re.I):
                continue

            # --- Title ---
            title_el = item.find(['h2', 'h3', 'h4'])
            if not title_el:
                title_el = item.find('a', string=re.compile(r'\w+'))
            title = title_el.get_text(strip=True) if title_el else ""
            if not title or len(title) < 4:
                continue

            # --- Link ---
            a_tag = item.find('a', href=True)
            link = a_tag['href'] if a_tag else ""
            if link and not link.startswith('http'):
                link = 'https://wisewheels.com.pk' + (link if link.startswith('/') else '/' + link)

            # Deduplicate by URL
            if link in seen_urls:
                continue
            if link:
                seen_urls.add(link)

            # --- Price ---
            price = '0'
            price_match = re.search(r'(PKR|Rs\.?)\s*([\d,.]+)\s*(Lacs?|Crores?)?', text_content, re.I)
            if price_match:
                price = price_match.group(0).strip()
            else:
                # Fallback: look for a price-specific element
                price_el = item.find(class_=re.compile(r'price', re.I))
                if price_el:
                    price = price_el.get_text(strip=True)

            # --- Year ---
            year = '0'
            year_match = re.search(r'\b(19[89]\d|20[0-2]\d)\b', text_content)
            if year_match:
                year = year_match.group(1)

            # --- Mileage ---
            mileage = '0'
            mileage_match = re.search(r'\b([\d,]+)\s*KM\b', text_content, re.I)
            if mileage_match:
                mileage = mileage_match.group(1).replace(',', '')

            # --- City ---
            city = 'Unknown'
            # First try a dedicated location element
            city_el = item.find(class_=re.compile(r'(location|city|area)', re.I))
            if city_el:
                city = city_el.get_text(strip=True).split(',')[0].strip()
            else:
                # Fallback: scan text for known Pakistani cities
                text_lower = text_content.lower()
                for known_city in PAKISTANI_CITIES:
                    if known_city in text_lower:
                        city = known_city.title()
                        break

            # --- Age/Freshness ---
            age_days = 999  # Failsafe default to 999 instead of 0
            text_lower = text_content.lower()

            # Try absolute dates like "Oct 12, 2023" or "October 12, 2023"
            abs_date_match = re.search(r'([A-Z][a-z]{2,8})\s+(\d{1,2}),?\s+(\d{4})', text_content)
            if abs_date_match:
                try:
                    month_str = abs_date_match.group(1)[:3]  # truncate to 3 chars for %b
                    clean_date_str = f"{month_str} {abs_date_match.group(2)}, {abs_date_match.group(3)}"
                    dt = datetime.strptime(clean_date_str, "%b %d, %Y")
                    delta = datetime.now() - dt
                    age_days = max(0, delta.days)
                except Exception:
                    age_days = 999
            else:
                if re.search(r'\b(minute|min|hour|hr|just now|today|moments?)\b', text_lower):
                    age_days = 0
                elif 'yesterday' in text_lower:
                    age_days = 1
                elif 'day' in text_lower:
                    day_match = re.search(r'(\d+)\s+days?', text_lower)
                    if day_match:
                        age_days = int(day_match.group(1))
                elif 'week' in text_lower:
                    week_match = re.search(r'(\d+)\s+weeks?', text_lower)
                    if week_match:
                        age_days = int(week_match.group(1)) * 7
                elif 'month' in text_lower:
                    month_match = re.search(r'(\d+)\s+months?', text_lower)
                    if month_match:
                        age_days = int(month_match.group(1)) * 30

            # --- Image ---
            image_url = ''
            img = item.find('img')
            if img:
                for attr in ('data-src', 'data-original', 'data-lazy-src', 'src'):
                    val = img.get(attr, '').strip()
                    if val and val.startswith('http') and 'placeholder' not in val.lower():
                        image_url = val
                        break

            # If it has no price and no year, it's a navbar/footer link!
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
