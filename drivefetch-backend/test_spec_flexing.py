"""
test_spec_flexing.py
Verification Test Suite for Flexible Target Count & Zero CoT Leakage
"""
import sys
import os
import asyncio
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agents.recommender import (
    SEMANTIC_MAPPER_PROMPT,
    _parse_llm_json,
    _sanitize_recommendations,
    semantic_mapper,
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
# TEST 1: SEMANTIC_MAPPER_PROMPT rule checks
# ==============================================================================
def test_prompt_rules():
    print("\n--- TEST 1: Prompt Rule Checks ---")
    assert_in("Prompt enforces STRICT OUTPUT FORMAT", SEMANTIC_MAPPER_PROMPT, "STRICT OUTPUT FORMAT:")
    assert_in("Prompt has Q-COUNT rule", SEMANTIC_MAPPER_PROMPT, "Q-COUNT (Dynamic 1-3 Quality Rule)")
    assert_in("Prompt has Q-SPEC-FLEX rule", SEMANTIC_MAPPER_PROMPT, "Q-SPEC-FLEX (Engine & Specs Flexibility)")
    assert_in("Prompt target count is 1 to 3", SEMANTIC_MAPPER_PROMPT, "1 to 3 objects")


# ==============================================================================
# TEST 2: _parse_llm_json robust regex
# ==============================================================================
def test_parser_strips_leakage():
    print("\n--- TEST 2: Parser Strips Leakage ---")
    raw_leakage = """
Wait, let's substitute Proton Saga since its engine is 1.3L... Re-evaluating 1.8L with sunroof in Pakistan...
Okay, here are the 2 targets:
```json
[
  {"make": "Toyota", "model": "Corolla", "trim": "Altis Grande 1.8", "city": "", "max_budget": 0, "min_year": 0, "required_features": ["sunroof"], "rationale": "Great car."}
]
```
I hope this helps!
"""
    result = _parse_llm_json(raw_leakage)
    assert_eq("Parser returns list length 1", len(result), 1)
    assert_eq("Parser extracts correct model", result[0]["model"], "Corolla")


# ==============================================================================
# TEST 3: _sanitize_recommendations rationale cleaner
# ==============================================================================
def test_sanitizer_cleans_rationale():
    print("\n--- TEST 3: Sanitizer Cleans Rationale ---")
    raw_list = [
        {"make": "Toyota", "model": "Corolla", "rationale": "Wait, let's see... this has a sunroof."},
        {"make": "Honda", "model": "Civic", "rationale": "Re-evaluating engine size, 1.8L is here."},
        {"make": "Hyundai", "model": "Elantra", "rationale": "Instead, adding 2.0L option."},
        {"make": "Kia", "model": "Sportage", "rationale": "Perfect crossover for city use."},
    ]
    
    sanitized = _sanitize_recommendations(raw_list)
    assert_eq("Item 1 cleaned", sanitized[0]["rationale"], "Proven Toyota Corolla variant matching your requested specifications.")
    assert_eq("Item 2 cleaned", sanitized[1]["rationale"], "Proven Honda Civic variant matching your requested specifications.")
    assert_eq("Item 3 cleaned", sanitized[2]["rationale"], "Proven Hyundai Elantra variant matching your requested specifications.")
    assert_eq("Item 4 preserved", sanitized[3]["rationale"], "Perfect crossover for city use.")


# ==============================================================================
# TEST 4: Engine Spec Flexing Query execution
# ==============================================================================
async def test_spec_flexing_query():
    print("\n--- TEST 4: Engine Spec Flexing Query ---")
    import agents.recommender

    class MockResponse:
        text = """[
            {"make": "Toyota", "model": "Corolla", "trim": "Altis Grande", "city": "", "max_budget": 0, "min_year": 0, "required_features": ["sunroof"], "rationale": "1.8L engine with factory sunroof."},
            {"make": "Honda", "model": "Civic", "trim": "Oriel", "city": "", "max_budget": 0, "min_year": 0, "required_features": ["sunroof"], "rationale": "1.8L i-VTEC with sunroof."},
            {"make": "Hyundai", "model": "Elantra", "trim": "GLS", "city": "", "max_budget": 0, "min_year": 0, "required_features": ["sunroof"], "rationale": "2.0L engine (slightly larger than requested 1.8L), but delivers a factory sunroof."}
        ]"""
    
    async def mock_generate_content(*args, **kwargs):
        return MockResponse()

    agents.recommender.client = MagicMock()
    agents.recommender.client.aio.models.generate_content = mock_generate_content
    
    result = await semantic_mapper("Best cars with stock sunroofs and 1.8 engine")
    assert_eq("Returns exactly 3 objects", len(result), 3)
    assert_not_in("No Proton Saga", json.dumps(result), "Proton")
    assert_true("Elantra 2.0L flexed properly", any("2.0L engine (slightly larger" in r["rationale"] for r in result))

def main():
    print("======================================================")
    print("  Flexible 1-3 & Spec-Flexing Test Suite             ")
    print("======================================================")

    test_prompt_rules()
    test_parser_strips_leakage()
    test_sanitizer_cleans_rationale()
    asyncio.run(test_spec_flexing_query())

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
