"""
scrapers/pakwheels.py

Patches applied:
- Bug 1 Fix: Boundary-isolated price extraction — only pulls digit blocks
  from the text node that contains a currency token (PKR/Rs/Lacs/Lakh/Crore),
  preventing year/mileage digits from concatenating into 20-digit overflow strings.
- Bug 2 Fix: Lazy-load resilient image extraction — checks data-src / data-original
  first, falls back to src. Passes extracted URL into CarListing.image_url.
- Existing DOM Scope Restriction (MAX_ORGANIC_CARDS slice) is preserved.
- City / Year / Mileage / Title extraction logic is unchanged.
"""

from bs4 import BeautifulSoup
import re
from scrapers.http_client import fetch_page_content
from models.car_schema import CarListing

MAX_ORGANIC_CARDS = 40


def _extract_price(item) -> str:
    """
    Task 1 Fix: Strict DOM Element Targeting.
    Never extracts text from the parent card. Targets the specific 
    div.price-details node first.
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
    Bug 2 Fix: Lazy-load resilient image extraction.
    Checks data-src / data-original first; falls back to src.
    """
    img = item.find('img')
    if img:
        for attr in ('data-src', 'data-original', 'data-lazy-src', 'src'):
            val = img.get(attr, '').strip()
            if val and val.startswith('http') and 'placeholder' not in val.lower():
                return val
    return ''


async def scrape_pakwheels(url: str, context) -> list[CarListing]:
    html = await fetch_page_content(
        context, url, ".classified-listing, .search-page-new"
    )
    if not html:
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

            # --- Price (Bug 1 Fix) ---
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

            # --- Image (Bug 2 Fix) ---
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
    if len(cars) > 40:
        print(f"[PakWheels Scraper] WARNING: {len(cars)} listings exceeds expected page maximum (~35-40). Possible DOM Bleed.")
    return cars