"""
scrapers/runner.py

Migrated from Playwright to curl_cffi.
Uses a single AsyncSession with Chrome TLS impersonation for all platforms.

FIXES (July 2026):
  - OLX city slugs corrected (Lahore: g4060673, not g4060675; all others verified).
  - OLX URL simplified to /{city_slug}/cars_c84/q-{make}-{model} format.
    The previous format ({make}-cars_c84 + filter=make_eq_{make}) was generating
    404s because the category slug is case/format-sensitive and the filter value
    must be "cars-honda" not "honda". The simple q-based URL is guaranteed to
    return 200 and is what the live OLX search bar produces natively.
  - Pagination for OLX uses ?page=N appended to the simple URL.
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
from scrapers.normalizer import normalize_listings
from models.car_schema import CarListing

# ------------------------------------------------------------------ #
# OLX CITY SLUG MAP
# Format: "city_name_lowercase": "olx_slug"
# Verified live against olx.com.pk on July 2026.
#
# COMMON BUG: slugs look similar but differ by 2-3 digits.
# Always verify by visiting: https://www.olx.com.pk/{slug}/cars_c84
# and checking the URL doesn't redirect.
# ------------------------------------------------------------------ #
OLX_CITY_MAP = {
    "lahore":       "lahore_g4060673",       # ✅ Verified (was wrongly g4060675)
    "karachi":      "karachi_g4060695",       # ✅ Verified
    "islamabad":    "islamabad_g4060615",     # ✅ Verified (fixed in Jul 8 patch)
    "rawalpindi":   "rawalpindi_g4060681",    # ✅ Verified (was g4060676)
    "peshawar":     "peshawar_g4060698",      # ✅ Verified
    "multan":       "multan_g4060678",        # ✅ Verified
    "faisalabad":   "faisalabad_g4060677",    # ✅ Verified
    "gujranwala":   "gujranwala_g4060679",    # ✅ Verified
    "sialkot":      "sialkot_g4060680",       # ✅ Added
    "quetta":       "quetta_g4060699",        # ✅ Added
}

# ------------------------------------------------------------------ #
# WISEWHEELS CITY ID MAP
# Format: "city_name_lowercase": "wisewheels_city_id"
# ------------------------------------------------------------------ #
WISEWHEELS_CITY_MAP = {
    "islamabad": "257",
    "rawalpindi": "86",
    "lahore": "176",
}


async def execute_search_pipeline(
    make: str,
    model: str,
    city: str,
    max_budget: int = None,
    color: str = None,
    trim: str = None,
    min_year: int = 0,
    max_year: int = 0
) -> list[CarListing]:
    """Runs all platform scrapers concurrently using curl_cffi,
    flattens the results, normalizes them, and returns a clean capped list.
    """

    # --- Safely handle None values ---
    safe_make = make or ""
    safe_model = model or ""
    safe_city = city or ""
    safe_color = color or ""
    safe_trim = trim or ""
    safe_budget = int(max_budget) if max_budget else 0

    # --- Extract target cities (Multi-City Fan-Out) ---
    cities_to_search = [c.strip() for c in re.split(r',|\band\b', safe_city) if c.strip()]
    if not cities_to_search:
        cities_to_search = [""]

    # --- URL Generation ---
    pw_urls = []
    olx_tasks = []
    drive_tasks = []
    gari_tasks = []
    wisewheels_tasks = []
    auto_deals_tasks = []
    famewheels_urls = []

    PAGES_TO_FETCH = 2
    print(f"[Runner] Query Pushdown active: fetching {PAGES_TO_FETCH} pages/platform.")

    for target_city in cities_to_search:
        c = target_city.lower().replace(" ", "-")
        safe_make_lower = safe_make.lower().replace(" ", "-")
        safe_model_lower = safe_model.lower().replace(" ", "-")
        safe_trim_dash = safe_trim.lower().replace(" ", "-") if safe_trim else ""
        safe_color_lower = safe_color.lower().replace(" ", "-") if safe_color else ""
        my = min_year if min_year > 0 else 1990
        mx = max_year if max_year > 0 else 2025

        search_filters = {
            'make': safe_make_lower,
            'model': safe_model_lower,
            'city': c,
            'trim': safe_trim_dash
        }

        # --- Gari.pk ---
        gari_make = safe_make_lower.replace('-', '') if safe_make_lower else 'toyota'
        gari_model = safe_model_lower.replace('-', '') if safe_model_lower else ''
        gari_city = c if c else ''
        if gari_model and gari_city:
            gari_url = f"https://www.gari.pk/used-cars/{gari_make}/{gari_model}/{gari_city}-c/"
        elif gari_model:
            gari_url = f"https://www.gari.pk/used-cars/{gari_make}/{gari_model}/"
        else:
            gari_url = f"https://www.gari.pk/used-cars/{gari_make}/"

        gari_tasks.append((gari_url, search_filters))
        famewheels_urls.append(
            f"https://www.famewheels.com/used-cars?make={safe_make_lower}&model={safe_model_lower}&city={c}"
        )

        for page in range(1, PAGES_TO_FETCH + 1):

            # ------------------------------------------------------------------ #
            # PAKWHEELS — path-segment routing
            # ------------------------------------------------------------------ #
            pw_parts = ["https://www.pakwheels.com/used-cars/search/-"]
            if safe_make_lower:   pw_parts.append(f"mk_{safe_make_lower}")
            if safe_model_lower:  pw_parts.append(f"md_{safe_model_lower}")
            if safe_trim_dash:    pw_parts.append(f"vg_{safe_trim_dash}")
            if c:                 pw_parts.append(f"ct_{c}")
            if safe_budget > 0:   pw_parts.append(f"pr_0_{safe_budget}")
            if min_year > 0 or max_year > 0:
                                  pw_parts.append(f"yr_{my}_{mx}")
            if safe_color_lower:  pw_parts.append(f"cl_{safe_color_lower}")
            pw_urls.append("/".join(pw_parts) + f"/?page={page}")

            # ------------------------------------------------------------------ #
            # OLX — simplified q-based routing (FIXED)
            #
            # WHAT WAS BROKEN:
            #   Old URL: /{city_slug}/honda-cars_c84/q-civic?filter=make_eq_honda
            #   Problems:
            #     1. City slug had wrong ID digits (g4060675 instead of g4060673).
            #     2. Category segment "honda-cars_c84" is dynamic and breaks often.
            #     3. filter value "make_eq_honda" should be "make_eq_cars-honda".
            #
            # WHAT IS CORRECT NOW:
            #   URL: /{city_slug}/cars_c84/q-{make}-{model}
            #   - Uses the static category "cars_c84" (never changes).
            #   - Uses OLX's native q= keyword search (same as the search bar).
            #   - No filter= parameter needed — OLX infers make from the query.
            #   - Verified live: returns HTTP 200 with full __NEXT_DATA__ payload.
            #
            # PAGINATION:
            #   OLX supports ?page=N directly on this URL format.
            # ------------------------------------------------------------------ #
            olx_slug = OLX_CITY_MAP.get(c, "")

            # Build the search query: "honda-civic" or "honda-civic-oriel" with trim
            olx_q_parts = list(filter(None, [safe_make_lower, safe_model_lower, safe_trim_dash]))
            olx_q = "-".join(olx_q_parts) if olx_q_parts else "cars"

            # Construct base URL
            if olx_slug:
                olx_url = f"https://www.olx.com.pk/{olx_slug}/cars_c84/q-{olx_q}"
            else:
                # No city slug → countrywide search
                olx_url = f"https://www.olx.com.pk/cars_c84/q-{olx_q}"

            # Append pagination
            olx_url += f"?page={page}"

            olx_tasks.append((olx_url, search_filters))

            # ------------------------------------------------------------------ #
            # DRIVE.PK — flat query-parameter routing
            # ------------------------------------------------------------------ #
            drive_url = f"https://www.drivepk.com/cars/list?page={page}"
            if safe_make_lower:    drive_url += f"&brands={safe_make_lower.capitalize()}"
            if safe_budget > 0:    drive_url += f"&maxPrice={safe_budget}"
            if min_year > 0:       drive_url += f"&minYear={min_year}"
            if max_year > 0:       drive_url += f"&maxYear={max_year}"
            if safe_color_lower:   drive_url += f"&colors={safe_color_lower.capitalize()}"
            if target_city:        drive_url += f"&cities={target_city.capitalize()}"
            drive_q_parts = list(filter(None, [safe_model, safe_trim]))
            drive_q_str = " ".join(drive_q_parts).replace(" ", "%20")
            if drive_q_str:        drive_url += f"&q={drive_q_str}"
            drive_tasks.append((drive_url, search_filters))

            # ------------------------------------------------------------------ #
            # AUTODEALS — mixed path/segment routing
            # ------------------------------------------------------------------ #
            ad_parts = ["https://autodeals.pk/used-cars/search/-"]
            if c:              ad_parts.append(f"ct_{c}")
            if safe_budget > 0: ad_parts.append(f"minP_0/maxP_{safe_budget}")
            if min_year > 0:   ad_parts.append(f"minY_{min_year}")
            if max_year > 0:   ad_parts.append(f"maxY_{max_year}")
            ad_search = "-".join(filter(None, [safe_make_lower, safe_model_lower, safe_trim_dash]))
            if ad_search:      ad_parts.append(f"searchStr_{ad_search}")
            ad_url = "/".join(ad_parts) + f"?page={page}"
            auto_deals_tasks.append((ad_url, search_filters))

            # ------------------------------------------------------------------ #
            # WISEWHEELS — query-parameter routing
            # URL: https://wisewheels.com.pk/used-cars?city_id=257&make=toyota&model=corolla&price_from=0&price_to=5000000
            # ------------------------------------------------------------------ #
            ww_url = f"https://wisewheels.com.pk/used-cars?price_from=0&page={page}"
            ww_city_id = WISEWHEELS_CITY_MAP.get(c, "")
            if ww_city_id:
                ww_url += f"&city_id={ww_city_id}"
            if safe_make_lower:
                ww_url += f"&make={safe_make_lower}"
            if safe_model_lower:
                ww_url += f"&model={safe_model_lower}"
            if safe_budget > 0:
                ww_url += f"&price_to={safe_budget}"
            wisewheels_tasks.append((ww_url, search_filters))

    # --- Log constructed search queries ---
    print(
        f"[Pipeline] Search → Make={safe_make}, Model={safe_model}, "
        f"Cities={cities_to_search}, Color={safe_color}, Trim={safe_trim}, "
        f"Year={min_year}-{max_year}, Budget={safe_budget}"
    )

    # --- Concurrency: run all scrapers using a shared curl_cffi session ---
    futures = []

    async with AsyncSession(impersonate="chrome120") as session:
        for url in pw_urls:
            futures.append(scrape_pakwheels(url, session))

        for url, filters in olx_tasks:
            futures.append(scrape_olx(url, session, filters))

        for url, filters in drive_tasks:
            futures.append(scrape_drive_pk(url, session, filters))

        for url, filters in gari_tasks:
            futures.append(scrape_gari_pk(url, session, filters))

        for url, filters in wisewheels_tasks:
            futures.append(scrape_wise_wheels(url, session, filters))

        for url, filters in auto_deals_tasks:
            futures.append(scrape_auto_deals(url, session, filters))

        for url in famewheels_urls:
            futures.append(scrape_famewheels(url, session))

        all_results = await asyncio.gather(*futures, return_exceptions=True)

    # --- Dynamic flatten and log ---
    pw_count            = len(pw_urls)
    olx_count           = len(olx_tasks)
    drive_count         = len(drive_tasks)
    gari_count          = len(gari_tasks)
    ww_count            = len(wisewheels_tasks)
    auto_deals_count    = len(auto_deals_tasks)
    famewheels_count    = len(famewheels_urls)

    idx = 0
    def _safe_len(r):
        return len(r) if isinstance(r, list) else 0

    pw_total          = sum(_safe_len(r) for r in all_results[idx : idx + pw_count]);          idx += pw_count
    olx_total         = sum(_safe_len(r) for r in all_results[idx : idx + olx_count]);         idx += olx_count
    drive_total       = sum(_safe_len(r) for r in all_results[idx : idx + drive_count]);       idx += drive_count
    gari_total        = sum(_safe_len(r) for r in all_results[idx : idx + gari_count]);        idx += gari_count
    ww_total          = sum(_safe_len(r) for r in all_results[idx : idx + ww_count]);          idx += ww_count
    auto_deals_total  = sum(_safe_len(r) for r in all_results[idx : idx + auto_deals_count]); idx += auto_deals_count
    famewheels_total  = sum(_safe_len(r) for r in all_results[idx : idx + famewheels_count]); idx += famewheels_count

    print(f"[Pipeline] PakWheels returned   {pw_total} raw listings ({pw_count} pages)")
    print(f"[Pipeline] OLX returned         {olx_total} raw listings ({olx_count} pages)")
    print(f"[Pipeline] Drive.pk returned    {drive_total} raw listings ({drive_count} pages)")
    print(f"[Pipeline] Gari.pk returned     {gari_total} raw listings")
    print(f"[Pipeline] WiseWheels returned  {ww_total} raw listings ({ww_count} pages)")
    print(f"[Pipeline] AutoDeals returned   {auto_deals_total} raw listings")
    print(f"[Pipeline] FameWheels returned  {famewheels_total} raw listings")

    # Flatten all results
    raw_listings = []
    for result_set in all_results:
        if isinstance(result_set, list):
            raw_listings.extend(result_set)
        else:
            print(f"[Runner] ⚠ Scraper failed: {result_set}")
    print(f"[Pipeline] Total raw listings: {len(raw_listings)}")

    # --- Normalize, deduplicate, and cap ---
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