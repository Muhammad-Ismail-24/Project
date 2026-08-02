"""
scrapers/url_builder.py
Dynamic URL Builder & Trim Route Injector for GaariGuru
"""

import re
import urllib.parse

# Generic / Instructional Trim Blacklist (Strips bad LLM tags & generic specs)
GENERIC_TRIM_TAGS: set[str] = {
    "all trims", "all trim", "any", "none", "all", "standard",
    "ev", "electric", "hev", "phev", "hybrid", "petrol", "diesel", "cng",
    "automatic", "auto", "manual", "cvt", "ags", "prosmatec",
    "awd", "fwd", "4x4", "4wd", "rwd", "2wd",
    "sedan", "hatchback", "crossover", "suv", "van", "mpv", "car",
}

TRIM_PLATFORM_MAP = {
    "pakwheels": {
        "type": "path_slug",
        "prefix": "vg_",
        "formatter": lambda trim: trim.lower().replace(" ", "-")
    },
    "olx": {
        "type": "path_slug",
        "prefix": "q-",
        "formatter": lambda trim: trim.lower().replace(" ", "-")
    },
    "autodeals": {
        "type": "path_slug",
        "prefix": "searchStr_",
        "formatter": lambda trim: trim.title().replace(" ", "-")
    },
    "wisewheels": {
        "type": "query_param",
        "key": "keyword",
        "formatter": lambda trim: urllib.parse.quote_plus(trim.lower())
    },
    "drivepk": {
        "type": "unsupported",
        "prefix": "",
        "formatter": lambda trim: ""
    }
}

def sanitize_trim(raw_trim: str) -> str:
    """Strips generic powertrain, drive, and instruction tags from raw trim."""
    if not raw_trim:
        return ""
    clean = raw_trim.strip().lower()
    if clean in GENERIC_TRIM_TAGS:
        return ""
    return raw_trim.strip()

def build_platform_search_url(base_url: str, platform: str, raw_trim: str) -> str:
    """Sanitizes and safely injects a trim string into platform base URLs."""
    clean_trim = sanitize_trim(raw_trim)
    if not clean_trim or platform not in TRIM_PLATFORM_MAP:
        return base_url

    config = TRIM_PLATFORM_MAP[platform]
    if config["type"] == "unsupported":
        return base_url

    formatted_trim = config["formatter"](clean_trim)
    if not formatted_trim:
        return base_url

    if config["type"] == "path_slug":
        slug = f"{config['prefix']}{formatted_trim}"
        clean_base = base_url.rstrip("/")
        return f"{clean_base}/{slug}"

    elif config["type"] == "query_param":
        separator = "&" if "?" in base_url else "?"
        return f"{base_url}{separator}{config['key']}={formatted_trim}"

    return base_url

# Unit test block
if __name__ == "__main__":
    test_trims = ["All trims", "Automatic", "Altis Grande"]
    platforms = ["pakwheels", "olx", "autodeals", "wisewheels", "drivepk"]
    
    for trim in test_trims:
        print(f"\\n--- Testing trim: '{trim}' ---")
        for plat in platforms:
            base = "https://example.com/base"
            res = build_platform_search_url(base, plat, trim)
            print(f"{plat.ljust(12)}: {res}")
