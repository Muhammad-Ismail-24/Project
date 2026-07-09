"""
scrapers/normalizer.py
GaariGuru — API-Free Heuristic Scoring Normalizer v3.0

Upgrade log over v2:
  - Pakistani make inference map (Alto/Cultus/Mehran → Suzuki, etc.)
  - Model alias map (BRV → BR-V, Vezel variants, etc.)
  - Typo spell-correction dictionary (carolla → corolla, vesel → vezel)
  - City alias normalizer (Isb → Islamabad, Khi → Karachi, etc.)
  - Strict city enforcement moved to soft penalty so padding still works
  - Per-veto debug logging so you can see exactly why cars are dropped
  - Empty result guard flag returned alongside list
  - REMOVED: Round-Robin picker.
  - ADDED: Global Master Sort (Absolute quality over forced diversity).
  - ADDED: Garbage City Rescuer to fix visual UI bugs from bad scraper data.
"""

import re
from difflib import SequenceMatcher
from models.car_schema import CarListing


# ---------------------------------------------------------------------------
# KNOWLEDGE MAPS
# ---------------------------------------------------------------------------

# If orchestrator extracts a model name as the make, fix it automatically.
# Key = what orchestrator wrongly extracts as make, Value = (correct_make, correct_model)
MAKE_INFERENCE_MAP: dict[str, tuple[str, str]] = {
    "alto":     ("Suzuki",   "Alto"),
    "cultus":   ("Suzuki",   "Cultus"),
    "mehran":   ("Suzuki",   "Mehran"),
    "wagon":    ("Suzuki",   "Wagon R"),
    "wagoner":  ("Suzuki",   "Wagon R"),
    "wagonr":   ("Suzuki",   "Wagon R"),
    "swift":    ("Suzuki",   "Swift"),
    "bolan":    ("Suzuki",   "Bolan"),
    "ravi":     ("Suzuki",   "Ravi"),
    "civic":    ("Honda",    "Civic"),
    "city":     ("Honda",    "City"),
    "brv":      ("Honda",    "BR-V"),
    "vezel":    ("Honda",    "Vezel"),
    "hrv":      ("Honda",    "HR-V"),
    "crv":      ("Honda",    "CR-V"),
    "accord":   ("Honda",    "Accord"),
    "corolla":  ("Toyota",   "Corolla"),
    "yaris":    ("Toyota",   "Yaris"),
    "prado":    ("Toyota",   "Prado"),
    "fortuner": ("Toyota",   "Fortuner"),
    "hilux":    ("Toyota",   "Hilux"),
    "vitz":     ("Toyota",   "Vitz"),
    "aqua":     ("Toyota",   "Aqua"),
    "tucson":   ("Hyundai",  "Tucson"),
    "elantra":  ("Hyundai",  "Elantra"),
    "santro":   ("Hyundai",  "Santro"),
    "sportage": ("Kia",      "Sportage"),
    "stonic":   ("Kia",      "Stonic"),
    "picanto":  ("Kia",      "Picanto"),
    "sorento":  ("Kia",      "Sorento"),
}

# Model aliases — all variations that refer to the same model.
# Key = canonical cleaned form (no spaces/hyphens), Values = list of aliases
MODEL_ALIAS_MAP: dict[str, list[str]] = {
    "brv":      ["brv", "br-v", "br v", "brvcar"],
    "hrv":      ["hrv", "hr-v", "hr v"],
    "crv":      ["crv", "cr-v", "cr v"],
    "vezel":    ["vezel", "vezal", "vesel", "vezzel"],
    "wagonr":   ["wagonr", "wagon r", "wagon-r", "wagoner"],
    "corolla":  ["corolla", "carolla", "corola", "coralla"],
    "civic":    ["civic"],
    "cultus":   ["cultus", "kultus", "cultis"],
    "mehran":   ["mehran", "meharan", "mehern"],
    "nwagon":   ["n wagon", "nwagon", "n-wagon"],
    "none":     ["n one", "none", "n-one"],          # Honda N-One edge case
}

