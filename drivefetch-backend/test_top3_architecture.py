"""
test_top3_architecture.py
Verification Test Suite for Top-3 Pure Quality Architecture
"""
import sys
import os
import asyncio
import json
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agents.recommender import SEMANTIC_MAPPER_PROMPT, _FALLBACK_PROMPT, _sanitize_recommendations
from api.recommend_routes import _target_label

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
# TEST 1: Prompt Structure - EXACTLY 3 Contract
# ==============================================================================
def test_prompt_contract():
    print("\n--- TEST 1: Prompt Contract = EXACTLY 3 ---")

    assert_in(
        "System header says EXACTLY 3 tier-1",
        SEMANTIC_MAPPER_PROMPT,
        "EXACTLY 3 tier-1 car search targets"
    )

    assert_in(
        "Output contract says EXACTLY 3 objects",
        SEMANTIC_MAPPER_PROMPT,
        "The array must contain EXACTLY 3 objects"
    )

    assert_not_in(
        "No UP TO 5 in contract",
        SEMANTIC_MAPPER_PROMPT,
        "UP TO 5 objects"
    )

# ==============================================================================
# TEST 2: Diversity Abolished, Dominance Established
# ==============================================================================
def test_dominance_rule():
    print("\n--- TEST 2: Diversity Abolished, Dominance Established ---")

    assert_not_in(
        "Q7 DIVERSITY rule removed",
        SEMANTIC_MAPPER_PROMPT,
        "Q7. DIVERSITY"
    )

    assert_not_in(
        "Q-QUOTA removed (superseded by EXACTLY 3)",
        SEMANTIC_MAPPER_PROMPT,
        "Q-QUOTA"
    )

    assert_in(
        "Q-DOMINANCE present",
        SEMANTIC_MAPPER_PROMPT,
        "Q-DOMINANCE (Pure Market Excellence Rule):"
    )

    assert_in(
        "Dominance allows all-Toyota top 3",
        SEMANTIC_MAPPER_PROMPT,
        "output all 3 from that brand"
    )

    assert_in(
        "Category hierarchy: Land Cruiser > Prado > Fortuner",
        SEMANTIC_MAPPER_PROMPT,
        "Toyota Land Cruiser (70/100/200/300) > Toyota Prado > Toyota Fortuner"
    )

# ==============================================================================
# TEST 3: Rugged 4x4 Few-Shot Example Correctness
# ==============================================================================
def test_rugged_4x4_example():
    print("\n--- TEST 3: Rugged 4x4 Few-Shot Example ---")

    # Extract the rugged 4x4 JSON array from the prompt
    rugged_section = SEMANTIC_MAPPER_PROMPT[
        SEMANTIC_MAPPER_PROMPT.find('"rugged 4x4 chahiye'):
    ]
    # Find the JSON array
    arr_start = rugged_section.find('[')
    arr_end = rugged_section.find('\n]', arr_start) + 2
    arr_text = rugged_section[arr_start:arr_end].replace('\r\n', '\n').replace('\r', '')

    try:
        cars = json.loads(arr_text)
    except json.JSONDecodeError:
        global failed_tests, total_tests
        total_tests += 1
        failed_tests += 1
        print(f"  {FAIL}  Could not parse rugged 4x4 JSON array")
        return

    assert_eq("Rugged 4x4 example has exactly 3 targets", len(cars), 3)

    makes = [c["make"] for c in cars]
    models = [c["model"] for c in cars]

    assert_true(
        "All 3 targets are Toyota (market dominance)",
        all(m == "Toyota" for m in makes)
    )

    assert_in(
        "Land Cruiser is pick #1",
        models[0],
        "Land Cruiser"
    )

    assert_in(
        "Prado is pick #2",
        models[1],
        "Prado"
    )

    assert_in(
        "Fortuner is pick #3",
        models[2],
        "Fortuner"
    )

    # Verify NO GWM/Isuzu/Mitsubishi in the example
    all_text = json.dumps(cars)
    assert_not_in("No GWM in rugged 4x4 top 3", all_text, "GWM")
    assert_not_in("No Isuzu in rugged 4x4 top 3", all_text, "Isuzu")
    assert_not_in("No Mitsubishi in rugged 4x4 top 3", all_text, "Mitsubishi")

# ==============================================================================
# TEST 4: All Few-Shot Examples Have Exactly 3 Objects
# ==============================================================================
def test_all_examples_have_3():
    print("\n--- TEST 4: All Few-Shot JSON Arrays Have 3 Objects ---")

    fewshot_start = SEMANTIC_MAPPER_PROMPT.find("FEW-SHOT EXAMPLES")
    fewshot_text = SEMANTIC_MAPPER_PROMPT[fewshot_start:]

    # Find all JSON arrays
    arrays = []
    idx = 0
    while True:
        start = fewshot_text.find('[\n', idx)
        if start == -1:
            break
        end = fewshot_text.find('\n]', start)
        if end == -1:
            break
        arr_str = fewshot_text[start:end+2]
        try:
            parsed = json.loads(arr_str)
            if isinstance(parsed, list) and len(parsed) > 0 and isinstance(parsed[0], dict) and "make" in parsed[0]:
                arrays.append(parsed)
        except json.JSONDecodeError:
            pass
        idx = end + 2

    assert_true(f"Found {len(arrays)} few-shot arrays (expect >= 5)", len(arrays) >= 5)

    for i, arr in enumerate(arrays):
        assert_eq(f"  Few-shot array {i+1} has 3 objects", len(arr), 3)

# ==============================================================================
# TEST 5: Sanitizer Accepts 3-Item Arrays
# ==============================================================================
def test_sanitizer_3_items():
    print("\n--- TEST 5: Sanitizer Handles 3-Item Arrays ---")

    raw = [
        {"make": "Toyota", "model": "Land Cruiser", "min_year": 2019},
        {"make": "Toyota", "model": "Prado", "min_year": 2019},
        {"make": "Toyota", "model": "Fortuner", "min_year": 2019},
    ]
    sanitized = _sanitize_recommendations(raw)
    assert_eq("Sanitizer returns all 3", len(sanitized), 3)

# ==============================================================================
# TEST 6: Extension Endpoint Exists
# ==============================================================================
def test_extension_endpoint():
    print("\n--- TEST 6: Extension Endpoint ---")

    with open("api/recommend_routes.py", "r", encoding="utf-8") as f:
        routes_content = f.read()

    assert_in(
        "/api/recommend/more endpoint exists",
        routes_content,
        '/api/recommend/more'
    )

    assert_in(
        "is_extension flag in response",
        routes_content,
        '"is_extension": True'
    )

# ==============================================================================
# TEST 7: Fallback Prompt Updated for Max 3
# ==============================================================================
def test_fallback_max_3():
    print("\n--- TEST 7: Fallback Prompt Max 3 ---")

    assert_in(
        "Fallback prompt says max 3",
        _FALLBACK_PROMPT,
        "max 3"
    )


def main():
    print("======================================================")
    print("  Top-3 Pure Quality Architecture - Verification Test  ")
    print("======================================================")

    test_prompt_contract()
    test_dominance_rule()
    test_rugged_4x4_example()
    test_all_examples_have_3()
    test_sanitizer_3_items()
    test_extension_endpoint()
    test_fallback_max_3()

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
