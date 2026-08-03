"""
scrapers/recommend_normalizer.py
Drive Fetch — AI Matchmaker Normalizer v2.3

Purpose:
    Scoring and selection pipeline for AI Recommendation results.
    Operates on one recommended model at a time, returns exactly
    `top_k` (default: 5) listings with a cross-platform mix.

v2.2 updates:
  - PERFECT MERGE: Combines the advanced v2.0 Feature Keyword Engine
    (with _MODEL_TRIM_GATES) with the v2.1 Local Identity Scorer.
  - Ensures luxury aliases (S-Class, Range Rover) are correctly parsed
    using the private _MODEL_ALIAS_MAP.
  - Retains 60/120-day staleness, graduated budget scoring, and
    platform-aware deduplication.

v2.3 updates:
  - AUTO BUDGET FLOOR: If min_budget == 0 and requested_budget > 0,
    auto-calculates effective_min_budget = int(requested_budget * 0.70).
    Hard-vetos listings below this floor to filter out cheap/old cars
    that don't match the buyer's intended price band.
  - DESCRIPTION DEEP SCAN: Trim and feature matching now scans both
    car.title and car.description (or car.about) via a combined
    search_text buffer. Lazy sellers who omit trim from the title but
    mention it in the description are no longer filtered out.
  - TRIM PRIORITY WEIGHTING: Title trim match = +25.0 pts (was +15.0),
    description-only trim match = +12.0 pts. Listings that declare the
    trim in the headline rank above those that only mention it in the body.
  - Feature gates also scan search_text (title + description) so features
    confirmed only in the description count toward scoring.
"""

import re
from difflib import SequenceMatcher
from models.car_schema import CarListing

# ── Import ONLY pure functions + read-only constants from main normalizer ──
# We do NOT import MAKE_VETO_ALIASES, MODEL_ALIAS_MAP, or _calculate_identity_score
# because we need private copies that won't pollute the keyword search pipeline.
from scrapers.normalizer import (
    normalize_make_model,
    normalize_city,
    _clean_price,
    _clean_int,
    TRIM_ALIASES,
    COMMON_COLORS,
)

# ---------------------------------------------------------------------------
# PRIVATE MAKE VETO ALIASES
# ---------------------------------------------------------------------------

_MAKE_VETO_ALIASES: dict[str, list[str]] = {
    # Japanese / Korean
    "daihatsu":    ["toyota", "daihatsu"],
    "toyota":      ["toyota", "daihatsu"],
    "mazda":       ["mazda", "suzuki"],
    "subaru":      ["subaru", "daihatsu", "toyota"],
    "nissan":      ["nissan", "suzuki", "mitsubishi"],
    "mitsubishi":  ["mitsubishi", "nissan", "suzuki"],
    "suzuki":      ["suzuki"],
    "honda":       ["honda"],
    "hyundai":     ["hyundai"],
    "kia":         ["kia"],
    "lexus":       ["lexus", "toyota"],
    # European / Luxury
    "mercedes-benz": ["mercedes-benz", "mercedes", "benz", "mercedesbenz"],
    "mercedes":      ["mercedes-benz", "mercedes", "benz"],
    "bmw":           ["bmw", "bimmer"],
    "audi":          ["audi"],
    "porsche":       ["porsche"],
    "land rover":    ["land rover", "landrover", "range rover", "rangerover"],
    "range rover":   ["range rover", "rangerover", "land rover", "vogue", "autobiography"],
    "volkswagen":    ["volkswagen", "vw"],
    "volvo":         ["volvo"],
    # Chinese
    "mg":            ["mg", "morris garages"],
    "changan":       ["changan", "chang'an"],
    "haval":         ["haval", "hawtai"],
    "chery":         ["chery", "cheryl"],
    "proton":        ["proton"],
    "byd":           ["byd", "build your dreams"],
    "gwm":           ["gwm", "great wall"],
}

# ---------------------------------------------------------------------------
# PRIVATE MODEL ALIAS MAP
# ---------------------------------------------------------------------------

