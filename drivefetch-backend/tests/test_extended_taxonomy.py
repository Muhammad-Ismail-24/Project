"""
test_extended_taxonomy.py
Verification Test Suite for Extended Market Taxonomy

Tests parse_user_query() (orchestrator) and normalize_listings() / identity
scoring (normalizer) against JDM imports, Chinese entrants, and local
sub-model queries that previously caused failures or vetoes.

Usage:
    cd drivefetch-backend
    python test_extended_taxonomy.py
"""

import asyncio
import sys
import os

# Ensure we can import from the backend package
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from models.car_schema import CarListing
from scrapers.normalizer import (
    normalize_make_model,
    _calculate_identity_score,
    _resolve_model_aliases,
    normalize_listings,
    MAKE_INFERENCE_MAP,
    MODEL_ALIAS_MAP,
    MAKE_VETO_ALIASES,
    TYPO_CORRECTIONS,
)

# ═══════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════

PASS = "\033[92m✓ PASS\033[0m"
FAIL = "\033[91m✗ FAIL\033[0m"

failed_tests = 0
total_tests = 0


def assert_eq(label: str, actual, expected):
    global failed_tests, total_tests
    total_tests += 1
    if actual == expected:
        print(f"  {PASS}  {label}")
    else:
        failed_tests += 1
        print(f"  {FAIL}  {label}")
        print(f"         Expected: {expected}")
        print(f"         Got:      {actual}")


def assert_gte(label: str, actual: float, threshold: float):
    global failed_tests, total_tests
    total_tests += 1
    if actual >= threshold:
        print(f"  {PASS}  {label} (score={actual:.2f} >= {threshold})")
    else:
        failed_tests += 1
        print(f"  {FAIL}  {label}")
        print(f"         Expected score >= {threshold}, got {actual:.2f}")


def assert_in(label: str, needle: str, haystack_key: str, data: dict):
    global failed_tests, total_tests
    total_tests += 1
    val = data.get(haystack_key)
    if val and needle.lower() in val.lower():
        print(f"  {PASS}  {label}")
    else:
        failed_tests += 1
        print(f"  {FAIL}  {label}")
        print(f"         Expected '{needle}' in data['{haystack_key}'], got: {val}")


def make_car(title: str, platform: str = "PakWheels", price: int = 2000000,
             city: str = "Lahore", year: int = 2020, mileage: int = 50000) -> CarListing:
    return CarListing(
        title=title, price=price, mileage=mileage, city=city,
        year=str(year), listing_url="https://example.com/test",
        image_url="", platform=platform, age_days=1,
    )


# ═══════════════════════════════════════════════════════════════════════════
# TEST 1: MAKE_INFERENCE_MAP Coverage
# ═══════════════════════════════════════════════════════════════════════════

