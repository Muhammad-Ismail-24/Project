"""
test_city_veto.py

Regression tests for the city hard veto and the city-erasure bug.

THE BUG
-------
Both normalisers already implemented the city hard veto correctly, complete
with NEARBY_CITY_MAP twin-city amnesty. Neither ever fired, because both guard
the veto behind `if req_city_str:` and the city never reached them:

  1. UserIntent had no `city` field, so "…in Lahore" in the prompt was never
     extracted.
  2. resolve_constraints() never set constraints["city"].
  3. _deduplicate_and_format() hardcoded  "city": ""  with the note
     "always empty — recommend_normalizer handles city softly".

So requested_city was "" for every prompt-specified city, the veto branch was
skipped entirely, and Karachi/Hyderabad listings passed a Lahore search.

Run:  python test_city_veto.py
"""
import sys

from models.car_schema import CarListing
from agents.recommender import (
    UserIntent,
    _deduplicate_and_format,
    _detect_city_in_prompt,
    resolve_constraints,
)
from scrapers.normalizer import NEARBY_CITY_MAP, _calculate_relevance_score
from scrapers.recommend_normalizer import _score_listing

_passed = 0
_failed = 0


def check(label, actual, expected):
    global _passed, _failed
    if actual == expected:
        _passed += 1
        print(f"  PASS  {label}: {actual!r}")
    else:
        _failed += 1
        print(f"  FAIL  {label}: got {actual!r}, expected {expected!r}")


def check_true(label, condition, detail=""):
    global _passed, _failed
    if condition:
        _passed += 1
        print(f"  PASS  {label}{(' - ' + str(detail)) if detail else ''}")
    else:
        _failed += 1
        print(f"  FAIL  {label}{(' - ' + str(detail)) if detail else ''}")


def car(city, title="Toyota Corolla Cross 2022 for Sale"):
    return CarListing(
        title=title, price="PKR 78 Lacs", mileage="30000", city=city,
        year="2022", listing_url=f"https://x/{city}", platform="PakWheels",
        age_days=5,
    )


def search_score(c, requested_city):
    return _calculate_relevance_score(
        car=c, requested_make="Toyota", requested_model="Corolla Cross",
        requested_city=requested_city, requested_budget=8_000_000,
        requested_color=None, clean_price=7_800_000, clean_year=2022,
        clean_mileage=30000,
    )


def rec_score(c, requested_city, debug=False):
    return _score_listing(
        car=c, requested_make="Toyota", requested_model="Corolla Cross",
        requested_city=requested_city, requested_budget=8_000_000,
        requested_color="", clean_price=7_800_000, clean_year=2022,
        clean_mileage=30000, debug=debug,
    )


# ---------------------------------------------------------------------------
print("\n[1] Prompt -> constraints: the city must survive resolve_constraints()")
# ---------------------------------------------------------------------------
intent = UserIntent(max_budget=8_000_000, body_style="SUV", city="Lahore")
intent.user_prompt = "Family SUV under 80 Lacs in Lahore"
constraints = resolve_constraints(intent)
check("LLM-extracted city reaches constraints", constraints.get("city"), "Lahore")

# LLM under-extraction must be recovered by the deterministic fallback.
intent_miss = UserIntent(max_budget=8_000_000, body_style="SUV", city=None)
intent_miss.user_prompt = "Family SUV under 80 Lacs in Lahore"
constraints_miss = resolve_constraints(intent_miss)
check("fallback recovers city when the LLM misses it",
      constraints_miss.get("city"), "Lahore")

# Alias canonicalisation, so "isb" matches listings that say "Islamabad".
intent_alias = UserIntent(max_budget=5_000_000, city="isb")
intent_alias.user_prompt = "sedan in isb"
check("city alias canonicalised",
      resolve_constraints(intent_alias).get("city"), "Islamabad")

# No city named must stay empty — that legitimately disables the veto.
intent_none = UserIntent(max_budget=5_000_000, city=None)
intent_none.user_prompt = "a reliable family car"
check("no city named stays empty",
      resolve_constraints(intent_none).get("city"), "")

# ---------------------------------------------------------------------------
print("\n[2] Erasure bug: the target dict must carry the city")
# ---------------------------------------------------------------------------


class _RawTarget:
    """Minimal stand-in for CarTargetRaw."""
    def __init__(self, make, model, trim="", rationale="r"):
        self.make = make
        self.model = model
        self.trim = trim
        self.rationale = rationale
        self.required_features = []


targets = _deduplicate_and_format(
    [_RawTarget("Toyota", "Corolla Cross"), _RawTarget("Kia", "Sportage")],
    {"city": "Lahore", "max_budget": 8_000_000, "min_budget": 5_600_000,
     "min_year": 0, "required_features": []},
)
check_true("targets produced", len(targets) >= 1, f"{len(targets)} targets")
for t in targets:
    check(f"target {t['make']} {t['model']} carries city", t["city"], "Lahore")

