# scrapers/url_builder.py

import urllib.parse
from scrapers.trim_dictionary import resolve_canonical_trim, GENERIC_TRIM_TAGS

def sanitize_trim(raw_trim: str) -> str:
    """Strips generic powertrain, drive, and instruction tags from raw trim."""
    if not raw_trim:
        return ""
    clean = raw_trim.strip().lower()
    if clean in GENERIC_TRIM_TAGS:
        return ""
    return raw_trim.strip()

def build_platform_search_url(base_url: str, platform: str, model: str, raw_trim: str) -> str:
    """
    Resolves canonical trim slug and cleanly appends or merges it into base_url.
    Prevents model name duplication (e.g. q-corolla + corolla-altis-grande -> q-corolla-altis-grande).
    """
    slug = resolve_canonical_trim(model, raw_trim, platform)
    if not slug:
        return base_url
        
    clean_base = base_url.rstrip("/")
    model_clean = (model or "").lower().strip().replace(" ", "-")
    
    if platform == "pakwheels":
        if slug.startswith("vg_") or slug.startswith("vr_"):
            return f"{clean_base}/{slug}"
        else:
            return f"{clean_base}/vg_{slug}"
        
    elif platform == "olx":
        # Strip redundant model prefix if slug starts with model name 
        # (e.g. "corolla-altis" -> "altis")
        clean_slug = slug
        if model_clean and clean_slug.startswith(f"{model_clean}-"):
            clean_slug = clean_slug[len(model_clean) + 1:]

        if "/q-" in clean_base:
            return f"{clean_base}-{clean_slug}"
        else:
            return f"{clean_base}/q-{clean_slug}"
            
    elif platform == "autodeals":
        if "/searchStr_" in clean_base:
            return f"{clean_base}-{slug}"
        else:
            return f"{clean_base}/searchStr_{slug}"
            
    elif platform == "wisewheels":
        separator = "&" if "?" in base_url else "?"
        encoded_slug = urllib.parse.quote_plus(slug)
        return f"{base_url}{separator}keyword={encoded_slug}"
        
    elif platform == "drivepk":
        return base_url
        
    return base_url

if __name__ == "__main__":
    print("\n--- Live Test Suite ---")
    base_pw = "https://www.pakwheels.com/used-cars/search/-/mk_toyota/md_corolla"
    base_olx = "https://www.olx.com.pk/islamabad_g4060615/toyota-cars_c84/q-corolla"

    print("1. PakWheels Grande:   ", build_platform_search_url(base_pw, "pakwheels", "corolla", "Grande"))
    print("2. OLX Grande:         ", build_platform_search_url(base_olx, "olx", "corolla", "Grande"))