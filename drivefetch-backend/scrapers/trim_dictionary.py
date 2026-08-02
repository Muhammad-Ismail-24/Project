# scrapers/trim_dictionary.py

import re

# Generic / Instructional Trim Blacklist (Strips bad LLM tags & generic specs)
GENERIC_TRIM_TAGS: set[str] = {
    "all trims", "all trim", "any", "none", "all", "standard",
    "ev", "electric", "hev", "phev", "hybrid", "petrol", "diesel", "cng",
    "automatic", "auto", "manual",
    "awd", "fwd", "4x4", "4wd", "rwd", "2wd",
    "sedan", "hatchback", "crossover", "suv", "van", "mpv", "car",
}

CANONICAL_TRIM_MAP = {
    # ── Toyota Corolla ──────────────────────────────────────────
    "corolla:xli": {
        "pakwheels": "lx-limited",
        "olx":       "xli",
        "autodeals": "XLi",
    },
    "corolla:gli": {
        "pakwheels": "gli--2",
        "olx":       "gli",
        "autodeals": "GLi",
    },
    "corolla:altis 1.6": {
        "pakwheels": "1-6",
        "olx":       "altis-1.6",
        "autodeals": "Altis-1.6",
    },
    "corolla:altis grande": {
        "pakwheels": "altis-1-8-grande",
        "olx":       "altis-grande",
        "autodeals": "Altis-Grande",
    },

    # ── Toyota Yaris ────────────────────────────────────────────
    "yaris:gli": {
        "pakwheels": "gli",
        "olx":       "gli",
        "autodeals": "GLi",
    },
    "yaris:ativ": {
        "pakwheels": "ativ",
        "olx":       "ativ",
        "autodeals": "ATIV",
    },
    "yaris:ativ x": {
        "pakwheels": "ativ-x",
        "olx":       "ativ-x",
        "autodeals": "ATIV-X",
    },

    # ── Toyota Fortuner ─────────────────────────────────────────
    "fortuner:2.7 vvti": {
        "pakwheels": "2-7-automatic",
        "olx":       "2.7-vvti",
        "autodeals": "2.7-VVTi",
    },
    "fortuner:legender": {
        "pakwheels": "legender",
        "olx":       "legender",
        "autodeals": "Legender",
    },

    # ── Toyota Prado ────────────────────────────────────────────
    "prado:tx": {
        "pakwheels": "tx",
        "olx":       "tx",
        "autodeals": "TX",
    },
    "prado:txl": {
        "pakwheels": "tx-l",
        "olx":       "tx-l",
        "autodeals": "TX-L",
    },
    "prado:tz": {
        "pakwheels": "tz",
        "olx":       "tz",
        "autodeals": "TZ",
    },
    "prado:vx": {
        "pakwheels": "vx",
        "olx":       "vx",
        "autodeals": "VX",
    },

    # ── Toyota Vitz / Aqua / Hilux ──────────────────────────────
    "vitz:f": {
        "pakwheels": "f",
        "olx":       "f",
        "autodeals": "F",
    },
    "vitz:u": {
        "pakwheels": "u",
        "olx":       "u",
        "autodeals": "U",
    },
    "vitz:jewela": {
        "pakwheels": "jewela",
        "olx":       "jewela",
        "autodeals": "Jewela",
    },
    "vitz:rs": {
        "pakwheels": "rs",
        "olx":       "rs",
        "autodeals": "RS",
    },
    "aqua:s": {
        "pakwheels": "s",
        "olx":       "s",
        "autodeals": "S",
    },
    "aqua:g": {
        "pakwheels": "g",
        "olx":       "g",
        "autodeals": "G",
    },
    "aqua:l": {
        "pakwheels": "l",
        "olx":       "l",
        "autodeals": "L",
    },
    "aqua:gr sport": {
        "pakwheels": "gr-sport",
        "olx":       "gr-sport",
        "autodeals": "GR-Sport",
    },
    "hilux:revo g": {
        "pakwheels": "revo-g",
        "olx":       "revo-g",
        "autodeals": "Revo-G",
    },
    "hilux:revo v": {
        "pakwheels": "revo-v",
        "olx":       "revo-v",
        "autodeals": "Revo-V",
    },
    "hilux:rocco": {
        "pakwheels": "revo-rocco",
        "olx":       "revo-rocco",
        "autodeals": "Revo-Rocco",
    },

    # ── Honda Civic ─────────────────────────────────────────────
    "civic:oriel": {
        "pakwheels": "1-5-vtec-turbo-oriel",
        "olx":       "oriel",
        "autodeals": "Oriel",
    },
    "civic:rs": {
        "pakwheels": "1-5-rs-turbo",
        "olx":       "rs",
        "autodeals": "RS",
    },
    "civic:turbo": {
        "pakwheels": "1-5-rs-turbo",
        "olx":       "turbo",
        "autodeals": "Turbo",
    },
    "civic:vti": {
        "pakwheels": "vti-1-6",
        "olx":       "vti",
        "autodeals": "VTi",
    },

    # ── Honda City ──────────────────────────────────────────────
    "city:idsi": {
        "pakwheels": "i-dsi",
        "olx":       "idsi",
        "autodeals": "iDSI",
    },
    "city:aspire": {
        "pakwheels": "aspire",
        "olx":       "aspire",
        "autodeals": "Aspire",
    },
    "city:1.2": {
        "pakwheels": "1-2l",
        "olx":       "1-2",
        "autodeals": "1-2L",
    },
    "city:1.5": {
        "pakwheels": "1-5l",
        "olx":       "1-5",
        "autodeals": "1-5L",
    },
    "city:cvt": {
        "pakwheels": "cvt",
        "olx":       "cvt",
        "autodeals": "CVT",
    },

    # ── Honda BR-V / Vezel / HR-V ───────────────────────────────
    "br-v:ivtec": {
        "pakwheels": "i-vtec",
        "olx":       "ivtec",
        "autodeals": "i-VTEC",
    },
    "br-v:ivtecs": {
        "pakwheels": "i-vtec-s",
        "olx":       "ivtec-s",
        "autodeals": "i-VTEC-S",
    },
    "vezel:x": {
        "pakwheels": "x",
        "olx":       "x",
        "autodeals": "X",
    },
    "vezel:z": {
        "pakwheels": "z",
        "olx":       "z",
        "autodeals": "Z",
    },
    "vezel:rs": {
        "pakwheels": "rs",
        "olx":       "rs",
        "autodeals": "RS",
    },
    "vezel:ehev": {
        "pakwheels": "e-hev",
        "olx":       "e-hev",
        "autodeals": "e-HEV",
    },
    "hr-v:vti": {
        "pakwheels": "vti",
        "olx":       "vti",
        "autodeals": "VTi",
    },
    "hr-v:vtis": {
        "pakwheels": "vti-s",
        "olx":       "vti-s",
        "autodeals": "VTi-S",
    },

    # ── Suzuki Alto ─────────────────────────────────────────────
    "alto:vx": {
        "pakwheels": "vx-14",
        "olx":       "vx",
        "autodeals": "VX",
    },
    "alto:vxr": {
        "pakwheels": "vxr-2",
        "olx":       "vxr",
        "autodeals": "VXR",
    },
    "alto:vxl": {
        "pakwheels": "vxl--2",
        "olx":       "vxl",
        "autodeals": "VXL",
    },
    "alto:vxl ags": {
        "pakwheels": "vxl--2",
        "olx":       "vxl-ags",
        "autodeals": "VXL-AGS",
    },

    # ── Suzuki Cultus / Wagon R ─────────────────────────────────
    "cultus:vxr": {
        "pakwheels": "vxr",
        "olx":       "vxr",
        "autodeals": "VXR",
    },
    "cultus:vxl": {
        "pakwheels": "vxl-2",
        "olx":       "vxl",
        "autodeals": "VXL",
    },
    "cultus:auto gear shift": {
        "pakwheels": "auto-gear-shift-vxl",
        "olx":       "auto-gear-shift",
        "autodeals": "Auto-Gear-Shift",
    },
    "cultus:euro ii": {
        "pakwheels": "vxri-euro-ii",
        "olx":       "euro-ii",
        "autodeals": "Euro-II",
    },
    "wagon r:vxr": {
        "pakwheels": "vxr",
        "olx":       "vxr",
        "autodeals": "VXR",
    },
    "wagon r:vxl": {
        "pakwheels": "vxl",
        "olx":       "vxl",
        "autodeals": "VXL",
    },

    # ── Suzuki Swift ────────────────────────────────────────────
    "swift:dlx": {
        "pakwheels": "dlx",
        "olx":       "dlx",
        "autodeals": "DLX",
    },
    "swift:glx": {
        "pakwheels": "glx-cvt",
        "olx":       "glx",
        "autodeals": "GLX",
    },
    "swift:gl": {
        "pakwheels": "gl-cvt",
        "olx":       "gl",
        "autodeals": "GL",
    },

    # ── Kia / Hyundai ───────────────────────────────────────────
    "sportage:alpha": {
        "pakwheels": "alpha--2",
        "olx":       "alpha",
        "autodeals": "Alpha",
    },
    "sportage:fwd": {
        "pakwheels": "fwd",
        "olx":       "fwd",
        "autodeals": "FWD",
    },
    "sportage:awd": {
        "pakwheels": "awd",
        "olx":       "awd",
        "autodeals": "AWD",
    },
    "stonic:ex": {
        "pakwheels": "ex",
        "olx":       "ex",
        "autodeals": "EX",
    },
    "stonic:ex+": {
        "pakwheels": "ex-plus",
        "olx":       "ex-plus",
        "autodeals": "EX-Plus",
    },
    "tucson:gls sport": {
        "pakwheels": "gls-sport",
        "olx":       "gls-sport",
        "autodeals": "GLS-Sport",
    },
    "tucson:ultimate": {
        "pakwheels": "ultimate",
        "olx":       "ultimate",
        "autodeals": "Ultimate",
    },
    "elantra:gl": {
        "pakwheels": "gl--9",
        "olx":       "gl",
        "autodeals": "GL",
    },
    "elantra:gls": {
        "pakwheels": "gls--9",
        "olx":       "gls",
        "autodeals": "GLS",
    },

    # ── Chinese Entrants (Haval, Changan, MG) ───────────────────
    "h6:1.5t": {
        "pakwheels": "1-5t",
        "olx":       "1-5",
        "autodeals": "1-5T",
    },
    "h6:2.0t": {
        "pakwheels": "2-0t",
        "olx":       "2-0",
        "autodeals": "2-0T",
    },
    "h6:hev": {
        "pakwheels": "hev",
        "olx":       "hev",
        "autodeals": "HEV",
    },
    "oshan x7:comfort": {
        "pakwheels": "comfort",
        "olx":       "comfort",
        "autodeals": "Comfort",
    },
    "oshan x7:future sense": {
        "pakwheels": "future-sense",
        "olx":       "future-sense",
        "autodeals": "Future-Sense",
    },
    "hs:exclusive": {
        "pakwheels": "exclusive",
        "olx":       "exclusive",
        "autodeals": "Exclusive",
    },
}

def resolve_canonical_trim(model: str, raw_trim: str, platform: str) -> str:
    """
    Sanitizes raw trim, checks against CANONICAL_TRIM_MAP via model,
    and returns exact platform slug. Falls back to naive format if not found.
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
        
    # Partial matching
    for map_key, platform_dict in CANONICAL_TRIM_MAP.items():
        if map_key.startswith(f"{model_clean}:"):
            trim_part = map_key.split(":")[1]
            if raw_trim_clean in trim_part or trim_part in raw_trim_clean:
                return platform_dict.get(platform, "")

    # Fallback
    return raw_trim_clean.replace(" ", "-")