def test_make_inference_map():
    print("\n═══ TEST 1: MAKE_INFERENCE_MAP Coverage ═══")

    required = {
        # JDM Kei / Micro-vans
        "atrai":    ("Daihatsu", "Atrai"),
        "tanto":    ("Daihatsu", "Tanto"),
        "taft":     ("Daihatsu", "Taft"),
        "wake":     ("Daihatsu", "Wake"),
        "cast":     ("Daihatsu", "Cast"),
        "boon":     ("Daihatsu", "Boon"),
        "thor":     ("Daihatsu", "Thor"),
        "rocky":    ("Daihatsu", "Rocky"),
        "scrum":    ("Mazda",    "Scrum"),
        "spacia":   ("Suzuki",   "Spacia"),
        "hustler":  ("Suzuki",   "Hustler"),
        "lapin":    ("Suzuki",   "Lapin"),
        "ignis":    ("Suzuki",   "Ignis"),
        "clipper":  ("Nissan",   "Clipper"),
        "roox":     ("Nissan",   "Roox"),
        "moco":     ("Nissan",   "Moco"),
        "minicab":  ("Mitsubishi", "Minicab"),
        "sambar":   ("Subaru",   "Sambar"),
        "justy":    ("Subaru",   "Justy"),
        # Toyota compact
        "roomy":    ("Toyota",   "Roomy"),
        "passo":    ("Toyota",   "Passo"),
        "sienta":   ("Toyota",   "Sienta"),
        "harrier":  ("Toyota",   "Harrier"),
        # Honda
        "nbox":     ("Honda",    "N-Box"),
        "nvan":     ("Honda",    "N-Van"),
        "grace":    ("Honda",    "Grace"),
        "insight":  ("Honda",    "Insight"),
        # Chinese
        "deepal":   ("Changan",  "Deepal"),
        "alsvin":   ("Changan",  "Alsvin"),
        "sealion":  ("BYD",      "Sealion"),
        "dashing":  ("Jetour",   "Dashing"),
        "jolion":   ("Haval",    "Jolion"),
        # Existing (sanity)
        "civic":    ("Honda",    "Civic"),
        "corolla":  ("Toyota",   "Corolla"),
        "sportage": ("Kia",      "Sportage"),
    }

    for key, (exp_make, exp_model) in required.items():
        entry = MAKE_INFERENCE_MAP.get(key)
        assert_eq(
            f"MAKE_INFERENCE_MAP['{key}'] = ({exp_make}, {exp_model})",
            entry, (exp_make, exp_model)
        )


# ═══════════════════════════════════════════════════════════════════════════
# TEST 2: MODEL_ALIAS_MAP Coverage
# ═══════════════════════════════════════════════════════════════════════════

def test_model_alias_map():
    print("\n═══ TEST 2: MODEL_ALIAS_MAP Coverage ═══")

    # Check that specific aliases resolve correctly
    checks = {
        "atrai wagon": "atrai",
        "hijet atrai": "atrai",
        "scrum wagon": "scrum",
        "nv100 clipper": "clipper",
        "n box": "nbox",
        "n van": "nvan",
        "dayz roox": "roox",
        "move canbus": "canbus",
        "wagon r stingray": "stingray",
        "every join": "every",
        "civic reborn": "civic",
        "corolla altis": "corolla",
        "city aspire": "city",
    }

    for alias_str, canonical_key in checks.items():
        aliases = MODEL_ALIAS_MAP.get(canonical_key, [])
        found = alias_str in aliases
        assert_eq(f"'{alias_str}' in MODEL_ALIAS_MAP['{canonical_key}']", found, True)


# ═══════════════════════════════════════════════════════════════════════════
# TEST 3: MAKE_VETO_ALIASES Cross-OEM
# ═══════════════════════════════════════════════════════════════════════════

def test_make_veto_aliases():
    print("\n═══ TEST 3: MAKE_VETO_ALIASES Cross-OEM ═══")

    # Daihatsu ↔ Toyota (existing)
    assert_eq(
        "Daihatsu/Toyota cross-accept",
        "toyota" in MAKE_VETO_ALIASES.get("daihatsu", []), True
    )
    assert_eq(
        "Toyota/Daihatsu cross-accept",
        "daihatsu" in MAKE_VETO_ALIASES.get("toyota", []), True
    )

    # Mazda ↔ Suzuki (Scrum = Every)
    assert_eq(
        "Mazda/Suzuki cross-accept",
        "suzuki" in MAKE_VETO_ALIASES.get("mazda", []), True
    )

    # Nissan ↔ Suzuki (Clipper = Every)
    assert_eq(
        "Nissan/Suzuki cross-accept",
        "suzuki" in MAKE_VETO_ALIASES.get("nissan", []), True
    )


# ═══════════════════════════════════════════════════════════════════════════
# TEST 4: TYPO_CORRECTIONS
# ═══════════════════════════════════════════════════════════════════════════

