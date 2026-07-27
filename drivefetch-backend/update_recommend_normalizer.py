import re

with open('scrapers/recommend_normalizer.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update _calculate_recommendation_score signature
content = content.replace(
    'clean_mileage: int,\n    requested_trim: str = None,\n    min_year: int = 0,',
    'clean_mileage: int,\n    requested_trim: str = None,\n    required_features: list[str] = None,\n    min_year: int = 0,'
)

# 2. Add Feature logic
feature_logic = """
    # ── 6.5. Feature Matcher (Hard Vetoes & Boosting) ────────────────────────────
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

    # ── 7. Year bounds ─────────────────────────────────────────────────────"""

content = content.replace('    # ── 7. Year bounds ─────────────────────────────────────────────────────', feature_logic)

# 3. Update total calculation
content = content.replace(
    'raw_total   = budget_score + city_score + age_score + quality_score + trim_score',
    'raw_total   = budget_score + city_score + age_score + quality_score + trim_score + feature_score'
)

# 4. Update debug string
content = content.replace(
    'f"quality={quality_score:.1f} trim={trim_score:.1f} "',
    'f"quality={quality_score:.1f} trim={trim_score:.1f} feat={feature_score:.1f} "'
)

# 5. Update normalize_recommendation_target signature
content = content.replace(
    'requested_trim: str,\n    min_year: int = 0,\n    max_year: int = 0,',
    'requested_trim: str,\n    required_features: list[str] = None,\n    min_year: int = 0,\n    max_year: int = 0,'
)

# 6. Update inner call to _calculate_recommendation_score
content = content.replace(
    'clean_mileage=clean_mileage,\n            requested_trim=requested_trim,\n            min_year=min_year,',
    'clean_mileage=clean_mileage,\n            requested_trim=requested_trim,\n            required_features=required_features,\n            min_year=min_year,'
)


with open('scrapers/recommend_normalizer.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("Updated recommend_normalizer.py")
