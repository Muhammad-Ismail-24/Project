"""
scrapers/recommend_normalizer.py
GaariGuru — AI Matchmaker Normalizer v1.4

Purpose:
    A purpose-built scoring pipeline for the AI Recommendation feature.
    Operates on a single recommended model at a time and returns exactly
    `top_k` (default: 5) listings with a cross-platform mix.

Key Features:
    - +5% negotiation buffer on budget.
    - Robust luxury make/model alias bypass (Mercedes, Range Rover, S-Class, Vogue).
    - Dynamic identity threshold (0.60 for luxury compound titles, 0.75 for standard).
    - 90-day staleness allowance for vehicles > 1.5 Crore PKR.
    - Soft city scoring & lazy seller trim handling.
"""

import re
from models.car_schema import CarListing

# ── Import shared knowledge maps and utilities from main normalizer ──────────
from scrapers.normalizer import (
    MAKE_VETO_ALIASES,
    MODEL_ALIAS_MAP,
    TRIM_ALIASES,
    COMMON_COLORS,
    normalize_make_model,
    normalize_city,
    _clean_price,
    _clean_int,
    _calculate_identity_score,
)

# ── 🚨 INJECT LUXURY ALIASES DIRECTLY 🚨 ─────────────────────────────────
# This guarantees the AI Matchmaker never vetoes European luxury cars
# even if they are missing from the main normalizer.py knowledge map.
MAKE_VETO_ALIASES.update({
    "mercedes-benz": ["mercedes-benz", "mercedes", "benz"],
    "mercedes":      ["mercedes-benz", "mercedes", "benz"],
    "land rover":    ["land rover", "range rover", "rangerover", "landrover"],
    "bmw":           ["bmw", "bimmer"],
    "porsche":       ["porsche"],
})

MODEL_ALIAS_MAP.update({
    "sclass":          ["s class", "s-class", "sclass", "s300", "s350", "s400", "s450", "s500", "s550", "s560", "s580", "s600", "s63", "s65"],
    "eclass":          ["e class", "e-class", "eclass", "e200", "e220", "e250", "e300", "e350", "e400", "e450", "e53", "e63"],
    "cclass":          ["c class", "c-class", "cclass", "c180", "c200", "c220", "c250", "c300", "c350", "c43", "c63"],
    "rangerover":      ["range rover", "rangerover", "vogue", "autobiography", "evoque", "velar"],
    "rangeroversport": ["range rover sport", "rangerover sport", "range rover sports", "sport"],
    "3series":         ["3 series", "3series", "318i", "320i", "328i", "330i", "335i"],
    "5series":         ["5 series", "5series", "520i", "525i", "528i", "530i", "535i", "540i"],
    "7series":         ["7 series", "7series", "730li", "740li", "750li", "760li"],
    "taycan":          ["taycan", "taycan 4s", "taycan turbo", "cross turismo"],
    "cayenne":         ["cayenne", "cayenne s", "cayenne gts", "cayenne turbo", "e-hybrid"],
})

# ---------------------------------------------------------------------------
# RECOMMEND-SPECIFIC CONFLICT MAP
# ---------------------------------------------------------------------------

TRIM_CONFLICTS: dict[str, list[str]] = {
    "awd":       ["fwd", "alpha", "alpha fwd"],
    "fwd":       ["awd", "4x4", "4wd"],
    "alpha":     ["awd", "fwd", "4x4"],
    "manual":    ["auto", "automatic", "cvt", "ags", "prosmatec", "easytronic"],
    "automatic": ["manual", "mt"],
    "auto":      ["manual", "mt"],
    "cvt":       ["manual", "mt"],
    "hybrid":    ["non-hybrid", "non hybrid", "petrol only"],
    "petrol":    ["diesel", "ev", "electric", "hybrid"],
    "diesel":    ["petrol", "ev", "electric", "hybrid"],
    "turbo":     ["naturally aspirated", "na"],
    "essence":   ["trophy"],
    "trophy":    ["essence"],
}


# ---------------------------------------------------------------------------
# SCORING ENGINE
# ---------------------------------------------------------------------------

