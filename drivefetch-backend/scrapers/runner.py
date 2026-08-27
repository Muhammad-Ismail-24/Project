from core.logger import get_logger
logger = get_logger(__name__)
"""
scrapers/runner.py

Migrated from Playwright to curl_cffi.
Uses a single AsyncSession with Chrome TLS impersonation for all platforms.

UPGRADES:
  - Added build_platform_search_url with is_budget_search flag.
  - Dynamic 70% budget floor calculation when min_budget is 0.
"""
import asyncio
import re
from curl_cffi.requests import AsyncSession
from scrapers.pakwheels import scrape_pakwheels
from scrapers.olx import scrape_olx
from scrapers.drive_pk import scrape_drive_pk
from scrapers.auto_deals import scrape_auto_deals
from scrapers.famewheels import scrape_famewheels
from scrapers.gari_pk import scrape_gari_pk
from scrapers.wise_wheels import scrape_wise_wheels
from scrapers.normalizer import normalize_listings, MAKE_ALIAS_MAP
from scrapers.url_builder import build_platform_search_url
from models.car_schema import CarListing

# Global semaphore: limits total concurrent outbound scraper connections
# across all coroutines within this process.
SCRAPER_SEMAPHORE = asyncio.Semaphore(10)

OLX_CITY_MAP = {
    "lahore":       "lahore_g4060673",
    "karachi":      "karachi_g4060695",
    "islamabad":    "islamabad_g4060615",
    "rawalpindi":   "rawalpindi_g4060681",
    "peshawar":     "peshawar_g4060698",
    "multan":       "multan_g4060678",
    "faisalabad":   "faisalabad_g4060677",
    "gujranwala":   "gujranwala_g4060679",
    "sialkot":      "sialkot_g4060680",
    "quetta":       "quetta_g4060699",
    "sargodha":         "sargodha_g4060684",
    "hyderabad":        "hyderabad_g4060693",
    "bahawalpur":       "bahawalpur_g4060653",
    "gujrat":           "gujrat_g4060663",
    "sahiwal":          "sahiwal_g4060683",
    "rahim yar khan":   "rahimyar-khan_g4060680",
    "sheikhupura":      "sheikhupura_g4060685",
    "okara":            "okara_g4060678",
    "jhelum":           "jhelum_g4060668",
    "mardan":           "mardan_g4060623",
    "abbottabad":       "abbottabad_g4060640",
    "attock":           "attock_g4060651",
    "mandi bahauddin":  "mandi-bahauddin_g4065538",
    "dera ghazi khan":  "dera-ghazi-khan_g4060658",
    "taxila":           "taxila_g4065567",
    "burewala":         "burewala_g4060654",
    "chakwal":          "chakwal_g4065543",
    "jhang":            "jhang_g1142",
    "bahawalnagar":     "bahawalnagar_g4060652",
    "kasur":            "kasur_g4060687",
    "toba tek singh":   "toba-tek-singh_g4060689",
    "layyah":           "layyah_g4065537",
    "mianwali":         "mianwali_g4060674",
    "khanewal":         "khanewal_g4060671",
    "daska":            "daska_g4060657",
    "chichawatni":      "chichawatni_g4065540",
    "muzaffargarh":     "muzaffargarh_g4060677",
    "sadiqabad":        "sadiqabad_g4060682",
    "chiniot":          "chiniot_g4060655",
    "wah cantt":        "wah_g4060692",
    "pakpattan":        "pakpattan_g4060679",
}

WISEWHEELS_CITY_MAP = {
    "islamabad":  "257",
    "rawalpindi": "86",
    "lahore":     "176",
}

