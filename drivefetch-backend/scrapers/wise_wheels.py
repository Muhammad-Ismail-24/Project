"""
scrapers/wise_wheels.py (WiseWheels.com.pk)

API INTERCEPTION REWRITE:
WiseWheels uses Next.js Client-Side Rendering. The initial HTML only contains 
Mantine UI skeleton loaders. This scraper bypasses the HTML DOM entirely and 
intercepts the raw JSON from their backend search API.

FIX: Added strict type-checking to prevent 'list' object attribute crashes 
when the API returns a raw JSON array instead of a dictionary object.
"""
import urllib.parse
from models.car_schema import CarListing
from datetime import datetime, timezone

MAX_ORGANIC_CARDS = 40

STANDARD_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://wisewheels.com.pk/",
}

async def scrape_wise_wheels(url: str, session, search_filters: dict = None) -> list[CarListing]:
    
    # Transform the frontend URL into the backend API endpoint
    api_url = url.replace("https://wisewheels.com.pk/used-cars", "https://api.wisewheels.com.pk/client/v1/used-cars/search")
    
    try:
        print(f"[WiseWheels API] Intercepting: {api_url}")
        response = await session.get(api_url, headers=STANDARD_HEADERS, timeout=15)
        
        if response.status_code != 200:
            print(f"[WiseWheels ❌] API HTTP Error: {response.status_code}")
            return []
            
        data = response.json()
    except Exception as e:
        print(f"[WiseWheels ❌] API Request Failed: {e}")
        return []

    # --- SAFELY EXTRACT ITEMS ARRAY ---
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = data.get('data', {}).get('items', [])
        if not items and 'data' in data and isinstance(data['data'], list):
            items = data['data']
        elif not items and 'items' in data:
            items = data['items']
    else:
        items = []

    if not items:
        # Safely log keys only if it's a dict to prevent further list crashes
        schema_info = list(data.keys()) if isinstance(data, dict) else f"Raw type: {type(data)}"
        print(f"[WiseWheels ❌] API returned 0 items. Schema: {schema_info}")
        return []

    # --- SCHEMA DISCOVERY LOG ---
    # This prints the dictionary structure of the first car so we can map exact keys
    print(f"[WiseWheels API] Successfully fetched {len(items)} raw JSON listings.")
    if isinstance(items[0], dict):
        print(f"[WiseWheels Schema] First item keys: {list(items[0].keys())}")
    
    cars = []
    
    for item in items[:MAX_ORGANIC_CARDS]:
        try:
            # Flexible dictionary extraction with fallbacks
            
            # Title
            title = item.get('title') or item.get('name') 
            if not title:
                make = item.get('make', {}).get('name', '') if isinstance(item.get('make'), dict) else item.get('make', '')
                model = item.get('model', {}).get('name', '') if isinstance(item.get('model'), dict) else item.get('model', '')
                variant = item.get('variant', {}).get('name', '') if isinstance(item.get('variant'), dict) else item.get('variant', '')
                title = f"{make} {model} {variant}".strip()

            # Price
            price = str(item.get('price') or item.get('price_pkr', '0'))
            
            # Year & Mileage
            year = str(item.get('year') or item.get('model_year', '0'))
            mileage = str(item.get('mileage') or item.get('milage', '0'))
            
            # City
            city = "Unknown"
            if isinstance(item.get('city'), dict):
                city = item['city'].get('name', 'Unknown')
            elif isinstance(item.get('city'), str):
                city = item['city']
                
            # Listing URL
            slug = item.get('slug', '')
            ad_id = str(item.get('id') or item.get('ad_id', ''))
            
            if slug and ad_id:
                link = f"https://wisewheels.com.pk/used-cars/{slug}-AD-{ad_id}"
            else:
                link = url
                
            # Image URL
            image_url = ''
            images = item.get('images', []) or item.get('media', [])
            if images and isinstance(images, list):
                first_img = images[0]
                if isinstance(first_img, dict):
                    # Check for direct URL or S3 path
                    path = first_img.get('url') or first_img.get('path') or first_img.get('image_url', '')
                    if path and not path.startswith('http'):
                        image_url = f"https://s3.ap-southeast-2.amazonaws.com/media.wisewheels/{path}"
                    else:
                        image_url = path
                elif isinstance(first_img, str):
                    image_url = first_img
            elif isinstance(images, str):
                image_url = images

            # Age (Assuming standard ISO timestamp in createdAt)
            age_days = 999
            created_at = item.get('created_at') or item.get('updated_at')
            if created_at:
                try:
                    # Handle basic ISO formats
                    dt_str = created_at.replace('Z', '+00:00')
                    dt = datetime.fromisoformat(dt_str)
                    delta = datetime.now(timezone.utc) - dt
                    age_days = max(0, delta.days)
                except Exception:
                    pass

            if price == '0' and year == '0':
                continue
                
            cars.append(CarListing(
                title=title,
                price=price,
                mileage=mileage,
                city=city,
                year=year,
                listing_url=link,
                image_url=image_url or None,
                platform='WiseWheels',
                age_days=age_days,
            ))

        except Exception as e:
            print(f"[WiseWheels Mapping Error] Failed to extract JSON node: {e}")
            continue

    print(f"[WiseWheels Scraper] Extracted {len(cars)} formatted listings from API.")
    return cars