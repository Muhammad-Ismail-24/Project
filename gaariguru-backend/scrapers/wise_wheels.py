"""
scrapers/wise_wheels.py (Gari.pk)

Uses curl_cffi to hit Gari.pk's hidden AJAX endpoint directly.
Impersonates Chrome to bypass their TLS fingerprint checks.
"""
from bs4 import BeautifulSoup
import re
from curl_cffi.requests import AsyncSession
from models.car_schema import CarListing


async def scrape_wise_wheels(url: str, session=None, search_filters: dict = None) -> list[CarListing]:
    """Scrapes Gari.pk via their AJAX search endpoint using curl_cffi."""
    make = search_filters.get('make', '').lower().replace("-", "") if search_filters else ""
    model = search_filters.get('model', '').lower().replace("-", "") if search_filters else ""

    param_list = []
    if make: param_list.append(f"c_make_0|{make}")
    if model: param_list.append(f"c_model_0|{model}")
    payload_str = "cars_mini/" + ",".join(param_list) + "/"
    ajax_url = "https://www.gari.pk/search-car-ajax.php"

    headers = {
        "X-Requested-With": "XMLHttpRequest",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": "https://www.gari.pk",
        "Referer": "https://www.gari.pk/"
    }

    try:
        # Use a dedicated session for Gari.pk since it needs a cookie-priming GET first
        async with AsyncSession(impersonate="chrome120") as gari_session:
            await gari_session.get("https://www.gari.pk/", timeout=15)
            resp = await gari_session.post(ajax_url, data={"search_param": payload_str}, headers=headers, timeout=15)

            if resp.status_code != 200:
                print(f"[Gari.pk Scraper] Failed with Status: {resp.status_code}")
                return []

            html = resp.text
            if not html or len(html) < 100:
                print(f"[Gari.pk Scraper] Received empty response.")
                return []

    except Exception as e:
        print(f"[Gari.pk Scraper] Connection error: {e}")
        return []

    soup = BeautifulSoup(html, 'html.parser')
    items = soup.find_all('div', class_=re.compile(r'(block_ss|search_item|car-item)', re.I))

    cars = []
    for item in items[:40]:
        try:
            title_el = item.find(['h2', 'h3', 'a'])
            title = title_el.get_text(strip=True) if title_el else ""
            if not title or len(title) < 4:
                continue

            link = item.find('a')['href'] if item.find('a') else ""
            if link and not link.startswith('http'):
                link = 'https://www.gari.pk' + link

            price_el = item.find(class_=re.compile(r'price', re.I))
            price = price_el.get_text(strip=True) if price_el else '0'

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
            city_el = item.find(class_=re.compile(r'(location|city)', re.I))
            if city_el:
                city = city_el.get_text(strip=True).split(',')[0]

            cars.append(CarListing(
                title=title, price=price, mileage=mileage, city=city,
                year=year, listing_url=link, platform='Gari.pk'
            ))
        except Exception:
            continue

    print(f"[Gari.pk Scraper] Extracted {len(cars)} listings.")
    return cars