_MODEL_ALIAS_MAP: dict[str, list[str]] = {
    # Mercedes-Benz
    "s-class":           ["s class", "s-class", "sclass", "s300", "s350", "s400",
                          "s450", "s500", "s550", "s560", "s580", "s600", "s63", "s65"],
    "e-class":           ["e class", "e-class", "eclass", "e200", "e220", "e250",
                          "e300", "e350", "e400", "e450", "e53", "e63"],
    "c-class":           ["c class", "c-class", "cclass", "c180", "c200", "c220",
                          "c250", "c300", "c350", "c43", "c63"],
    "g-class":           ["g class", "g-class", "gclass", "g63", "g500", "g350",
                          "g400", "g55", "g wagon", "gwagon"],
    "cla":               ["cla", "cla180", "cla200", "cla220", "cla250", "cla45"],
    "gla":               ["gla", "gla180", "gla200", "gla220", "gla250", "gla45"],
    "glc":               ["glc", "glc200", "glc220", "glc250", "glc300", "glc43", "glc63"],
    "gle":               ["gle", "gle300", "gle350", "gle400", "gle450", "gle53", "gle63"],
    "gls":               ["gls", "gls350", "gls400", "gls450", "gls580", "gls63"],
    # BMW
    "3 series":          ["3 series", "3series", "318i", "320i", "325i", "328i",
                          "330i", "335i", "340i", "316i", "318d", "320d"],
    "5 series":          ["5 series", "5series", "520i", "523i", "525i", "528i",
                          "530i", "535i", "540i", "545i", "550i", "520d", "525d", "530d"],
    "7 series":          ["7 series", "7series", "730li", "735li", "740li", "745li",
                          "750li", "760li", "730i", "740i"],
    "x1":                ["x1", "bmw x1"],
    "x3":                ["x3", "bmw x3", "x3 m40i", "x3 xdrive"],
    "x5":                ["x5", "bmw x5", "x5 m50i", "x5 xdrive"],
    "x7":                ["x7", "bmw x7", "x7 m50i"],
    # Audi
    "a3":                ["a3", "audi a3", "a3 1.4", "a3 1.8", "a3 2.0"],
    "a4":                ["a4", "audi a4", "a4 1.8t", "a4 2.0t", "a4 allroad"],
    "a6":                ["a6", "audi a6", "a6 2.0", "a6 3.0", "a6 allroad"],
    "q5":                ["q5", "audi q5", "q5 2.0t", "q5 3.0t", "q5 sportback"],
    "q7":                ["q7", "audi q7", "q7 3.0", "q7 4.2"],
    # Porsche
    "cayenne":           ["cayenne", "cayenne s", "cayenne gts", "cayenne turbo",
                          "cayenne e-hybrid", "cayenne hybrid", "cayenne coupe"],
    "macan":             ["macan", "macan s", "macan gts", "macan turbo"],
    "panamera":          ["panamera", "panamera 4s", "panamera turbo", "panamera gts"],
    "taycan":            ["taycan", "taycan 4s", "taycan turbo", "cross turismo"],
    # Land Rover / Range Rover
    "range rover":       ["range rover", "rangerover", "vogue", "autobiography",
                          "lwb", "swb", "land rover range"],
    "range rover sport": ["range rover sport", "rangerover sport", "rr sport",
                          "range rover sports"],
    "evoque":            ["evoque", "range rover evoque", "rr evoque"],
    "velar":             ["velar", "range rover velar", "rr velar"],
    "defender":          ["defender", "defender 90", "defender 110", "defender 130"],
    "discovery":         ["discovery", "disco", "discovery sport", "lr4"],
    # Lexus
    "lx":                ["lx", "lx570", "lx 570", "lx600", "lx 600", "lexus lx"],
    "rx":                ["rx", "rx300", "rx350", "rx450h", "rx 300", "rx 350",
                          "rx 450h", "lexus rx"],
    "es":                ["es", "es250", "es300", "es350", "es300h", "lexus es"],
    "is":                ["is", "is200", "is250", "is300", "is350", "lexus is"],
    "nx":                ["nx", "nx200", "nx300", "nx350h", "lexus nx"],
    # Nissan Patrol variants
    "patrol":            ["patrol", "patrol y62", "patrol y61", "patrol safari",
                          "patrol v8", "patrol v6", "patrol platinum"],
    # Toyota Prado variants
    "prado":             ["prado", "land cruiser prado", "lc prado", "prado txl",
                          "prado vxl", "prado 4.0", "prado 2.7"],
    "land cruiser":      ["land cruiser", "landcruiser", "lc200", "lc300",
                          "land cruiser v8", "land cruiser zx"],
    # Common JDM models with typo variants
    "vezel":             ["vezel", "vezal", "vesel", "vezzel"],
    "corolla":           ["corolla", "carolla", "corola", "coralla", "altis", "grande",
                          "corolla fielder"],
    "civic":             ["civic", "civick", "civec", "civic reborn", "civic rs",
                          "civic x", "civic turbo"],
    "wagon r":           ["wagon r", "wagonr", "wagoner", "wagon-r", "stingray"],
    "br-v":              ["brv", "br-v", "br v"],
    "hr-v":              ["hrv", "hr-v", "hr v"],
    "cr-v":              ["crv", "cr-v", "cr v"],
    "n-box":             ["n box", "nbox", "n-box", "en box"],
    "n-wgn":             ["n wgn", "nwgn", "n-wgn", "en wgn"],
    # Chinese
    "zs ev":             ["zs ev", "zsev", "zs-ev", "zs electric", "mg zs ev"],
    "alsvin":            ["alsvin", "alswin", "alveen"],
    "deepal s07":        ["deepal s07", "deepal s7", "s07"],
    "deepal l07":        ["deepal l07", "deepal l7", "l07"],
    "atto 3":            ["atto 3", "atto3", "atto-3", "byd atto"],
    "jolion":            ["jolion", "haval jolion"],
    "h6":                ["h6", "haval h6"],
    "tiggo 4 pro":       ["tiggo 4", "tiggo4", "tiggo 4 pro"],
    "tiggo 8 pro":       ["tiggo 8", "tiggo8", "tiggo 8 pro"],
    "sportage":          ["sportage", "sportech"],
    "tucson":            ["tucson", "tuson", "tuscon"],
    "fortuner":          ["fortuner", "fortunner", "fortener"],
}