# Typo spell-correction for raw query strings (applied before orchestrator parsing)
# Used in normalize_listings to fix orchestrator output
TYPO_CORRECTIONS: dict[str, str] = {
    "carolla":  "corolla",
    "corola":   "corolla",
    "coralla":  "corolla",
    "vesel":    "vezel",
    "vezal":    "vezel",
    "civec":    "civic",
    "civick":   "civic",
    "kultus":   "cultus",
    "cultis":   "cultus",
    "meharan":  "mehran",
    "alto660":  "alto",
    "wagoner":  "wagon r",
    "hilux":    "hilux",
    "fortunner":"fortuner",
    "pajaro":   "pajero",
}

# City aliases — normalize what users type to canonical city names
CITY_ALIAS_MAP: dict[str, str] = {
    "isb":          "Islamabad",
    "isl":          "Islamabad",
    "islamabad":    "Islamabad",
    "rwp":          "Rawalpindi",
    "rawalpindi":   "Rawalpindi",
    "pindi":        "Rawalpindi",
    "lhr":          "Lahore",
    "lahore":       "Lahore",
    "khi":          "Karachi",
    "karachi":      "Karachi",
    "krt":          "Karachi",
    "pesh":         "Peshawar",
    "peshawar":     "Peshawar",
    "fsd":          "Faisalabad",
    "faisalabad":   "Faisalabad",
    "mtn":          "Multan",
    "multan":       "Multan",
    "gujranwala":   "Gujranwala",
    "sialkot":      "Sialkot",
    "quetta":       "Quetta",
    "abbottabad":   "Abbottabad",
    "hyderabad":    "Hyderabad",
}

# Trim aliases — same pattern as MODEL_ALIAS_MAP.
# Key = canonical cleaned form, Values = all known real-world spellings for it.
TRIM_ALIASES: dict[str, list[str]] = {
    "2d":       ["2d", "2.0d", "20d", "diesel"],
    "2.0d":     ["2d", "2.0d", "20d", "diesel"],
    "oriel":    ["oriel", "ug", "oriel ug", "orielug"],
    "ug":       ["oriel", "ug", "oriel ug", "orielug"],
    "rs":       ["rs", "rs turbo", "rsturbo"],
    "turbo":    ["turbo", "rs turbo", "rsturbo"],
    "altis":    ["altis", "grande", "altis grande"],
    "grande":   ["altis", "grande", "altis grande"],
    "gli":      ["gli"],
    "xli":      ["xli"],
    "vxr":      ["vxr", "vxr agc", "vxragc"],
    "vxl":      ["vxl", "vxl agc", "vxlagc", "vxl+"],
    "aspire":   ["aspire", "aspire prosmatec"],
    "ivtec":    ["ivtec", "i vtec", "i-vtec"],
    "ativ":     ["ativ", "ativ x", "ativx"],
    "alpha":    ["alpha", "alpha fwd", "alphafwd"],
}

# Colors to check for anti-conflict veto
COMMON_COLORS = ["black", "white", "silver", "grey", "gray", "red", "blue",
                 "green", "maroon", "golden", "beige", "brown", "orange", "purple"]


# ---------------------------------------------------------------------------
# UTILITY: NORMALIZE MAKE / MODEL / CITY FROM ORCHESTRATOR OUTPUT
# ---------------------------------------------------------------------------

def normalize_make_model(make: str, model: str) -> tuple[str, str]:
    """
    Fixes orchestrator errors where a model name is extracted as the make.
    e.g. make='Alto', model='' → make='Suzuki', model='Alto'
    Also applies typo corrections to the model string.
    Returns (corrected_make, corrected_model).
    """
    make_clean = (make or "").strip().lower()
    model_clean = (model or "").strip().lower()

    # Apply typo correction to model
    model_corrected = TYPO_CORRECTIONS.get(model_clean, model_clean)

    # If make is actually a model name, fix it
    if make_clean in MAKE_INFERENCE_MAP:
        inferred_make, inferred_model = MAKE_INFERENCE_MAP[make_clean]
        # Only override model if model was empty or same wrong value
        if not model_corrected or model_corrected == make_clean:
            print(f"[Normalizer] Make inference: '{make}' → Make='{inferred_make}', Model='{inferred_model}'")
            return inferred_make, inferred_model
        else:
            print(f"[Normalizer] Make inference: '{make}' → Make='{inferred_make}' (model kept as '{model_corrected}')")
            return inferred_make, model_corrected.title()

    return (make or "").strip(), model_corrected.title() if model_corrected else ""


