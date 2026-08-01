"""
agents/recommender.py
LLM logic for the AI Matchmaker.

Architecture (simplified — tier system removed):
  Phase 1 — LLM:    extract_intent()                   → UserIntent
  Phase 1 — Python: resolve_constraints()              → budget floor + origin flag only
  Phase 2 — Python: get_budget_eligible_cars()         → every car whose price range
                                                         overlaps the budget window
  Phase 2 — LLM:    select_car_targets()               → picks 1-3 from the eligible list
  Phase 2 — Python: _validate_targets_against_market() → safety net drop of impossible picks
  Phase 2 — Python: _deduplicate_and_format_targets()  → 9-key contract dicts
  Phase 3 — LLM:    get_fallback_recommendations()     → replacement when a target hits zero
  Phase 3 — LLM:    get_extended_recommendations()     → "show more" alternatives

What changed vs previous version:
  REMOVED — tier system (economy / mid / premium / premium_upper / apex_luxury)
  REMOVED — _STYLE_TIER_ALLOWLIST catalog (body style told to LLM as instruction, not filter)
  REMOVED — fit_score ranking (Python no longer ranks cars for the LLM)
  REMOVED — is_luxury_request escalation logic
  REMOVED — make cap (2 per make) — LLM decides diversity, not Python

  KEPT    — PAKISTAN_MARKET_PRICES (the only data the LLM needs)
  KEPT    — Chinese brand gate (allow_chinese must be explicitly set)
  KEPT    — _validate_targets_against_market() safety net
  KEPT    — _deduplicate_and_format_targets() canonicalization
  KEPT    — excluded_models logic for fallback / extend

  NEW     — get_budget_eligible_cars() replaces get_candidate_pool().
            It only does ONE thing: filters the price map by budget overlap.
            No scoring, no style filter, no tier filter. Full eligible list
            passed to the LLM so IT can apply body style, use case, and
            any other criteria it knows better than Python does.

  NEW     — resolve_constraints() is much simpler: budget floor + Chinese gate.
            No tier derivation. No min_year (budget floor handles quality).
"""

import os
import json
import traceback
from dotenv import load_dotenv
from google import genai
from google.genai import types
from typing import Optional, Literal
from pydantic import BaseModel, Field

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
client = genai.Client(api_key=GEMINI_API_KEY)

_GEMINI_MODEL = "gemini-2.0-flash-lite"   # single constant — update here to change all calls


# ---------------------------------------------------------------------------
# MARKET PRICE MAP
# Format: "make:model" → (min_PKR, max_PKR)
# Represents realistic used-market transaction prices on PakWheels / OLX.
# Update this periodically as the market shifts.
# ---------------------------------------------------------------------------

