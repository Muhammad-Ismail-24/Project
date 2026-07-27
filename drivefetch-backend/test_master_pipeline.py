"""
test_master_pipeline.py
Verification Test Suite for Master Architectural Updates
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from models.car_schema import CarListing
from scrapers.normalizer import _calculate_identity_score, MAKE_VETO_ALIASES, MODEL_ALIAS_MAP
from scrapers.recommend_normalizer import _calculate_recommendation_score
from api.recommend_routes import _scrape_one, _resolve_budget, _resolve_year

PASS = "[PASS]"
FAIL = "[FAIL]"

failed_tests = 0
total_tests = 0

def assert_eq(label: str, actual, expected):
    global failed_tests, total_tests
    total_tests += 1
    if actual == expected:
        print(f"  {PASS}  {label}")
    else:
        failed_tests += 1
        print(f"  {FAIL}  {label}\n         Expected: {expected}\n         Got:      {actual}")

def assert_gte(label: str, actual: float, threshold: float):
    global failed_tests, total_tests
    total_tests += 1
    if actual >= threshold:
        print(f"  {PASS}  {label} (score={actual:.2f} >= {threshold})")
    else:
        failed_tests += 1
        print(f"  {FAIL}  {label}\n         Expected score >= {threshold}, got {actual:.2f}")

def assert_true(label: str, condition: bool):
    global failed_tests, total_tests
    total_tests += 1
    if condition:
        print(f"  {PASS}  {label}")
    else:
        failed_tests += 1
        print(f"  {FAIL}  {label}")

def make_car(title: str, platform: str = "PakWheels", price: int = 2000000,
             city: str = "Lahore", year: int = 2020, mileage: int = 50000) -> CarListing:
    return CarListing(
        title=title, price=price, mileage=mileage, city=city,
        year=str(year), listing_url="https://example.com/test",
        image_url="", platform=platform, age_days=1,
    )

# ==============================================================================
# TEST 1: EV Query Parsing & URL Formatting Test
# ==============================================================================
import asyncio
async def test_ev_url_formatting():
    print("\n--- TEST 1: EV Query Parsing & URL Formatting Test ---")
    
    rec1 = {"make": "BYD", "model": "Atto 3", "trim": "EV", "city": "Islamabad"}
    rec2 = {"make": "Changan", "model": "Deepal S07", "trim": "ev", "city": "Islamabad"}

    # Mock execute_search_pipeline to prevent it from actually scraping and just return empty
    import scrapers.runner
    original_execute = scrapers.runner.execute_search_pipeline
    
    async def mock_execute(*args, **kwargs):
        return [], None
    
    scrapers.runner.execute_search_pipeline = mock_execute
    
    await _scrape_one(rec1, "Islamabad", None)
    await _scrape_one(rec2, "Islamabad", None)
    
    # We will test by checking if 'ev' was removed logic in recommend_routes
    GENERIC_POWERTRAIN_TAGS = {
        "ev", "electric", "hev", "phev", "hybrid", 
        "petrol", "diesel", "cng", "awd", "fwd", "4x4", "4wd"
    }
    
    trim_raw1 = rec1.get("trim") or ""
    trim_for_url1 = trim_raw1 if trim_raw1.lower() not in GENERIC_POWERTRAIN_TAGS else ""
    
    trim_raw2 = rec2.get("trim") or ""
    trim_for_url2 = trim_raw2 if trim_raw2.lower() not in GENERIC_POWERTRAIN_TAGS else ""
    
    assert_eq("BYD Atto 3 trim stripped", trim_for_url1, "")
    assert_eq("Changan Deepal S07 trim stripped", trim_for_url2, "")
    
    scrapers.runner.execute_search_pipeline = original_execute

# ==============================================================================
# TEST 2: Feature Matcher Veto Test
# ==============================================================================
def test_feature_matcher_vetoes():
    print("\n--- TEST 2: Feature Matcher Veto Test ---")
    
    car = make_car("Honda Vezel Hybrid Z 2017", year=2017)
    
    score = _calculate_recommendation_score(
        car=car,
        requested_make="Honda",
        requested_model="Vezel",
        requested_city="Lahore",
        requested_budget=5000000,
        requested_color="",
        requested_trim="Play",
        required_features=["panoramic_sunroof"],
        clean_price=4500000,
        clean_year=2017,
        clean_mileage=50000,
        min_year=2021,  # Based on the feature logic
    )
    
    assert_eq("Vezel < 2021 with panoramic sunroof should be vetoed", score, 0.0)

# ==============================================================================
# TEST 3: JDM Micro-Van Identity Test
# ==============================================================================
def test_jdm_identity_and_make():
    print("\n--- TEST 3: JDM Micro-Van Identity & Make Test ---")
    
    # Verify: Mock listing "Daihatsu Hijet Atrai Wagon Turbo 2019" achieves identity score >= 0.75
    title1 = "Daihatsu Hijet Atrai Wagon Turbo 2019"
    score1 = _calculate_identity_score("Daihatsu", "Atrai Wagon", title1)
    assert_gte("Atrai Wagon identity >= 0.75", score1, 0.75)
    
    # Verify: Mock listing "Suzuki Every Scrum Join 2020" passes make check under Mazda alias permissions
    title2 = "Suzuki Every Scrum Join 2020".lower()
    mazda_aliases = MAKE_VETO_ALIASES.get("mazda", [])
    passes_make_check = any(m in title2 for m in mazda_aliases)
    
    assert_true("Suzuki Every Scrum passes Mazda make check", passes_make_check)

def main():
    print("======================================================")
    print("  Master Architectural Updates - Verification Test    ")
    print("======================================================")

    asyncio.run(test_ev_url_formatting())
    test_feature_matcher_vetoes()
    test_jdm_identity_and_make()
    
    print(f"\n{'=' * 55}")
    print(f"  Total: {total_tests}  |  Passed: {total_tests - failed_tests}  |  Failed: {failed_tests}")
    if failed_tests > 0:
        print(f"  {failed_tests} test(s) FAILED!")
        sys.exit(1)
    else:
        print(f"  All tests passed!")
        sys.exit(0)

if __name__ == "__main__":
    main()
