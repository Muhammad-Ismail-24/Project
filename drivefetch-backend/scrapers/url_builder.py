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
    Resolves canonical trim slug and cleanly appends or merges it into the base_url
    to prevent double-slug stacking bugs (e.g. preventing /q-civic/q-rs-turbo).
    """
    slug = resolve_canonical_trim(model, raw_trim, platform)
    if not slug:
        return base_url
        
    clean_base = base_url.rstrip("/")
    
    if platform == "pakwheels":
        return f"{clean_base}/vg_{slug}"
        
    elif platform == "olx":
        if "/q-" in clean_base:
            return clean_base + f"-{slug}"
        else:
            return f"{clean_base}/q-{slug}"
            
    elif platform == "autodeals":
        if "/searchStr_" in clean_base:
            return clean_base + f"-{slug}"
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
    print("\\n--- Verification Test Suite ---")
    
    # 1. Toyota Corolla + "Grande" (Must resolve PakWheels to vg_altis-grande)
    base1 = "https://www.pakwheels.com/used-cars/search/-/mk_toyota/md_corolla"
    print("1.", build_platform_search_url(base1, "pakwheels", "corolla", "Grande"))
    
    # 2. Suzuki Cultus + "AGS" (Must resolve PakWheels to vg_auto-gear-shift)
    base2 = "https://www.pakwheels.com/used-cars/search/-/mk_suzuki/md_cultus"
    print("2.", build_platform_search_url(base2, "pakwheels", "cultus", "AGS"))
    
    # 3. Hyundai Elantra + "GL" (Must resolve PakWheels to vg_1-6-gl)
    base3 = "https://www.pakwheels.com/used-cars/search/-/mk_hyundai/md_elantra"
    print("3.", build_platform_search_url(base3, "pakwheels", "elantra", "GL"))
    
    # 4. Honda Civic + "RS" (Must resolve OLX to q-civic-rs-turbo or q-rs-turbo)
    base4 = "https://www.olx.com.pk/islamabad_g4060615/honda-cars_c84/q-civic"
    print("4.", build_platform_search_url(base4, "olx", "civic", "RS"))
    
    # 5. Toyota Corolla + "All trims" (Generic tag: must return clean base URL)
    base5 = "https://www.pakwheels.com/used-cars/search/-/mk_toyota/md_corolla"
    print("5.", build_platform_search_url(base5, "pakwheels", "corolla", "All trims"))