PAKISTAN_MARKET_PRICES: dict[str, tuple[int, int]] = {
    # ── Suzuki ──────────────────────────────────────────────────────────────
    "suzuki:mehran":              (300_000,    1_500_000),
    "suzuki:alto":                (700_000,    3_600_000),
    "suzuki:alto 660cc":          (1_500_000,  3_800_000),
    "suzuki:cultus":              (1_000_000,  4_500_000),
    "suzuki:wagon r":             (1_500_000,  3_500_000),
    "suzuki:swift":               (1_200_000,  5_200_000),
    "suzuki:baleno":              (1_000_000,  2_500_000),
    "suzuki:liana":               (1_200_000,  2_800_000),
    "suzuki:hustler":             (1_800_000,  4_000_000),
    "suzuki:spacia":              (1_800_000,  4_000_000),
    "suzuki:solio":               (2_000_000,  4_500_000),
    "suzuki:jimny":               (2_500_000,  8_500_000),
    "suzuki:every":               (1_000_000,  3_000_000),
    "suzuki:bolan":               (500_000,    2_000_000),
    "suzuki:apv":                 (1_500_000,  3_500_000),

    # ── Toyota ──────────────────────────────────────────────────────────────
    "toyota:vitz":                (1_500_000,  4_500_000),
    "toyota:passo":               (1_500_000,  4_000_000),
    "toyota:probox":              (2_000_000,  4_500_000),
    "toyota:corolla":             (2_000_000,  8_500_000),
    "toyota:yaris":               (3_500_000,  6_000_000),
    "toyota:allion":              (3_000_000,  8_000_000),
    "toyota:premio":              (3_500_000,  9_000_000),
    "toyota:mark x":              (3_000_000,  7_000_000),
    "toyota:fielder":             (2_500_000,  6_000_000),
    "toyota:aqua":                (2_500_000,  6_500_000),
    "toyota:prius":               (2_500_000,  12_000_000),
    "toyota:sienta":              (3_000_000,  6_500_000),
    "toyota:tank":                (3_000_000,  4_500_000),
    "toyota:roomy":               (3_000_000,  5_000_000),
    "toyota:crown":               (4_000_000,  25_000_000),
    "toyota:camry":               (7_000_000,  18_000_000),
    "toyota:c-hr":                (4_500_000,  10_000_000),
    "toyota:raize":               (5_000_000,  7_500_000),
    "toyota:rush":                (5_500_000,  9_000_000),
    "toyota:yaris cross":         (6_000_000,  9_500_000),
    "toyota:fortuner":            (9_000_000,  21_000_000),
    "toyota:hilux":               (8_000_000,  16_000_000),
    "toyota:alphard":             (6_000_000,  35_000_000),
    "toyota:vellfire":            (6_000_000,  35_000_000),
    "toyota:hiace":               (3_500_000,  12_000_000),
    "toyota:prado":               (18_000_000, 48_000_000),
    "toyota:land cruiser":        (35_000_000, 90_000_000),

    # ── Honda ───────────────────────────────────────────────────────────────
    "honda:n-box":                (1_800_000,  4_200_000),
    "honda:n-wgn":                (1_500_000,  3_800_000),
    "honda:fit":                  (2_000_000,  5_500_000),
    "honda:city":                 (1_500_000,  6_000_000),
    "honda:civic":                (2_000_000,  9_500_000),
    "honda:grace":                (3_500_000,  6_500_000),
    "honda:insight":              (2_500_000,  6_500_000),
    "honda:freed":                (2_500_000,  6_000_000),
    "honda:shuttle":              (3_500_000,  7_000_000),
    "honda:stepwgn":              (3_000_000,  8_000_000),
    "honda:br-v":                 (3_500_000,  6_500_000),
    "honda:hr-v":                 (6_000_000,  8_500_000),
    "honda:vezel":                (4_000_000,  11_000_000),
    "honda:cr-v":                 (6_000_000,  14_000_000),
    "honda:accord":               (4_500_000,  12_000_000),

    # ── Hyundai ─────────────────────────────────────────────────────────────
    "hyundai:santro":             (700_000,    1_800_000),
    "hyundai:i10":                (1_200_000,  3_000_000),
    "hyundai:elantra":            (5_000_000,  7_500_000),
    "hyundai:sonata":             (7_500_000,  11_000_000),
    "hyundai:tucson":             (6_000_000,  9_000_000),
    "hyundai:porter":             (2_500_000,  4_000_000),
    "hyundai:palisade":           (18_000_000, 35_000_000),

    # ── Kia ─────────────────────────────────────────────────────────────────
    "kia:picanto":                (2_500_000,  3_800_000),
    "kia:stonic":                 (4_500_000,  6_000_000),
    "kia:sportage":               (5_500_000,  10_000_000),
    "kia:sorento":                (7_500_000,  11_000_000),
    "kia:carnival":               (9_000_000,  18_000_000),

    # ── Daihatsu ────────────────────────────────────────────────────────────
    "daihatsu:cuore":             (600_000,    1_600_000),
    "daihatsu:mira":              (1_200_000,  3_800_000),
    "daihatsu:move":              (1_200_000,  3_500_000),
    "daihatsu:tanto":             (1_500_000,  4_000_000),
    "daihatsu:cast":              (2_000_000,  3_500_000),
    "daihatsu:hijet":             (1_000_000,  2_500_000),
    "daihatsu:rocky":             (5_000_000,  7_500_000),
    "daihatsu:terios":            (2_500_000,  6_000_000),

    # ── Nissan ──────────────────────────────────────────────────────────────
    "nissan:dayz":                (1_500_000,  3_500_000),
    "nissan:roox":                (1_500_000,  3_800_000),
    "nissan:note":                (3_500_000,  6_500_000),
    "nissan:juke":                (3_500_000,  8_000_000),
    "nissan:x-trail":             (5_000_000,  14_000_000),
    "nissan:patrol":              (20_000_000, 55_000_000),

    # ── Mitsubishi ──────────────────────────────────────────────────────────
    "mitsubishi:mirage":          (2_000_000,  4_500_000),
    "mitsubishi:asx":             (3_500_000,  8_000_000),
    "mitsubishi:outlander":       (5_000_000,  14_000_000),
    "mitsubishi:pajero":          (5_000_000,  16_000_000),
    "mitsubishi:pajero sport":    (8_000_000,  18_000_000),

    # ── Subaru ──────────────────────────────────────────────────────────────
    "subaru:impreza":             (2_500_000,  6_000_000),
    "subaru:xv":                  (4_000_000,  7_500_000),
    "subaru:forester":            (4_500_000,  9_000_000),
    "subaru:brz":                 (4_500_000,  10_000_000),

    # ── Mazda ───────────────────────────────────────────────────────────────
    "mazda:demio":                (2_500_000,  4_500_000),
    "mazda:mazda3":               (3_000_000,  7_000_000),
    "mazda:rx-8":                 (1_500_000,  4_000_000),
    "mazda:cx-3":                 (4_000_000,  7_000_000),
    "mazda:cx-5":                 (5_500_000,  9_500_000),

    # ── Chinese & New Entrants ───────────────────────────────────────────────
    "mg:zs":                      (4_500_000,  6_500_000),
    "mg:zs ev":                   (7_000_000,  11_000_000),
    "mg:hs":                      (6_000_000,  8_500_000),
    "mg:rx5":                     (4_500_000,  9_000_000),
    "mg:cyberster":               (15_000_000, 25_000_000),
    "changan:alsvin":             (3_200_000,  4_800_000),
    "changan:karvaan":            (1_500_000,  3_000_000),
    "changan:oshan x7":           (7_000_000,  9_500_000),
    "changan:uni-t":              (8_000_000,  11_000_000),
    "changan:deepal s07":         (13_000_000, 18_000_000),
    "changan:deepal l07":         (13_000_000, 18_000_000),
    "haval:jolion":               (7_000_000,  9_000_000),
    "haval:h6":                   (8_900_000,  10_000_000),
    "haval:h6 hev":               (11_400_000, 14_000_000),
    "chery:tiggo 4 pro":          (5_500_000,  7_500_000),
    "chery:tiggo 8 pro":          (8_000_000,  10_500_000),
    "proton:saga":                (2_500_000,  3_800_000),
    "proton:x70":                 (6_000_000,  8_000_000),
    "byd:dolphin":                (9_000_000,  12_000_000),
    "byd:atto 3":                 (11_000_000, 15_000_000),
    "byd:seal":                   (16_000_000, 22_000_000),
    "gwm:ora 03":                 (8_000_000,  11_000_000),
    "gwm:tank 500":               (35_000_000, 45_000_000),

    # ── European & Luxury ────────────────────────────────────────────────────
    "bmw:3 series":               (6_000_000,  25_000_000),
    "bmw:5 series":               (8_000_000,  35_000_000),
    "bmw:7 series":               (15_000_000, 60_000_000),
    "bmw:x1":                     (7_000_000,  20_000_000),
    "bmw:x3":                     (9_000_000,  30_000_000),
    "bmw:x5":                     (12_000_000, 50_000_000),
    "bmw:x7":                     (40_000_000, 80_000_000),
    "bmw:i4":                     (25_000_000, 35_000_000),
    "bmw:i7":                     (60_000_000, 90_000_000),
    "bmw:ix":                     (35_000_000, 55_000_000),
    "mercedes-benz:cla":          (7_000_000,  18_000_000),
    "mercedes-benz:c-class":      (6_000_000,  30_000_000),
    "mercedes-benz:e-class":      (8_000_000,  45_000_000),
    "mercedes-benz:s-class":      (15_000_000, 80_000_000),
    "mercedes-benz:gla":          (7_500_000,  20_000_000),
    "mercedes-benz:glc":          (12_000_000, 35_000_000),
    "mercedes-benz:gle":          (15_000_000, 50_000_000),
    "mercedes-benz:gls":          (30_000_000, 75_000_000),
    "audi:a3":                    (5_000_000,  12_000_000),
    "audi:a4":                    (6_500_000,  20_000_000),
    "audi:a5":                    (8_000_000,  25_000_000),
    "audi:a6":                    (9_000_000,  35_000_000),
    "audi:a7":                    (15_000_000, 45_000_000),
    "audi:q2":                    (6_500_000,  11_000_000),
    "audi:q3":                    (7_500_000,  15_000_000),
    "audi:q5":                    (10_000_000, 25_000_000),
    "audi:q7":                    (15_000_000, 45_000_000),
    "audi:q8":                    (30_000_000, 60_000_000),
    "audi:e-tron":                (18_000_000, 35_000_000),
    "audi:e-tron gt":             (35_000_000, 60_000_000),
    "porsche:macan":              (20_000_000, 45_000_000),
    "porsche:cayenne":            (25_000_000, 70_000_000),
    "porsche:panamera":           (25_000_000, 60_000_000),
    "porsche:taycan":             (40_000_000, 85_000_000),
    "land rover:evoque":          (9_000_000,  25_000_000),
    "land rover:discovery":       (15_000_000, 50_000_000),
    "land rover:velar":           (20_000_000, 45_000_000),
    "land rover:range rover sport":(20_000_000, 75_000_000),
    "land rover:defender":        (35_000_000, 85_000_000),
    "land rover:range rover":     (25_000_000, 95_000_000),
    "land rover:vogue":           (25_000_000, 95_000_000),
    "lexus:ct200h":               (4_000_000,  7_500_000),
    "lexus:is":                   (5_000_000,  15_000_000),
    "lexus:es":                   (8_000_000,  25_000_000),
    "lexus:rx":                   (10_000_000, 35_000_000),
    "lexus:nx":                   (12_000_000, 28_000_000),
    "lexus:lx570":                (30_000_000, 75_000_000),
    "lexus:lx":                   (30_000_000, 75_000_000),
    "lexus:lx600":                (90_000_000, 140_000_000),
}

