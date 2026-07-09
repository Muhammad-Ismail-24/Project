"""
scrapers/olx.py
Fixed: Routed through fetch_html (curl_cffi) instead of Playwright to bypass Cloudflare Turnstile blocks.
"""
from bs4 import BeautifulSoup
import re
import json
from scrapers.http_client import fetch_html
from models.car_schema import CarListing

MAX_ORGANIC_CARDS = 35

async def scrape_olx(url: str, context, search_filters: dict = None) -> list[CarListing]:
    # THE FIX: Use fetch_html to trigger the curl_cffi TLS spoofer
    html = await fetch_html(url)
    if not html: return []

    soup = BeautifulSoup(html, 'html.parser')
    cars = []
    
    hits = []
    for s in soup.find_all('script'):
        content = s.string or ''
        
        match = re.search(r'window\.state\s*=\s*({.*?});', content, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(1))
                alg_hits = data.get('algolia', {}).get('content', {}).get('hits', [])
                if alg_hits: hits.extend(alg_hits); break
            except Exception: pass
            
        elif s.get('id') == '__NEXT_DATA__':
            try:
                data = json.loads(content)
                items_arr = data.get("props", {}).get("pageProps", {}).get("initialState", {}).get("listingSearch", {}).get("items", [])
                if items_arr: hits.extend(items_arr)
                
                if not hits:
                    apollo = data.get("props", {}).get("pageProps", {}).get("apolloState", {})
                    if apollo:
                        for k, v in apollo.items():
                            if isinstance(v, dict) and "title" in v and "price" in v:
                                if v.get('__typename') == 'Item' or k.startswith('Item:'):
                                    status = v.get('status', {})
                                    if isinstance(status, dict) and status.get('display') and status.get('display') != 'ACTIVE':
                                        continue
                                    if 'id' not in v and k.startswith('Item:'): v['id'] = k.split(':')[1]
                                    hits.append(v)
                if hits: break
            except Exception: pass

    if not hits:
        print(f"[OLX Scraper] ⚠ JSON State missing for {url}. Attempting Visual DOM Fallback...")
        cards = soup.find_all('li', attrs={'aria-label': 'Listing'})
        for card in cards[:MAX_ORGANIC_CARDS]:
            try:
                title = card.find('h2').text if card.find('h2') else card.find('a')['title']
                link = 'https://www.olx.com.pk' + card.find('a')['href']
                price = card.find(attrs={'aria-label': 'Price'}).text
                cars.append(CarListing(title=title, price=price, platform='OLX', listing_url=link))
            except: continue
        return cars

    hits = hits[:MAX_ORGANIC_CARDS]
    for item in hits:
        try:
            title = item.get('title', '')
            if not title: continue
            
            raw_price = item.get('price', {})
            price = str(raw_price.get('display') or raw_price.get('value') or '0') if isinstance(raw_price, dict) else str(raw_price or '0')
            
            params = item.get('parameters', []) or item.get('main_info', [])
            year = '0'
            mileage = '0'
            for p in (params if isinstance(params, list) else []):
                if isinstance(p, dict):
                    k = str(p.get('key') or p.get('name') or '').lower()
                    v = str(p.get('value') or p.get('value_name') or p.get('displayValue') or '')
                    if 'year' in k: year = v
                    elif 'mileage' in k or 'km' in k: mileage = v
            
            city = 'Unknown'
            loc_data = item.get('locations') or item.get('location')
            if isinstance(loc_data, list) and loc_data:
                for loc in loc_data:
                    if isinstance(loc, dict) and loc.get('level') == 2: 
                        city = loc.get('name', 'Unknown')
                        break
            
            raw_id = str(item.get('id') or item.get('objectID') or '')
            item_id = re.sub(r'\D', '', raw_id)
            raw_slug = item.get('slug') or re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-') or 'vehicle'
            link = f"https://www.olx.com.pk/item/{raw_slug}-iid-{item_id}" if len(item_id) > 7 else url
            
            cars.append(CarListing(title=title, price=price, mileage=mileage, city=city, year=year, listing_url=link, platform='OLX'))
        except Exception:
            continue

    print(f"[OLX Scraper] Extracted {len(cars)} listings via Next.js JSON")
    return cars