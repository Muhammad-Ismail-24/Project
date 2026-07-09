"""
scrapers/wise_wheels.py (Gari.pk)

HACKER BYPASS: The Google Translate Proxy
Since Gari.pk has strictly enforced Cloudflare JS Challenges against data center IPs,
we use Google's own servers to fetch the HTML for us. Cloudflare never blocks Google.
"""
from bs4 import BeautifulSoup
import re
from models.car_schema import CarListing

MAX_CARDS = 40

async def scrape_gari_pk(
    url: str,
    session,
    search_filters: dict = None
) -> list[CarListing]:
    
    # 1. Transform the Gari.pk URL into a Google Translate Proxy URL
    # E.g., https://www.gari.pk/used-cars... -> https://www-gari-pk.translate.goog/used-cars...
    path = url.replace("https://www.gari.pk", "")
    
    # We tell Google to translate from Auto to English. 
    # Google's massive IP network fetches the page, bypassing Cloudflare instantly.
    proxy_url = f"https://www-gari-pk.translate.goog{path}?_x_tr_sl=auto&_x_tr_tl=en&_x_tr_hl=en&_x_tr_pto=wapp"

    try:
        # We can use a standard GET request now because Google doesn't block us
        response = await session.get(proxy_url, timeout=15)
        
        if response.status_code != 200:
            print(f"[Gari.pk Scraper] Google Proxy HTTP {response.status_code}")
            return []
            
        html = response.text

    except Exception as e:
        print(f"[Gari.pk Scraper] Proxy connection error: {e}")
        return []

    # 2. Parse the HTML returned by Google
    soup = BeautifulSoup(html, 'html.parser')

    # Google Translate wraps text in <font> tags, but BeautifulSoup's .get_text() handles this seamlessly!
    items = soup.find_all('div', class_=re.compile(r'car-item', re.I))
    if not items:
        items = soup.find_all('div', class_=re.compile(r'search[_-]?item', re.I))
    if not items:
        items = soup.find_all('div', class_=re.compile(r'block_ss', re.I))
    if not items:
        items = soup.find_all('div', class_=re.compile(r'card', re.I))

    if not items:
        print(f"[Gari.pk Scraper] ❌ 0 card elements found via Google Proxy. Raw HTML:\n{html[:1000]}")
        return []

    cars = []
    for item in items[:MAX_CARDS]:
        try:
            # --- Title ---
            title_el = item.find(['h2', 'h3', 'h4', 'h5']) or item.find('a', string=re.compile(r'\w+'))
            title = title_el.get_text(strip=True) if title_el else ""
            if not title or len(title) < 4:
                continue

            # --- Link ---
            # Google rewrites URLs, so we need to clean them back to normal Gari.pk links
            a_tag = item.find('a', href=True)
            link = a_tag['href'] if a_tag else ""
            if link:
                # Clean Google Translate formatting out of the URL if it exists
                link = link.replace("https://www-gari-pk.translate.goog", "https://www.gari.pk")
                link = link.split("?_x_tr")[0] # remove translate parameters
                if not link.startswith('http'):
                    link = 'https://www.gari.pk' + link

            # --- Price ---
            price_el = item.find(class_=re.compile(r'price', re.I))
            price = price_el.get_text(strip=True) if price_el else '0'

            # --- Text Content for RegEx Fallbacks ---
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

            # --- City ---
            city = 'Unknown'
            city_el = item.find(class_=re.compile(r'(location|city|area)', re.I))
            if city_el:
                city = city_el.get_text(strip=True).split(',')[0].strip()

            # --- Age/Freshness ---
            age_days = 0
            if 'hours' in text_content.lower() or 'mins' in text_content.lower():
                age_days = 0
            elif 'days' in text_content.lower():
                day_match = re.search(r'(\d+)\s+days?', text_content, re.I)
                if day_match:
                    age_days = int(day_match.group(1))

            cars.append(CarListing(
                title=title,
                price=price,
                mileage=mileage,
                city=city,
                year=year,
                listing_url=link,
                platform='Gari.pk',
                age_days=age_days
            ))
        except Exception:
            continue

    print(f"[Gari.pk Scraper] Extracted {len(cars)} listings via Google Proxy.")
    return cars