# Chinese makes — only included when user explicitly requests Chinese brands
_CHINESE_MAKES = {"mg", "changan", "chery", "haval", "proton", "baic", "geely", "byd", "gwm"}


# ---------------------------------------------------------------------------
# CANONICAL MODEL NAME MAP
# Normalizes LLM output to scraper-safe names for runner.py URL building.
# ---------------------------------------------------------------------------

_CANONICAL_MODEL_MAP: dict[str, str] = {
    # Toyota
    "land cruiser prado":           "Prado",
    "toyota land cruiser prado":    "Prado",
    "lc prado":                     "Prado",
    "lc300":                        "Land Cruiser",
    "lc200":                        "Land Cruiser",
    "v8":                           "Land Cruiser",
    "revo hilux":                   "Hilux",
    "hilux revo":                   "Hilux",
    "corolla altis":                "Corolla",
    "corolla grande":               "Corolla",
    "corolla xli":                  "Corolla",
    "corolla gli":                  "Corolla",
    "markx":                        "Mark X",
    "yaris cross":                  "Yaris Cross",
    # Honda
    "civic fc":                     "Civic",
    "civic oriel":                  "Civic",
    "civic vti":                    "Civic",
    "city aspire":                  "City",
    "city prosmatec":               "City",
    "br-v":                         "BR-V",
    "brv":                          "BR-V",
    "hr-v":                         "HR-V",
    "hrv":                          "HR-V",
    "cr-v":                         "CR-V",
    "crv":                          "CR-V",
    "n-box":                        "N-Box",
    "nbox":                         "N-Box",
    "n-wgn":                        "N-WGN",
    "nwgn":                         "N-WGN",
    "step wgn":                     "StepWGN",
    # Suzuki
    "wagon r":                      "Wagon R",
    "wagonr":                       "Wagon R",
    "alto 660":                     "Alto 660cc",
    # Nissan
    "x-trail":                      "X-Trail",
    "xtrail":                       "X-Trail",
    "note e-power":                 "Note e-Power",
    # Mazda
    "rx-8":                         "RX-8",
    "rx8":                          "RX-8",
    "cx-5":                         "CX-5",
    "cx5":                          "CX-5",
    "mazda2":                       "Demio",
    "demio/mazda2":                 "Demio",
    # Chinese
    "zs ev":                        "ZS EV",
    "oshan x7":                     "Oshan X7",
    "uni-t":                        "Uni-T",
    "deepal s07":                   "Deepal S07",
    "deepal l07":                   "Deepal L07",
    "h6 hev":                       "H6 HEV",
    "tiggo 4 pro":                  "Tiggo 4 Pro",
    "tiggo 8 pro":                  "Tiggo 8 Pro",
    "atto 3":                       "Atto 3",
    "tank 500":                     "Tank 500",
    "ora 03":                       "Ora 03",
    # European / Luxury
    "3 series":                     "3 Series",
    "5 series":                     "5 Series",
    "7 series":                     "7 Series",
    "c-class":                      "C-Class",
    "e-class":                      "E-Class",
    "s-class":                      "S-Class",
    "range rover":                  "Range Rover",
    "range rover sport":            "Range Rover Sport",
    "vogue":                        "Vogue",
    "evoque":                       "Evoque",
    "velar":                        "Velar",
    "e-tron":                       "e-tron",
    "e-tron gt":                    "e-tron GT",
    "lx 570":                       "LX570",
    "lx 600":                       "LX600",
    "pajero sport":                 "Pajero Sport",
}