async def execute_search_pipeline(
    make: str,
    model: str,
    city: str,
    max_budget: int = None,
    min_budget: int = 0,
    color: str = None,
    trim: str = None,
    min_year: int = 0,
    max_year: int = 0
) -> list[CarListing]:
    """Runs all platform scrapers concurrently using curl_cffi,
    flattens the results, normalizes them, and returns a clean capped list.
    """

    safe_make   = make or ""
    safe_model  = model or ""
    safe_city   = city or ""
    safe_color  = color or ""

    GENERIC_POWERTRAIN_TAGS = {
        "ev", "electric", "hev", "phev", "hybrid", 
        "petrol", "diesel", "cng", "awd", "fwd", "4x4", "4wd"
    }
    safe_trim = "" if (trim and trim.lower() in GENERIC_POWERTRAIN_TAGS) else (trim or "")
    safe_budget = int(max_budget) if max_budget else 0

    # Auto-calculate 70% budget floor if min_budget is 0 but max_budget exists
    if min_budget == 0 and safe_budget > 0:
        safe_min_budget = int(safe_budget * 0.70)
    else:
        safe_min_budget = int(min_budget) if min_budget else 0

    is_budget = safe_budget > 0 or safe_min_budget > 0

    cities_to_search = [c.strip() for c in re.split(r',|\band\b', safe_city) if c.strip()]
    if not cities_to_search:
        cities_to_search = [""]

    pw_urls          = []
    olx_tasks        = []
    drive_tasks      = []
    gari_tasks       = []
    wisewheels_tasks = []
    auto_deals_tasks = []
    famewheels_urls  = []

    PAGES_TO_FETCH = 2
    logger.info(f"[Runner] Query Pushdown active: fetching {PAGES_TO_FETCH} pages/platform.")

    for target_city in cities_to_search:
        c                = target_city.lower().replace(" ", "-")
        safe_make_lower  = safe_make.lower().replace(" ", "-")
        safe_model_lower = safe_model.lower().replace(" ", "-")
        safe_color_lower = safe_color.lower().replace(" ", "-") if safe_color else ""
        my = min_year if min_year > 0 else 1990
        mx = max_year if max_year > 0 else 2025

        search_filters = {
            'make':  safe_make_lower,
            'model': safe_model_lower,
            'city':  c,
            'trim':  safe_trim,
        }

        # Gari.pk
        gari_make  = safe_make_lower.replace('-', '') if safe_make_lower else 'toyota'
        gari_model = safe_model_lower.replace('-', '') if safe_model_lower else ''
        gari_city  = c if c else ''
        if gari_model and gari_city:
            gari_url = f"https://www.gari.pk/used-cars/{gari_make}/{gari_model}/{gari_city}-c/"
        elif gari_model:
            gari_url = f"https://www.gari.pk/used-cars/{gari_make}/{gari_model}/"
        else:
            gari_url = f"https://www.gari.pk/used-cars/{gari_make}/"
        gari_tasks.append((gari_url, search_filters))

        famewheels_urls.append(
            f"https://www.famewheels.com/used-cars"
            f"?make={safe_make_lower}&model={safe_model_lower}&city={c}"
        )

        for page in range(1, PAGES_TO_FETCH + 1):
            # PakWheels
            pw_make_slug = MAKE_ALIAS_MAP.get(safe_make_lower, safe_make_lower)
            pw_parts = ["https://www.pakwheels.com/used-cars/search/-"]
            if pw_make_slug:      pw_parts.append(f"mk_{pw_make_slug}")
            if safe_model_lower:  pw_parts.append(f"md_{safe_model_lower}")
            if c:                 pw_parts.append(f"ct_{c}")
            if safe_budget > 0 or safe_min_budget > 0:
                mx_b = safe_budget if safe_budget > 0 else ""
                pw_parts.append(f"pr_{safe_min_budget}_{mx_b}")
            if min_year > 0 or max_year > 0:
                                  pw_parts.append(f"yr_{my}_{mx}")
            if safe_color_lower:  pw_parts.append(f"cl_{safe_color_lower}")
            pw_base = "/".join(pw_parts)
            pw_base = build_platform_search_url(
                pw_base, "pakwheels", safe_model, safe_trim, is_budget_search=is_budget
            )
            pw_urls.append(pw_base + f"/?page={page}")

            # OLX
            olx_slug     = OLX_CITY_MAP.get(target_city.lower(), "")
            olx_category = f"{safe_make_lower}-cars_c84" if safe_make_lower else "cars_c84"
            olx_base_parts = ["https://www.olx.com.pk"]
            if olx_slug:
                olx_base_parts.append(olx_slug)
            olx_base_parts.append(olx_category)

            olx_q_parts = list(filter(None, [safe_model_lower]))
            if olx_q_parts:
                olx_base_parts.append("q-" + "-".join(olx_q_parts))

            olx_base = "/".join(olx_base_parts)
            olx_url = build_platform_search_url(
                olx_base, "olx", safe_model, safe_trim, is_budget_search=is_budget
            )

            olx_filters = []
            if safe_budget > 0 or safe_min_budget > 0:
                mx_b = safe_budget if safe_budget > 0 else ""
                olx_filters.append(f"price_between_{safe_min_budget}_to_{mx_b}")
            if min_year > 0 or max_year > 0:
                olx_filters.append(f"year_between_{my}_to_{mx}")

            filter_string = ",".join(olx_filters)
            query_parts   = ["sorting=desc-creation"]
            if filter_string:
                query_parts.append(f"filter={filter_string}")
            query_parts.append(f"page={page}")

            olx_url += "?" + "&".join(query_parts)
            olx_tasks.append((olx_url, search_filters))

            # Drive.pk
            drive_url = f"https://www.drivepk.com/cars/list?page={page}"
            if safe_make_lower:      drive_url += f"&brands={safe_make_lower.capitalize()}"
            if safe_min_budget > 0:  drive_url += f"&minPrice={safe_min_budget}"
            if safe_budget > 0:      drive_url += f"&maxPrice={safe_budget}"
            if min_year > 0:         drive_url += f"&minYear={min_year}"
            if max_year > 0:         drive_url += f"&maxYear={max_year}"
            if safe_color_lower:     drive_url += f"&colors={safe_color_lower.capitalize()}"
            if target_city:          drive_url += f"&cities={target_city.capitalize()}"
            drive_q_parts = list(filter(None, [safe_model]))
            drive_q_str   = " ".join(drive_q_parts).replace(" ", "%20")
            if drive_q_str:          drive_url += f"&q={drive_q_str}"
            drive_url = build_platform_search_url(
                drive_url, "drivepk", safe_model, safe_trim, is_budget_search=is_budget
            )
            drive_tasks.append((drive_url, search_filters))

            # AutoDeals
            ad_parts = ["https://autodeals.pk/used-cars/search/-"]
            if c:               ad_parts.append(f"ct_{c}")
            ad_min = safe_min_budget if safe_min_budget > 0 else 0
            if safe_budget > 0: ad_parts.append(f"minP_{ad_min}/maxP_{safe_budget}")
            if min_year > 0:    ad_parts.append(f"minY_{min_year}")
            if max_year > 0:    ad_parts.append(f"maxY_{max_year}")
            ad_search = "-".join(filter(None, [safe_make_lower, safe_model_lower]))
            if ad_search:       ad_parts.append(f"searchStr_{ad_search}")
            ad_base = "/".join(ad_parts)
            ad_base = build_platform_search_url(
                ad_base, "autodeals", safe_model, safe_trim, is_budget_search=is_budget
            )
            ad_url = ad_base + f"?page={page}"
            auto_deals_tasks.append((ad_url, search_filters))

            # WiseWheels
            ww_url = f"https://wisewheels.com.pk/used-cars?price_from={safe_min_budget}&page={page}"
            ww_city_id = WISEWHEELS_CITY_MAP.get(c, "")
            if ww_city_id:       ww_url += f"&city_id={ww_city_id}"
            if safe_make_lower:  ww_url += f"&make={safe_make_lower}"
            if safe_model_lower: ww_url += f"&model={safe_model_lower}"
            if safe_budget > 0:  ww_url += f"&price_to={safe_budget}"
            ww_url = build_platform_search_url(
                ww_url, "wisewheels", safe_model, safe_trim, is_budget_search=is_budget
            )
            wisewheels_tasks.append((ww_url, search_filters))

    logger.info(
        f"[Pipeline] Search -> Make={safe_make}, Model={safe_model}, "
        f"Cities={cities_to_search}, Color={safe_color}, Trim={safe_trim}, "
        f"Year={min_year}-{max_year}, Budget={safe_min_budget}-{safe_budget}"
    )

    async def bounded_task(coro):
        async with SCRAPER_SEMAPHORE:
            return await coro

    futures = []
    async with AsyncSession(impersonate="chrome120") as session:
        for url in pw_urls:
            futures.append(bounded_task(scrape_pakwheels(url, session)))
        for url, filters in olx_tasks:
            futures.append(bounded_task(scrape_olx(url, session, filters)))
        for url, filters in drive_tasks:
            futures.append(bounded_task(scrape_drive_pk(url, session, filters)))
        for url, filters in gari_tasks:
            futures.append(bounded_task(scrape_gari_pk(url, session, filters)))
        for url, filters in wisewheels_tasks:
            futures.append(bounded_task(scrape_wise_wheels(url, session, filters)))
        for url, filters in auto_deals_tasks:
            futures.append(bounded_task(scrape_auto_deals(url, session, filters)))
        for url in famewheels_urls:
            futures.append(bounded_task(scrape_famewheels(url, session)))

        all_results = await asyncio.gather(*futures, return_exceptions=True)

    raw_listings = []
    for result_set in all_results:
        if isinstance(result_set, list):
            raw_listings.extend(result_set)

    clean_listings, is_empty = normalize_listings(
        raw_listings=raw_listings,
        requested_make=make,
        requested_model=model,
        requested_city=city,
        requested_budget=max_budget,
        requested_color=color,
        requested_trim=trim,
        min_budget=safe_min_budget,
        min_year=min_year,
        max_year=max_year,
        debug=True
    )

    return clean_listings, is_empty