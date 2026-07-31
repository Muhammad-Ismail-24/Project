"""
scrapers/recommend_normalizer.py
GaariGuru — AI Matchmaker Normalizer v1.1

Purpose:
    A purpose-built scoring pipeline for the AI Recommendation feature.
    Operates on a single recommended model at a time and returns exactly
    `top_k` (default: 5) listings with a cross-platform mix.

Key differences from the strict keyword-search normalizer:
    - +5% negotiation buffer on budget (buyers negotiate in Pakistan).
    - "Lazy Seller" trim handling: missing trim ≠ wrong trim.
    - Trim boost: +15.0 pts when the exact trim IS found in the title.
    - Elite Staleness Veto: Standard cars die at 14 days, but budgets 
      over 1.5 Crore are allowed up to 90 days on market.
    - No city hard veto — city is a soft signal for AI recommendations.
    - Feature matcher (sunroof, push start boosts).
"""

import re
from models.car_schema import CarListing

# ── Import all shared knowledge maps and utilities from main normalizer ─────
from scrapers.normalizer import (
    MAKE_VETO_ALIASES,
    TRIM_ALIASES,
    COMMON_COLORS,
    normalize_make_model,
    normalize_city,
    _clean_price,
    _clean_int,
    _calculate_identity_score,
)

# ---------------------------------------------------------------------------
# RECOMMEND-SPECIFIC CONFLICT MAP
# ---------------------------------------------------------------------------
# Maps a requested trim keyword to trims that explicitly contradict it.
# Only used when the title CONTAINS one of the listed conflict strings.
# Absence of a trim in the title is NOT a conflict — it's a lazy seller.

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
    # Strip phone numbers / long digit sequences from title before any matching
    clean_title = re.sub(r'\b\d{7,}\b', '', car.title).strip()
    title_lower = clean_title.lower()

    def veto(reason: str) -> float:
        if debug:
            print(f"  [REC-VETO] '{clean_title[:50]}' — {reason}")
        return 0.0

    # ── 1. Identity check ──────────────────────────────────────────────────
    identity_score = _calculate_identity_score(requested_make, requested_model, clean_title)
    if identity_score < 0.75:
        return veto(f"Identity too low ({identity_score:.2f}) for model='{requested_model}'")

    # ── 2. Make check (With Elite Fallbacks) ───────────────────────────────
    if requested_make:
        req_make_lower = requested_make.lower()
        acceptable_makes = MAKE_VETO_ALIASES.get(req_make_lower, [req_make_lower])
        
        # 🚨 FOOLPROOF MAKE ALIASES FOR ELITE CARS 🚨
        if "mercedes" in req_make_lower:
            acceptable_makes.extend(["mercedes", "benz", "mercedes-benz", "mercedes benz"])
        if "land rover" in req_make_lower or "range rover" in requested_model.lower():
            acceptable_makes.extend(["land rover", "range rover", "rangerover"])
            
        # Robust hyphen handling: treat hyphens and spaces as equivalent
        acceptable_makes = [m.replace("-", " ") for m in acceptable_makes] + acceptable_makes
        title_make_check = title_lower.replace("-", " ")
        
        if not any(m in title_make_check for m in acceptable_makes):
            return veto(f"Make '{requested_make}' not found in title")

    # ── 3. Budget — with +5% negotiation buffer ────────────────────────────
    if clean_price > 0:
        if min_budget > 0 and clean_price < min_budget:
            return veto(f"Listing price ({clean_price:,} PKR) is below 30% budget floor ({min_budget:,} PKR)")

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
        city_score = 30.0 if city_matched else 10.0   # penalty, not veto
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
            # exact match — reward it
            trim_score = 15.0
        else:
            # Check for explicit conflicts before assuming lazy seller
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
            # No trim, no conflict → lazy seller, keep the listing
            trim_score = 0.0

    # ── 6.5. Feature Matcher (Hard Vetoes & Boosting) ────────────────────────
    feature_score = 0.0
    if required_features:
        for feature in required_features:
            feat_lower = feature.lower().replace("_", " ")
            
            # 1. Trim-to-Feature Hardcoding
            if "sunroof" in feat_lower and requested_model.lower() == "corolla":
                if "gli" in title_lower or "xli" in title_lower:
                    return veto("Corolla GLi/XLi do not have factory sunroofs")
                if "grande" in title_lower or "altis" in title_lower:
                    feature_score += 20.0
            
            # 2. Year-to-Feature Hardcoding
            if "panoramic" in feat_lower and requested_model.lower() == "vezel":
                if clean_year > 0 and clean_year < 2021:
                    return veto("Vezel panoramic sunroof only available 2021+")
                    
            # 3. Keyword Scanning
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
    # age_days == 999 = unknown → not vetoed.
    # Elite luxury cars take longer to sell. If budget > 1.5 Crore, allow 90 days.
    # Cast to int to guarantee the evaluation doesn't fail due to type coercion.
    eff_budget = int(requested_budget) if requested_budget else 0
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

    Returns a list of up to `top_k` CarListing objects, cross-platform mixed
    where possible. Never raises — returns [] on failure.
    """
    corrected_make,  corrected_model = normalize_make_model(
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

        # Garbage city rescue — overwrite transmission/fuel strings with real city
        display_city  = (car.city or "").strip()
        GARBAGE_VALS  = {
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

        # Keep highest-scored version when duplicate
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
        "Other":     [],   # Drive.pk, AutoDeals, FameWheels, etc.
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

    pw_quota   = half        # 2 of 5
    olx_quota  = quarter     # 1 of 5 
    gari_quota = remainder   # 2 of 5 

    if top_k == 5:
        pw_quota, olx_quota, gari_quota = 2, 2, 1

    pw_selected   = buckets["PakWheels"][:pw_quota]
    olx_selected  = buckets["OLX"][:olx_quota]
    gari_selected = (buckets["Gari.pk"] + buckets["Other"])
    gari_selected.sort(key=lambda x: x["score"], reverse=True)
    gari_selected = gari_selected[:gari_quota]

    selection = pw_selected + olx_selected + gari_selected

    # ── Step 4: Backfill to guarantee exactly top_k results ───────────────
    shortfall = top_k - len(selection)
    if shortfall > 0:
        already_selected_keys = {
            id(item) for item in selection
        }
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