# ---------------------------------------------------------------------------
# BUDGET-ELIGIBLE CAR LIST
# The only Python filtering that happens before the LLM sees cars.
# No tiers, no style filter, no scoring. Just: does this budget reach this car?
# ---------------------------------------------------------------------------

def get_budget_eligible_cars(
    max_budget: int,
    min_budget: int,
    allow_chinese: bool,
    excluded_models: list[str] | None = None,
) -> str:
    """
    Returns a formatted list of every car in PAKISTAN_MARKET_PRICES whose
    price range overlaps the user's budget window [min_budget, max_budget].

    Overlap condition (both must hold):
      a. max_budget >= lo * 0.80  — user can afford at least the lower end
      b. hi >= min_budget * 0.80  — car isn't far too cheap for the budget

    The LLM receives this full list and decides which 1-3 to recommend
    based on body style, use case, transmission, origin, and any other
    criteria in the user's query. Python does not pre-filter by those.

    If no budget is stated (both 0), returns the entire price map so the
    LLM can still make sensible picks.
    """
    excluded_lower = {m.lower() for m in (excluded_models or [])}
    eligible: list[tuple[str, str, int, int]] = []   # (display, key, lo, hi)

    for key, (lo, hi) in PAKISTAN_MARKET_PRICES.items():
        make, model = key.split(":", 1)

        # Chinese brand gate
        if make in _CHINESE_MAKES and not allow_chinese:
            continue

        # Exclusion gate (for fallback / extend calls)
        display = f"{make} {model}".lower()
        if any(ex in display for ex in excluded_lower):
            continue

        # Budget overlap gates
        if max_budget > 0 and max_budget < lo * 0.80:
            continue   # can't reach this car's floor price
        if min_budget > 0 and hi < min_budget * 0.80:
            continue   # car's ceiling is way below the budget floor

        eligible.append((f"{make.title()} {model.title()}", key, lo, hi))

    if not eligible:
        return "No cars found matching this budget. The LLM should return an empty array []."

    lines = [
        f"  {display}: PKR {lo:,} – {hi:,}"
        for display, key, lo, hi in eligible
    ]

    budget_note = (
        f"PKR {min_budget:,} – {max_budget:,}" if max_budget > 0 else "no budget limit"
    )

    return (
        f"CARS AVAILABLE IN THIS BUDGET ({budget_note}) — {len(eligible)} options:\n"
        + "\n".join(lines)
        + "\n\n"
        "These cars are pre-verified to overlap the buyer's budget window.\n"
        "You must pick ONLY from this list.\n"
    )


