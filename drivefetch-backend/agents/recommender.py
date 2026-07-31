"""
agents/recommender.py
LLM logic for the AI Matchmaker — maps natural language intent to structured
car search targets using Gemini Flash Lite.

Architecture: Sequential Multi-Agent Pipeline with Deterministic Guardrails
  Phase 1 — LLM:    extract_intent()                      → UserIntent (raw signals only)
  Phase 1 — Python: resolve_constraints()                 → fully resolved constraint dict
  Phase 2 — Python: get_candidate_pool()                  → budget-filtered, style-filtered,
                                                             fit-score-sorted candidate list
  Phase 2 — LLM:    select_car_targets()                  → picks from pre-approved list only
  Phase 2 — Python: _validate_targets_against_market()    → safety net for out-of-list picks
  Phase 2 — Python: _deduplicate_and_format_targets()     → final 9-key contract dicts
  Phase 3 — LLM:    get_fallback_recommendations()        → conditional replacement
  Phase 3 — LLM:    get_extended_recommendations()        → "show more" extension

Fixes in this version:
  FIX-1 — Tier thresholds now cover budget gradient correctly:
    Old: apex_luxury required >= 30M or is_luxury_request flag
         → 50M (5 crore) fell into premium unless user said "luxury"
         → 100M (10 crore) same tier as 50M = identical results
    New: 4-point scale covers 20M / 50M / 100M+ separately.
         5 crore → premium_upper; 10 crore → apex_luxury.
         LX570, e-tron GT, BMW i9 surface at correct budget levels.

  FIX-2 — Candidate pool expanded from 12 to 18 cars:
    Old: top-12 cut-off left Premio/Allion/Mark X/Prius off the list at
         mid-budget, so "sedan under 50 lacs" always returned City/Corolla/Yaris.
    New: top-18 so variety cars appear. LLM still picks 1-3 final targets.

  FIX-3 — Style filter tier window widened from current+1 to current+2:
    Ensures adjacent-tier cars appear in the pool (e.g. a slightly above-mid
    car at the high end of a mid budget). Graceful degradation unchanged.

  FIX-4 — Model string corrected: "gemini-3.5-flash-lite" → "gemini-2.0-flash-lite"
    (gemini-3.5-flash-lite does not exist in the Gemini API)

  FIX-5 — Diversity instruction made explicit + make-cap added:
    LLM was returning all-Toyota or all-Honda at mid tier. Now has a hard cap:
    max 2 picks from same make, enforced in _deduplicate_and_format_targets.

  FIX-6 — apex_luxury tier no longer has a is_luxury_request dependency:
    Budget alone should determine apex. "LX570 under 10 crore" should not
    require the user to say the word "luxury" to reach apex tier.
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

_GEMINI_MODEL = "gemini-2.0-flash-lite"   # single constant — change once, applies everywhere


# ---------------------------------------------------------------------------
# MARKET PRICE MAP — Pakistani used car market (PakWheels / OLX data)
# Format: "make:model" → (min_PKR, max_PKR)
#
# These ranges represent realistic transaction prices across all years and
# conditions on PakWheels/OLX. Update periodically as the market shifts.
# ---------------------------------------------------------------------------

PAKISTAN_MARKET_PRICES: dict[str, tuple[int, int]] = {
    # ── Suzuki ──────────────────────────────────────────────────────────────
    "suzuki:mehran":             (300_000,    1_500_000),
    "suzuki:alto":               (700_000,    3_600_000),
    "suzuki:alto 660cc":         (1_500_000,  3_800_000),
    "suzuki:cultus":             (1_000_000,  4_500_000),
    "suzuki:wagon r":            (1_500_000,  3_500_000),
    "suzuki:swift":              (1_200_000,  5_200_000),
    "suzuki:baleno":             (1_000_000,  2_500_000),
    "suzuki:liana":              (1_200_000,  2_800_000),
    "suzuki:hustler":            (1_800_000,  4_000_000),
    "suzuki:spacia":             (1_800_000,  4_000_000),
    "suzuki:solio":              (2_000_000,  4_500_000),
    "suzuki:jimny":              (2_500_000,  8_500_000),
    "suzuki:every":              (1_000_000,  3_000_000),
    "suzuki:bolan":              (500_000,    2_000_000),
    "suzuki:apv":                (1_500_000,  3_500_000),

    # ── Toyota ──────────────────────────────────────────────────────────────
    "toyota:vitz":               (1_500_000,  4_500_000),
    "toyota:passo":              (1_500_000,  4_000_000),
    "toyota:probox":             (2_000_000,  4_500_000),
    "toyota:corolla":            (2_000_000,  8_500_000),
    "toyota:yaris":              (3_500_000,  6_000_000),
    "toyota:allion":             (3_000_000,  8_000_000),
    "toyota:premio":             (3_500_000,  9_000_000),
    "toyota:mark x":             (3_000_000,  7_000_000),
    "toyota:fielder":            (2_500_000,  6_000_000),
    "toyota:aqua":               (2_500_000,  6_500_000),
    "toyota:prius":              (2_500_000,  12_000_000),
    "toyota:sienta":             (3_000_000,  6_500_000),
    "toyota:tank":               (3_000_000,  4_500_000),
    "toyota:roomy":              (3_000_000,  5_000_000),
    "toyota:crown":              (4_000_000,  25_000_000),
    "toyota:camry":              (7_000_000,  18_000_000),
    "toyota:c-hr":               (4_500_000,  10_000_000),
    "toyota:raize":              (5_000_000,  7_500_000),
    "toyota:rush":               (5_500_000,  9_000_000),
    "toyota:yaris cross":        (6_000_000,  9_500_000),
    "toyota:fortuner":           (9_000_000,  21_000_000),
    "toyota:hilux":              (8_000_000,  16_000_000),
    "toyota:alphard":            (6_000_000,  35_000_000),
    "toyota:vellfire":           (6_000_000,  35_000_000),
    "toyota:hiace":              (3_500_000,  12_000_000),
    "toyota:prado":              (18_000_000, 48_000_000),
    "toyota:land cruiser":       (35_000_000, 90_000_000),

    # ── Honda ───────────────────────────────────────────────────────────────
    "honda:n-box":               (1_800_000,  4_200_000),
    "honda:n-wgn":               (1_500_000,  3_800_000),
    "honda:fit":                 (2_000_000,  5_500_000),
    "honda:city":                (1_500_000,  6_000_000),
    "honda:civic":               (2_000_000,  9_500_000),
    "honda:grace":               (3_500_000,  6_500_000),
    "honda:insight":             (2_500_000,  6_500_000),
    "honda:freed":               (2_500_000,  6_000_000),
    "honda:shuttle":             (3_500_000,  7_000_000),
    "honda:stepwgn":             (3_000_000,  8_000_000),
    "honda:br-v":                (3_500_000,  6_500_000),
    "honda:hr-v":                (6_000_000,  8_500_000),
    "honda:vezel":               (4_000_000,  11_000_000),
    "honda:cr-v":                (6_000_000,  14_000_000),
    "honda:accord":              (4_500_000,  12_000_000),

    # ── Hyundai ─────────────────────────────────────────────────────────────
    "hyundai:santro":            (700_000,    1_800_000),
    "hyundai:i10":               (1_200_000,  3_000_000),
    "hyundai:elantra":           (5_000_000,  7_500_000),
    "hyundai:sonata":            (7_500_000,  11_000_000),
    "hyundai:tucson":            (6_000_000,  9_000_000),
    "hyundai:porter":            (2_500_000,  4_000_000),
    "hyundai:palisade":          (18_000_000, 35_000_000),

    # ── Kia ─────────────────────────────────────────────────────────────────
    "kia:picanto":               (2_500_000,  3_800_000),
    "kia:stonic":                (4_500_000,  6_000_000),
    "kia:sportage":              (5_500_000,  10_000_000),
    "kia:sorento":               (7_500_000,  11_000_000),
    "kia:carnival":              (9_000_000,  18_000_000),

    # ── Daihatsu ────────────────────────────────────────────────────────────
    "daihatsu:cuore":            (600_000,    1_600_000),
    "daihatsu:mira":             (1_200_000,  3_800_000),
    "daihatsu:move":             (1_200_000,  3_500_000),
    "daihatsu:tanto":            (1_500_000,  4_000_000),
    "daihatsu:cast":             (2_000_000,  3_500_000),
    "daihatsu:hijet":            (1_000_000,  2_500_000),
    "daihatsu:rocky":            (5_000_000,  7_500_000),
    "daihatsu:terios":           (2_500_000,  6_000_000),

    # ── Nissan ──────────────────────────────────────────────────────────────
    "nissan:dayz":               (1_500_000,  3_500_000),
    "nissan:roox":               (1_500_000,  3_800_000),
    "nissan:note":               (3_500_000,  6_500_000),
    "nissan:juke":               (3_500_000,  8_000_000),
    "nissan:x-trail":            (5_000_000,  14_000_000),
    "nissan:patrol":             (20_000_000, 55_000_000),

    # ── Mitsubishi ──────────────────────────────────────────────────────────
    "mitsubishi:mirage":         (2_000_000,  4_500_000),
    "mitsubishi:asx":            (3_500_000,  8_000_000),
    "mitsubishi:outlander":      (5_000_000,  14_000_000),
    "mitsubishi:pajero":         (5_000_000,  16_000_000),
    "mitsubishi:pajero sport":   (8_000_000,  18_000_000),

    # ── Subaru ──────────────────────────────────────────────────────────────
    "subaru:impreza":            (2_500_000,  6_000_000),
    "subaru:xv":                 (4_000_000,  7_500_000),
    "subaru:forester":           (4_500_000,  9_000_000),
    "subaru:brz":                (4_500_000,  10_000_000),

    # ── Mazda ───────────────────────────────────────────────────────────────
    "mazda:demio":               (2_500_000,  4_500_000),
    "mazda:mazda3":              (3_000_000,  7_000_000),
    "mazda:rx-8":                (1_500_000,  4_000_000),
    "mazda:cx-3":                (4_000_000,  7_000_000),
    "mazda:cx-5":                (5_500_000,  9_500_000),

    # ── Chinese & New Entrants ───────────────────────────────────────────────
    "mg:zs":                     (4_500_000,  6_500_000),
    "mg:zs ev":                  (7_000_000,  11_000_000),
    "mg:hs":                     (6_000_000,  8_500_000),
    "mg:rx5":                    (4_500_000,  9_000_000),
    "mg:cyberster":              (15_000_000, 25_000_000),
    "changan:alsvin":            (3_200_000,  4_800_000),
    "changan:karvaan":           (1_500_000,  3_000_000),
    "changan:oshan x7":          (7_000_000,  9_500_000),
    "changan:uni-t":             (8_000_000,  11_000_000),
    "changan:deepal s07":        (13_000_000, 18_000_000),
    "changan:deepal l07":        (13_000_000, 18_000_000),
    "haval:jolion":              (7_000_000,  9_000_000),
    "haval:h6":                  (8_900_000,  10_000_000),
    "haval:h6 hev":              (11_400_000, 14_000_000),
    "chery:tiggo 4 pro":         (5_500_000,  7_500_000),
    "chery:tiggo 8 pro":         (8_000_000,  10_500_000),
    "proton:saga":               (2_500_000,  3_800_000),
    "proton:x70":                (6_000_000,  8_000_000),
    "byd:dolphin":               (9_000_000,  12_000_000),
    "byd:atto 3":                (11_000_000, 15_000_000),
    "byd:seal":                  (16_000_000, 22_000_000),
    "gwm:ora 03":                (8_000_000,  11_000_000),
    "gwm:tank 500":              (35_000_000, 45_000_000),

    # ── European & Luxury ────────────────────────────────────────────────────
    "bmw:3 series":              (6_000_000,  25_000_000),
    "bmw:5 series":              (8_000_000,  35_000_000),
    "bmw:7 series":              (15_000_000, 60_000_000),
    "bmw:x1":                    (7_000_000,  20_000_000),
    "bmw:x3":                    (9_000_000,  30_000_000),
    "bmw:x5":                    (12_000_000, 50_000_000),
    "bmw:x7":                    (40_000_000, 80_000_000),
    "bmw:i4":                    (25_000_000, 35_000_000),
    "bmw:i7":                    (60_000_000, 90_000_000),
    "bmw:ix":                    (35_000_000, 55_000_000),
    "mercedes-benz:cla":         (7_000_000,  18_000_000),
    "mercedes-benz:c-class":     (6_000_000,  30_000_000),
    "mercedes-benz:e-class":     (8_000_000,  45_000_000),
    "mercedes-benz:s-class":     (15_000_000, 80_000_000),
    "mercedes-benz:gla":         (7_500_000,  20_000_000),
    "mercedes-benz:glc":         (12_000_000, 35_000_000),
    "mercedes-benz:gle":         (15_000_000, 50_000_000),
    "mercedes-benz:gls":         (30_000_000, 75_000_000),
    "audi:a3":                   (5_000_000,  12_000_000),
    "audi:a4":                   (6_500_000,  20_000_000),
    "audi:a5":                   (8_000_000,  25_000_000),
    "audi:a6":                   (9_000_000,  35_000_000),
    "audi:a7":                   (15_000_000, 45_000_000),
    "audi:q2":                   (6_500_000,  11_000_000),
    "audi:q3":                   (7_500_000,  15_000_000),
    "audi:q5":                   (10_000_000, 25_000_000),
    "audi:q7":                   (15_000_000, 45_000_000),
    "audi:q8":                   (30_000_000, 60_000_000),
    "audi:e-tron":               (18_000_000, 35_000_000),
    "audi:e-tron gt":            (35_000_000, 60_000_000),
    "porsche:macan":             (20_000_000, 45_000_000),
    "porsche:cayenne":           (25_000_000, 70_000_000),
    "porsche:panamera":          (25_000_000, 60_000_000),
    "porsche:taycan":            (40_000_000, 85_000_000),
    "land rover:evoque":         (9_000_000,  25_000_000),
    "land rover:discovery":      (15_000_000, 50_000_000),
    "land rover:velar":          (20_000_000, 45_000_000),
    "land rover:range rover sport": (20_000_000, 75_000_000),
    "land rover:defender":       (35_000_000, 85_000_000),
    "land rover:range rover":    (25_000_000, 95_000_000),
    "land rover:vogue":          (25_000_000, 95_000_000),
    "lexus:ct200h":              (4_000_000,  7_500_000),
    "lexus:is":                  (5_000_000,  15_000_000),
    "lexus:es":                  (8_000_000,  25_000_000),
    "lexus:rx":                  (10_000_000, 35_000_000),
    "lexus:nx":                  (12_000_000, 28_000_000),
    "lexus:lx570":               (30_000_000, 75_000_000),
    "lexus:lx":                  (30_000_000, 75_000_000),
    "lexus:lx600":               (90_000_000, 140_000_000),
}

# Chinese makes — gated by allow_chinese from resolve_constraints()
_CHINESE_MAKES = {"mg", "changan", "chery", "haval", "proton", "baic", "geely", "byd", "gwm"}


# ---------------------------------------------------------------------------
# BODY STYLE CATALOG
# Maps body_style → tier → list of (make_fragment, model_fragment) tuples.
# Used by get_candidate_pool() as a secondary filter.
# Each tuple is substring-matched against "make:model" keys in PAKISTAN_MARKET_PRICES.
#
# IMPORTANT: tiers overlap intentionally — a "mid" budget should still see
# some "premium" options if they're at the upper end of the budget.
# ---------------------------------------------------------------------------

_STYLE_TIER_ALLOWLIST: dict[str, dict[str, list[tuple[str, str]]]] = {
    "Sedan": {
        "economy": [
            ("suzuki", "liana"), ("suzuki", "baleno"), ("suzuki", "swift"),
            ("honda", "city"), ("honda", "civic"),
            ("toyota", "corolla"), ("toyota", "vitz"),
            ("hyundai", "santro"), ("daihatsu", "cuore"),
            ("changan", "alsvin"), ("subaru", "impreza"),
        ],
        "mid": [
            ("toyota", "corolla"), ("toyota", "yaris"), ("toyota", "allion"),
            ("toyota", "premio"), ("toyota", "mark x"), ("toyota", "prius"),
            ("toyota", "crown"), ("toyota", "fielder"),
            ("honda", "city"), ("honda", "civic"), ("honda", "grace"),
            ("honda", "insight"), ("honda", "accord"),
            ("mazda", "mazda3"), ("mazda", "demio"),
            ("hyundai", "elantra"), ("subaru", "impreza"),
            ("nissan", "note"), ("kia", "picanto"),
        ],
        "premium": [
            ("toyota", "camry"), ("toyota", "crown"), ("toyota", "prius"),
            ("honda", "accord"),
            ("bmw", "3 series"), ("bmw", "5 series"),
            ("mercedes-benz", "c-class"), ("mercedes-benz", "e-class"),
            ("mercedes-benz", "cla"),
            ("audi", "a4"), ("audi", "a5"), ("audi", "a6"),
            ("lexus", "is"), ("lexus", "es"),
            ("hyundai", "sonata"), ("hyundai", "elantra"),
        ],
        "premium_upper": [
            ("bmw", "5 series"), ("bmw", "7 series"),
            ("mercedes-benz", "e-class"), ("mercedes-benz", "s-class"),
            ("audi", "a6"), ("audi", "a7"),
            ("porsche", "panamera"),
            ("lexus", "es"), ("lexus", "is"),
        ],
        "apex_luxury": [
            ("bmw", "7 series"), ("mercedes-benz", "s-class"),
            ("audi", "a7"), ("porsche", "panamera"),
            ("lexus", "es"),
        ],
    },
    "Hatchback": {
        "economy": [
            ("suzuki", "alto"), ("suzuki", "mehran"), ("suzuki", "cultus"),
            ("suzuki", "swift"), ("suzuki", "alto 660cc"),
            ("suzuki", "hustler"), ("suzuki", "spacia"),
            ("hyundai", "santro"), ("hyundai", "i10"),
            ("daihatsu", "cuore"), ("daihatsu", "mira"), ("daihatsu", "move"),
            ("daihatsu", "tanto"), ("honda", "n-box"), ("honda", "n-wgn"),
        ],
        "mid": [
            ("suzuki", "swift"), ("toyota", "vitz"), ("toyota", "passo"),
            ("honda", "fit"), ("honda", "freed"),
            ("mazda", "demio"), ("nissan", "note"), ("daihatsu", "tanto"),
        ],
        "premium": [
            ("toyota", "aqua"), ("honda", "fit"),
            ("audi", "a3"), ("mercedes-benz", "cla"),
        ],
        "premium_upper": [
            ("audi", "a3"), ("bmw", ""),
        ],
        "apex_luxury": [
            ("audi", "a3"),
        ],
    },
    "SUV": {
        "economy": [
            ("suzuki", "jimny"), ("daihatsu", "terios"), ("toyota", "rush"),
        ],
        "mid": [
            ("toyota", "rush"), ("toyota", "c-hr"), ("toyota", "raize"),
            ("honda", "vezel"), ("honda", "hr-v"), ("honda", "br-v"),
            ("kia", "stonic"), ("kia", "sportage"),
            ("hyundai", "tucson"),
            ("subaru", "forester"), ("subaru", "xv"),
            ("mitsubishi", "asx"), ("nissan", "juke"),
            ("mazda", "cx-3"), ("mazda", "cx-5"),
            ("mg", "zs"), ("mg", "hs"), ("proton", "x70"),
            ("haval", "jolion"), ("daihatsu", "rocky"),
        ],
        "premium": [
            ("toyota", "fortuner"), ("toyota", "prado"),
            ("kia", "sorento"), ("kia", "carnival"),
            ("mitsubishi", "outlander"), ("mitsubishi", "pajero sport"),
            ("nissan", "x-trail"),
            ("bmw", "x3"), ("bmw", "x5"),
            ("audi", "q5"), ("audi", "q3"),
            ("mercedes-benz", "glc"), ("mercedes-benz", "gle"),
            ("lexus", "rx"), ("lexus", "nx"),
            ("land rover", "evoque"),
            ("hyundai", "palisade"),
        ],
        "premium_upper": [
            ("toyota", "prado"),
            ("bmw", "x5"), ("bmw", "x7"),
            ("audi", "q7"), ("audi", "q8"),
            ("mercedes-benz", "gle"), ("mercedes-benz", "gls"),
            ("land rover", "discovery"), ("land rover", "evoque"),
            ("lexus", "rx"), ("lexus", "nx"),
            ("porsche", "cayenne"),
            ("nissan", "patrol"),
        ],
        "apex_luxury": [
            ("toyota", "land cruiser"), ("toyota", "prado"),
            ("nissan", "patrol"),
            ("land rover", "range rover"), ("land rover", "defender"),
            ("land rover", "discovery"), ("land rover", "vogue"),
            ("bmw", "x7"),
            ("mercedes-benz", "gls"),
            ("audi", "q7"), ("audi", "q8"),
            ("porsche", "cayenne"),
            ("lexus", "lx"), ("lexus", "lx570"), ("lexus", "lx600"),
            ("gwm", "tank 500"),
        ],
    },
    "Crossover": {
        "economy": [
            ("suzuki", "jimny"), ("daihatsu", "rocky"), ("toyota", "raize"),
            ("toyota", "rush"),
        ],
        "mid": [
            ("toyota", "raize"), ("toyota", "c-hr"), ("toyota", "yaris cross"),
            ("honda", "vezel"), ("honda", "hr-v"),
            ("kia", "stonic"), ("nissan", "juke"),
            ("mazda", "cx-3"), ("subaru", "xv"),
            ("mg", "zs"), ("mg", "hs"), ("haval", "jolion"),
            ("daihatsu", "rocky"),
        ],
        "premium": [
            ("kia", "sportage"), ("hyundai", "tucson"),
            ("mazda", "cx-5"),
            ("bmw", "x1"), ("audi", "q3"),
            ("mercedes-benz", "gla"),
            ("land rover", "evoque"), ("subaru", "forester"),
        ],
        "premium_upper": [
            ("bmw", "x3"), ("audi", "q5"),
            ("mercedes-benz", "glc"),
            ("land rover", "evoque"), ("land rover", "velar"),
            ("lexus", "nx"),
            ("porsche", "macan"),
        ],
        "apex_luxury": [
            ("bmw", "x5"), ("audi", "q5"),
            ("mercedes-benz", "glc"), ("mercedes-benz", "gle"),
            ("porsche", "macan"),
            ("land rover", "evoque"), ("land rover", "velar"),
            ("lexus", "nx"),
        ],
    },
    "Pickup": {
        "economy":       [("toyota", "hilux")],
        "mid":           [("toyota", "hilux")],
        "premium":       [("toyota", "hilux")],
        "premium_upper": [("toyota", "hilux")],
        "apex_luxury":   [("toyota", "hilux")],
    },
    "Van": {
        "economy":       [("suzuki", "bolan"), ("suzuki", "every"), ("suzuki", "apv"), ("changan", "karvaan")],
        "mid":           [("toyota", "hiace"), ("honda", "stepwgn"), ("honda", "freed"), ("toyota", "sienta")],
        "premium":       [("toyota", "alphard"), ("toyota", "vellfire"), ("kia", "carnival")],
        "premium_upper": [("toyota", "alphard"), ("toyota", "vellfire")],
        "apex_luxury":   [("toyota", "alphard"), ("toyota", "vellfire")],
    },
}


# ---------------------------------------------------------------------------
# CANONICAL MODEL NAME MAP
# Normalizes LLM output variants to scraper-safe names for runner.py
# ---------------------------------------------------------------------------

_CANONICAL_MODEL_MAP: dict[str, str] = {
    # Toyota
    "land cruiser prado":          "Prado",
    "toyota land cruiser prado":   "Prado",
    "lc prado":                    "Prado",
    "lc300":                       "Land Cruiser",
    "lc200":                       "Land Cruiser",
    "v8":                          "Land Cruiser",
    "revo hilux":                  "Hilux",
    "hilux revo":                  "Hilux",
    "corolla altis":               "Corolla",
    "corolla grande":              "Corolla",
    "corolla xli":                 "Corolla",
    "corolla gli":                 "Corolla",
    "markx":                       "Mark X",
    "yaris cross":                 "Yaris Cross",
    # Honda
    "civic fc":                    "Civic",
    "civic oriel":                 "Civic",
    "civic vti":                   "Civic",
    "city aspire":                 "City",
    "city prosmatec":              "City",
    "br-v":                        "BR-V",
    "brv":                         "BR-V",
    "hr-v":                        "HR-V",
    "hrv":                         "HR-V",
    "cr-v":                        "CR-V",
    "crv":                         "CR-V",
    "n-box":                       "N-Box",
    "nbox":                        "N-Box",
    "n-wgn":                       "N-WGN",
    "nwgn":                        "N-WGN",
    "step wgn":                    "StepWGN",
    # Suzuki
    "wagon r":                     "Wagon R",
    "wagonr":                      "Wagon R",
    "alto 660":                    "Alto 660cc",
    # Nissan
    "x-trail":                     "X-Trail",
    "xtrail":                      "X-Trail",
    "note e-power":                "Note e-Power",
    # Mazda
    "rx-8":                        "RX-8",
    "rx8":                         "RX-8",
    "cx-5":                        "CX-5",
    "cx5":                         "CX-5",
    "mazda2":                      "Demio",
    "demio/mazda2":                "Demio",
    # Chinese
    "zs ev":                       "ZS EV",
    "oshan x7":                    "Oshan X7",
    "uni-t":                       "Uni-T",
    "deepal s07":                  "Deepal S07",
    "deepal l07":                  "Deepal L07",
    "h6 hev":                      "H6 HEV",
    "tiggo 4 pro":                 "Tiggo 4 Pro",
    "tiggo 8 pro":                 "Tiggo 8 Pro",
    "atto 3":                      "Atto 3",
    "tank 500":                    "Tank 500",
    "ora 03":                      "Ora 03",
    # European / Luxury
    "3 series":                    "3 Series",
    "5 series":                    "5 Series",
    "7 series":                    "7 Series",
    "c-class":                     "C-Class",
    "e-class":                     "E-Class",
    "s-class":                     "S-Class",
    "range rover":                 "Range Rover",
    "range rover sport":           "Range Rover Sport",
    "vogue":                       "Vogue",
    "evoque":                      "Evoque",
    "velar":                       "Velar",
    "e-tron":                      "e-tron",
    "e-tron gt":                   "e-tron GT",
    "lx 570":                      "LX570",
    "lx 600":                      "LX600",
    "pajero sport":                "Pajero Sport",
}


# ---------------------------------------------------------------------------
# CANDIDATE POOL — the core budget-sensitivity mechanism
# ---------------------------------------------------------------------------

def get_candidate_pool(
    max_budget: int,
    min_budget: int,
    body_style: str | None,
    allow_chinese: bool,
    tier: str,
    excluded_models: list[str] | None = None,
) -> str:
    """
    Builds a budget-filtered, style-filtered, fit-score-sorted candidate list
    and returns it as a prompt block with a hard "PICK ONLY FROM THIS LIST" instruction.

    Steps:
      1. BUDGET FILTER: keep models where budget window [min_budget, max_budget]
         intersects price range [lo, hi]. Two hard gates each direction.
      2. CHINESE GATE: drop Chinese makes unless allow_chinese=True.
      3. EXCLUSION FILTER: drop already-tried models (fallback/extend calls).
      4. STYLE FILTER: cross-reference _STYLE_TIER_ALLOWLIST using current tier
         and TWO tiers above for edge-case tolerance. Graceful degradation to
         budget-only if style filter empties the list.
      5. FIT SCORE: mathematical scoring — overlap coverage + budget centrality.
      6. SORT + TOP-18: wider pool than before to surface variety models.
    """
    if max_budget <= 0 and min_budget <= 0:
        # No budget stated — return full non-Chinese list
        candidates = [
            {
                "display":    f"{make.title()} {model.title()}",
                "range":      f"PKR {lo:,} – {hi:,}",
                "fit_score":  0.5,
            }
            for key, (lo, hi) in PAKISTAN_MARKET_PRICES.items()
            for make, model in [key.split(":", 1)]
            if not (make in _CHINESE_MAKES and not allow_chinese)
        ]
        candidates = candidates[:18]
    else:
        excluded_lower = {m.lower() for m in (excluded_models or [])}
        raw_candidates = []

        for key, (lo, hi) in PAKISTAN_MARKET_PRICES.items():
            make, model = key.split(":", 1)

            # Chinese gate
            if make in _CHINESE_MAKES and not allow_chinese:
                continue

            # Exclusion gate
            display_name = f"{make} {model}".lower()
            if any(ex in display_name for ex in excluded_lower):
                continue

            # Budget gate — both directions
            if max_budget > 0 and max_budget < lo * 0.80:
                continue   # can't afford the floor
            if min_budget > 0 and hi < min_budget * 0.80:
                continue   # model is too cheap for the budget

            # Fit score
            eff_min = min_budget if min_budget > 0 else lo
            eff_max = max_budget if max_budget > 0 else hi

            overlap    = max(0, min(eff_max, hi) - max(eff_min, lo))
            price_span = max(hi - lo, 1)
            coverage   = overlap / price_span

            midpoint = (lo + hi) / 2
            centered = 1.0 - abs(eff_max - midpoint) / max(midpoint, 1)
            centered = max(0.0, min(1.0, centered))

            fit_score = 0.6 * coverage + 0.4 * centered

            raw_candidates.append({
                "key":       key,
                "make":      make,
                "model":     model,
                "lo":        lo,
                "hi":        hi,
                "fit_score": fit_score,
                "display":   f"{make.title()} {model.title()}",
                "range":     f"PKR {lo:,} – {hi:,}",
            })

        # Style filter — cross-reference _STYLE_TIER_ALLOWLIST
        # FIX-3: window widened to current tier + 2 above for better edge coverage
        style_filtered = raw_candidates
        if body_style and body_style in _STYLE_TIER_ALLOWLIST:
            tier_order = ["economy", "mid", "premium", "premium_upper", "apex_luxury"]
            tier_idx   = tier_order.index(tier) if tier in tier_order else 1

            allowed_pairs: list[tuple[str, str]] = []
            for t in tier_order[max(0, tier_idx - 0): tier_idx + 3]:   # +3 window (was +2)
                allowed_pairs.extend(_STYLE_TIER_ALLOWLIST[body_style].get(t, []))

            def _matches_style(c: dict) -> bool:
                cm, cmod = c["make"], c["model"]
                for am, amod in allowed_pairs:
                    if am and am not in cm:
                        continue
                    if amod and amod not in cmod:
                        continue
                    return True
                return False

            filtered = [c for c in raw_candidates if _matches_style(c)]
            # Graceful degradation: never crash to empty
            style_filtered = filtered if filtered else raw_candidates

        # Sort by fit score, take top 18 (FIX-2: was 12)
        style_filtered.sort(key=lambda x: x["fit_score"], reverse=True)
        candidates = style_filtered[:18]

    if not candidates:
        return ""

    stars = lambda s: "★" * max(1, round(s * 5)) + "☆" * (5 - max(1, round(s * 5)))
    lines = [
        f"  {c['display']}: {c['range']}  {stars(c['fit_score'])}"
        for c in candidates
    ]

    style_note  = f" matching {body_style}" if body_style else ""
    budget_note = (
        f"PKR {min_budget:,} – {max_budget:,}" if max_budget > 0 else "no budget limit"
    )

    return (
        f"PRE-APPROVED CANDIDATE LIST{style_note} for budget {budget_note}:\n"
        "(Sorted by budget fit — ★★★★★ = perfect fit, ★☆☆☆☆ = edge of range)\n"
        + "\n".join(lines)
        + "\n\n"
        "HARD RULE: Pick ONLY from this list. Do not suggest any car not listed above.\n"
        "The list is pre-verified by Python against real Pakistani market prices.\n"
        "Higher ★ = this car's price range is more centered on the buyer's budget.\n"
    )


# ---------------------------------------------------------------------------
# POST-SELECTION VALIDATOR
# ---------------------------------------------------------------------------

def _validate_targets_against_market(targets: list, constraints: dict) -> list:
    """
    Python safety net after LLM selection.
    Should rarely fire since get_candidate_pool() pre-filters,
    but catches edge cases where the LLM ignores the list instruction.
    """
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
                        f"market floor PKR {lo:,} unreachable at PKR {max_budget:,}"
                    )
                    continue
                if min_budget > 0 and hi < min_budget * 0.80:
                    print(
                        f"[Validator] Dropping {t.make} {t.model} — "
                        f"market ceiling PKR {hi:,} below budget floor PKR {min_budget:,}"
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
    Raw signals from the user's query — extraction only, no decisions.
    All math and rule application happens in resolve_constraints().
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
    Temperature 0.0, response_schema enforces UserIntent shape natively.
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
    Phase 1 Python gate — ALL rule logic, zero LLM.

    FIX-1: 5-point tier scale replaces old 4-point scale.
    Old thresholds caused 5 crore and 10 crore to land in the same tier.

    New tiers:
      economy       < 40 lacs         → Alto, City, Corolla basic
      mid           40 lacs – 80 lacs  → Civic, Corolla Grande, Yaris, Premio
      premium       80 lacs – 2 crore  → Fortuner, Sportage, BMW 3 Series
      premium_upper 2 crore – 5 crore  → Prado, BMW 5 Series, E-Class, LX570
      apex_luxury   5 crore+           → Land Cruiser, Range Rover, Porsche, Patrol

    FIX-6: apex_luxury no longer requires is_luxury_request flag.
    Budget alone determines the tier. "LX570 under 10 crore" should work
    without the user saying "luxury".
    """
    max_budget = intent.max_budget or 0
    min_budget = 0

    if max_budget > 0:
        # Wider floor for apex to account for heavy depreciation on luxury imports
        min_budget = int(max_budget * 0.45 if max_budget >= 50_000_000 else max_budget * 0.70)

    # FIX-1: 5-point tier scale — tighter resolution between budget bands
    if max_budget >= 50_000_000:       # 5 crore+
        tier = "apex_luxury"           # LC300, LX570, Range Rover, Patrol, Porsche
    elif max_budget >= 20_000_000:     # 2 crore+
        tier = "premium_upper"         # Prado, BMW 5 Series, E-Class, Q7, LX570
    elif max_budget >= 8_000_000:      # 80 lacs+
        tier = "premium"               # Fortuner, Sportage, BMW 3 Series, Sorento
    elif max_budget >= 4_000_000:      # 40 lacs+
        tier = "mid"                   # Civic, Corolla Grande, Yaris, Premio
    else:
        tier = "economy"               # Alto, WagonR, Cultus, Vitz, older City

    # is_luxury_request escalates tier when budget is ambiguous
    if intent.is_luxury_request and tier not in ("apex_luxury", "premium_upper"):
        tier = "premium_upper"

    return {
        "min_budget":        min_budget,
        "max_budget":        max_budget,
        "min_year":          0,          # budget floor handles quality; no year veto here
        "tier":              tier,
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
    Phase 2 LLM call — car knowledge and use-case ranking only.
    Python has already filtered the candidate pool — LLM just picks from it.
    """
    max_budget    = constraints.get("max_budget", 0)
    min_budget    = constraints.get("min_budget", 0)
    tier          = constraints.get("tier", "mid")
    body_style    = constraints.get("body_style")
    allow_chinese = constraints.get("allow_chinese", False)

    candidate_pool = get_candidate_pool(
        max_budget=max_budget,
        min_budget=min_budget,
        body_style=body_style,
        allow_chinese=allow_chinese,
        tier=tier,
    )

    budget_str = (
        f"PKR {min_budget:,} – {max_budget:,}" if max_budget > 0
        else "No stated budget ceiling"
    )

    constraint_summary = {
        "budget_window":     budget_str,
        "tier":              tier,
        "body_style":        body_style or "Any",
        "transmission":      constraints.get("transmission") or "Any",
        "use_case":          constraints.get("use_case") or "General",
        "origin_pref":       constraints.get("origin_pref") or "Any (prefer Japanese/Korean)",
        "allow_chinese":     allow_chinese,
        "required_features": constraints.get("required_features", []),
    }

    prompt = (
        f"{candidate_pool}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "TASK: From the pre-approved list above, pick the best 1–3 cars "
        "for this Pakistani buyer. DO NOT suggest any car not in the list.\n\n"
        f"BUYER PROFILE:\n{json.dumps(constraint_summary, indent=2)}\n\n"
        "RANKING RULES (in priority order):\n"
        "1. LIST ONLY: Never suggest a car not in the pre-approved list above.\n"
        "2. BODY STYLE: Strictly match body_style. Pickup = open bed only (Hilux). "
        "No closed SUVs for Pickup. No sedans for SUV.\n"
        "3. TRANSMISSION: If Automatic, eliminate manual-only models.\n"
        "4. TIER MATCH: Respect the tier. If tier is 'apex_luxury', do NOT suggest "
        "Fortuner, Prado, Sportage, Tucson — those are premium tier. "
        "If tier is 'premium_upper', pick Prado/BMW 5 Series/E-Class/LX570 class cars.\n"
        "5. USE CASE FIT: Rank by how well the car matches use_case — "
        "family daily → reliability + boot space, sports → performance, "
        "offroad → ground clearance + 4WD, city commute → fuel economy + parking.\n"
        "6. MAKE DIVERSITY: Pick from DIFFERENT makes. Max 2 picks from the same make. "
        "If all 3 top picks are Toyota, substitute the 3rd with the best non-Toyota.\n"
        "7. JDM: If origin_pref is JDM, specify exact trim (e.g. trim='G Grade', trim='Turbo RS').\n"
        "8. QUANTITY: Return 1 if only 1 fits well. Never pad to reach 3.\n"
        "9. TRIM: Leave empty unless a specific trim adds clear value.\n"
        "10. RATIONALE: 1 sentence, buyer-friendly, WHY this car fits their need."
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

    FIX-5: Hard make-cap enforced here in Python.
    Max 2 picks from the same make. If LLM returns 3 Toyotas despite the
    diversity instruction, the 3rd Toyota is dropped.
    """
    validated = _validate_targets_against_market(raw_targets, constraints)

    seen:       set[tuple[str, str]] = set()
    make_count: dict[str, int]       = {}
    formatted:  list[dict]           = []

    for raw in validated:
        make_lower  = raw.make.lower().strip()
        model_raw   = raw.model.strip()
        model_lower = model_raw.lower()

        canonical_model = _CANONICAL_MODEL_MAP.get(model_lower, model_raw)

        # Dedup on (make, model)
        dedup_key = (make_lower, canonical_model.lower())
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        # FIX-5: make diversity cap — max 2 from same make
        if make_count.get(make_lower, 0) >= 2:
            print(f"[Dedup] Dropping {raw.make} {canonical_model} — make cap reached (max 2 per make)")
            continue
        make_count[make_lower] = make_count.get(make_lower, 0) + 1

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
    Phase 3 LLM call — fires only on NORMALIZER_ZERO.
    Returns exactly 1 replacement. Excluded models are removed from the
    candidate pool before the LLM sees it.
    """
    max_budget    = constraints.get("max_budget", 0)
    min_budget    = constraints.get("min_budget", 0)
    tier          = constraints.get("tier", "mid")
    body_style    = constraints.get("body_style")
    allow_chinese = constraints.get("allow_chinese", False)

    candidate_pool = get_candidate_pool(
        max_budget=max_budget,
        min_budget=min_budget,
        body_style=body_style,
        allow_chinese=allow_chinese,
        tier=tier,
        excluded_models=excluded_models,
    )

    budget_str = (
        f"PKR {min_budget:,} – {max_budget:,}" if max_budget > 0
        else "No stated budget ceiling"
    )

    prompt = (
        f"{candidate_pool}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "TASK: Pick exactly 1 replacement car. "
        "Previous recommendations returned zero listings.\n\n"
        f"CONSTRAINTS:\n"
        f"  Budget: {budget_str}\n"
        f"  Body style: {body_style or 'Any'}\n"
        f"  Transmission: {constraints.get('transmission') or 'Any'}\n"
        f"  Use case: {constraints.get('use_case') or 'General'}\n"
        f"  Tier: {tier}\n\n"
        f"ALREADY TRIED (excluded from list above): {json.dumps(excluded_models)}\n\n"
        "RULES:\n"
        "- Return exactly 1 target. Never return more than 1.\n"
        "- Pick only from the pre-approved list above.\n"
        "- Must match body_style and transmission.\n"
        "- If the list is empty or no valid pick exists, return []."
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
    Phase 3 LLM call — powers the 'Show More Options' button.
    Returns 1–3 alternatives. Excluded models removed from pool before LLM sees it.
    """
    max_budget    = original_constraints.get("max_budget", 0)
    min_budget    = original_constraints.get("min_budget", 0)
    tier          = original_constraints.get("tier", "mid")
    body_style    = original_constraints.get("body_style")
    allow_chinese = original_constraints.get("allow_chinese", False)

    candidate_pool = get_candidate_pool(
        max_budget=max_budget,
        min_budget=min_budget,
        body_style=body_style,
        allow_chinese=allow_chinese,
        tier=tier,
        excluded_models=excluded_models,
    )

    budget_str = (
        f"PKR {min_budget:,} – {max_budget:,}" if max_budget > 0
        else "No stated budget ceiling"
    )

    legacy_only_note = ""
    if 0 < max_budget <= 1_200_000:
        legacy_only_note = (
            "\nLOW-BUDGET RULE: Budget ≤ PKR 1,200,000. "
            "ONLY suggest legacy cars: Mehran, Cuore, Santro. "
            "Never suggest any modern car regardless of list.\n"
        )

    prompt = (
        f"{candidate_pool}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"TASK: Pick 1–3 alternative 'Show More' cars from the list above.{legacy_only_note}\n\n"
        f"CONSTRAINTS:\n"
        f"  Budget: {budget_str}\n"
        f"  Body style: {body_style or 'Any'}\n"
        f"  Transmission: {original_constraints.get('transmission') or 'Any'}\n"
        f"  Use case: {original_constraints.get('use_case') or 'General'}\n"
        f"  Tier: {tier}\n\n"
        f"ALREADY SHOWN (excluded from list above): {json.dumps(excluded_models)}\n\n"
        "RULES:\n"
        "- Pick only from the pre-approved list above.\n"
        "- Zero body style leaks — Sedan query → no SUVs or hatchbacks.\n"
        "- Spread picks across DIFFERENT makes from those already shown.\n"
        "- Quality > Quantity: return 1 if only 1 good option exists.\n"
        "- If the list is empty or no valid alternatives, return []."
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