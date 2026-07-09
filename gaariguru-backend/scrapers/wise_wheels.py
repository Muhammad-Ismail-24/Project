"""
scrapers/wise_wheels.py (Gari.pk)
Fixed: Removed manual User-Agent override. Let curl_cffi handle the headers natively
to prevent TLS fingerprint mismatches that cause 403 blocks.
"""
from bs4 import BeautifulSoup
import re
from curl_cffi.requests import AsyncSession
from models.car_schema import CarListing

async def scrape_wise_wheels(url: str, context=None, search_filters: dict = None) -> list[CarListing]:
    make = search_filters.get('make', '').lower().replace("-", "") if search_filters else ""
    model = search_filters.get('model', '').lower().replace("-", "") if search_filters else ""
    
    param_list = []
    if make: param_list.append(f"c_make_0|{make}")
    if model: param_list.append(f"c_model_0|{model}")
    payload_str = "cars_mini/" + ",".join(param_list) + "/"
    ajax_url = "https://www.gari.pk/search-car-ajax.php"
    
    # THE FIX: Removed User-Agent. curl_cffi sets it perfectly for "chrome120" automatically.
    headers = {
        "X-Requested-With": "XMLHttpRequest",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": "https://www.gari.pk",
        "Referer": "https://www.gari.pk/"
    }
    
    try:
        async with AsyncSession(impersonate="chrome120") as session:
            await session.get("https://www.gari.pk/", timeout=15)
            resp = await session.post(ajax_url, data={"search_param": payload_str}, headers=headers, timeout=15)
            
            if resp.status_code != 200:
                print(f"[Gari.pk Debug] Failed with Status: {resp.status_code}")
                return []
            
            html = resp.text
            if not html or len(html) < 100:
                print(f"[Gari.pk Debug] Received empty response.")
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
            if not title or len(title) < 4: continue
            
            link = item.find('a')['href'] if item.find('a') else ""
            if link and not link.startswith('http'): link = 'https://www.gari.pk' + link
            
            price_el = item.find(class_=re.compile(r'price', re.I))
            price = price_el.get_text(strip=True) if price_el else '0'
            
            cars.append(CarListing(title=title, price=price, platform='Gari.pk', listing_url=link))
        except: continue
        
    print(f"[Gari.pk Scraper] Extracted {len(cars)} listings.")
    return cars