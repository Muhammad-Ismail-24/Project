"""
test_q_tier_hierarchy.py
Verification Test Suite for Q-TIER and Market Hierarchy
"""
import sys
import os
import asyncio
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agents.recommender import (
    SEMANTIC_MAPPER_PROMPT,
    _FALLBACK_PROMPT,
    _EXTENDED_MAPPER_PROMPT,
    semantic_mapper,
    get_extended_recommendations,
)
from unittest.mock import MagicMock

PASS = "[PASS]"
FAIL = "[FAIL]"
failed_tests = 0
total_tests = 0

def assert_eq(label, actual, expected):
    global failed_tests, total_tests
    total_tests += 1
    if actual == expected:
        print(f"  {PASS}  {label}")
    else:
        failed_tests += 1
        print(f"  {FAIL}  {label}\n         Expected: {expected}\n         Got:      {actual}")

def assert_true(label, condition):
    global failed_tests, total_tests
    total_tests += 1
    if condition:
        print(f"  {PASS}  {label}")
    else:
        failed_tests += 1
        print(f"  {FAIL}  {label}")

def assert_in(label, text, substring):
    global failed_tests, total_tests
    total_tests += 1
    if substring in text:
        print(f"  {PASS}  {label}")
    else:
        failed_tests += 1
        print(f"  {FAIL}  {label}\n         Missing: {substring}")

def test_q_tier_in_prompts():
    print("\n--- TEST 1: Q-TIER in Prompts ---")
    assert_in("SEMANTIC_MAPPER_PROMPT contains Q-TIER", SEMANTIC_MAPPER_PROMPT, "Q-TIER (Market Hierarchy & Resale Rule)")
    assert_in("SEMANTIC_MAPPER_PROMPT contains SUV Hierarchy", SEMANTIC_MAPPER_PROMPT, "SUVs under 1 Crore: Toyota Fortuner > Kia Sportage")
    assert_in("_FALLBACK_PROMPT contains Q-TIER", _FALLBACK_PROMPT, "Q-TIER: If user did NOT explicitly request a Chinese brand")
    assert_in("_EXTENDED_MAPPER_PROMPT contains Q-TIER", _EXTENDED_MAPPER_PROMPT, "Q-TIER: If user did NOT explicitly request a Chinese brand")

async def test_generic_query():
    print("\n--- TEST 2: Generic SUV Query ---")
    
    import agents.recommender
    captured_prompt = ""
    
    class MockResponse:
        text = json.dumps([
            {"make": "Kia", "model": "Sportage", "trim": "", "city": "Islamabad", "max_budget": 10000000, "min_year": 0, "required_features": [], "rationale": "Tier 1"},
            {"make": "Hyundai", "model": "Tucson", "trim": "", "city": "Islamabad", "max_budget": 10000000, "min_year": 0, "required_features": [], "rationale": "Tier 1"},
            {"make": "Toyota", "model": "Fortuner", "trim": "", "city": "Islamabad", "max_budget": 10000000, "min_year": 0, "required_features": [], "rationale": "Tier 1"},
        ])

    async def mock_generate_content(*args, **kwargs):
        nonlocal captured_prompt
        captured_prompt = kwargs.get("contents", "")
        if "system_instruction" in kwargs.get("config", {}):
             pass # Not capturing system prompt here, it's checked in Test 1
        return MockResponse()

    agents.recommender.client = MagicMock()
    agents.recommender.client.aio.models.generate_content = mock_generate_content
    
    # Run the mapper to check if everything works
    result = await semantic_mapper("best SUVs under 1 crore in islamabad")
    assert_eq("Returns 3 tier 1 models", len(result), 3)

def main():
    print("======================================================")
    print("  Q-TIER Hierarchy - Verification Test               ")
    print("======================================================")

    test_q_tier_in_prompts()
    asyncio.run(test_generic_query())

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