def _calculate_recommendation_score(
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
    required_features: list[str] = None,
    min_budget: int = 0,
    min_year: int = 0,
    max_year: int = 0,
    debug: bool = False,
) -> float:
    """
    Scores a single listing for AI recommendation relevance.
    Returns 0.0 for any hard veto, otherwise a positive float.
    """
    clean_title = re.sub(r'\b\d{7,}\b', '', car.title).strip()
    title_lower = clean_title.lower()

    def veto(reason: str) -> float:
        if debug:
            print(f"  [REC-VETO] '{clean_title[:50]}' — {reason}")
        return 0.0

    eff_budget = int(requested_budget) if requested_budget else 0

    # ── 1. Identity check ──────────────────────────────────────────────────
    identity_score = _calculate_identity_score(requested_make, requested_model, clean_title)
    
    # Soften identity requirement slightly for luxury vehicles with long/variant titles
    min_identity = 0.60 if eff_budget >= 15_000_000 else 0.75
    if identity_score < min_identity:
        return veto(f"Identity too low ({identity_score:.2f}) for model='{requested_model}'")

    # ── 2. Make check (With Luxury Brand Bypass) ───────────────────────────
    if requested_make:
        req_make_lower = requested_make.lower()
        title_make_check = title_lower.replace("-", " ")

        # Direct bypass for brands frequently omitted or abbreviated in titles
        is_luxury_bypass = False
        if "mercedes" in req_make_lower and ("mercedes" in title_make_check or "benz" in title_make_check):
            is_luxury_bypass = True
        elif ("land rover" in req_make_lower or "range rover" in requested_model.lower()) and (
            "land rover" in title_make_check or "range rover" in title_make_check or "rangerover" in title_make_check or "vogue" in title_make_check
        ):
            is_luxury_bypass = True

        if not is_luxury_bypass:
            acceptable_makes = MAKE_VETO_ALIASES.get(req_make_lower, [req_make_lower])
            acceptable_makes = [m.replace("-", " ") for m in acceptable_makes] + acceptable_makes

            if not any(m in title_make_check for m in acceptable_makes):
                return veto(f"Make '{requested_make}' not found in title")

    # ── 3. Budget — with +5% negotiation buffer ────────────────────────────
    if clean_price > 0:
        if min_budget > 0 and clean_price < min_budget:
            return veto(f"Listing price ({clean_price:,} PKR) is below price floor ({min_budget:,} PKR)")

        if requested_budget and requested_budget > 0:
            hard_ceiling = int(requested_budget * 1.05)
            if clean_price > hard_ceiling:
                return veto(
                    f"Listing price ({clean_price:,} PKR) exceeds max budget "
                    f"({requested_budget:,} PKR) + 5% buffer ({hard_ceiling:,})"
                )

    # ── 4. Color conflict ──────────────────────────────────────────────────
    if requested_color:
        req_color = requested_color.lower().strip()
        for color in COMMON_COLORS:
            if color == req_color:
                continue
            if color in title_lower:
                return veto(f"Title contains '{color}' but user wants '{req_color}'")

    # ── 5. City — soft signal only ─────────────────────────────────────────
    car_city_lower = (car.city or "").lower().strip()
    req_city_str   = (requested_city or "").lower().strip()
    if req_city_str:
        req_cities = [c.strip() for c in re.split(r',|\band\b', req_city_str) if c.strip()]
        city_matched = any(rc in car_city_lower or rc in title_lower for rc in req_cities)
        city_score = 30.0 if city_matched else 10.0
    else:
        city_score = 30.0 if car_city_lower else 15.0

    budget_score = 10.0 if clean_price == 0 else 40.0

    # ── 6. Smart trim — lazy seller fix ───────────────────────────────────
    trim_score = 0.0
    title_clean = title_lower.replace("-", "")

    if requested_trim:
        req_trim_clean = requested_trim.lower().replace("-", "")
        GENERIC_SKIP   = {"automatic", "manual", "car", "sedan", "petrol", "hybrid"}
        trim_keywords  = req_trim_clean.split()

        trim_explicitly_found = False
        for keyword in trim_keywords:
            if keyword in GENERIC_SKIP:
                continue
            valid_forms = TRIM_ALIASES.get(keyword, [keyword])
            if any(form in title_clean for form in valid_forms):
                trim_explicitly_found = True
                break

        if trim_explicitly_found:
            trim_score = 15.0
        else:
            for keyword in trim_keywords:
                if keyword in GENERIC_SKIP:
                    continue
                conflicts = TRIM_CONFLICTS.get(keyword, [])
                for conflict in conflicts:
                    if conflict in title_clean:
                        return veto(
                            f"Conflicting trim. Wanted '{requested_trim}', "
                            f"title contains '{conflict}'"
                        )
            trim_score = 0.0

    # ── 6.5. Feature Matcher ───────────────────────────────────────────────
    feature_score = 0.0
    if required_features:
        for feature in required_features:
            feat_lower = feature.lower().replace("_", " ")

            if "sunroof" in feat_lower and requested_model.lower() == "corolla":
                if "gli" in title_lower or "xli" in title_lower:
                    return veto("Corolla GLi/XLi do not have factory sunroofs")
                if "grande" in title_lower or "altis" in title_lower:
                    feature_score += 20.0

            if "panoramic" in feat_lower and requested_model.lower() == "vezel":
                if clean_year > 0 and clean_year < 2021:
                    return veto("Vezel panoramic sunroof only available 2021+")

            if feat_lower in title_lower or feat_lower.replace(" ", "") in title_clean:
                feature_score += 15.0
            elif "push start" in feat_lower and ("push" in title_lower or "start" in title_lower):
                feature_score += 10.0

    # ── 7. Year bounds ─────────────────────────────────────────────────────
    if clean_year > 0:
        if min_year > 0 and clean_year < min_year:
            return veto(f"Too old. Car is {clean_year}, min requested {min_year}.")
        if max_year > 0 and clean_year > max_year:
            return veto(f"Too new. Car is {clean_year}, max requested {max_year}.")

    # ── 8. Staleness veto ──────────────────────────────────────────────────
    # Allow 90 days on market for budgets >= 1.5 Crore PKR
    max_age_limit = 90 if eff_budget >= 15_000_000 else 14
    age_score = max(0.0, 15.0 - (car.age_days * 0.5))

    if 0 < car.age_days <= 998 and car.age_days > max_age_limit:
        return veto(f"Stale listing. Posted {car.age_days} days ago (limit: {max_age_limit}).")

    # ── 9. Data quality ────────────────────────────────────────────────────
    year_score    = 7.5 if clean_year    > 0 else 0.0
    mileage_score = 7.5 if clean_mileage > 0 else 0.0
    quality_score = year_score + mileage_score

    # ── Total ──────────────────────────────────────────────────────────────
    raw_total   = budget_score + city_score + age_score + quality_score + trim_score + feature_score
    total_score = round(raw_total * identity_score, 2)

    if debug:
        print(
            f"  [REC-SCORE] '{car.title[:45]}' | "
            f"id={identity_score:.2f} budget={budget_score:.1f} "
            f"city={city_score:.1f} age={age_score:.1f} "
            f"quality={quality_score:.1f} trim={trim_score:.1f} feat={feature_score:.1f} "
            f"→ {total_score:.2f}"
        )

    return total_score