# ---------------------------------------------------------------------------
# TRIM CONFLICTS
# ---------------------------------------------------------------------------

_TRIM_CONFLICTS: dict[str, list[str]] = {
    "awd":       ["fwd", "alpha", "alpha fwd", "2wd"],
    "4x4":       ["fwd", "2wd", "alpha fwd"],
    "fwd":       ["awd", "4x4", "4wd", "xdrive", "quattro"],
    "alpha":     ["awd", "fwd", "4x4"],
    "manual":    ["auto", "automatic", "cvt", "ags", "prosmatec", "easytronic",
                  "tiptronic", "dct", "pdk"],
    "automatic": ["manual", "mt"],
    "auto":      ["manual", "mt"],
    "cvt":       ["manual", "mt"],
    "pdk":       ["manual", "mt"],
    "dct":       ["manual", "mt"],
    "hybrid":    ["non-hybrid", "non hybrid", "petrol only"],
    "petrol":    ["diesel", "ev", "electric", "hybrid", "plug-in"],
    "diesel":    ["petrol", "ev", "electric", "hybrid"],
    "turbo":     ["naturally aspirated", "na engine"],
    "essence":   ["trophy"],
    "trophy":    ["essence"],
    "v6":        ["v8", "v12"],
    "v8":        ["v6", "v12"],
}

# ---------------------------------------------------------------------------
# FEATURE KEYWORDS MAP & GATES (From v2.0)
# ---------------------------------------------------------------------------

_FEATURE_KEYWORDS: dict[str, dict] = {
    "sunroof": {
        "positive": ["sunroof", "moonroof", "panoramic", "sunrooof", "sun roof"],
        "negative": [],
    },
    "panoramic sunroof": {
        "positive": ["panoramic", "pano roof", "panoroof"],
        "negative": [],
    },
    "push start": {
        "positive": ["push start", "push-start", "keyless", "smart key"],
        "negative": [],
    },
    "back camera": {
        "positive": ["back camera", "reverse camera", "rear camera", "parking camera", "backup camera"],
        "negative": [],
    },
    "leather seats": {
        "positive": ["leather", "leather seats", "nappa", "leatherette"],
        "negative": [],
    },
    "alloy wheels": {
        "positive": ["alloy", "alloy wheels", "mags"],
        "negative": ["steel rim", "steel wheel"],
    },
    "cruise control": {
        "positive": ["cruise control", "adaptive cruise"],
        "negative": [],
    },
}

