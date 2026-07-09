"""
scrapers/famewheels.py
Fixed: Declared the cars list to prevent NameError exceptions during runner flattening.
"""
from bs4 import BeautifulSoup
import re
from scrapers.http_client import fetch_html
from models.car_schema import CarListing

async def scrape_famewheels(url: str) -> list[CarListing]:
    html = await fetch_html(url)
    if not html: return []
    soup = BeautifulSoup(html, 'html.parser')
    
    cars = []  # <--- CRITICAL FIX: Stops the 'cars is not defined' pipeline leak
    
    for item in soup.find_all(['div', 'li', 'article'], class_=re.compile(r'(car-card|listing|col-md-4|ad-container)', re.I)):
        try:
            title_el = item.find(['h2', 'h3', 'h4'])
            if not title_el:
                title_el = item.find('a', text=re.compile(r'[A-Za-z]+'))
            if not title_el: continue
            
            title = title_el.text.strip()
            if not title: continue
            
            a_tag = title_el if title_el.name == 'a' else title_el.find('a')
            if not a_tag:
                a_tag = item.find('a')
                
            link = a_tag.get('href', '') if a_tag else url
            if link and not link.startswith('http'): 
                link = 'https://www.famewheels.com' + link
                
            price_text = '0'
            price_node = item.find(text=re.compile(r'(Lacs|PKR|Rs)', re.I))
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
                
            cars.append(CarListing(title=title, price=price, mileage=mileage, city=city, year=year, listing_url=link, platform='Famewheels'))
        except Exception:
            pass
            
    return cars