# ---------------------------------------------------------------------------
# POST-SELECTION VALIDATOR
# Safety net: catches picks outside the budget window in case the LLM
# ignores the list. Unknown models (not in price map) always pass through.
# ---------------------------------------------------------------------------

def _validate_targets_against_market(targets: list, constraints: dict) -> list:
    max_budget    = constraints.get("max_budget", 0)
    min_budget    = constraints.get("min_budget", 0)
    allow_chinese = constraints.get("allow_chinese", False)

    valid = []
    for t in targets:
        make_lower  = t.make.lower().strip()
        model_lower = t.model.lower().strip()

        if make_lower in _CHINESE_MAKES and not allow_chinese:
            print(f"[Validator] Dropping {t.make} {t.model} — Chinese brand not requested")
            continue

        if max_budget > 0:
            key = f"{make_lower}:{model_lower}"
            if key in PAKISTAN_MARKET_PRICES:
                lo, hi = PAKISTAN_MARKET_PRICES[key]
                if max_budget < lo * 0.85:
                    print(
                        f"[Validator] Dropping {t.make} {t.model} — "
                        f"floor PKR {lo:,} unreachable at budget PKR {max_budget:,}"
                    )
                    continue
                if min_budget > 0 and hi < min_budget * 0.80:
                    print(
                        f"[Validator] Dropping {t.make} {t.model} — "
                        f"ceiling PKR {hi:,} below budget floor PKR {min_budget:,}"
                    )
                    continue

        valid.append(t)

    if not valid and targets:
        print("[Validator] All targets dropped — returning first original as safety fallback.")
        return [targets[0]]

    return valid


# ---------------------------------------------------------------------------
# PHASE 1: INTENT EXTRACTOR & CONSTRAINT RESOLVER
# ---------------------------------------------------------------------------

