"""
test_dynamic_quota.py
Verification Test for Dynamic 1-5 Quota in Recommender
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agents.recommender import SEMANTIC_MAPPER_PROMPT, _FALLBACK_PROMPT, _sanitize_recommendations

PASS = "[PASS]"
FAIL = "[FAIL]"

failed_tests = 0
total_tests = 0

def assert_in_text(label: str, text: str, substring: str):
    global failed_tests, total_tests
    total_tests += 1
    if substring in text:
        print(f"  {PASS}  {label}")
    else:
        failed_tests += 1
        print(f"  {FAIL}  {label}\n         Did not find substring:\n         {substring}")

def assert_eq(label: str, actual, expected):
    global failed_tests, total_tests
    total_tests += 1
    if actual == expected:
        print(f"  {PASS}  {label}")
    else:
        failed_tests += 1
        print(f"  {FAIL}  {label}\n         Expected: {expected}\n         Got:      {actual}")

def test_prompts():
    print("\n--- TEST 1: Prompt Contract Updates ---")
    
    assert_in_text(
        "Semantic Mapper allows 1-5 targets", 
        SEMANTIC_MAPPER_PROMPT, 
        "Translate their intent into 1 to 5 car search targets (UP TO 5)"
    )
    
    assert_in_text(
        "Semantic Mapper output contract updated",
        SEMANTIC_MAPPER_PROMPT,
        "The array must contain UP TO 5 objects (1 to 5)"
    )
    
    assert_in_text(
        "Q-QUOTA logic added",
        SEMANTIC_MAPPER_PROMPT,
        "Q-QUOTA (Quality > Quantity Rule):"
    )

    assert_in_text(
        "Fallback Prompt asks for UP TO requested number",
        _FALLBACK_PROMPT,
        "Return UP TO the requested number"
    )

def test_sanitizer():
    print("\n--- TEST 2: Array Size Sanitization ---")
    
    # Mocking a valid 3-item array returned by LLM
    raw_array = [
        {"make": "Toyota", "model": "Aqua", "min_year": 2012},
        {"make": "Honda", "model": "Fit", "min_year": 2013},
        {"make": "Nissan", "model": "Note", "min_year": 2017},
    ]
    
    sanitized = _sanitize_recommendations(raw_array)
    assert_eq("Sanitizer successfully parses 3 items without enforcing 5", len(sanitized), 3)

def main():
    print("======================================================")
    print("  Dynamic 1-5 Quota - Verification Test ")
    print("======================================================")

    test_prompts()
    test_sanitizer()
    
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