def normalize_city(city: str) -> str:
    """
    Normalizes city input to a canonical form.
    e.g. 'isb' → 'Islamabad', 'khi' → 'Karachi'
    """
    if not city:
        return ""
    city_key = city.strip().lower()
    return CITY_ALIAS_MAP.get(city_key, city.strip().title())


# ---------------------------------------------------------------------------
# CLEANING HELPERS
# ---------------------------------------------------------------------------

def _clean_price(raw_price) -> int:
    """
    Converts a raw price string/value into a clean integer PKR amount.

    Critical ordering: the Lac/Lakh/Crore multiplier MUST be detected
    from the raw text BEFORE any letters are stripped away. Stripping
    first and detecting the multiplier second is what caused prices
    like "47 Lacs" to truncate down to just 47.
    """
    if raw_price is None or raw_price == "":
        return 0

    if isinstance(raw_price, (int, float)):
        return int(raw_price)

    price_str = str(raw_price).strip().lower()

    if not price_str or "call for price" in price_str or "call" in price_str:
        return 0

    # --- Step 1: Determine the multiplier BEFORE stripping any letters ---
    multiplier = 1
    if re.search(r'\b(lac|lacs|lakh|lakhs)\b', price_str):
        multiplier = 100_000
    elif re.search(r'\b(crore|crores)\b', price_str):
        multiplier = 10_000_000

    # --- Step 2: Strip everything EXCEPT digits and the decimal point ---
    clean_num_str = re.sub(r'[^\d.]', '', price_str)

    # Guard against a lone decimal point or multiple decimal points
    # left over from malformed source text (e.g. "Rs. .." or "1.2.3")
    if not clean_num_str or clean_num_str == '.' or clean_num_str.count('.') > 1:
        return 0

    # --- Step 3: Convert to float first (handles "47.5"), apply
    #             multiplier, then cast to a final integer ---
    try:
        final_price = int(float(clean_num_str) * multiplier)
        if multiplier > 1:
            print(f"[Normalizer] Price multiplier applied: '{raw_price}' → {final_price:,} (×{multiplier:,})")
        return final_price
    except ValueError:
        return 0


def _clean_int(raw_value) -> int:
    """Strips commas and non-digit characters and returns an integer."""
    if isinstance(raw_value, int):
        return raw_value
    if not isinstance(raw_value, str):
        return 0

    text = raw_value.strip().replace(",", "")
    digits = re.sub(r"[^\d]", "", text)
    if digits:
        try:
            return int(digits)
        except ValueError:
            return 0
    return 0


# ---------------------------------------------------------------------------
# IDENTITY MATCHER
# ---------------------------------------------------------------------------

def _normalize_str(s: str) -> str:
    """Strips spaces, hyphens, periods, underscores — used for identity matching."""
    return s.lower().replace(" ", "").replace("-", "").replace(".", "").replace("_", "")


def _resolve_model_aliases(model_clean: str) -> list[str]:
    """
    Returns all known alias forms for a model string.
    e.g. 'brv' → ['brv', 'br-v', 'br v', 'brvcar']
    If not in map, returns [model_clean] as-is.
    """
    normalized = _normalize_str(model_clean)
    for canonical, aliases in MODEL_ALIAS_MAP.items():
        alias_normalized = [_normalize_str(a) for a in aliases]
        if normalized in alias_normalized:
            return alias_normalized
    return [normalized]


def _calculate_identity_score(
    requested_make: str,
    requested_model: str,
    title: str
) -> float:
    """
    Fault-tolerant identity match between requested model and listing title.
    
    Upgrade: Replaced the dangerous 'sliding window' with a safe 'word-boundary' 
    fuzzy matcher to prevent false positives across all car models universally.
    """
    if not requested_model:
        return 1.0

    # 1. Strip make from model string to prevent cross-contamination
    model_clean = _normalize_str(requested_model)
    if requested_make:
        make_clean = _normalize_str(requested_make)
        model_clean = model_clean.replace(make_clean, "").strip()

    if not model_clean:
        return 1.0

    target_clean = _normalize_str(title)
    aliases = _resolve_model_aliases(model_clean)

    # 2. EXACT SUBSTRING MATCH (The Indestructible JDM Matcher)
    # This solves 95% of cases, including spacing issues like "n one" vs "none"
    for alias in aliases:
        if alias in target_clean:
            return 1.0

    # 3. SAFE FUZZY MATCHER (Word-by-Word, NO Sliding Window!)
    best_ratio = 0.0
    
    # Clean the title but KEEP spaces so we can split it into actual words
    title_words = title.lower().replace("-", " ").replace(".", " ").replace("_", " ").split()
    
    for alias in aliases:
        for word in title_words:
            # Only compare if the word is roughly the same length as the alias
            # (Prevents a 5-letter alias from matching a 2-letter word)
            if abs(len(word) - len(alias)) <= 2:
                ratio = SequenceMatcher(None, alias, word).ratio()
                if ratio > best_ratio:
                    best_ratio = ratio

    return round(best_ratio, 4)


