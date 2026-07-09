"""
scrapers/runner.py
Fixed: Migrated to Browserless.io to bypass Render's 512MB memory limit.
Updated: Enabled Stealth Mode to bypass Cloudflare/403 blocks.
"""
import asyncio
import json
import re
import os
from concurrent.futures import ThreadPoolExecutor
from playwright.async_api import async_playwright
from scrapers.pakwheels import scrape_pakwheels
from scrapers.olx import scrape_olx
from scrapers.drive_pk import scrape_drive_pk
from scrapers.auto_deals import scrape_auto_deals
from scrapers.famewheels import scrape_famewheels
from scrapers.wise_wheels import scrape_wise_wheels
from scrapers.normalizer import normalize_listings
from models.car_schema import CarListing

OLX_CITY_MAP = {
    "lahore": "lahore_g4060675",
    "karachi": "karachi_g4060695",
    "islamabad": "islamabad_g4060615",
    "rawalpindi": "rawalpindi_g4060676",
    "peshawar": "peshawar_g4060698",
    "multan": "multan_g4060678",
    "faisalabad": "faisalabad_g4060677",
    "gujranwala": "gujranwala_g4060679",
}

async def execute_search_pipeline(make: str, model: str, city: str, max_budget: int = None, color: str = None, trim: str = None, min_year: int = 0, max_year: int = 0) -> list[CarListing]:
    safe_make = make or ""
    safe_model = model or ""
    safe_city = city or ""
    safe_color = color or ""
    safe_trim = trim or ""
    safe_budget = int(max_budget) if max_budget else 0

    cities_to_search = [c.strip() for c in re.split(r',|\band\b', safe_city) if c.strip()]
    if not cities_to_search: cities_to_search = [""]

    pw_urls = []
    famewheels_urls = []
    
    olx_tasks = []
    drive_tasks = []
    wisewheels_tasks = []
    auto_deals_tasks = []
    
    PAGES_TO_FETCH = 2
    print(f"[Runner] Query Pushdown Dividend active: fetching {PAGES_TO_FETCH} pages/platform.")
    
    for target_city in cities_to_search:
        c = target_city.lower().replace(" ", "-")
        safe_make_lower = safe_make.lower().replace(" ", "-")
        safe_model_lower = safe_model.lower().replace(" ", "-")
        safe_trim_dash = safe_trim.lower().replace(" ", "-") if safe_trim else ""
        safe_color_lower = safe_color.lower().replace(" ", "-") if safe_color else ""
        my = min_year if min_year > 0 else 1990
        mx = max_year if max_year > 0 else 2025

        city_filters = {
            'make': safe_make_lower,
            'model': safe_model_lower,
            'city': c,
            'trim': safe_trim_dash
        }

        gari_make = safe_make_lower.replace('-', '') if safe_make_lower else 'toyota'
        gari_model = safe_model_lower.replace('-', '') if safe_model_lower else ''
        gari_city = c if c else ''
        if gari_model and gari_city:
            gari_url = f"https://www.gari.pk/used-cars/{gari_make}/{gari_model}/{gari_city}-c/"
        elif gari_model:
            gari_url = f"https://www.gari.pk/used-cars/{gari_make}/{gari_model}/"
        else:
            gari_url = f"https://www.gari.pk/used-cars/{gari_make}/"
            
        wisewheels_tasks.append((gari_url, city_filters))
        famewheels_urls.append(f"https://www.famewheels.com/used-cars?make={safe_make_lower}&model={safe_model_lower}&city={c}")

        for page in range(1, PAGES_TO_FETCH + 1):
            pw_parts = ["https://www.pakwheels.com/used-cars/search/-"]
            if safe_make_lower: pw_parts.append(f"mk_{safe_make_lower}")
            if safe_model_lower: pw_parts.append(f"md_{safe_model_lower}")
            if safe_trim_dash: pw_parts.append(f"vg_{safe_trim_dash}")
            if c: pw_parts.append(f"ct_{c}")
            if safe_budget > 0: pw_parts.append(f"pr_0_{safe_budget}")
            if min_year > 0 or max_year > 0: pw_parts.append(f"yr_{my}_{mx}")
            if safe_color_lower: pw_parts.append(f"cl_{safe_color_lower}")
            pw_urls.append("/".join(pw_parts) + f"/?page={page}")

            olx_slug = OLX_CITY_MAP.get(c, "")
            olx_category = f"{safe_make_lower}-cars_c84" if safe_make_lower else "cars_c84"
            olx_base_parts = ["https://www.olx.com.pk"]
            if olx_slug: olx_base_parts.append(olx_slug)
            olx_base_parts.append(olx_category)
            q_parts = list(filter(None, [safe_model_lower, safe_trim_dash]))
            if q_parts:
                olx_base_parts.append("q-" + "-".join(q_parts))
            olx_url = "/".join(olx_base_parts)
            olx_filters = []
            if safe_make_lower: olx_filters.append(f"make_eq_{safe_make_lower}")
            if safe_budget > 0: olx_filters.append(f"price_between_0_to_{safe_budget}")
            if min_year > 0 or max_year > 0: olx_filters.append(f"year_between_{my}_to_{mx}")
            filter_string = "%2C".join(olx_filters)
            if filter_string:
                olx_url += f"?filter={filter_string}&page={page}"
            else:
                olx_url += f"?page={page}"
            olx_tasks.append((olx_url, city_filters))

            drive_url = f"https://www.drivepk.com/cars/list?page={page}"
            if safe_make_lower: drive_url += f"&brands={safe_make_lower.capitalize()}"
            if safe_budget > 0: drive_url += f"&maxPrice={safe_budget}"
            if min_year > 0: drive_url += f"&minYear={min_year}"
            if max_year > 0: drive_url += f"&maxYear={max_year}"
            if safe_color_lower: drive_url += f"&colors={safe_color_lower.capitalize()}"
            if target_city: drive_url += f"&cities={target_city.capitalize()}"
            drive_q_parts = filter(None, [safe_model, safe_trim])
            drive_q_str = " ".join(drive_q_parts).replace(" ", "%20")
            if drive_q_str: drive_url += f"&q={drive_q_str}"
            drive_tasks.append((drive_url, city_filters))

            ad_parts = ["https://autodeals.pk/used-cars/search/-"]
            if c: ad_parts.append(f"ct_{c}")
            if safe_budget > 0: ad_parts.append(f"minP_0/maxP_{safe_budget}")
            if min_year > 0: ad_parts.append(f"minY_{min_year}")
            if max_year > 0: ad_parts.append(f"maxY_{max_year}")
            ad_search = "-".join(filter(None, [safe_make_lower, safe_model_lower, safe_trim_dash]))
            if ad_search: ad_parts.append(f"searchStr_{ad_search}")
            ad_url = "/".join(ad_parts) + f"?page={page}"
            auto_deals_tasks.append((ad_url, city_filters))

    futures = []

    async with async_playwright() as p:
        # 1. Grab the key from the environment
        BROWSERLESS_KEY = os.getenv("BROWSERLESS_API_KEY")
        
        # 2. Build the connection string with stealth mode enabled to bypass Cloudflare
        browserless_url = f"wss://chrome.browserless.io?token={BROWSERLESS_KEY}&stealth=true"

        # 3. Connect to the remote Browserless server
        browser = await p.chromium.connect_over_cdp(browserless_url)
        
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            java_script_enabled=True
        )
        
        for url in pw_urls: futures.append(scrape_pakwheels(url, context))
        for url, filters in olx_tasks: futures.append(scrape_olx(url, context, filters))
        for url, filters in drive_tasks: futures.append(scrape_drive_pk(url, context, filters))
        for url, filters in wisewheels_tasks: futures.append(scrape_wise_wheels(url, context, filters))
        for url, filters in auto_deals_tasks: futures.append(scrape_auto_deals(url, context, filters))
        for url in famewheels_urls: futures.append(scrape_famewheels(url))

        all_results = await asyncio.gather(*futures, return_exceptions=True)
        await browser.close()

    pw_count, olx_count, drive_count = len(pw_urls), len(olx_tasks), len(drive_tasks)
    idx = 0
    def _safe_len(r): return len(r) if isinstance(r, list) else 0

    pw_total = sum(_safe_len(r) for r in all_results[idx : idx + pw_count]); idx += pw_count
    olx_total = sum(_safe_len(r) for r in all_results[idx : idx + olx_count]); idx += olx_count
    drive_total = sum(_safe_len(r) for r in all_results[idx : idx + drive_count]); idx += drive_count
    
    gari_count = len(wisewheels_tasks)
    auto_deals_count_len = len(auto_deals_tasks)
    famewheels_count_len = len(famewheels_urls)

    gari_total = sum(_safe_len(r) for r in all_results[idx : idx + gari_count]); idx += gari_count
    auto_deals_total = sum(_safe_len(r) for r in all_results[idx : idx + auto_deals_count_len]); idx += auto_deals_count_len
    famewheels_total = sum(_safe_len(r) for r in all_results[idx : idx + famewheels_count_len]); idx += famewheels_count_len

    print(f"[Pipeline] PakWheels returned   {pw_total} raw listings ({pw_count} pages)")
    print(f"[Pipeline] OLX returned         {olx_total} raw listings ({olx_count} pages)")
    print(f"[Pipeline] Drive.pk returned    {drive_total} raw listings ({drive_count} pages)")
    print(f"[Pipeline] Gari.pk returned     {gari_total} raw listings")

    raw_listings = []
    for result_set in all_results:
        if isinstance(result_set, list):
            raw_listings.extend(result_set)
        else:
            print(f"[Runner] Warning: Scraper failed with error: {result_set}")
            
    print(f"[Pipeline] Total raw listings: {len(raw_listings)}")

    clean_listings, is_empty = normalize_listings(
        raw_listings=raw_listings, 
        requested_make=make, 
        requested_model=model,
        requested_city=city,
        requested_budget=max_budget,
        requested_color=color,
        requested_trim=trim,
        min_year=min_year,
        max_year=max_year,
        debug=True 
    )

    return clean_listings, is_empty