_MODEL_TRIM_GATES: dict[str, dict[str, dict]] = {
    "toyota:corolla": {
        "sunroof": {
            "require_trims": ["grande", "altis grande", "altis", "x corolla"],
            "min_year": 0,
            "veto_trims": ["gli", "xli"],
        },
    },
    "toyota:yaris":   {"sunroof": {"require_trims": [], "min_year": 0, "veto_trims": ["any"]}},
    "toyota:rush":    {"sunroof": {"require_trims": [], "min_year": 0, "veto_trims": ["any"]}},
    "toyota:aqua":    {"sunroof": {"require_trims": [], "min_year": 0, "veto_trims": ["any"]}},
    "toyota:fortuner": {
        "sunroof": {
            "require_trims": ["vrz", "sigma3", "sigma 3", "legender"],
            "min_year": 0,
            "veto_trims": [],
        },
    },
    "honda:city": {
        "sunroof": {
            "require_trims": ["aspire", "rs", "1.5 aspire"],
            "min_year": 0,
            "veto_trims": ["prosmatec", "vti", "manual"],
        },
    },
    "honda:civic": {
        "sunroof": {
            "require_trims": ["rs", "oriel 1.5", "oriel turbo", "oriel prosmatec 1.8"],
            "min_year": 0,
            "veto_trims": ["reborn", "exi"],
        },
    },
    "honda:br-v":     {"sunroof": {"require_trims": [], "min_year": 0, "veto_trims": ["any"]}},
    "honda:fit":      {"sunroof": {"require_trims": [], "min_year": 0, "veto_trims": ["any"]}},
    "honda:vezel": {
        "sunroof": {
            "require_trims": ["rs", "z", "ehev", "e:hev"],
            "min_year": 2021,
            "veto_trims": [],
        },
    },
    "kia:stonic":     {"sunroof": {"require_trims": [], "min_year": 0, "veto_trims": ["any"]}},
    "suzuki:cultus":  {"sunroof": {"require_trims": [], "min_year": 0, "veto_trims": ["any"]}},
    "suzuki:wagon r": {"sunroof": {"require_trims": [], "min_year": 0, "veto_trims": ["any"]}},
    "suzuki:swift":   {"sunroof": {"require_trims": [], "min_year": 0, "veto_trims": ["any"]}},
    "suzuki:alto":    {"sunroof": {"require_trims": [], "min_year": 0, "veto_trims": ["any"]}},
    "suzuki:liana":   {"sunroof": {"require_trims": [], "min_year": 0, "veto_trims": ["any"]}},
    "suzuki:baleno":  {"sunroof": {"require_trims": [], "min_year": 0, "veto_trims": ["any"]}},
}

_CITY_COLOR_EXCEPTIONS: set[str] = {
    "blue area", "blue world", "maroon town", "gold town", "golden town",
    "green town", "green valley", "silver city", "silver town", "white city",
    "black town", "red zone", "orange town",
}

# ---------------------------------------------------------------------------
# HELPER: FEATURE GATES
# ---------------------------------------------------------------------------

def _check_feature_gates(
    car,
    requested_make: str,
    requested_model: str,
    required_features: list[str],
    title_lower: str,
    clean_year: int,
    debug: bool,
) -> tuple[float, str | None]:
    """
    Returns (feature_score, veto_reason).
    veto_reason is None when the listing passes all feature gates.
    feature_score is a bonus (+15 per confirmed feature, -5 if likely absent).
    """
    feature_score = 0.0
    make_lower    = (requested_make or "").lower().strip()
    model_lower   = (requested_model or "").lower().strip()
    gate_key      = f"{make_lower}:{model_lower}"

    for feat in required_features:
        feat_lower = feat.lower().strip()

        # Find keyword config (try exact, then first word)
        feat_info = _FEATURE_KEYWORDS.get(feat_lower) or _FEATURE_KEYWORDS.get(feat_lower.split()[0], {})
        positive_kws = feat_info.get("positive", [feat_lower])
        found_positive = any(kw in title_lower for kw in positive_kws)

        if found_positive:
            feature_score += 15.0
            if debug:
                print(f"  [FEATURE +15] '{feat}' confirmed in title")

        # Find model gate (try exact feature name, then first word)
        model_gates = _MODEL_TRIM_GATES.get(gate_key, {})
        feat_gate   = model_gates.get(feat_lower) or model_gates.get(feat_lower.split()[0])

        if feat_gate:
            veto_trims    = feat_gate.get("veto_trims", [])
            require_trims = feat_gate.get("require_trims", [])
            min_year      = feat_gate.get("min_year", 0)

            # veto_trims=["any"] → model never has this feature
            if veto_trims == ["any"]:
                reason = f"{requested_make} {requested_model} has no factory {feat} in any trim"
                if debug:
                    print(f"  [FEAT-VETO] {reason}")
                return 0.0, reason

            # Specific trim vetoes
            for vt in veto_trims:
                if vt in title_lower:
                    reason = f"Trim '{vt}' confirmed to NOT have {feat}"
                    if debug:
                        print(f"  [FEAT-VETO] {reason}")
                    return 0.0, reason

            # Year gate
            if min_year > 0 and clean_year > 0 and clean_year < min_year:
                reason = f"{feat} only available from {min_year} (listing is {clean_year})"
                if debug:
                    print(f"  [FEAT-VETO] {reason}")
                return 0.0, reason

            # require_trims soft check — penalty if feature not confirmed and trim not shown
            if require_trims and not found_positive:
                has_required = any(rt in title_lower for rt in require_trims)
                if not has_required:
                    feature_score -= 5.0
                    if debug:
                        print(f"  [FEATURE -5] '{feat}' required trim not found in title")

    return feature_score, None