# ---------------------------------------------------------------------------
# HEURISTIC SCORING ENGINE
# ---------------------------------------------------------------------------

def _calculate_relevance_score(
    car: CarListing,
    requested_make: str,
    requested_model: str,
    requested_city: str,
    requested_budget: int,
    requested_color: str,
    clean_price: int,
    clean_year: int,
    clean_mileage: int,
    requested_trim: str = None,
    min_year: int = 0,
    max_year: int = 0,
    debug: bool = False,
) -> float:
    """
    Scores a car listing from 0 to 100 based on how well it matches
    the user's request. Returns 0.0 for any hard veto.
    """
    title_lower = car.title.lower()

    def veto(reason: str) -> float:
        if debug:
            print(f"  [VETO] '{car.title[:50]}' — {reason}")
        return 0.0

    # --- HARD VETO 1: Identity ---
    identity_score = _calculate_identity_score(requested_make, requested_model, car.title)
    if identity_score < 0.75:
        return veto(f"Identity too low ({identity_score:.2f}) for model='{requested_model}'")

    # --- HARD VETO 2: Make not in title ---
    if requested_make and requested_make.lower() not in title_lower:
        return veto(f"Make '{requested_make}' not found in title")

    # --- HARD VETO 3: Budget ceiling ---
    if requested_budget and clean_price > 0:
        if clean_price > requested_budget:
            return veto(
                f"Price {clean_price:,} exceeds budget {requested_budget:,}"
            )

    # --- HARD VETO 4: Color anti-conflict ---
    if requested_color:
        req_color = requested_color.lower().strip()
        for color in COMMON_COLORS:
            if color == req_color:
                continue
            if color in title_lower:
                return veto(f"Title contains '{color}' but user wants '{req_color}'")

    # --- SOFT PENALTY: Budget (40 pts) ---
    if clean_price == 0:
        budget_score = 10.0   
    else:
        budget_score = 40.0   

    # --- HARD VETO 5: STRICT MULTI-CITY ENFORCEMENT ---
    car_city_lower = (car.city or "").lower().strip()
    req_city_str = (requested_city or "").lower().strip()

    if req_city_str:
        # Split user's requested cities by comma or 'and'
        req_cities = [c.strip() for c in re.split(r',|\band\b', req_city_str) if c.strip()]
        
        city_matched = False
        for rc in req_cities:
            # Check if the requested city is in the scraped city field 
            # OR if it's explicitly written in the car's title!
            if rc in car_city_lower or rc in title_lower:
                city_matched = True
                break
        
        # If it doesn't match any of the requested cities, KILL IT instantly.
        if not city_matched:
            return veto(f"Wrong city. User requested '{req_city_str}', found '{car.city}'")
        
        city_score = 30.0
    else:
        city_score = 30.0 if car_city_lower else 15.0

    # --- HARD VETO 6: STRICT TRIM ENFORCEMENT ---
    if requested_trim:
        # Keep periods and spaces (2.0 vs 20, multi-word trims). Strip hyphens only.
        req_trim_clean = requested_trim.lower().replace("-", "")
        title_clean = title_lower.replace("-", "")

        GENERIC_SKIP_WORDS = {"automatic", "manual", "car", "sedan", "petrol", "hybrid"}

        trim_keywords = req_trim_clean.split()

        trim_matched = False
        for keyword in trim_keywords:
            if keyword in GENERIC_SKIP_WORDS:
                continue

            # Expand via TRIM_ALIASES, fall back to the raw keyword if unmapped
            valid_forms = TRIM_ALIASES.get(keyword, [keyword])

            if any(form in title_clean for form in valid_forms):
                trim_matched = True
                break

        if not trim_matched:
            return veto(f"Trim missing. User wanted '{requested_trim}', not found in title.")

    # --- HARD VETO: STRICT YEAR ENFORCEMENT ---
    # Only enforce if the car has a valid parsed year AND the user
    # explicitly requested a bound. A car with an unparseable/zero
    # year is NOT vetoed here — that's already handled by the
    # existing Data Quality soft-penalty scoring.
    if clean_year > 0:
        if min_year > 0 and clean_year < min_year:
            return veto(f"Too old. Car is {clean_year}, user requested min {min_year}.")
        if max_year > 0 and clean_year > max_year:
            return veto(f"Too new. Car is {clean_year}, user requested max {max_year}.")

    # --- SOFT PENALTY: Freshness (15 pts) ---
    age_score = max(0.0, 15.0 - (car.age_days * 0.5))  

    # --- SOFT PENALTY: Data Quality (15 pts) ---
    year_score = 7.5 if clean_year > 0 else 0.0
    mileage_score = 7.5 if clean_mileage > 0 else 0.0
    quality_score = year_score + mileage_score

    # --- TOTAL ---
    raw_total = budget_score + city_score + age_score + quality_score
    total_score = raw_total * identity_score

    if debug:
        print(
            f"  [SCORE] '{car.title[:45]}' | "
            f"id={identity_score:.2f} budget={budget_score} city={city_score} "
            f"age={age_score:.1f} quality={quality_score} -> {total_score:.2f}"
        )

    return round(total_score, 2)


