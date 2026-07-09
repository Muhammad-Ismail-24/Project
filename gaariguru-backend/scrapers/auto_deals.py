"""
scrapers/auto_deals.py
Fixed: Added strict title validation to ignore SEO footer links and dummy cards.
"""
from bs4 import BeautifulSoup
import re
from scrapers.http_client import fetch_page_content, fetch_html
from models.car_schema import CarListing

MAX_ORGANIC_CARDS = 35
CARD_SELECTOR_CLASS = re.compile(r'(car-card|listing|col-md-4|ad-container|search-item)', re.I)

async def scrape_auto_deals(url: str, context, search_filters: dict = None) -> list[CarListing]:
    if context:
        html = await fetch_page_content(context, url, ".car-card, .listing, .col-md-4, .ad-container, .search-item, h2")
    else:
        html = await fetch_html(url)
    if not html: return []

    soup = BeautifulSoup(html, 'html.parser')
    cars = []

    main_container = soup.find('div', class_=re.compile(r'(search-results|listing-grid|row)', re.I))
    
    if main_container:
        items = main_container.find_all(['div', 'article'], class_=CARD_SELECTOR_CLASS)
    else:
        items = soup.find_all(['div', 'article'], class_=CARD_SELECTOR_CLASS)

    if len(items) > MAX_ORGANIC_CARDS:
        print(f"[AutoDeals Scraper] Slicing {len(items)} candidate cards down to top {MAX_ORGANIC_CARDS} to avoid DOM Bleed.")
        items = items[:MAX_ORGANIC_CARDS]

    for item in items:
        try:
            title_el = item.find(['h2', 'h3', 'h4'])
            if not title_el:
                title_el = item.find('a', string=re.compile(r'[A-Za-z]+'))
                
            title = title_el.get_text(strip=True) if title_el else ""
            
            # --- THE GHOST CARD SLAYER ---
            # If the card is just a generic SEO link, skip it immediately.
            if not title or len(title) < 4 or "used car for sale" in title.lower():
                continue

            a_tag = title_el if title_el and title_el.name == 'a' else item.find('a')
            link = a_tag.get('href', '').strip() if a_tag else url
            if link and not link.startswith('http'):
                link = 'https://autodeals.pk' + link

            price_text = '0'
            price_node = item.find(string=re.compile(r'(Lacs|PKR|Rs)', re.I))
            if price_node:
                parent = price_node.parent
                if parent:
                    price_text = parent.get_text(separator=' ', strip=True)
                else:
                    price_text = price_node.strip()
            price = price_text

            text_content = item.get_text(separator=' ')
            year = '0'
            year_match = re.search(r'\b(19[89]\d|20[0-2]\d)\b', text_content)
            if year_match: year = year_match.group(1)

            mileage = '0'
            mileage_match = re.search(r'\b([\d,]+)\s*km\b', text_content, re.I)
            if mileage_match: mileage = mileage_match.group(1).replace(',', '')

            city = 'Unknown'
            city_node = item.find(class_=re.compile(r'location|city', re.I))
            if city_node:
                city = city_node.get_text(strip=True).split(',')[0]

            cars.append(CarListing(
                title=title, price=price, mileage=mileage, city=city,
                year=year, listing_url=link, platform='AutoDeals'
            ))
        except Exception:
            continue

    print(f"[AutoDeals Scraper] Extracted {len(cars)} listings")
    return cars