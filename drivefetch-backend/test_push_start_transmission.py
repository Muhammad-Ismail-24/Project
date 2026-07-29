"""
test_push_start_transmission.py
Verification Test Suite for Transmission Locks & Push-Start Trim logic
"""
import sys
import os
import asyncio
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agents.recommender import (
    SEMANTIC_MAPPER_PROMPT,
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

def assert_not_in(label, text, substring):
    global failed_tests, total_tests
    total_tests += 1
    if substring not in text:
        print(f"  {PASS}  {label}")
    else:
        failed_tests += 1
        print(f"  {FAIL}  {label}\n         Should NOT contain: {substring}")

# ==============================================================================
# TEST 1: Check Prompts for new rules
# ==============================================================================
def test_prompt_rules():
    print("\n--- TEST 1: Prompt Rule Checks ---")
    assert_in("SEMANTIC_MAPPER has Q-TRANSMISSION-STRICT", SEMANTIC_MAPPER_PROMPT, "Q-TRANSMISSION-STRICT")
    assert_in("SEMANTIC_MAPPER has Q-PUSH-START-TRIMS", SEMANTIC_MAPPER_PROMPT, "Q-PUSH-START-TRIMS")
    assert_in("_EXTENDED_MAPPER has TRANSMISSION LOCK", _EXTENDED_MAPPER_PROMPT, "TRANSMISSION LOCK")
    assert_in("_EXTENDED_MAPPER has FEATURE LOCK", _EXTENDED_MAPPER_PROMPT, "FEATURE LOCK")

# ==============================================================================
# TEST 2: Initial Top 3 Mock Test (Push Start)
# ==============================================================================
async def test_initial_push_start():
    print("\n--- TEST 2: Initial Push Start Target Ordering ---")
    import agents.recommender

    class MockResponse:
        text = """[
            {"make": "Nissan", "model": "Dayz", "trim": "Highway Star", "city": "Lahore", "max_budget": 2500000, "min_year": 0, "required_features": ["push start"], "rationale": "High-spec 660cc import with standard push start."},
            {"make": "Daihatsu", "model": "Move", "trim": "Custom", "city": "Lahore", "max_budget": 2500000, "min_year": 0, "required_features": ["push start"], "rationale": "Top trim JDM variant with push start."},
            {"make": "Suzuki", "model": "WagonR", "trim": "Stingray", "city": "Lahore", "max_budget": 2500000, "min_year": 0, "required_features": ["push start"], "rationale": "JDM WagonR variant natively equipped with push start."}
        ]"""

    async def mock_generate_content(*args, **kwargs):
        return MockResponse()

    agents.recommender.client = MagicMock()
    agents.recommender.client.aio.models.generate_content = mock_generate_content
    
    result = await semantic_mapper("Automatic small car with factory push start under 25 lacs in Lahore")
    assert_eq("Returns 3 objects", len(result), 3)
    assert_in("Nissan Dayz found", json.dumps(result), "Dayz")
    assert_in("Daihatsu Move found", json.dumps(result), "Move")
    assert_in("Suzuki WagonR Stingray found", json.dumps(result), "Stingray")
    assert_not_in("No Vitz F", json.dumps(result), "Vitz F")
    assert_not_in("No base Cultus", json.dumps(result), "Cultus")

# ==============================================================================
# TEST 3: Extended Mapper Transmission Lock
# ==============================================================================
async def test_extended_transmission_lock():
    print("\n--- TEST 3: Extended Transmission Lock ---")
    import agents.recommender

    class MockResponse:
        text = """[
            {"make": "Honda", "model": "N-Wgn", "trim": "Custom", "city": "Lahore", "max_budget": 2500000, "min_year": 0, "required_features": ["push start"], "rationale": "Automatic JDM import with push start."},
            {"make": "Mitsubishi", "model": "eK Wagon", "trim": "", "city": "Lahore", "max_budget": 2500000, "min_year": 0, "required_features": ["push start"], "rationale": "Another excellent JDM with push start."}
        ]"""

    async def mock_generate_content(*args, **kwargs):
        return MockResponse()

    agents.recommender.client = MagicMock()
    agents.recommender.client.aio.models.generate_content = mock_generate_content
    
    result = await get_extended_recommendations(
        "Automatic small car with factory push start under 25 lacs in Lahore",
        exclude_models=["Nissan Dayz", "Daihatsu Move", "Suzuki WagonR"]
    )
    assert_eq("Returns 2 extended objects", len(result), 2)
    assert_not_in("No Cultus Manual", json.dumps(result), "Manual")
    assert_in("Honda N-Wgn found", json.dumps(result), "N-Wgn")

def main():
    print("======================================================")
    print("  Transmission Lock & Push-Start Logic Tests         ")
    print("======================================================")

    test_prompt_rules()
    asyncio.run(test_initial_push_start())
    asyncio.run(test_extended_transmission_lock())

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