# ---------------------------------------------------------------------------
# MAIN PIPELINE
# ---------------------------------------------------------------------------

def normalize_recommendation_target(
    raw_listings: list[CarListing],
    requested_make: str,
    requested_model: str,
    requested_city: str,
    requested_budget: int,
    requested_color: str,
    requested_trim: str,
    required_features: list[str] = None,
    min_budget: int = 0,
    min_year: int = 0,
    max_year: int = 0,
    top_k: int = 5,
    debug: bool = False,
) -> list[CarListing]:
    """
    Scores, deduplicates, and selects the best `top_k` listings for a single
    AI-recommended car model.
    """
    corrected_make, corrected_model = normalize_make_model(
        requested_make or "", requested_model or ""
    )
    corrected_city = normalize_city(requested_city or "")

    # ── Step 1: Score all listings, build dedup map ────────────────────────
    scored_map: dict[tuple, dict] = {}
    veto_count = 0

    for car in raw_listings:
        clean_price   = _clean_price(car.price)
        clean_year    = _clean_int(car.year)
        clean_mileage = _clean_int(car.mileage)

        score = _calculate_recommendation_score(
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
            required_features=required_features,
            min_budget=min_budget,
            min_year=min_year,
            max_year=max_year,
            debug=debug,
        )

        if score == 0.0:
            veto_count += 1
            continue

        display_city = (car.city or "").strip()
        GARBAGE_VALS = {
            "automatic", "manual", "unregistered", "petrol",
            "hybrid", "cng", "diesel", "electric",
        }
        if display_city.lower() in GARBAGE_VALS:
            req_cities = [
                c.strip()
                for c in re.split(r',|\band\b', corrected_city.lower())
                if c.strip()
            ]
            for rc in req_cities:
                if rc in car.title.lower():
                    display_city = rc.title()
                    break

        dedup_key = (car.title.lower().strip(), clean_year, clean_mileage)
        if dedup_key in scored_map:
            if score > scored_map[dedup_key]["score"]:
                scored_map[dedup_key] = {
                    "car": car, "score": score, "price": clean_price,
                    "year": clean_year, "mileage": clean_mileage,
                    "display_city": display_city,
                }
        else:
            scored_map[dedup_key] = {
                "car": car, "score": score, "price": clean_price,
                "year": clean_year, "mileage": clean_mileage,
                "display_city": display_city,
            }

    label = f"{corrected_make} {corrected_model}".strip()
    print(
        f"[RecNorm] {label}: "
        f"{len(raw_listings)} raw -> {len(scored_map)} qualified, "
        f"{veto_count} vetoed."
    )

    if not scored_map:
        return []

    # ── Step 2: Sort and bucket by platform ───────────────────────────────
    all_scored = sorted(scored_map.values(), key=lambda x: x["score"], reverse=True)

    buckets: dict[str, list] = {
        "PakWheels": [],
        "OLX":       [],
        "Gari.pk":   [],
        "Other":     [],
    }

    for item in all_scored:
        plat = item["car"].platform
        if plat == "PakWheels":
            buckets["PakWheels"].append(item)
        elif plat == "OLX":
            buckets["OLX"].append(item)
        elif "Gari" in plat or "Wise" in plat:
            buckets["Gari.pk"].append(item)
        else:
            buckets["Other"].append(item)

    # ── Step 3: Cross-platform allocation for top_k slots ─────────────────
    half      = max(1, top_k // 2)
    quarter   = max(1, top_k // 4)
    remainder = max(0, top_k - half - quarter)

    pw_quota, olx_quota, gari_quota = (2, 2, 1) if top_k == 5 else (half, quarter, remainder)

    pw_selected   = buckets["PakWheels"][:pw_quota]
    olx_selected  = buckets["OLX"][:olx_quota]
    gari_selected = (buckets["Gari.pk"] + buckets["Other"])
    gari_selected.sort(key=lambda x: x["score"], reverse=True)
    gari_selected = gari_selected[:gari_quota]

    selection = pw_selected + olx_selected + gari_selected

    # ── Step 4: Backfill to guarantee exactly top_k results ───────────────
    shortfall = top_k - len(selection)
    if shortfall > 0:
        already_selected_keys = {id(item) for item in selection}
        backup_pool = [
            item for item in all_scored
            if id(item) not in already_selected_keys
        ]
        selection.extend(backup_pool[:shortfall])
        if debug and backup_pool[:shortfall]:
            print(
                f"[RecNorm] {label}: backfilled "
                f"{len(backup_pool[:shortfall])} slot(s) from overflow pool."
            )

    selection.sort(key=lambda x: x["score"], reverse=True)
    top_data = selection[:top_k]

    # ── Step 5: Build output CarListing objects ────────────────────────────
    result: list[CarListing] = []
    for data in top_data:
        car = data["car"]
        result.append(CarListing(
            id=car.id,
            title=car.title.strip(),
            price=data["price"],
            mileage=data["mileage"],
            city=data["display_city"],
            year=data["year"],
            listing_url=car.listing_url,
            image_url=car.image_url,
            platform=car.platform,
            age_days=car.age_days,
            scraped_at=car.scraped_at,
        ))

    print(
        f"[RecNorm] {label}: returning {len(result)}/{top_k} listings "
        f"(PW={len(pw_selected)}, OLX={len(olx_selected)}, "
        f"Gari={len(gari_selected)}, backfill={max(0, shortfall)})."
    )
    return result