empty_city = _deduplicate_and_format(
    [_RawTarget("Toyota", "Corolla Cross")],
    {"max_budget": 8_000_000, "required_features": []},
)
check("absent city key degrades to empty string, not a crash",
      empty_city[0]["city"], "")

# ---------------------------------------------------------------------------
print("\n[3] Search normalizer - hard veto on city mismatch")
# ---------------------------------------------------------------------------
check("Karachi listing vetoed for a Lahore search",
      search_score(car("Karachi"), "Lahore"), 0.0)
check("Hyderabad listing vetoed for a Lahore search",
      search_score(car("Hyderabad"), "Lahore"), 0.0)
check("Islamabad listing vetoed for a Lahore search",
      search_score(car("Islamabad"), "Lahore"), 0.0)

lahore = search_score(car("Lahore"), "Lahore")
check_true("Lahore listing passes", lahore > 0.0, f"score {lahore}")

# Twin-city amnesty must survive the veto.
check_true("Sheikhupura (Lahore twin) passes",
           search_score(car("Sheikhupura"), "Lahore") > 0.0,
           f"score {search_score(car('Sheikhupura'), 'Lahore')}")
check_true("exact city outranks twin city",
           lahore > search_score(car("Sheikhupura"), "Lahore"),
           f"{lahore} > {search_score(car('Sheikhupura'), 'Lahore')}")

# City named only in the title still counts — scrapers often leave city blank.
check_true("city in title counts as a match",
           search_score(car("", "Toyota Corolla Cross 2022 Lahore"), "Lahore") > 0.0)

# No requested city -> no veto at all.
check_true("no requested city leaves Karachi listing alive",
           search_score(car("Karachi"), "") > 0.0)

# ---------------------------------------------------------------------------
print("\n[4] Recommendation normalizer - same hard veto")
# ---------------------------------------------------------------------------
check("Karachi listing vetoed", rec_score(car("Karachi"), "Lahore"), 0.0)
check("Hyderabad listing vetoed", rec_score(car("Hyderabad"), "Lahore"), 0.0)
check_true("Lahore listing passes", rec_score(car("Lahore"), "Lahore") > 0.0,
           f"score {rec_score(car('Lahore'), 'Lahore')}")
check_true("Kasur (Lahore twin) passes",
           rec_score(car("Kasur"), "Lahore") > 0.0,
           f"score {rec_score(car('Kasur'), 'Lahore')}")

print("\n  [REC-VETO] output for a Karachi listing on a Lahore search:")
rec_score(car("Karachi"), "Lahore", debug=True)

# Karachi<->Hyderabad is a real corridor and must still work in its own right.
check_true("Hyderabad passes a Karachi search (twin corridor intact)",
           rec_score(car("Hyderabad"), "Karachi") > 0.0)

# ---------------------------------------------------------------------------
print("\n[5] Twin-city map sanity")
# ---------------------------------------------------------------------------
check_true("lahore has twins", bool(NEARBY_CITY_MAP.get("lahore")),
           sorted(NEARBY_CITY_MAP.get("lahore", ())))
check_true("karachi<->hyderabad corridor exists",
           "hyderabad" in NEARBY_CITY_MAP.get("karachi", set()))
check_true("karachi is NOT a twin of lahore",
           "karachi" not in NEARBY_CITY_MAP.get("lahore", set()))

# ---------------------------------------------------------------------------
print("\n[6] End-to-end: 'Family SUV under 80 Lacs in Lahore'")
# ---------------------------------------------------------------------------
e2e_intent = UserIntent(max_budget=8_000_000, body_style="SUV", city="Lahore")
e2e_intent.user_prompt = "Family SUV under 80 Lacs in Lahore"
e2e_constraints = resolve_constraints(e2e_intent)
e2e_targets = _deduplicate_and_format(
    [_RawTarget("Toyota", "Corolla Cross")], e2e_constraints
)
target_city = e2e_targets[0]["city"]
check("target city passed to scraper + normalizer", target_city, "Lahore")

mixed = [car("Lahore"), car("Karachi"), car("Hyderabad"),
         car("Sheikhupura"), car("Islamabad")]
kept = [c.city for c in mixed if rec_score(c, target_city) > 0.0]
check("only Lahore + its twin survive", sorted(kept), ["Lahore", "Sheikhupura"])

print(f"\n{'=' * 60}")
print(f"  {_passed} passed, {_failed} failed")
print(f"{'=' * 60}\n")
sys.exit(1 if _failed else 0)
