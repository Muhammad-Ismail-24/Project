"""
scrapers/pakwheels.py

Migrated from Playwright to curl_cffi.
Accepts a curl_cffi AsyncSession and fetches HTML directly.
"""
from bs4 import BeautifulSoup
import re
from models.car_schema import CarListing

MAX_ORGANIC_CARDS = 40


def _extract_price(item) -> str:
    """
    Strict DOM Element Targeting.
    Targets the specific div.price-details node first.
    Returns the FULL raw text so the Normalizer can detect Lacs/Crore.
    """
    price_el = item.find('div', class_=re.compile(r'price-details|generic-green', re.I))
    if price_el:
        raw = price_el.get_text(separator=' ', strip=True)
        if raw:
            return raw
    return '0'


def _extract_image(item) -> str:
    """
    Lazy-load resilient image extraction.
    Checks data-src / data-original first; falls back to src.
    """
    img = item.find('img')
    if img:
        for attr in ('data-src', 'data-original', 'data-lazy-src', 'src'):
            val = img.get(attr, '').strip()
            if val and val.startswith('http') and 'placeholder' not in val.lower():
                return val
    return ''


async def scrape_pakwheels(url: str, session) -> list[CarListing]:
    """Scrapes PakWheels using a shared curl_cffi AsyncSession."""
    try:
        response = await session.get(url, timeout=20)
        if response.status_code != 200:
            print(f"[PakWheels Scraper] HTTP {response.status_code} for {url}")
            return []
        html = response.text
    except Exception as e:
        print(f"[PakWheels Scraper] Request failed: {e}")
        return []

    if not html or len(html) < 500:
        return []

    soup = BeautifulSoup(html, 'html.parser')
    cars = []

    items = soup.find_all('li', class_=re.compile(r'classified-listing', re.I))
    if not items:
        items = soup.find_all('div', class_=re.compile(r'ad-container', re.I))

    if len(items) > MAX_ORGANIC_CARDS:
        items = items[:MAX_ORGANIC_CARDS]

    for item in items:
        try:
            # --- Title ---
            title_el = item.find(['h2', 'h3', 'h4'])
            if not title_el:
                title_el = item.find('a', string=re.compile(r'\w+'))
            if not title_el:
                continue

            title = title_el.get_text(strip=True)
            if not title:
                continue

            a_tag = title_el if title_el.name == 'a' else title_el.find('a')
            if not a_tag:
                a_tag = item.find('a')

            link = a_tag.get('href', '').strip() if a_tag else url
            if link and not link.startswith('http'):
                link = 'https://www.pakwheels.com' + link

            # --- Price ---
            price = _extract_price(item)

            # --- Year & Mileage ---
            year, mileage = '0', '0'
            text_content = item.get_text(separator=' ')

            year_match = re.search(r'\b(19[89]\d|20[0-2]\d)\b', text_content)
            if year_match:
                year = year_match.group(1)

            mileage_match = re.search(r'\b([\d,]+)\s*km\b', text_content, re.I)
            if mileage_match:
                mileage = mileage_match.group(1).replace(',', '')

            # --- City ---
            city_text = 'Unknown'
            city_ul = item.find('ul', class_=re.compile(r'search-vehicle-info\b', re.I))
            if city_ul:
                li = city_ul.find('li')
                if li:
                    extracted_text = li.get_text(strip=True)
                    if extracted_text and not extracted_text.isdigit():
                        if not re.search(r'(km|cc|petrol|diesel|hybrid|automatic|manual)', extracted_text, re.I):
                            city_text = extracted_text

            # --- Image ---
            image_url = _extract_image(item)

            cars.append(CarListing(
                title=title,
                price=price,
                mileage=mileage,
                city=city_text,
                year=year,
                listing_url=link,
                image_url=image_url,
                platform='PakWheels'
            ))
        except Exception:
            continue

    print(f"[PakWheels Scraper] Extracted {len(cars)} listings")
    return cars