def test_typo_corrections():
    print("\n═══ TEST 4: TYPO_CORRECTIONS ═══")

    typos = {
        "atry": "atrai", "sakrum": "scrum", "hastler": "hustler",
        "tunto": "tanto", "tauft": "taft", "rumi": "roomy",
        "minikab": "minicab", "samber": "sambar", "clipar": "clipper",
        "deepl": "deepal", "alswin": "alsvin", "seelion": "sealion",
        # Existing (sanity)
        "carolla": "corolla", "civec": "civic", "kultus": "cultus",
    }

    for typo, correction in typos.items():
        assert_eq(
            f"TYPO_CORRECTIONS['{typo}'] = '{correction}'",
            TYPO_CORRECTIONS.get(typo), correction
        )


# ═══════════════════════════════════════════════════════════════════════════
# TEST 5: Identity Scoring — Compound JDM Titles
# ═══════════════════════════════════════════════════════════════════════════

def test_identity_scoring():
    print("\n═══ TEST 5: Identity Scoring — Compound Titles ═══")

    cases = [
        # (make, model, title, min_expected_score)
        ("Daihatsu", "Atrai",        "Daihatsu Hijet Atrai Wagon 2019",           0.75),
        ("Daihatsu", "Atrai Wagon",  "Daihatsu Hijet Atrai Wagon 2019",           0.75),
        ("Suzuki",   "Every",        "Suzuki Every Join Turbo 2021",               0.75),
        ("Toyota",   "Roomy",        "Toyota Roomy Custom GT 2022",                0.75),
        ("Honda",    "N-Box",        "Honda N Box Custom G L 2020",                0.75),
        ("Honda",    "N-Van",        "Honda N-Van +Style Fun 2023",                0.75),
        ("Mitsubishi","Minicab",     "Mitsubishi Minicab Van 660cc 2018",          0.75),
        ("Mazda",    "Scrum",        "Mazda Scrum Wagon PC 2019",                  0.75),
        ("Toyota",   "Corolla",      "Toyota Corolla Altis Grande 1.8 CVT-i 2021", 0.75),
        ("Honda",    "Civic",        "Honda Civic Reborn VTi Oriel Prosmatec 2012", 0.75),
        ("Changan",  "Deepal",       "Changan Deepal S7 EV 2024",                 0.75),
        ("BYD",      "Sealion",      "BYD Sealion 7 AWD 2025",                    0.75),
    ]

    for make, model, title, threshold in cases:
        score = _calculate_identity_score(make, model, title)
        assert_gte(f"'{model}' vs '{title[:50]}...'", score, threshold)


# ═══════════════════════════════════════════════════════════════════════════
# TEST 6: normalize_make_model Inference
# ═══════════════════════════════════════════════════════════════════════════

def test_normalize_make_model():
    print("\n═══ TEST 6: normalize_make_model Inference ═══")

    cases = [
        # (input_make, input_model, expected_make, expected_model)
        ("",          "atrai",     "Daihatsu",    "Atrai"),
        ("",          "scrum",     "Mazda",       "Scrum"),
        ("",          "spacia",    "Suzuki",      "Spacia"),
        ("",          "hustler",   "Suzuki",      "Hustler"),
        ("",          "roomy",     "Toyota",      "Roomy"),
        ("",          "deepal",    "Changan",     "Deepal"),
        ("",          "minicab",   "Mitsubishi",  "Minicab"),
        ("",          "sambar",    "Subaru",      "Sambar"),
        ("",          "nbox",      "Honda",       "N-Box"),
        ("",          "nvan",      "Honda",       "N-Van"),
        # Existing (sanity)
        ("",          "civic",     "Honda",       "Civic"),
        ("",          "corolla",   "Toyota",      "Corolla"),
    ]

    for in_make, in_model, exp_make, exp_model in cases:
        actual_make, actual_model = normalize_make_model(in_make, in_model)
        assert_eq(
            f"normalize('{in_make}', '{in_model}') → ({exp_make}, {exp_model})",
            (actual_make, actual_model), (exp_make, exp_model)
        )