class UserIntent(BaseModel):
    """
    Raw signals only. LLM extracts, Python decides nothing here.
    resolve_constraints() does the only math: budget floor + Chinese gate.
    """
    max_budget:        Optional[int]                                                                 = None
    body_style:        Optional[Literal["SUV", "Sedan", "Hatchback", "Pickup", "Crossover", "Van"]] = None
    transmission:      Optional[Literal["Automatic", "Manual"]]                                     = None
    use_case:          Optional[str]                                                                 = None
    origin_pref:       Optional[Literal["JDM", "Local", "European", "Chinese"]]                     = None
    is_luxury_request: bool                                                                          = False
    required_features: list[str]                                                                     = Field(default_factory=list)


async def extract_intent(user_prompt: str) -> UserIntent:
    """
    Phase 1 LLM call — pure signal extraction, zero decisions.
    """
    prompt = (
        f"Extract the user's car search intent from this query: '{user_prompt}'\n\n"
        "Rules:\n"
        "- Convert Pakistani currency precisely:\n"
        "  '1 crore' → 10000000,  '5 crore'  → 50000000,  '10 crore' → 100000000\n"
        "  '20 lacs' → 2000000,   '50 lacs'  → 5000000,   '80 lacs'  → 8000000\n"
        "  Always convert — never leave currency as a text string.\n"
        "- use_case: brief phrase — 'family daily', 'city commute', 'offroad adventure',\n"
        "  'sports driving', 'ride sharing', 'school run'.\n"
        "- is_luxury_request: true ONLY for explicit words: 'luxury', 'premium', 'aura',\n"
        "  'VIP', 'boss car', 'status symbol', 'high-end'.\n"
        "- required_features: only features EXPLICITLY mentioned by the user.\n"
        "  e.g. 'sunroof', 'push start', 'leather seats', 'back camera'. Never infer.\n"
        "- body_style: 'sedan car' or just 'car' → Sedan. 'SUV' or '4x4' → SUV.\n"
        "  'small car' or 'hatchback' → Hatchback. 'pickup' or 'truck' → Pickup.\n"
        "- If a field is not clearly stated, leave it null/empty — do not guess."
    )
    response = await client.aio.models.generate_content(
        model=_GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=UserIntent,
            temperature=0.0,
        ),
    )
    return UserIntent.model_validate_json(response.text)


def resolve_constraints(intent: UserIntent) -> dict:
    """
    Phase 1 Python gate — only two things happen here:
      1. Budget floor (70% of max, 50% for very large budgets to account
         for wide depreciation spread on luxury imports)
      2. Chinese brand flag

    No tier. No min_year. No style rules. The LLM handles all of that.
    """
    max_budget = intent.max_budget or 0
    min_budget = 0

    if max_budget > 0:
        # Wider floor for large budgets: a 5-crore buyer who sees a 3-crore
        # Patrol isn't wasting their time — it's negotiation territory.
        floor_pct = 0.50 if max_budget >= 30_000_000 else 0.70
        min_budget = int(max_budget * floor_pct)

    return {
        "min_budget":        min_budget,
        "max_budget":        max_budget,
        "min_year":          0,
        "allow_chinese":     intent.origin_pref == "Chinese",
        "body_style":        intent.body_style,
        "transmission":      intent.transmission,
        "use_case":          intent.use_case,
        "origin_pref":       intent.origin_pref,
        "is_luxury_request": intent.is_luxury_request,
        "required_features": intent.required_features,
    }


# ---------------------------------------------------------------------------
# PHASE 2: CAR SELECTOR, VALIDATOR & CANONICALIZER
# ---------------------------------------------------------------------------

class CarTargetRaw(BaseModel):
    make:              str
    model:             str
    trim:              str
    rationale:         str
    required_features: list[str] = Field(default_factory=list)


