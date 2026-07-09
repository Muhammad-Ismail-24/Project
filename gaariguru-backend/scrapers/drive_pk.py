"""
scrapers/drive_pk.py
Fixed: Routed through fetch_html (curl_cffi) instead of Playwright.
Drive.pk serves Server-Side Rendered HTML, so we don't need a browser to read it.
"""
from bs4 import BeautifulSoup
import re
from scrapers.http_client import fetch_html
from models.car_schema import CarListing

MAX_ORGANIC_CARDS = 35
CARD_SELECTOR_CLASS = re.compile(r'(car-card|listing|col-md-4|ad-container)', re.I)

async def scrape_drive_pk(url: str, context, search_filters: dict = None) -> list[CarListing]:
    # THE FIX: Use fetch_html to trigger the curl_cffi TLS spoofer
    html = await fetch_html(url)
    if not html: return []

    soup = BeautifulSoup(html, 'html.parser')
    cars = []

    main_container = soup.find('div', class_=re.compile(r'(search-results|listing-grid|row)', re.I))
    items = main_container.find_all(['div', 'article'], class_=CARD_SELECTOR_CLASS) if main_container else soup.find_all(['div', 'article'], class_=CARD_SELECTOR_CLASS)

    if len(items) > MAX_ORGANIC_CARDS:
        items = items[:MAX_ORGANIC_CARDS]

    for item in items:
        try:
            title_el = item.find(['h2', 'h3', 'h4'])
            if not title_el:
                title_el = item.find('a', string=re.compile(r'[A-Za-z]+'))
            
            title = title_el.get_text(strip=True) if title_el else ""
            if not title or len(title) < 4 or "used car for sale" in title.lower():
                continue

            link = ""
            a_tags = item.find_all('a', href=True)
            for a in a_tags:
                href = a['href']
                if len(href) > 15 and not href.startswith('?'):
                    link = href
                    break
            
            if link and not link.startswith('http'):
                link = 'https://www.drivepk.com' + (link if link.startswith('/') else '/' + link)

            price_el = item.find(['div', 'span', 'p'], string=re.compile(r'(PKR|Rs\.?|Lacs|Lakh|Crore)', re.I))
            price = price_el.get_text(separator=' ', strip=True) if price_el else '0'
            
            text_content = item.get_text(separator=' ')
            
            year_match = re.search(r'\b(19[89]\d|20[0-2]\d)\b', text_content)
            year = year_match.group(1) if year_match else '0'

            mileage_match = re.search(r'\b([\d,]+)\s*km\b', text_content, re.I)
            mileage = mileage_match.group(1).replace(',', '') if mileage_match else '0'

            city_match = re.search(r'\b(Islamabad|Lahore|Karachi|Rawalpindi|Peshawar|Multan|Faisalabad|Gujranwala|Sialkot)\b', text_content, re.I)
            city = city_match.group(1).capitalize() if city_match else 'Unknown'

            cars.append(CarListing(
                title=title, price=price, mileage=mileage, city=city, 
                year=year, listing_url=link, platform='Drive.pk'
            ))
        except Exception:
            continue

    print(f"[Drive.pk Scraper] Extracted {len(cars)} listings")
    return cars