# ---------------------------------------------------------------------------
# MAIN ENTRY POINT
# ---------------------------------------------------------------------------

def normalize_listings(
    raw_listings: list[CarListing],
    requested_make: str = None,
    requested_model: str = None,
    requested_city: str = None,
    requested_budget: int = None,
    requested_color: str = None,
    requested_trim: str = None,
    min_year: int = 0,
    max_year: int = 0,
    debug: bool = False,
) -> tuple[list[CarListing], bool]:
    """
    Main normalizer pipeline.
    """

    # --- Step 1: Auto-correct make/model from orchestrator output ---
    corrected_make, corrected_model = normalize_make_model(
        requested_make or "", requested_model or ""
    )

    # --- Step 2: Normalize city ---
    corrected_city = normalize_city(requested_city or "")

    if corrected_make != (requested_make or "").strip():
        print(f"[Normalizer] Corrected make: '{requested_make}' -> '{corrected_make}'")
    if corrected_model != (requested_model or "").strip():
        print(f"[Normalizer] Corrected model: '{requested_model}' -> '{corrected_model}'")
    if corrected_city != (requested_city or "").strip():
        print(f"[Normalizer] Corrected city: '{requested_city}' -> '{corrected_city}'")

    # --- Step 3 & 4: Score all listings, discard vetoed ones ---
    scored_map: dict[tuple, dict] = {}  # deduplication map keyed by (title, year, mileage)
    veto_count = 0
    year_veto_count = 0

    for car in raw_listings:
        clean_price = _clean_price(car.price)
        clean_year = _clean_int(car.year)
        clean_mileage = _clean_int(car.mileage)

        score = _calculate_relevance_score(
            car=car,
            requested_make=corrected_make,
            requested_model=corrected_model,
            requested_city=corrected_city,
            requested_budget=requested_budget,
            requested_color=requested_color,
            clean_price=clean_price,
            clean_year=clean_year,
            clean_mileage=clean_mileage,
            requested_trim=requested_trim,
            min_year=min_year,
            max_year=max_year,
            debug=debug,
        )

        if score == 0.0:
            veto_count += 1
            if min_year > 0 or max_year > 0:
                if clean_year > 0 and ((min_year > 0 and clean_year < min_year) or (max_year > 0 and clean_year > max_year)):
                    year_veto_count += 1
            continue

        # --- NEW FIX: GARBAGE CITY RESCUER ---
        # If the scraper accidentally grabbed the transmission or fuel type, overwrite it!
        display_city = (car.city or "").strip()
        garbage_strings = ["automatic", "manual", "unregistered", "petrol", "hybrid", "cng", "diesel", "electric"]
        
        if display_city.lower() in garbage_strings:
            # Extract the real city from the user's request if it exists in the title
            req_cities = [c.strip() for c in re.split(r',|\band\b', (corrected_city or "").lower()) if c.strip()]
            for rc in req_cities:
                if rc in car.title.lower():
                    display_city = rc.title() # Convert "islamabad" to "Islamabad"
                    break

        # --- Step 5: Deduplication ---
        dedup_key = (car.title.lower().strip(), clean_year, clean_mileage)

        if dedup_key in scored_map:
            if score > scored_map[dedup_key]["score"]:
                scored_map[dedup_key] = {
                    "car": car,
                    "score": score,
                    "price": clean_price,
                    "year": clean_year,
                    "mileage": clean_mileage,
                    "display_city": display_city  # Save the rescued city here
                }
        else:
            scored_map[dedup_key] = {
                "car": car,
                "score": score,
                "price": clean_price,
                "year": clean_year,
                "mileage": clean_mileage,
                "display_city": display_city  # Save the rescued city here
            }

    qualified_count = len(scored_map)
    print(
        f"[Normalizer] Scored {len(raw_listings)} listings -> "
        f"{qualified_count} qualified, {veto_count} vetoed."
    )
    if min_year > 0 or max_year > 0:
        print(f"[Normalizer] Year veto: {year_veto_count} listings dropped outside range {min_year}-{max_year}")

    if qualified_count == 0:
        print("[Normalizer] [WARNING] Zero listings passed scoring. Returning empty - result will NOT be cached.")
        return [], True   # <- is_empty = True signals caller not to cache

    # --- Step 6: Hard Bucketing & Cascade Backfill ---
    all_scored_cars = list(scored_map.values())
    all_scored_cars.sort(key=lambda x: x["score"], reverse=True)

    buckets = {
        'PakWheels': [],
        'OLX': [],
        'Drive.pk': [],
        'Gari.pk': [], 
        'AutoDeals': []
    }

    # Group qualified cars into buckets
    for item in all_scored_cars:
        plat = item['car'].platform
        # Normalize platform names for the bucket matcher
        if 'Gari' in plat or 'Wise' in plat:
            plat_key = 'Gari.pk'
        elif plat in buckets:
            plat_key = plat
        else:
            continue
            
        buckets[plat_key].append(item)

    # Initial Quota Allocation
    final_selection = []
    
    pw_selected = buckets['PakWheels'][:5]
    olx_selected = buckets['OLX'][:4]
    drive_selected = buckets['Drive.pk'][:3]
    
    # Gari.pk / AutoDeals share 3 slots.
    gari_auto_pool = buckets['Gari.pk'] + buckets['AutoDeals']
    gari_auto_pool.sort(key=lambda x: x["score"], reverse=True)
    gari_auto_selected = gari_auto_pool[:3]
    
    final_selection.extend(pw_selected)
    final_selection.extend(olx_selected)
    final_selection.extend(drive_selected)
    final_selection.extend(gari_auto_selected)

    # Cascade Backfill Rule (Anti-Starvation Fallback)
    shortfall = 15 - len(final_selection)
    if shortfall > 0:
        # Build a backup pool of unselected top-tier cars (PakWheels & OLX)
        backup_pool = buckets['PakWheels'][len(pw_selected):] + buckets['OLX'][len(olx_selected):]
        backup_pool.sort(key=lambda x: x["score"], reverse=True)
        
        backfill_selected = backup_pool[:shortfall]
        final_selection.extend(backfill_selected)
        if backfill_selected:
            print(f"[Normalizer] Backfilled {len(backfill_selected)} slots from premium unselected PakWheels/OLX cars to prevent gaps.")

    # Re-sort the final aggregated array so highest score is always #1 globally on the UI
    final_selection.sort(key=lambda x: x["score"], reverse=True)
    
    top_15_data = final_selection[:15]
    
    final_list: list[CarListing] = []
    for data in top_15_data:
        car = data["car"]
        cleaned_car = CarListing(
            id=car.id,
            title=car.title.strip(),
            price=data["price"],
            mileage=data["mileage"],
            city=data["display_city"],  # <--- THE FIX: Use the rescued city!
            year=data["year"],
            listing_url=car.listing_url,
            image_url=car.image_url,
            platform=car.platform,
            age_days=car.age_days,
            scraped_at=car.scraped_at,
        )
        final_list.append(cleaned_car)

    print(f"[Normalizer] Global sort selected top {len(final_list)} absolute best listings.")

    is_empty = len(final_list) == 0
    if is_empty:
        print("[Normalizer] [WARNING] Global sort returned 0 — result will NOT be cached.")

    return final_list, is_empty