# ---------------------------------------------------------------------------
# LOCAL IDENTITY SCORER (Uses private _MODEL_ALIAS_MAP)
# ---------------------------------------------------------------------------

def _normalize_str(s: str) -> str:
    return s.lower().replace(" ", "").replace("-", "").replace(".", "").replace("_", "")

def _local_identity_score(requested_make: str, requested_model: str, title: str) -> float:
    if not requested_model:
        return 1.0

    model_clean = _normalize_str(requested_model)
    if requested_make:
        make_clean = _normalize_str(requested_make)
        model_clean = model_clean.replace(make_clean, "").strip()

    if not model_clean:
        return 1.0

    target_clean = _normalize_str(title)
    
    # 1. Resolve aliases using the PRIVATE _MODEL_ALIAS_MAP
    aliases = [model_clean]
    for canonical, alias_list in _MODEL_ALIAS_MAP.items():
        alias_normalized = [_normalize_str(a) for a in alias_list]
        if model_clean in alias_normalized or model_clean == canonical:
            aliases = alias_normalized
            break

    # 2. Exact substring match
    for alias in aliases:
        if alias in target_clean:
            return 1.0

    # 3. Token overlap for compound titles
    model_tokens = set(requested_model.lower().replace("-", " ").split())
    title_tokens = set(title.lower().replace("-", " ").split())
    if model_tokens:
        overlap = model_tokens & title_tokens
        token_ratio = len(overlap) / len(model_tokens)
        if token_ratio >= 0.75:
            return max(0.85, token_ratio)

    # 4. Fuzzy match
    best_ratio = 0.0
    title_words = title.lower().replace("-", " ").replace(".", " ").replace("_", " ").split()

    for alias in aliases:
        for word in title_words:
            if abs(len(word) - len(alias)) <= 2:
                ratio = SequenceMatcher(None, alias, word).ratio()
                if ratio > best_ratio:
                    best_ratio = ratio

    return round(best_ratio, 4)

# ---------------------------------------------------------------------------
# SCORING ENGINE
# ---------------------------------------------------------------------------