async def select_car_targets(constraints: dict) -> list[CarTargetRaw]:
    """
    Phase 2 LLM call.

    The LLM receives:
      - The full list of budget-eligible cars (Python filtered by price only)
      - The buyer's full profile (body style, use case, transmission, etc.)

    The LLM's job:
      - Apply body style, use case, transmission, origin preferences
      - Pick the 1-3 best matches
      - Explain why each pick fits the buyer
      - Provide make diversity across picks

    Python does NOT pre-filter by body style or use case here.
    The LLM knows what a crossover is, what family daily means, what JDM
    trims exist. Let it use that knowledge.
    """
    max_budget    = constraints.get("max_budget", 0)
    min_budget    = constraints.get("min_budget", 0)
    allow_chinese = constraints.get("allow_chinese", False)

    eligible_list = get_budget_eligible_cars(
        max_budget=max_budget,
        min_budget=min_budget,
        allow_chinese=allow_chinese,
    )

    budget_str = (
        f"PKR {min_budget:,} – {max_budget:,}" if max_budget > 0
        else "No budget stated"
    )

    buyer_profile = {
        "budget":            budget_str,
        "body_style":        constraints.get("body_style") or "No preference",
        "transmission":      constraints.get("transmission") or "No preference",
        "use_case":          constraints.get("use_case") or "General",
        "origin_pref":       constraints.get("origin_pref") or "No preference (Japanese/Korean preferred by default)",
        "is_luxury_request": constraints.get("is_luxury_request", False),
        "required_features": constraints.get("required_features", []),
    }

    prompt = (
        f"{eligible_list}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "TASK: You are a Pakistani used car expert. From the list above, pick "
        "the best 1–3 cars for this buyer. Only pick from the list above.\n\n"
        f"BUYER PROFILE:\n{json.dumps(buyer_profile, indent=2)}\n\n"
        "SELECTION RULES:\n"
        "1. BUDGET: The list above is already budget-filtered. Trust it.\n"
        "2. BODY STYLE: If body_style is set, only pick cars of that type.\n"
        "   - Sedan: 4-door enclosed cabin (Corolla, Civic, BMW 3 Series, etc.)\n"
        "   - SUV: larger, higher ride height, typically 7-seat capable\n"
        "   - Hatchback: small car with rear hatch (Alto, Swift, Vitz, etc.)\n"
        "   - Crossover: car-based SUV, softer ride (Vezel, Stonic, C-HR, etc.)\n"
        "   - Pickup: open cargo bed (Hilux only in this market)\n"
        "   - Van: people mover (Hiace, Alphard, Stepwgn, etc.)\n"
        "3. TRANSMISSION: If Automatic requested, exclude manual-only models.\n"
        "4. USE CASE: Match the car to how it will be used:\n"
        "   - Family daily: boot space, reliability, running costs\n"
        "   - City commute: fuel economy, easy parking, tight turning\n"
        "   - Offroad / adventure: 4WD, ground clearance, approach angle\n"
        "   - Sports / performance: engine output, handling, fun factor\n"
        "   - Ride sharing / taxi: reliability, resale, diesel preferred\n"
        "5. LUXURY: If is_luxury_request is true, pick the highest-end options\n"
        "   available in budget — Land Cruiser, Range Rover, BMW, Lexus over\n"
        "   Fortuner or Sportage even if the cheaper car also fits budget.\n"
        "6. ORIGIN: If origin_pref is JDM, specify exact JDM trim\n"
        "   (e.g. trim='G Grade', trim='Turbo RS', trim='RS Advance').\n"
        "   If European, prefer BMW/Audi/Mercedes/Porsche from the list.\n"
        "7. MAKE DIVERSITY: Try to pick from different makes. Avoid returning\n"
        "   all 3 picks from the same brand unless no alternatives exist.\n"
        "8. QUANTITY: Return 1 if only 1 genuinely fits. Never pad to 3.\n"
        "9. TRIM: Leave empty unless a specific trim meaningfully matters.\n"
        "10. RATIONALE: 1 sentence per car — buyer-friendly, says WHY it fits.\n"
        "11. HARD RULE: Never suggest a car not in the list above, regardless\n"
        "    of how well it seems to fit."
    )

    response = await client.aio.models.generate_content(
        model=_GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=list[CarTargetRaw],
            temperature=0.2,
        ),
    )

    try:
        return [CarTargetRaw.model_validate(item) for item in json.loads(response.text)]
    except Exception as e:
        print(f"[Selector] Parse failed: {e}\nRaw: {response.text[:300]}")
        return []


def _deduplicate_and_format_targets(
    raw_targets: list[CarTargetRaw],
    constraints: dict,
) -> list[dict]:
    """
    Phase 2 Python gate — validation, canonicalization, deduplication, 9-key format.
    """
    validated = _validate_targets_against_market(raw_targets, constraints)

    seen:      set[tuple[str, str]] = set()
    formatted: list[dict]           = []

    for raw in validated:
        make_lower  = raw.make.lower().strip()
        model_raw   = raw.model.strip()
        model_lower = model_raw.lower()

        canonical_model = _CANONICAL_MODEL_MAP.get(model_lower, model_raw)

        dedup_key = (make_lower, canonical_model.lower())
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        merged_features = list(
            set(constraints.get("required_features", []) + raw.required_features)
        )

        formatted.append({
            "make":              raw.make.strip(),
            "model":             canonical_model,
            "trim":              raw.trim.strip(),
            "city":              "",   # always empty — recommend_normalizer handles city softly
            "min_budget":        constraints.get("min_budget", 0),
            "max_budget":        constraints.get("max_budget", 0),
            "min_year":          constraints.get("min_year", 0),
            "required_features": merged_features,
            "rationale":         raw.rationale.strip(),
        })

    return formatted


