"""
scrapers/wise_wheels.py (WiseWheels.com.pk)

NEXT.JS STREAMING-RESILIENT SCRAPER
- Bypasses fragile container selectors to parse streamed Next.js layout trees globally.
- Explicitly filters out Mantine skeleton loaders from real vehicle data cards.
- Decodes obfuscated Next.js optimized image URLs seamlessly.
- Includes comprehensive debug metrics to monitor extraction health in the console.
"""
from bs4 import BeautifulSoup
import re
import urllib.parse
from models.car_schema import CarListing

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
        print(f"[WiseWheels] Initiating network request for: {url}")
        response = await session.get(url, headers=STANDARD_HEADERS, timeout=15)
        if response.status_code != 200:
            print(f"[WiseWheels ❌] HTTP error status: {response.status_code}")
            return []
        html = response.text
    except Exception as e:
        print(f"[WiseWheels ❌] Network connection failed: {e}")
        return []

    if not html or len(html) < 500:
        print(f"[WiseWheels ❌] Received empty or truncated HTML payload (Length: {len(html) if html else 0})")
        return []

    soup = BeautifulSoup(html, 'html.parser')

    # Global card matching strategy to capture streamed elements inside Next.js layout updates
    items = soup.find_all('div', class_=re.compile(r'shadow-card', re.I))
    print(f"[WiseWheels Debug] Found {len(items)} raw elements containing 'shadow-card' class.")

    if not items:
        print("[WiseWheels ❌] No structural card elements detected. Layout structure might have updated.")
        return []

    cars = []
    seen_urls = set()
    skeleton_count = 0
    sold_count = 0
    invalid_count = 0

    for idx, item in enumerate(items):
        if len(cars) >= MAX_ORGANIC_CARDS:
            break
        try:
            text_content = item.get_text(separator=' ')

            # --- SKELETON FILTER ---
            if "mantine-Skeleton-root" in html and item.find(class_=re.compile(r'Skeleton', re.I)):
                skeleton_count += 1
                continue

            # --- SOLD FILTER ---
            if re.search(r'\bsold\b', text_content, re.I) or item.find(class_=re.compile(r'sold', re.I)):
                sold_count += 1
                continue

            # --- TITLE EXTRACTION ---
            title_el = item.find('h3')
            title = title_el.get_text(strip=True) if title_el else ""
            if not title or len(title) < 4:
                invalid_count += 1
                continue

            # --- LINK EXTRACTION ---
            a_tag = item.find('a', href=re.compile(r'/used-cars/', re.I))
            link = a_tag['href'] if a_tag else ""
            if link and not link.startswith('http'):
                link = 'https://wisewheels.com.pk' + link

            if link in seen_urls:
                continue
            if link:
                seen_urls.add(link)

            # --- PRICE EXTRACTION ---
            price = '0'
            # Look inside the bottom flex row for text components containing pricing formatting
            price_container = item.find('span', class_=re.compile(r'font-bold', re.I))
            if price_container:
                price = price_container.get_text(strip=True)
            else:
                price_match = re.search(r'(PKR|Rs|\₨)\s*([\d,.]+)\s*(Lacs?|Crores?|Lakh)?', text_content, re.I)
                if price_match:
                    price = price_match.group(0).strip()

            # --- SPECIFICATION PROCESSING ---
            year = '0'
            mileage = '0'
            city = 'Unknown'
            
            spec_wrapper = item.find('div', class_=re.compile(r'text-muted-foreground', re.I))
            if spec_wrapper:
                spans = spec_wrapper.find_all('span')
                if len(spans) >= 6:
                    year = spans[0].get_text(strip=True)
                    raw_mileage = spans[1].get_text(strip=True)
                    mileage = re.sub(r'[^\d]', '', raw_mileage)
                    city = spans[5].get_text(strip=True)
                else:
                    # Fallback structural regex parsing
                    year_match = re.search(r'\b(19[89]\d|20[0-2]\d)\b', text_content)
                    if year_match: year = year_match.group(1)
                    mileage_match = re.search(r'\b([\d,]+)\s*KM\b', text_content, re.I)
                    if mileage_match: mileage = mileage_match.group(1).replace(',', '')

            # --- AGE EXTRACTION ---
            age_days = 999
            date_el = item.find('h5')
            if date_el:
                age_days = _time_str_to_days(date_el.get_text(strip=True))

            # --- NEXT.JS IMAGE DECODER ---
            image_url = ''
            img = item.find('img')
            if img:
                src = img.get('src', '')
                if '/_next/image?url=' in src:
                    url_param = re.search(r'url=([^&]+)', src)
                    if url_param:
                        image_url = urllib.parse.unquote(url_param.group(1))
                else:
                    image_url = src

            # Final guard boundary validation
            if price == '0' and year == '0':
                invalid_count += 1
                continue
            
            cars.append(CarListing(
                title=title,
                price=price,
                mileage=mileage,
                city=city,
                year=year,
                listing_url=link or url,
                image_url=image_url or None,
                platform='WiseWheels',
                age_days=age_days,
            ))

        except Exception as e:
            print(f"[WiseWheels Loop Error] Exception encountered on card element #{idx}: {e}")
            continue

    print(f"[WiseWheels Scraper Summary] Total Processed: {len(items)} elements.")
    print(f" -> Skeletons Skipped: {skeleton_count}")
    print(f" -> Sold Listings Skipped: {sold_count}")
    print(f" -> Invalid Elements Filtered: {invalid_count}")
    print(f" -> Successfully Extycled Car Listings: {len(cars)}")
    
    return cars