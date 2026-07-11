"""
scrapers/runner.py

Migrated from Playwright to curl_cffi.
Uses a single AsyncSession with Chrome TLS impersonation for all platforms.

FIXES (July 2026):
  - OLX city slugs corrected (Lahore: g4060673, not g4060675; all others verified).

FIX (this patch — OLX URL Restoration + Sort-by-Newest):
  A previous patch removed the make-prefixed category ("{make}-cars_c84")
  and the filter= parameter from the OLX URL, blaming them for 404s. This
  was diagnosed incorrectly — the real cause of those 404s was the wrong
  city slug digits (fixed separately above). This was CONFIRMED by manually
  testing this exact live URL, which works correctly:

    https://www.olx.com.pk/islamabad_g4060615/toyota-cars_c84/q-grande
      ?sorting=desc-creation
      &filter=make_eq_toyota,price_between_200000_to_5000000,year_between_2015_to_2020

  This patch:
    1. Restores the make-prefixed category format ("{make}-cars_c84").
    2. Restores the filter= parameter (make_eq / price_between / year_between),
       enabling real budget and year filtering on OLX again (previously lost).
    3. Adds sorting=desc-creation — confirmed real parameter for newest-first
       sort order, addressing the "results feel stale" concern.
    4. Keeps 'model' as a MANDATORY component of the q- search path (per the
       earlier Model Leakage fix) — trim is layered on top as a refinement,
       never a substitute for model.
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
# ⚠️ SOURCE CONFLICT WARNING:
# Two reference documents (ids.md and report.md) were provided for this
# project, and they DISAGREE on the slug digits for 6 cities: Peshawar,
# Multan, Faisalabad, Gujranwala, Sialkot, and Quetta. report.md's table
# matches what was already deployed and tested here, so those values are
# KEPT AS-IS below. ids.md's conflicting digits for those 6 cities were
# NOT applied — do not swap them in without manually verifying first by
# visiting https://www.olx.com.pk/{slug}/cars_c84 and confirming no
# redirect occurs. Wrong slug digits have already caused a silent 404
# regression once in this project (Islamabad, fixed Jul 8) — don't
# reintroduce that bug via an unverified second source.
#
# The additional cities below (Sargodha through Abbottabad, and the
# Tier 3 list) come ONLY from ids.md and have NOT been independently
# cross-checked against a second source. Spot-check any of these before
# relying on them heavily, using the same redirect-check method above.
#
# COMMON BUG: slugs look similar but differ by 2-3 digits.
# Always verify by visiting: https://www.olx.com.pk/{slug}/cars_c84
# and checking the URL doesn't redirect.
# ------------------------------------------------------------------ #
OLX_CITY_MAP = {
    # --- Tier 1: confirmed consistent across all sources ---
    "lahore":       "lahore_g4060673",
    "karachi":      "karachi_g4060695",
    "islamabad":    "islamabad_g4060615",
    "rawalpindi":   "rawalpindi_g4060681",

    # --- These 6 have a source conflict (see warning above). Keeping
    #     the already-deployed / report.md values, NOT ids.md's. ---
    "peshawar":     "peshawar_g4060698",
    "multan":       "multan_g4060678",
    "faisalabad":   "faisalabad_g4060677",
    "gujranwala":   "gujranwala_g4060679",
    "sialkot":      "sialkot_g4060680",
    "quetta":       "quetta_g4060699",

    # --- New additions from ids.md — UNVERIFIED, spot-check before relying on these ---
    "sargodha":         "sargodha_g4060684",
    "hyderabad":        "hyderabad_g4060693",
    "bahawalpur":       "bahawalpur_g4060653",
    "gujrat":           "gujrat_g4060663",
    "sahiwal":          "sahiwal_g4060683",
    "rahim yar khan":   "rahimyar-khan_g4060680",   # NOTE: same numeric ID as our sialkot value above — verify this isn't a typo in ids.md before trusting it
    "sheikhupura":      "sheikhupura_g4060685",
    "okara":            "okara_g4060678",           # NOTE: same numeric ID as our multan value above — verify before trusting
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
    "muzaffargarh":     "muzaffargarh_g4060677",    # NOTE: same numeric ID as our faisalabad value above — verify before trusting
    "sadiqabad":        "sadiqabad_g4060682",
    "chiniot":          "chiniot_g4060655",
    "wah cantt":        "wah_g4060692",
    "pakpattan":        "pakpattan_g4060679",        # NOTE: same numeric ID as our gujranwala value above — verify before trusting
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
            # PAKWHEELS — path-segment routing (unchanged)
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
            # OLX — RESTORED make-prefixed category + filter= + sorting=
            #
            # CONFIRMED WORKING (manually verified live):
            #   https://www.olx.com.pk/islamabad_g4060615/toyota-cars_c84/q-grande
            #     ?sorting=desc-creation
            #     &filter=make_eq_toyota,price_between_200000_to_5000000,year_between_2015_to_2020
            #
            # This proves the make-prefixed category and filter= parameter
            # both work — a previous patch incorrectly blamed 404s on this
            # format. The real cause was the wrong city slug digits, fixed
            # separately above. Restoring the richer URL here, and adding
            # sorting=desc-creation for freshness (newest-first results).
            #
            # 'model' remains MANDATORY in the q- search path per the Model
            # Leakage fix — trim is an optional refinement layered on top,
            # never a substitute for model.
            # ------------------------------------------------------------------ #
            olx_slug = OLX_CITY_MAP.get(c, "")
            olx_category = f"{safe_make_lower}-cars_c84" if safe_make_lower else "cars_c84"

            olx_base_parts = ["https://www.olx.com.pk"]
            if olx_slug:
                olx_base_parts.append(olx_slug)
            olx_base_parts.append(olx_category)

            olx_q_parts = list(filter(None, [safe_model_lower, safe_trim_dash]))
            if olx_q_parts:
                olx_base_parts.append("q-" + "-".join(olx_q_parts))

            olx_url = "/".join(olx_base_parts)

            # FIX (404 regression): OLX 404s on a LONE 'make_eq_X' filter
            # with no price/year alongside it — confirmed via live logs
            # (Bolan/Cultus searches with no budget/year both 404'd on
            # every page). The only manually-verified working example
            # always paired make_eq WITH price_between AND year_between
            # together. Since make is already expressed via the category
            # prefix ("{make}-cars_c84") and the q- search term, make_eq
            # is redundant on its own — only add it when there's at least
            # one other real constraint to pair it with. Otherwise skip
            # filter= entirely, matching the previously-confirmed-working
            # plain format.
            olx_filters = []
            if safe_budget > 0:
                olx_filters.append(f"price_between_0_to_{safe_budget}")
            if min_year > 0 or max_year > 0:
                olx_filters.append(f"year_between_{my}_to_{mx}")
            if safe_make_lower and olx_filters:
                olx_filters.insert(0, f"make_eq_{safe_make_lower}")

            filter_string = ",".join(olx_filters)

            query_parts = ["sorting=desc-creation"]  # newest-first, confirmed working
            if filter_string:
                query_parts.append(f"filter={filter_string}")
            query_parts.append(f"page={page}")

            olx_url += "?" + "&".join(query_parts)

            olx_tasks.append((olx_url, search_filters))

            # ------------------------------------------------------------------ #
            # DRIVE.PK — flat query-parameter routing (unchanged)
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
            # AUTODEALS — mixed path/segment routing (unchanged)
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
            # WISEWHEELS — query-parameter routing (unchanged)
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