# ---------------------------------------------------------------------------
# PHASE 3: FALLBACK & EXTENSION PIPELINES
# ---------------------------------------------------------------------------

async def get_fallback_recommendations(
    constraints: dict,
    excluded_models: list[str],
) -> list[dict]:
    """
    Phase 3 — fires on NORMALIZER_ZERO. Returns exactly 1 replacement.
    Excluded models are removed from the eligible list before the LLM sees it.
    """
    max_budget    = constraints.get("max_budget", 0)
    min_budget    = constraints.get("min_budget", 0)
    allow_chinese = constraints.get("allow_chinese", False)

    eligible_list = get_budget_eligible_cars(
        max_budget=max_budget,
        min_budget=min_budget,
        allow_chinese=allow_chinese,
        excluded_models=excluded_models,
    )

    budget_str = (
        f"PKR {min_budget:,} – {max_budget:,}" if max_budget > 0
        else "No budget stated"
    )

    prompt = (
        f"{eligible_list}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "TASK: Pick exactly 1 replacement car. Previous picks returned zero listings.\n\n"
        f"CONSTRAINTS:\n"
        f"  Budget: {budget_str}\n"
        f"  Body style: {constraints.get('body_style') or 'No preference'}\n"
        f"  Transmission: {constraints.get('transmission') or 'No preference'}\n"
        f"  Use case: {constraints.get('use_case') or 'General'}\n\n"
        f"ALREADY TRIED (already excluded from list above): {json.dumps(excluded_models)}\n\n"
        "RULES:\n"
        "- Return exactly 1 target. Never more than 1.\n"
        "- Pick only from the list above.\n"
        "- Must match body_style and transmission if set.\n"
        "- If the list is empty or no valid option, return []."
    )

    try:
        response = await client.aio.models.generate_content(
            model=_GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=list[CarTargetRaw],
                temperature=0.25,
            ),
        )
        raw_list = json.loads(response.text)

        if len(raw_list) > 1:
            raw_list = [raw_list[0]]

        valid_targets = [CarTargetRaw.model_validate(item) for item in raw_list]
        valid_targets = _validate_targets_against_market(valid_targets, constraints)
        return _deduplicate_and_format_targets(valid_targets, constraints)

    except Exception as e:
        print(f"[FallbackMapper] Failed: {e}")
        traceback.print_exc()
        return []


async def get_extended_recommendations(
    original_constraints: dict,
    excluded_models: list[str],
) -> list[dict]:
    """
    Phase 3 — powers the 'Show More Options' button.
    Returns 1–3 alternatives. Excluded models removed from list before LLM sees it.
    """
    max_budget    = original_constraints.get("max_budget", 0)
    min_budget    = original_constraints.get("min_budget", 0)
    allow_chinese = original_constraints.get("allow_chinese", False)

    eligible_list = get_budget_eligible_cars(
        max_budget=max_budget,
        min_budget=min_budget,
        allow_chinese=allow_chinese,
        excluded_models=excluded_models,
    )

    budget_str = (
        f"PKR {min_budget:,} – {max_budget:,}" if max_budget > 0
        else "No budget stated"
    )

    prompt = (
        f"{eligible_list}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "TASK: Pick 1–3 alternative 'Show More' options from the list above.\n\n"
        f"CONSTRAINTS:\n"
        f"  Budget: {budget_str}\n"
        f"  Body style: {original_constraints.get('body_style') or 'No preference'}\n"
        f"  Transmission: {original_constraints.get('transmission') or 'No preference'}\n"
        f"  Use case: {original_constraints.get('use_case') or 'General'}\n\n"
        f"ALREADY SHOWN (already excluded from list above): {json.dumps(excluded_models)}\n\n"
        "RULES:\n"
        "- Pick only from the list above.\n"
        "- Match body_style strictly — no body style leakage.\n"
        "- Pick from different makes than those already shown.\n"
        "- Quality over quantity — return 1 if only 1 good option exists.\n"
        "- If no valid alternatives remain, return []."
    )

    try:
        response = await client.aio.models.generate_content(
            model=_GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=list[CarTargetRaw],
                temperature=0.3,
            ),
        )
        raw_list = json.loads(response.text)
        valid_targets = [CarTargetRaw.model_validate(item) for item in raw_list]
        valid_targets = _validate_targets_against_market(valid_targets, original_constraints)
        return _deduplicate_and_format_targets(valid_targets, original_constraints)

    except Exception as e:
        print(f"[ExtendedMapper] Failed: {e}")
        traceback.print_exc()
        return []