# scrapers/trim_dictionary.py

import re

GENERIC_TRIM_TAGS: set[str] = {
    "all trims", "all trim", "any", "none", "all", "standard",
    "ev", "electric", "hev", "phev", "hybrid", "petrol", "diesel", "cng",
    "automatic", "auto", "manual",
    "awd", "fwd", "4x4", "4wd", "rwd", "2wd",
    "sedan", "hatchback", "crossover", "suv", "van", "mpv", "car",
}

CANONICAL_TRIM_MAP = {
    # ── Toyota Corolla ──────────────────────────────────────────
    "corolla:grande": {
        "pakwheels": "vr_altis-1-8-grande",
        "olx":       "corolla-altis-grande",
        "autodeals": "Altis-Grande",
    },
    "corolla:altis grande": {
        "pakwheels": "vr_altis-1-8-grande",
        "olx":       "corolla-altis-grande",
        "autodeals": "Altis-Grande",
    },
    "corolla:altis 1.6": {
        "pakwheels": "vr_altis-1-6-automatic",
        "olx":       "corolla-altis",
        "autodeals": "Altis-1.6",
    },
    "corolla:gli": {
        "pakwheels": "vr_gli-vvti",
        "olx":       "corolla-gli",
        "autodeals": "GLi",
    },
    "corolla:xli": {
        "pakwheels": "vr_xli-vvti",
        "olx":       "corolla-xli",
        "autodeals": "XLi",
    },
    "corolla:2.0d": {
        "pakwheels": "vr_2-0d",
        "olx":       "corolla-2.0d",
        "autodeals": "2.0D",
    },

    # ── Toyota Yaris ────────────────────────────────────────────
    "yaris:gli": {
        "pakwheels": "vg_gli",
        "olx":       "yaris-gli",
        "autodeals": "GLi",
    },
    "yaris:ativ": {
        "pakwheels": "vg_ativ",
        "olx":       "yaris-ativ",
        "autodeals": "ATIV",
    },
    "yaris:ativ x": {
        "pakwheels": "vr_ativ-x-cvt-1-5",
        "olx":       "yaris-ativ-x",
        "autodeals": "ATIV-X",
    },

    # ── Toyota Fortuner ─────────────────────────────────────────
    "fortuner:g": {
        "pakwheels": "vr_g",
        "olx":       "fortuner-g",
        "autodeals": "G",
    },
    "fortuner:2.7 vvti": {
        "pakwheels": "vr_2-7-vvti",
        "olx":       "fortuner-2.7",
        "autodeals": "2.7-VVTi",
    },
    "fortuner:vrz": {
        "pakwheels": "vr_vrz",
        "olx":       "fortuner-vrz",
        "autodeals": "VRZ",
    },
    "fortuner:sigma 3": {
        "pakwheels": "vr_sigma-4",
        "olx":       "fortuner-sigma",
        "autodeals": "Sigma-3",
    },
    "fortuner:legender": {
        "pakwheels": "vr_legender",
        "olx":       "fortuner-legender",
        "autodeals": "Legender",
    },

    # ── Toyota Prado ────────────────────────────────────────────
    "prado:tx": {
        "pakwheels": "vg_tx",
        "olx":       "prado-tx",
        "autodeals": "TX",
    },
    "prado:txl": {
        "pakwheels": "vg_tx-l",
        "olx":       "prado-tx-l",
        "autodeals": "TX-L",
    },
    "prado:tz": {
        "pakwheels": "vg_tz",
        "olx":       "prado-tz",
        "autodeals": "TZ",
    },
    "prado:vx": {
        "pakwheels": "vg_vx",
        "olx":       "prado-vx",
        "autodeals": "VX",
    },

    # ── Toyota Land Cruiser ─────────────────────────────────────
    "land cruiser:zx": {
        "pakwheels": "vg_zx",
        "olx":       "land-cruiser-zx",
        "autodeals": "ZX",
    },
    "land cruiser:ax": {
        "pakwheels": "vg_ax",
        "olx":       "land-cruiser-ax",
        "autodeals": "AX",
    },
    "land cruiser:ax g selection": {
        "pakwheels": "vr_ax-g-selection",
        "olx":       "land-cruiser-ax-g",
        "autodeals": "AX-G-Selection",
    },
    "land cruiser:vx": {
        "pakwheels": "vg_vx",
        "olx":       "land-cruiser-vx",
        "autodeals": "VX",
    },
    "land cruiser:gx": {
        "pakwheels": "vg_gx",
        "olx":       "land-cruiser-gx",
        "autodeals": "GX",
    },
    "land cruiser:sahara": {
        "pakwheels": "vr_sahara",
        "olx":       "land-cruiser-sahara",
        "autodeals": "Sahara",
    },

    # ── Toyota Passo / Prius / Mark X / Premio / Allion / Crown / Camry / Raize / Rush ──
    "passo:x": {
        "pakwheels": "vr_1-0-x",
        "olx":       "passo-x",
        "autodeals": "X",
    },
    "passo:g": {
        "pakwheels": "vr_1-0-g",
        "olx":       "passo-g",
        "autodeals": "G",
    },
    "passo:moda": {
        "pakwheels": "vr_moda",
        "olx":       "passo-moda",
        "autodeals": "Moda",
    },
    "prius:s": {
        "pakwheels": "vr_s",
        "olx":       "prius-s",
        "autodeals": "S",
    },
    "prius:g": {
        "pakwheels": "vr_g",
        "olx":       "prius-g",
        "autodeals": "G",
    },
    "prius:touring": {
        "pakwheels": "vr_touring",
        "olx":       "prius-touring",
        "autodeals": "Touring",
    },
    "mark x:250g": {
        "pakwheels": "vr_250g",
        "olx":       "mark-x-250g",
        "autodeals": "250G",
    },
    "mark x:300g": {
        "pakwheels": "vr_300g",
        "olx":       "mark-x-300g",
        "autodeals": "300G",
    },
    "mark x:350g": {
        "pakwheels": "vr_350g",
        "olx":       "mark-x-350g",
        "autodeals": "350G",
    },
    "premio:f": {
        "pakwheels": "vr_1-5-f",
        "olx":       "premio-f",
        "autodeals": "F",
    },
    "premio:x": {
        "pakwheels": "vr_1-8-x",
        "olx":       "premio-x",
        "autodeals": "X",
    },
    "premio:g": {
        "pakwheels": "vr_2-0-g",
        "olx":       "premio-g",
        "autodeals": "G",
    },
    "allion:a15": {
        "pakwheels": "vr_a15",
        "olx":       "allion-a15",
        "autodeals": "A15",
    },
    "allion:a18": {
        "pakwheels": "vr_a18",
        "olx":       "allion-a18",
        "autodeals": "A18",
    },
    "allion:a20": {
        "pakwheels": "vr_a20",
        "olx":       "allion-a20",
        "autodeals": "A20",
    },
    "crown:royal saloon": {
        "pakwheels": "vr_royal-saloon",
        "olx":       "crown-royal-saloon",
        "autodeals": "Royal-Saloon",
    },
    "crown:athlete": {
        "pakwheels": "vr_athlete",
        "olx":       "crown-athlete",
        "autodeals": "Athlete",
    },
    "camry:high grade": {
        "pakwheels": "vr_high-grade",
        "olx":       "camry-high-grade",
        "autodeals": "High-Grade",
    },
    "camry:hybrid": {
        "pakwheels": "vr_hybrid",
        "olx":       "camry-hybrid",
        "autodeals": "Hybrid",
    },
    "raize:x": {
        "pakwheels": "vr_x",
        "olx":       "raize-x",
        "autodeals": "X",
    },
    "raize:g": {
        "pakwheels": "vr_g",
        "olx":       "raize-g",
        "autodeals": "G",
    },
    "raize:z": {
        "pakwheels": "vr_z",
        "olx":       "raize-z",
        "autodeals": "Z",
    },
    "rush:g": {
        "pakwheels": "vr_g",
        "olx":       "rush-g",
        "autodeals": "G",
    },
    "rush:s": {
        "pakwheels": "vr_s",
        "olx":       "rush-s",
        "autodeals": "S",
    },

    # ── Honda ───────────────────────────────────────────────────
    "civic:standard": {
        "pakwheels": "vr_standard",
        "olx":       "civic-1.8",
        "autodeals": "Standard",
    },
    "civic:oriel": {
        "pakwheels": "vr_oriel",
        "olx":       "civic-oriel",
        "autodeals": "Oriel",
    },
    "civic:rs": {
        "pakwheels": "vr_civic-rs",
        "olx":       "civic-rs",
        "autodeals": "RS",
    },
    "city:i-dsi": {
        "pakwheels": "vr_i-dsi",
        "olx":       "city-i-dsi",
        "autodeals": "iDSI",
    },
    "city:aspire": {
        "pakwheels": "vr_aspire",
        "olx":       "city-aspire",
        "autodeals": "Aspire",
    },
    "city:1.2": {
        "pakwheels": "vr_1-2",
        "olx":       "city-1.2",
        "autodeals": "1.2",
    },
    "city:1.5": {
        "pakwheels": "vr_1-5",
        "olx":       "city-1.5",
        "autodeals": "1.5",
    },
    "fit:f": {
        "pakwheels": "vr_f",
        "olx":       "fit-f",
        "autodeals": "F",
    },
    "fit:l": {
        "pakwheels": "vr_l",
        "olx":       "fit-l",
        "autodeals": "L",
    },
    "fit:hybrid": {
        "pakwheels": "vr_hybrid",
        "olx":       "fit-hybrid",
        "autodeals": "Hybrid",
    },
    "grace:dx": {
        "pakwheels": "vr_dx",
        "olx":       "grace-dx",
        "autodeals": "DX",
    },
    "grace:lx": {
        "pakwheels": "vr_lx",
        "olx":       "grace-lx",
        "autodeals": "LX",
    },
    "grace:ex": {
        "pakwheels": "vr_ex",
        "olx":       "grace-ex",
        "autodeals": "EX",
    },
    "accord:vti-l": {
        "pakwheels": "vr_vti-l",
        "olx":       "accord-vti-l",
        "autodeals": "VTi-L",
    },
    "accord:ex-l": {
        "pakwheels": "vr_ex-l",
        "olx":       "accord-ex-l",
        "autodeals": "EX-L",
    },
    "cr-v:2.0": {
        "pakwheels": "vr_2-0",
        "olx":       "cr-v-20",
        "autodeals": "2.0",
    },
    "cr-v:2.4": {
        "pakwheels": "vr_2-4",
        "olx":       "cr-v-24",
        "autodeals": "2.4",
    },
    "cr-v:ex": {
        "pakwheels": "vr_ex",
        "olx":       "cr-v-ex",
        "autodeals": "EX",
    },

    # ── Suzuki & Daihatsu ───────────────────────────────────────
    "alto:vx": {
        "pakwheels": "vr_vx",
        "olx":       "alto-vx",
        "autodeals": "VX",
    },
    "alto:vxr": {
        "pakwheels": "vr_vxr",
        "olx":       "alto-vxr",
        "autodeals": "VXR",
    },
    "alto:vxl": {
        "pakwheels": "vr_vxl",
        "olx":       "alto-vxl",
        "autodeals": "VXL",
    },
    "cultus:vxr": {
        "pakwheels": "vr_vxr",
        "olx":       "cultus-vxr",
        "autodeals": "VXR",
    },
    "cultus:vxl": {
        "pakwheels": "vr_vxl",
        "olx":       "cultus-vxl",
        "autodeals": "VXL",
    },
    "cultus:ags": {
        "pakwheels": "vr_ags",
        "olx":       "cultus-ags",
        "autodeals": "AGS",
    },
    "jimny:sierra": {
        "pakwheels": "vr_sierra",
        "olx":       "jimny-sierra",
        "autodeals": "Sierra",
    },
    "jimny:jl": {
        "pakwheels": "vr_jl",
        "olx":       "jimny-jl",
        "autodeals": "JL",
    },
    "jimny:jc": {
        "pakwheels": "vr_jc",
        "olx":       "jimny-jc",
        "autodeals": "JC",
    },
    "every:ga": {
        "pakwheels": "vr_ga",
        "olx":       "every-ga",
        "autodeals": "GA",
    },
    "every:pa": {
        "pakwheels": "vr_pa",
        "olx":       "every-pa",
        "autodeals": "PA",
    },
    "every:join": {
        "pakwheels": "vr_join",
        "olx":       "every-join",
        "autodeals": "JOIN",
    },
    "mira:l": {
        "pakwheels": "vr_l",
        "olx":       "mira-l",
        "autodeals": "L",
    },
    "mira:x": {
        "pakwheels": "vr_x",
        "olx":       "mira-x",
        "autodeals": "X",
    },
    "mira:es": {
        "pakwheels": "vr_es",
        "olx":       "mira-es",
        "autodeals": "ES",
    },
    "move:l": {
        "pakwheels": "vr_l",
        "olx":       "move-l",
        "autodeals": "L",
    },
    "move:x": {
        "pakwheels": "vr_x",
        "olx":       "move-x",
        "autodeals": "X",
    },
    "move:custom": {
        "pakwheels": "vr_custom",
        "olx":       "move-custom",
        "autodeals": "Custom",
    },
    "hijet:cruise": {
        "pakwheels": "vr_cruise",
        "olx":       "hijet-cruise",
        "autodeals": "Cruise",
    },
    "hijet:deluxe": {
        "pakwheels": "vr_deluxe",
        "olx":       "hijet-deluxe",
        "autodeals": "Deluxe",
    },
    "rocky:l": {
        "pakwheels": "vr_l",
        "olx":       "rocky-l",
        "autodeals": "L",
    },
    "rocky:premium": {
        "pakwheels": "vr_premium",
        "olx":       "rocky-premium",
        "autodeals": "Premium",
    },

    # ── Nissan & Mazda ──────────────────────────────────────────
    "dayz:x": {
        "pakwheels": "vr_x",
        "olx":       "dayz-x",
        "autodeals": "X",
    },
    "dayz:highway star": {
        "pakwheels": "vr_highway-star",
        "olx":       "dayz-highway-star",
        "autodeals": "Highway-Star",
    },
    "x-trail:20x": {
        "pakwheels": "vr_20x",
        "olx":       "x-trail-20x",
        "autodeals": "20X",
    },
    "x-trail:hybrid": {
        "pakwheels": "vr_hybrid",
        "olx":       "x-trail-hybrid",
        "autodeals": "Hybrid",
    },
    "demio:13c": {
        "pakwheels": "vr_13c",
        "olx":       "demio-13c",
        "autodeals": "13C",
    },
    "demio:13s": {
        "pakwheels": "vr_13s",
        "olx":       "demio-13s",
        "autodeals": "13S",
    },
    "demio:touring": {
        "pakwheels": "vr_touring",
        "olx":       "demio-touring",
        "autodeals": "Touring",
    },
    "cx-5:20s": {
        "pakwheels": "vr_20s",
        "olx":       "cx-5-20s",
        "autodeals": "20S",
    },
    "cx-5:xd": {
        "pakwheels": "vr_xd",
        "olx":       "cx-5-xd",
        "autodeals": "XD",
    },

    # ── Kia & Hyundai ───────────────────────────────────────────
    "sorento:2.4 fwd": {
        "pakwheels": "vr_2-4-fwd",
        "olx":       "sorento-24-fwd",
        "autodeals": "2.4-FWD",
    },
    "sorento:3.5 awd": {
        "pakwheels": "vr_3-5-awd",
        "olx":       "sorento-35-awd",
        "autodeals": "3.5-AWD",
    },
    "carnival:lx": {
        "pakwheels": "vr_lx",
        "olx":       "carnival-lx",
        "autodeals": "LX",
    },
    "carnival:ex": {
        "pakwheels": "vr_ex",
        "olx":       "carnival-ex",
        "autodeals": "EX",
    },
    "carnival:executive": {
        "pakwheels": "vr_executive",
        "olx":       "carnival-executive",
        "autodeals": "Executive",
    },
    "santa fe:smart": {
        "pakwheels": "vr_smart",
        "olx":       "santa-fe-smart",
        "autodeals": "Smart",
    },
    "santa fe:signature": {
        "pakwheels": "vr_signature",
        "olx":       "santa-fe-signature",
        "autodeals": "Signature",
    },
    "palisade:style": {
        "pakwheels": "vr_style",
        "olx":       "palisade-style",
        "autodeals": "Style",
    },
    "palisade:elegance": {
        "pakwheels": "vr_elegance",
        "olx":       "palisade-elegance",
        "autodeals": "Elegance",
    },

    # ── Chinese Entrants ────────────────────────────────────────
    "mg hs:essence": {
        "pakwheels": "vr_essence",
        "olx":       "mg-hs-essence",
        "autodeals": "Essence",
    },
    "mg hs:exclusive": {
        "pakwheels": "vr_exclusive",
        "olx":       "mg-hs-exclusive",
        "autodeals": "Exclusive",
    },
    "haval h6:1.5t": {
        "pakwheels": "vr_1-5t",
        "olx":       "haval-h6-15t",
        "autodeals": "1.5T",
    },
    "haval h6:2.0t": {
        "pakwheels": "vr_2-0t",
        "olx":       "haval-h6-20t",
        "autodeals": "2.0T",
    },
    "haval h6:hev": {
        "pakwheels": "vr_hev",
        "olx":       "haval-h6-hev",
        "autodeals": "HEV",
    },
    "haval jolion:1.5t": {
        "pakwheels": "vr_1-5t",
        "olx":       "jolion-15t",
        "autodeals": "1.5T",
    },
    "haval jolion:hev": {
        "pakwheels": "vr_hev",
        "olx":       "jolion-hev",
        "autodeals": "HEV",
    },

    # ── European Luxury ─────────────────────────────────────────
    "3 series:316i": {
        "pakwheels": "vr_316i",
        "olx":       "bmw-3-series-316i",
        "autodeals": "316i",
    },
    "3 series:318i": {
        "pakwheels": "vr_318i",
        "olx":       "bmw-3-series-318i",
        "autodeals": "318i",
    },
    "3 series:320i": {
        "pakwheels": "vr_320i",
        "olx":       "bmw-3-series-320i",
        "autodeals": "320i",
    },
    "5 series:520i": {
        "pakwheels": "vr_520i",
        "olx":       "bmw-5-series-520i",
        "autodeals": "520i",
    },
    "5 series:530e": {
        "pakwheels": "vr_530e",
        "olx":       "bmw-5-series-530e",
        "autodeals": "530e",
    },
    "c-class:c180": {
        "pakwheels": "vr_c180",
        "olx":       "c-class-c180",
        "autodeals": "C180",
    },
    "c-class:c200": {
        "pakwheels": "vr_c200",
        "olx":       "c-class-c200",
        "autodeals": "C200",
    },
    "e-class:e200": {
        "pakwheels": "vr_e200",
        "olx":       "e-class-e200",
        "autodeals": "E200",
    },
    "e-class:e250": {
        "pakwheels": "vr_e250",
        "olx":       "e-class-e250",
        "autodeals": "E250",
    },
    "e-class:e300": {
        "pakwheels": "vr_e300",
        "olx":       "e-class-e300",
        "autodeals": "E300",
    },
}

def resolve_canonical_trim(model: str, raw_trim: str, platform: str) -> str:
    """
    Sanitizes raw trim, checks against CANONICAL_TRIM_MAP via model,
    and returns exact platform slug. Falls back to naive hyphenation for unverified cars.
    """
    if not raw_trim or not model:
        return ""
        
    model_clean = model.lower().strip()
    raw_trim_clean = raw_trim.lower().strip()
    
    if raw_trim_clean in GENERIC_TRIM_TAGS:
        return ""
        
    key = f"{model_clean}:{raw_trim_clean}"
    if key in CANONICAL_TRIM_MAP:
        return CANONICAL_TRIM_MAP[key].get(platform, "")
        
    # Substring / partial matching
    for map_key, platform_dict in CANONICAL_TRIM_MAP.items():
        if map_key.startswith(f"{model_clean}:"):
            trim_part = map_key.split(":")[1]
            if raw_trim_clean in trim_part or trim_part in raw_trim_clean:
                return platform_dict.get(platform, "")

    # Fallback for unverified models
    return raw_trim_clean.replace(" ", "-")