# ═══════════════════════════════════════════════════════════════════════════
# TEST 7: End-to-End normalize_listings (no vetoes on valid JDM titles)
# ═══════════════════════════════════════════════════════════════════════════

def test_normalize_listings_jdm():
    print("\n═══ TEST 7: End-to-End — JDM listings NOT vetoed ═══")

    listings = [
        make_car("Daihatsu Hijet Atrai Wagon 660cc 2019", city="Lahore", price=2200000),
        make_car("Mazda Scrum Wagon DG17W 2020", city="Lahore", price=2100000),
        make_car("Honda N-Box Custom G L Turbo 2022", city="Lahore", price=2800000),
        make_car("Suzuki Every Join Turbo 2021", city="Lahore", price=1800000),
        make_car("Toyota Roomy Custom GT 2023", city="Lahore", price=3000000),
        make_car("Mitsubishi Minicab Van 660cc 2018", city="Lahore", price=1500000),
    ]

    test_cases = [
        ("Daihatsu", "Atrai",    "Lahore", 2500000),
        ("Mazda",    "Scrum",    "Lahore", 2500000),
        ("Honda",    "N-Box",    "Lahore", 3000000),
        ("Suzuki",   "Every",    "Lahore", 2000000),
        ("Toyota",   "Roomy",    "Lahore", 3500000),
        ("Mitsubishi","Minicab", "Lahore", 2000000),
    ]

    for make, model, city, budget in test_cases:
        results, empty = normalize_listings(
            listings, requested_make=make, requested_model=model,
            requested_city=city, requested_budget=budget, debug=False,
        )
        assert_gte(
            f"'{make} {model}' returns >= 1 result (got {len(results)})",
            float(len(results)), 1.0
        )


# ═══════════════════════════════════════════════════════════════════════════
# TEST 8: End-to-End — Chinese / Local sub-model queries
# ═══════════════════════════════════════════════════════════════════════════

def test_normalize_listings_chinese_local():
    print("\n═══ TEST 8: End-to-End — Chinese & Local sub-model queries ═══")

    listings = [
        make_car("Changan Deepal S7 EV 2024", city="Lahore", price=7500000),
        make_car("Toyota Corolla Altis Grande 1.8 2021", city="Rawalpindi", price=5500000),
        make_car("Honda Civic RS Turbo 2022", city="Rawalpindi", price=7000000),
    ]

    # Deepal S7
    results, _ = normalize_listings(
        listings, requested_make="Changan", requested_model="Deepal",
        requested_city="Lahore", requested_budget=8000000,
    )
    assert_gte("Changan Deepal returns >= 1 result", float(len(results)), 1.0)

    # Corolla Grande
    results, _ = normalize_listings(
        listings, requested_make="Toyota", requested_model="Corolla",
        requested_city="Rawalpindi", requested_budget=6000000,
        requested_trim="Grande",
    )
    assert_gte("Toyota Corolla Grande returns >= 1 result", float(len(results)), 1.0)


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 55)
    print("  Extended Market Taxonomy - Verification Test Suite")
    print("=" * 55)

    test_make_inference_map()
    test_model_alias_map()
    test_make_veto_aliases()
    test_typo_corrections()
    test_identity_scoring()
    test_normalize_make_model()
    test_normalize_listings_jdm()
    test_normalize_listings_chinese_local()

    print(f"\n{'=' * 55}")
    print(f"  Total: {total_tests}  |  Passed: {total_tests - failed_tests}  |  Failed: {failed_tests}")
    if failed_tests > 0:
        print(f"  \033[91m{failed_tests} test(s) FAILED!\033[0m")
        sys.exit(1)
    else:
        print(f"  \033[92mAll tests passed!\033[0m")
        sys.exit(0)


if __name__ == "__main__":
    main()
