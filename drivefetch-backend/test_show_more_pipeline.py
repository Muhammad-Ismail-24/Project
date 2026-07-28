"""
test_show_more_pipeline.py
End-to-End Verification for the "Show More Options" Extension Pipeline
"""
import sys
import os
import asyncio
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agents.recommender import (
    SEMANTIC_MAPPER_PROMPT,
    _EXTENDED_MAPPER_PROMPT,
    _sanitize_recommendations,
    get_extended_recommendations,
)
from api.recommend_routes import _target_label
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
# TEST 1: _EXTENDED_MAPPER_PROMPT exists and has correct structure
# ==============================================================================
def test_extended_prompt():
    print("\n--- TEST 1: Extended Mapper Prompt Structure ---")
    assert_true("_EXTENDED_MAPPER_PROMPT is a non-empty string", len(_EXTENDED_MAPPER_PROMPT) > 100)
    assert_in("Prompt says 2-3 secondary alternatives", _EXTENDED_MAPPER_PROMPT, "2")
    assert_in("Prompt mentions HARD-EXCLUDE", _EXTENDED_MAPPER_PROMPT, "HARD-EXCLUDE")
    assert_in("Prompt mentions 8-key schema", _EXTENDED_MAPPER_PROMPT, "8-key schema")
    assert_in("Prompt enforces raw JSON output", _EXTENDED_MAPPER_PROMPT, "raw JSON array")


# ==============================================================================
# TEST 2: get_extended_recommendations() function exists and works
# ==============================================================================
async def test_extended_function():
    print("\n--- TEST 2: get_extended_recommendations() Function ---")

    import agents.recommender
    captured_prompt = ""

    class MockResponse:
        text = json.dumps([
            {"make": "Suzuki", "model": "Baleno", "trim": "", "city": "Lahore",
             "max_budget": 1500000, "min_year": 0, "required_features": [],
             "rationale": "Budget sedan alternative"},
            {"make": "Suzuki", "model": "Liana", "trim": "", "city": "Lahore",
             "max_budget": 1500000, "min_year": 0, "required_features": [],
             "rationale": "Spacious and reliable"},
        ])

    async def mock_generate_content(*args, **kwargs):
        nonlocal captured_prompt
        captured_prompt = kwargs.get("contents", "")
        return MockResponse()

    # Mock the Gemini client
    agents.recommender.client = MagicMock()
    agents.recommender.client.aio.models.generate_content = mock_generate_content

    result = await get_extended_recommendations(
        user_prompt="Best sedan under 15 lacs in Lahore",
        exclude_models=["Toyota Corolla", "Honda Civic", "Honda City"],
        city="Lahore",
        budget=1500000,
    )

    assert_true("Returns a list", isinstance(result, list))
    assert_eq("Returns 2 items (matching mock)", len(result), 2)
    assert_eq("First item is Suzuki Baleno", result[0]["model"], "Baleno")
    assert_eq("Second item is Suzuki Liana", result[1]["model"], "Liana")

    # Verify the prompt sent to Gemini contains exclusion list
    assert_in("Prompt mentions Corolla exclusion", captured_prompt, "Toyota Corolla")
    assert_in("Prompt mentions Civic exclusion", captured_prompt, "Honda Civic")
    assert_in("Prompt mentions City exclusion", captured_prompt, "Honda City")
    assert_in("Prompt contains budget", captured_prompt, "1,500,000")


# ==============================================================================
# TEST 3: Exclusion enforcement - LLM returns excluded model, should be dropped
# ==============================================================================
async def test_exclusion_enforcement():
    print("\n--- TEST 3: Hard Exclusion Enforcement ---")

    import agents.recommender

    class MockResponse:
        text = json.dumps([
            {"make": "Toyota", "model": "Corolla", "trim": "", "city": "Lahore",
             "max_budget": 1500000, "min_year": 0, "required_features": [],
             "rationale": "LLM ignored exclusion"},
            {"make": "Suzuki", "model": "Baleno", "trim": "", "city": "Lahore",
             "max_budget": 1500000, "min_year": 0, "required_features": [],
             "rationale": "Budget sedan alternative"},
        ])

    async def mock_generate_content(*args, **kwargs):
        return MockResponse()

    agents.recommender.client = MagicMock()
    agents.recommender.client.aio.models.generate_content = mock_generate_content

    result = await get_extended_recommendations(
        user_prompt="Best sedan under 15 lacs",
        exclude_models=["Toyota Corolla", "Honda Civic", "Honda City"],
        city="Lahore",
        budget=1500000,
    )

    assert_eq("Excluded Corolla dropped, only Baleno remains", len(result), 1)
    assert_eq("Remaining item is Baleno", result[0]["model"], "Baleno")


# ==============================================================================
# TEST 4: /api/recommend/extend endpoint exists
# ==============================================================================
def test_extend_endpoint():
    print("\n--- TEST 4: /api/recommend/extend Endpoint ---")

    with open("api/recommend_routes.py", "r", encoding="utf-8") as f:
        routes_content = f.read()

    assert_in(
        "/api/recommend/extend endpoint declared",
        routes_content,
        '/api/recommend/extend'
    )

    assert_in(
        "extension_results SSE event emitted",
        routes_content,
        '"extension_results"'
    )

    assert_in(
        "get_extended_recommendations imported",
        routes_content,
        'get_extended_recommendations'
    )

    # Verify old /api/recommend/more is replaced
    assert_not_in(
        "Old /api/recommend/more removed",
        routes_content,
        '/api/recommend/more'
    )


# ==============================================================================
# TEST 5: Initial pipeline unchanged (EXACTLY 3 contract preserved)
# ==============================================================================
def test_initial_pipeline_unchanged():
    print("\n--- TEST 5: Initial Pipeline Unchanged ---")

    assert_in(
        "SEMANTIC_MAPPER_PROMPT still says EXACTLY 3",
        SEMANTIC_MAPPER_PROMPT,
        "EXACTLY 3 tier-1 car search targets"
    )

    with open("api/recommend_routes.py", "r", encoding="utf-8") as f:
        routes = f.read()

    assert_in(
        "Original /api/recommend endpoint preserved",
        routes,
        '/api/recommend"'
    )

    assert_in(
        "semantic_mapper still imported",
        routes,
        'semantic_mapper'
    )


# ==============================================================================
# TEST 6: Frontend integration check
# ==============================================================================
def test_frontend_integration():
    print("\n--- TEST 6: Frontend Integration ---")

    frontend_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..", "drivefetch-frontend", "src", "pages", "RecommendPage.jsx"
    )

    with open(frontend_path, "r", encoding="utf-8") as f:
        jsx = f.read()

    assert_in("Show More button exists", jsx, "Show More Options")
    assert_in("Extension loading state", jsx, "Finding more options")
    assert_in("Extension SSE handler", jsx, "extension_results")
    assert_in("Extends /api/recommend/extend", jsx, "/api/recommend/extend")
    assert_in("Extension rationale cards rendered", jsx, "Additional Recommendations")
    assert_in("All options shown badge", jsx, "All available options shown")
    assert_in("exclude_models sent in request", jsx, "exclude_models")


def main():
    print("======================================================")
    print("  Show More Options Pipeline - Verification Test       ")
    print("======================================================")

    test_extended_prompt()
    asyncio.run(test_extended_function())
    asyncio.run(test_exclusion_enforcement())
    test_extend_endpoint()
    test_initial_pipeline_unchanged()
    test_frontend_integration()

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
