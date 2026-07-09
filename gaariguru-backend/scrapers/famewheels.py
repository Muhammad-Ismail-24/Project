"""
scrapers/famewheels.py

Migrated from aiohttp to curl_cffi.
Accepts a curl_cffi AsyncSession and fetches HTML directly.
"""
from bs4 import BeautifulSoup
import re
from models.car_schema import CarListing


async def scrape_famewheels(url: str, session) -> list[CarListing]:
    """Scrapes FameWheels using a shared curl_cffi AsyncSession."""
    try:
        response = await session.get(url, timeout=20)
        if response.status_code != 200:
            print(f"[FameWheels Scraper] HTTP {response.status_code} for {url}")
            return []
        html = response.text
    except Exception as e:
        print(f"[FameWheels Scraper] Request failed: {e}")
        return []

    if not html or len(html) < 500:
        return []

    soup = BeautifulSoup(html, 'html.parser')
    cars = []

    for item in soup.find_all(['div', 'li', 'article'], class_=re.compile(r'(car-card|listing|col-md-4|ad-container)', re.I)):
        try:
            title_el = item.find(['h2', 'h3', 'h4'])
            if not title_el:
                title_el = item.find('a', string=re.compile(r'[A-Za-z]+'))
            if not title_el:
                continue

            title = title_el.text.strip()
            if not title:
                continue

            a_tag = title_el if title_el.name == 'a' else title_el.find('a')
            if not a_tag:
                a_tag = item.find('a')

            link = a_tag.get('href', '') if a_tag else url
            if link and not link.startswith('http'):
                link = 'https://www.famewheels.com' + link

            price_text = '0'
            price_node = item.find(string=re.compile(r'(Lacs|PKR|Rs)', re.I))
            if price_node:
                price_text = price_node.strip()
            price = price_text

            text_content = item.get_text(separator=' ')
            year = '0'
            year_match = re.search(r'\b(19[89]\d|20[0-2]\d)\b', text_content)
            if year_match:
                year = year_match.group(1)

            mileage = '0'
            mileage_match = re.search(r'\b([\d,]+)\s*km\b', text_content, re.I)
            if mileage_match:
                mileage = mileage_match.group(1).replace(',', '')

            city = 'Unknown'
            city_node = item.find(class_=re.compile(r'location|city', re.I))
            if city_node:
                city = city_node.text.strip().split(',')[0]

            cars.append(CarListing(
                title=title, price=price, mileage=mileage, city=city,
                year=year, listing_url=link, platform='Famewheels'
            ))
        except Exception:
            continue

    print(f"[FameWheels Scraper] Extracted {len(cars)} listings")
    return cars