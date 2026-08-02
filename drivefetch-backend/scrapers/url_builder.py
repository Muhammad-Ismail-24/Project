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
    Surgically injects PakWheels segments to preserve city and budget filters.
    """
    slug = resolve_canonical_trim(model, raw_trim, platform, is_budget_search=is_budget_search)
    if not slug:
        return base_url
        
    clean_base = base_url.rstrip("/")
    model_clean = (model or "").lower().strip().replace(" ", "-")
    
    if platform == "pakwheels":
        # Ensure correct prefix if missing
        if not (slug.startswith("vg_") or slug.startswith("vr_")):
            slug = f"vr_{slug}"
        
        # PakWheels requires trim slug to be injected immediately after md_ (model)
        parts = clean_base.split('/')
        insert_idx = len(parts)
        for i, part in enumerate(parts):
            if part.startswith("md_"):
                insert_idx = i + 1
                break
            elif part.startswith("mk_") and insert_idx == len(parts):
                insert_idx = i + 1
        
        parts.insert(insert_idx, slug)
        return "/".join(parts)
        
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
        separator = "&" if "?" in clean_base else "?"
        encoded_slug = urllib.parse.quote_plus(slug)
        return f"{clean_base}{separator}keyword={encoded_slug}"
        
    elif platform == "drivepk":
        # Merge safely if a query parameter already exists
        if "&q=" in clean_base:
            return f"{clean_base}%20{urllib.parse.quote_plus(slug)}"
        else:
            separator = "&" if "?" in clean_base else "?"
            return f"{clean_base}{separator}q={urllib.parse.quote_plus(slug)}"
        
    return base_url