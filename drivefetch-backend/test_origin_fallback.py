"""
test_origin_fallback.py
Verification Test for Origin & Body-Type Constraints + Fallback Leak
"""
import sys
import os
import asyncio

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from api.recommend_routes import _target_label
from agents.recommender import SEMANTIC_MAPPER_PROMPT, get_fallback_recommendations
from unittest.mock import MagicMock

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

def assert_in_text(label: str, text: str, substring: str):
    global failed_tests, total_tests
    total_tests += 1
    if substring in text:
        print(f"  {PASS}  {label}")
    else:
        failed_tests += 1
        print(f"  {FAIL}  {label}\n         Did not find substring: {substring}")

# ==============================================================================
# TEST 1: Duplicate String Formatting Test
# ==============================================================================
def test_target_label_formatting():
    print("\n--- TEST 1: Target Label Formatting ---")
    
    # 1. ZS EV with EV trim
    rec_zs = {"make": "MG", "model": "ZS EV", "trim": "EV"}
    assert_eq("MG ZS EV prevents duplicate [EV]", _target_label(rec_zs), "MG ZS EV")
    
    # 2. Civic with Oriel trim
    rec_civic = {"make": "Honda", "model": "Civic", "trim": "Oriel"}
    assert_eq("Honda Civic keeps [Oriel]", _target_label(rec_civic), "Honda Civic [Oriel]")
    
    # 3. No trim
    rec_atto = {"make": "BYD", "model": "Atto 3", "trim": ""}
    assert_eq("BYD Atto 3 keeps no trim", _target_label(rec_atto), "BYD Atto 3")

# ==============================================================================
# TEST 2: Fallback Context Leak Test
# ==============================================================================
async def test_fallback_context():
    print("\n--- TEST 2: Fallback Context Leak Test ---")
    
    # We will mock the `client.aio.models.generate_content` inside `get_fallback_recommendations`
    # to simply capture the prompt and return an empty list so we can inspect it.
    
    import agents.recommender
    captured_prompt = ""
    
    class MockResponse:
        text = "[]"

    async def mock_generate_content(*args, **kwargs):
        nonlocal captured_prompt
        captured_prompt = kwargs.get("contents")
        return MockResponse()
    
    agents.recommender.client = MagicMock()
    agents.recommender.client.aio.models.generate_content = mock_generate_content
    
    await get_fallback_recommendations(
        user_prompt="Electric chinese crossovers islamabad",
        city="Islamabad",
        budget=10000000,
        failed_targets=["MG ZS EV"],
        tried_models=["MG ZS EV"],
        count=2
    )
    
    assert_in_text(
        "Fallback prompt preserves explicit constraints", 
        captured_prompt, 
        "CRITICAL: Maintain ALL constraints from original request (e.g., Brand Origin/Nationality, Body Type/Segment, Drivetrain)"
    )

# ==============================================================================
# TEST 3: Prompt Structure Test (Q-ORIGIN & Q-BODYSTYLE)
# ==============================================================================
def test_prompt_structure():
    print("\n--- TEST 3: Prompt Structure Test ---")
    
    assert_in_text(
        "Prompt contains Q0-A (Brand Nationality Check)", 
        SEMANTIC_MAPPER_PROMPT, 
        "Q0-A. ORIGIN (Brand Nationality Check):"
    )
    
    assert_in_text(
        "Prompt contains Q0-B (Segment Check)", 
        SEMANTIC_MAPPER_PROMPT, 
        "Q0-B. BODY-STYLE (Segment Check):"
    )

def main():
    print("======================================================")
    print("  Origin & Body-Type Constraint Fixes - Verification  ")
    print("======================================================")

    test_target_label_formatting()
    asyncio.run(test_fallback_context())
    test_prompt_structure()
    
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