def _score_listing(
    car: CarListing,
    requested_make: str,
    requested_model: str,
    requested_city: str,
    requested_budget: int,
    requested_color: str,
    clean_price: int,
    clean_year: int,
    clean_mileage: int,
    requested_trim: str = "",
    required_features: list[str] | None = None,
    min_budget: int = 0,
    min_year: int = 0,
    max_year: int = 0,
    debug: bool = False,
) -> float:
    """
    Scores one listing for AI recommendation relevance.
    Returns 0.0 on any hard veto, positive float otherwise.
    """
    clean_title = re.sub(r'\b\d{7,}\b', '', car.title).strip()
    title_lower = clean_title.lower()

    eff_budget = int(requested_budget) if requested_budget else 0
    is_luxury  = eff_budget >= 15_000_000    # 1.5 crore+ → luxury thresholds

    def veto(reason: str) -> float:
        if debug:
            print(f"  [REC-VETO] '{clean_title[:55]}' — {reason}")
        return 0.0

    # ── 1. Identity score ──────────────────────────────────────────────────
    identity_score = _local_identity_score(requested_make, requested_model, clean_title)
    
    min_identity = 0.55 if is_luxury else 0.75
    if identity_score < min_identity:
        return veto(
            f"Identity {identity_score:.2f} < {min_identity} for model='{requested_model}'"
        )

    # ── 2. Make check ──────────────────────────────────────────────────────
    if requested_make:
        req_make_lower = requested_make.lower().strip()
        title_normalized = title_lower.replace("-", " ")

        acceptable = _MAKE_VETO_ALIASES.get(req_make_lower, [req_make_lower])
        acceptable_norm = [m.replace("-", " ").replace("_", " ") for m in acceptable]

        if not any(m in title_normalized for m in acceptable_norm):
            return veto(f"Make '{requested_make}' not found in title")

    # ── 3. Budget check (graduated score + auto 70% floor) ───────────────
    # Auto-calculate 70% floor when caller passes min_budget=0 but budget is
    # known. Prevents e.g. a PKR 2M Alto surfacing for a PKR 5M Corolla search.
    eff_min_budget = min_budget
    if eff_min_budget == 0 and eff_budget > 0:
        eff_min_budget = int(eff_budget * 0.70)

    budget_score = 0.0
    if clean_price > 0 and eff_budget > 0:
        if eff_min_budget > 0 and clean_price < eff_min_budget:
            return veto(
                f"Price PKR {clean_price:,} below 70% floor "
                f"PKR {eff_min_budget:,} (budget PKR {eff_budget:,})"
            )

        hard_ceiling = int(eff_budget * 1.05)
        if clean_price > hard_ceiling:
            return veto(
                f"Price PKR {clean_price:,} > ceiling PKR {hard_ceiling:,} "
                f"(budget {eff_budget:,} + 5%)"
            )

        ratio = clean_price / eff_budget
        if ratio >= 0.85:
            budget_score = 40.0                             
        elif ratio >= 0.70:
            budget_score = 20.0 + (ratio - 0.70) / 0.15 * 20.0  
        else:
            budget_score = 20.0                             

    elif clean_price == 0:
        budget_score = 10.0
    else:
        budget_score = 30.0

    # ── 4. Color conflict check ───────────────────────────────────────────
    # Three-tier check (in priority order):
    #
    #   Tier 1 — car.color field (structured scraper attribute, highest confidence)
    #     PakWheels and OLX expose a dedicated color field. If populated and
    #     mismatched, veto immediately without scanning any text.
    #
    #   Tier 2 — Title scan (unstructured)
    #     Color word found in headline. Skips _CITY_COLOR_EXCEPTIONS so that
    #     "Blue Area Islamabad" in the title doesn't trigger a blue conflict.
    #
    #   Tier 3 — Description / about scan (unstructured, word-boundary safe)
    #     Sellers sometimes only mention color in the listing body. Scans
    #     description/about for conflicting color words using word-boundary
    #     regex to avoid false matches (e.g. "silver" inside "silverware").
    #     Also applies _CITY_COLOR_EXCEPTIONS for safety.
    if requested_color:
        req_color = requested_color.lower().strip()

        # ── Tier 1: structured car.color field ──────────────────────────────
        car_color_field = (getattr(car, "color", None) or "").lower().strip()
        if car_color_field:
            # Normalise composite values: "pearl white" → "white", "metallic grey" → "grey"
            normalised_car_color = car_color_field
            for color in COMMON_COLORS:
                if color in car_color_field:
                    normalised_car_color = color
                    break
            if normalised_car_color and normalised_car_color != req_color:
                return veto(
                    f"Color field mismatch: car is '{normalised_car_color}', "
                    f"user wants '{req_color}'"
                )

        # ── Tier 2: title scan (with city-color exception guard) ─────────────
        for color in COMMON_COLORS:
            if color == req_color:
                continue
            if color in title_lower:
                is_location_color = any(
                    exc in title_lower for exc in _CITY_COLOR_EXCEPTIONS
                    if exc.startswith(color)
                )
                if not is_location_color:
                    return veto(
                        f"Color conflict: title has '{color}', user wants '{req_color}'"
                    )

        # ── Tier 3: description / about scan ────────────────────────────────
        raw_desc   = (getattr(car, "description", None) or
                      getattr(car, "about", None) or "")
        desc_lower = raw_desc.lower()
        if desc_lower:
            for color in COMMON_COLORS:
                if color == req_color:
                    continue
                if re.search(rf'\b{re.escape(color)}\b', desc_lower):
                    is_location_color = any(
                        exc in desc_lower for exc in _CITY_COLOR_EXCEPTIONS
                        if exc.startswith(color)
                    )
                    if not is_location_color:
                        return veto(
                            f"Description contains '{color}', user wants '{req_color}'"
                        )

    # ── 5. City (soft signal) ──────────────────────────────────────────────
    car_city_lower = (car.city or "").lower().strip()
    req_city_str   = (requested_city or "").lower().strip()

    if req_city_str:
        req_cities    = [c.strip() for c in re.split(r',|\band\b', req_city_str) if c.strip()]
        city_matched  = any(rc in car_city_lower or rc in title_lower for rc in req_cities)
        city_score    = 30.0 if city_matched else 10.0
    else:
        city_score = 30.0 if car_city_lower else 15.0

    # ── 6. Staleness veto + age score ─────────────────────────────────────
    staleness_limit = 120 if is_luxury else 60
    if 0 < car.age_days <= 998 and car.age_days > staleness_limit:
        return veto(f"Stale: {car.age_days} days old (limit {staleness_limit})")

    if car.age_days > 0:
        age_score = max(0.0, 15.0 * (1.0 - car.age_days / staleness_limit))
    else:
        age_score = 10.0

    # ── 7. Year bounds ─────────────────────────────────────────────────────
    if clean_year > 0:
        if min_year > 0 and clean_year < min_year:
            return veto(f"Year {clean_year} < min_year {min_year}")
        if max_year > 0 and clean_year > max_year:
            return veto(f"Year {clean_year} > max_year {max_year}")

    # ── 8. Trim score (title + description scan, priority weighting) ──────
    # Build a combined search buffer from title + description/about.
    # This catches lazy sellers who omit the trim from the headline but
    # mention it in the listing body.
    raw_desc    = getattr(car, "description", None) or getattr(car, "about", None) or ""
    search_text = (title_lower + " " + raw_desc.lower()).strip()

    trim_score  = 0.0
    title_clean = title_lower.replace("-", "")
    desc_clean  = raw_desc.lower().replace("-", "")

    if requested_trim:
        req_trim_clean = requested_trim.lower().replace("-", "")
        GENERIC_SKIP   = {
            "automatic", "manual", "car", "sedan", "petrol",
            "hybrid", "crossover", "suv", "hatchback",
        }
        trim_keywords = [kw for kw in req_trim_clean.split() if kw not in GENERIC_SKIP]

        # Pass 1 — scan TITLE (highest confidence, +25 pts)
        trim_in_title = False
        for keyword in trim_keywords:
            valid_forms  = TRIM_ALIASES.get(keyword, [keyword])
            valid_nohyph = [f.replace("-", "") for f in valid_forms]
            if any(f in title_clean for f in valid_nohyph):
                trim_in_title = True
                break

        # Pass 2 — scan DESCRIPTION only if not found in title (+12 pts)
        trim_in_desc = False
        if not trim_in_title and desc_clean:
            for keyword in trim_keywords:
                valid_forms  = TRIM_ALIASES.get(keyword, [keyword])
                valid_nohyph = [f.replace("-", "") for f in valid_forms]
                if any(f in desc_clean for f in valid_nohyph):
                    trim_in_desc = True
                    break

        if trim_in_title:
            trim_score = 25.0   # Title match: seller declared trim in headline
        elif trim_in_desc:
            trim_score = 12.0   # Description match: lazy seller, still valid
        else:
            # Neither found — check for hard conflicts before passing listing through
            search_clean = search_text.replace("-", "")
            for keyword in trim_keywords:
                for conflict in _TRIM_CONFLICTS.get(keyword, []):
                    if conflict.replace("-", "") in search_clean:
                        return veto(
                            f"Trim conflict: wanted '{requested_trim}', "
                            f"found '{conflict}' in listing"
                        )
            # No conflict → lazy seller, passes with trim_score = 0

    # ── 9. Feature matching ────────────────────────────────────────────────
    # Passes search_text (title + description) so features confirmed in the
    # listing body (not just headline) count as a positive match.
    feature_score = 0.0
    if required_features:
        feature_score, feat_veto_reason = _check_feature_gates(
            car=car,
            requested_make=requested_make,
            requested_model=requested_model,
            required_features=required_features,
            title_lower=search_text,   # scans title + description combined
            clean_year=clean_year,
            debug=debug,
        )
        if feat_veto_reason:
            return veto(feat_veto_reason)

    # ── 10. Data quality ───────────────────────────────────────────────────
    quality_score = (7.5 if clean_year > 0 else 0.0) + (7.5 if clean_mileage > 0 else 0.0)

    # ── Total ──────────────────────────────────────────────────────────────
    raw_total   = budget_score + city_score + age_score + quality_score + trim_score + feature_score
    total_score = round(raw_total * identity_score, 2)

    if debug:
        print(
            f"  [REC-SCORE] '{clean_title[:50]}' | "
            f"id={identity_score:.2f} "
            f"budget={budget_score:.1f} city={city_score:.1f} "
            f"age={age_score:.1f} quality={quality_score:.1f} "
            f"trim={trim_score:.1f} feat={feature_score:.1f} "
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
    required_features: list[str] | None = None,
    min_budget: int = 0,
    min_year: int = 0,
    max_year: int = 0,
    top_k: int = 5,
    debug: bool = False,
) -> list[CarListing]:
    """
    Scores, deduplicates, and selects the best `top_k` listings for one
    AI-recommended car model.
    """
    corrected_make, corrected_model = normalize_make_model(
        requested_make or "", requested_model or ""
    )
    corrected_city = normalize_city(requested_city or "")

    # ── Step 1: Score + deduplicate ────────────────────────────────────────
    scored_map: dict[tuple, dict] = {}
    veto_count  = 0

    for car in raw_listings:
        clean_price   = _clean_price(car.price)
        clean_year    = _clean_int(car.year)
        clean_mileage = _clean_int(car.mileage)

        score = _score_listing(
            car=car,
            requested_make=corrected_make,
            requested_model=corrected_model,
            requested_city=corrected_city,
            requested_budget=requested_budget,
            requested_color=requested_color,
            clean_price=clean_price,
            clean_year=clean_year,
            clean_mileage=clean_mileage,
            requested_trim=requested_trim or "",
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
        _GARBAGE_CITY_VALS = {
            "automatic", "manual", "unregistered", "petrol",
            "hybrid", "cng", "diesel", "electric", "other",
        }
        if display_city.lower() in _GARBAGE_CITY_VALS:
            req_cities = [
                c.strip()
                for c in re.split(r',|\band\b', corrected_city.lower())
                if c.strip()
            ]
            display_city = ""
            for rc in req_cities:
                if rc in car.title.lower():
                    display_city = rc.title()
                    break

        title_norm = re.sub(r'\s+', ' ', car.title.lower().strip())
        dedup_key  = (title_norm, clean_year, clean_mileage, car.platform)

        if dedup_key in scored_map:
            if score > scored_map[dedup_key]["score"]:
                scored_map[dedup_key].update({
                    "score": score, "price": clean_price,
                    "year": clean_year, "mileage": clean_mileage,
                    "display_city": display_city,
                })
        else:
            scored_map[dedup_key] = {
                "car": car, "score": score, "price": clean_price,
                "year": clean_year, "mileage": clean_mileage,
                "display_city": display_city,
            }

    label = f"{corrected_make} {corrected_model}".strip()
    print(
        f"[RecNorm] {label}: "
        f"{len(raw_listings)} raw → {len(scored_map)} qualified, "
        f"{veto_count} vetoed"
    )

    if not scored_map:
        return []

    # ── Step 2: Sort all qualified listings by score ───────────────────────
    all_scored = sorted(scored_map.values(), key=lambda x: x["score"], reverse=True)

    # ── Step 3: Bucket by platform ─────────────────────────────────────────
    buckets: dict[str, list] = {
        "PakWheels":  [],
        "OLX":        [],
        "WiseWheels": [],
        "Gari.pk":    [],
        "Drive.pk":   [],
        "Other":      [],
    }

    for item in all_scored:
        plat = (item["car"].platform or "").strip()
        if plat == "PakWheels":
            buckets["PakWheels"].append(item)
        elif plat == "OLX":
            buckets["OLX"].append(item)
        elif "WiseWheels" in plat or "Wise" in plat:
            buckets["WiseWheels"].append(item)
        elif "Gari" in plat:
            buckets["Gari.pk"].append(item)
        elif "Drive" in plat:
            buckets["Drive.pk"].append(item)
        else:
            buckets["Other"].append(item)

    # ── Step 4: Platform slot allocation ──────────────────────────────────
    if top_k == 5:
        pw_quota  = 2
        olx_quota = 2
        third_quota = 1
    else:
        pw_quota    = max(1, top_k // 2)
        olx_quota   = max(1, top_k // 4)
        third_quota = max(0, top_k - pw_quota - olx_quota)

    pw_selected  = buckets["PakWheels"][:pw_quota]
    olx_selected = buckets["OLX"][:olx_quota]

    third_pool = (
        buckets["WiseWheels"]
        + buckets["Gari.pk"]
        + buckets["Drive.pk"]
        + buckets["Other"]
    )
    third_pool.sort(key=lambda x: x["score"], reverse=True)
    third_selected = third_pool[:third_quota]

    selection = pw_selected + olx_selected + third_selected

    # ── Step 5: Backfill to reach top_k ───────────────────────────────────
    shortfall = top_k - len(selection)
    if shortfall > 0:
        already = {id(item) for item in selection}
        backup  = [item for item in all_scored if id(item) not in already]
        selection.extend(backup[:shortfall])
        if debug and backup[:shortfall]:
            print(
                f"[RecNorm] {label}: backfilled "
                f"{min(shortfall, len(backup))} from overflow pool"
            )

    selection.sort(key=lambda x: x["score"], reverse=True)
    top_data = selection[:top_k]

    # ── Step 6: Build output CarListing objects ────────────────────────────
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

    pw_n    = len(pw_selected)
    olx_n   = len(olx_selected)
    third_n = len(third_selected)
    bf_n    = max(0, shortfall)

    print(
        f"[RecNorm] {label}: returning {len(result)}/{top_k} "
        f"(PW={pw_n}, OLX={olx_n}, 3rd={third_n}, backfill={bf_n})"
    )
    return result