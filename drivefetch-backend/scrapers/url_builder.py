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

def build_platform_search_url(
    base_url: str, 
    platform: str, 
    model: str, 
    raw_trim: str,
    is_budget_search: bool = False
) -> str:
    """
    Resolves canonical trim slug and cleanly appends or merges it into base_url.
    Prevents model name duplication (e.g. q-corolla + corolla-altis-grande -> q-corolla-altis-grande).
    Passes is_budget_search to bypass strict vr_ slugs on PakWheels for multi-gen trims.
    """
    slug = resolve_canonical_trim(model, raw_trim, platform, is_budget_search=is_budget_search)
    if not slug:
        return base_url
        
    clean_base = base_url.rstrip("/")
    model_clean = (model or "").lower().strip().replace(" ", "-")
    
    if platform == "pakwheels":
        if slug.startswith("vg_") or slug.startswith("vr_"):
            return f"{clean_base}/{slug}"
        else:
            return f"{clean_base}/vr_{slug}"
        
    elif platform == "olx":
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
    print("\n--- Hybrid Test Suite ---")
    base_pw = "https://www.pakwheels.com/used-cars/search/-/mk_honda/md_civic"

    print("1. Matchmaker Specific (RS Turbo): ", build_platform_search_url(base_pw, "pakwheels", "civic", "RS Turbo"))
    print("2. Direct Budget Search (Oriel):    ", build_platform_search_url(base_pw, "pakwheels", "civic", "Oriel", is_budget_search=True))
    print("3. Matchmaker Specific (Oriel):     ", build_platform_search_url(base_pw, "pakwheels", "civic", "Oriel", is_budget_search=False))