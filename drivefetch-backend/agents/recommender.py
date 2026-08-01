"""
agents/recommender.py
LLM logic for the AI Matchmaker — Hybrid Pipeline with Unified Car Registry.

Architecture (Sequential Multi-Agent with Deterministic Guardrails):
  Phase 1 — LLM:    extract_intent()              → UserIntent (raw signals only)
  Phase 1 — Python: resolve_constraints()          → budget floor, luxury flag, chinese gate
  Phase 2 — Python: get_eligible_cars()            → budget + body-style + chinese filtered,
                                                     fit-score sorted ranked list
  Phase 2 — LLM:    select_car_targets()           → ranks from pre-approved list using
                                                     rule-based reasoning principles
  Phase 2 — Python: _validate_targets()            → safety-net double-check
  Phase 2 — Python: _deduplicate_and_format()      → 9-key contract dicts
  Phase 3 — LLM:    get_fallback_recommendations() → 1 replacement on NORMALIZER_ZERO
  Phase 3 — LLM:    get_extended_recommendations() → 1-3 "show more" alternatives

KEY DESIGN DECISIONS:

  1. UNIFIED CAR REGISTRY (CAR_REGISTRY)
     Single source of truth per car. Each entry holds:
       price range, body style, use-case tags, transmission type, and notes.
     Previously PAKISTAN_MARKET_PRICES and BODY_STYLE_MAP were two separate
     structures that could go out of sync. Now there is one dict — add a car
     once and all filters work automatically.

  2. RULE PRINCIPLES INSTEAD OF FEW-SHOT EXAMPLES
     Previous few-shot examples taught the LLM to copy specific cars from
     examples (e.g. "Mark X for sports") rather than understand WHY.
     Replaced with USE_CASE_PRINCIPLES — a set of reasoning rules per use-case
     that the LLM applies to whatever cars are in the eligible list.
     This generalises to edge cases that no example covered.

  3. FIT-SCORE SORTING
     Eligible list is sorted by how well the budget fits the car's price range.
     A 1 lac change in budget shifts scores and reorders the list, making budget
     sensitivity deterministic (Python math) rather than LLM-dependent.

  4. LUXURY ESCALATION SIGNAL
     resolve_constraints() computes is_apex_luxury (bool) separately from
     Chinese gate. Passed to get_eligible_cars() so it can apply an additional
     filter: if apex_luxury, remove cars whose price ceiling is below
     max_budget * 0.60 (prevents Fortuner appearing in a 5-crore query).

  5. TRANSMISSION MAP
     CAR_REGISTRY includes transmission field. get_eligible_cars() hard-filters
     manual-only cars when user requests Automatic — the LLM never sees them.
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

_GEMINI_MODEL = "gemini-3.5-flash-lite"


# ---------------------------------------------------------------------------
# UNIFIED CAR REGISTRY
#
# Single source of truth. Every car used anywhere in this file is defined here.
#
# Schema per entry:
#   "make:model" -> {
#       "lo":           int,          # min used-market price PKR (PakWheels/OLX)
#       "hi":           int,          # max used-market price PKR
#       "styles":       set[str],     # body styles this model belongs to
#                                     # ("Sedan","Hatchback","SUV","Crossover","Pickup","Van")
#       "transmission": str,          # "auto", "manual", or "both"
#                                     # "auto"   = only sold with auto in PK market
#                                     # "manual" = only available manual
#                                     # "both"   = available in both
#       "tags":         set[str],     # use-case and character tags — used by
#                                     # USE_CASE_PRINCIPLES ranking rules
#                                     # Tags: "economy","family","city","sports","offroad",
#                                     #       "jdm","luxury","status","hybrid","ev",
#                                     #       "7seat","cargo","performance","awd"
#       "chinese":      bool,         # True = Chinese brand, gated by allow_chinese
#       "priority":     int,          # 1 = best-in-class (Corolla, Civic, Fortuner)
#                                     # 2 = solid alternative (Liana, Baleno, Rush)
#                                     # 3 = niche/JDM/last-resort pick
#                                     # Higher priority wins tie-breakers at same budget fit.
#                                     # Prevents Liana ranking above Corolla at 22 lacs.
#       "sunroof_trims":list[str]|None, # Which trims of this model have factory sunroof.
#                                     # None = no factory sunroof in any trim.
#                                     # []   = unknown / seller-dependent.
#                                     # ["VRZ","Sigma3"] = only these trims.
#                                     # Used by get_eligible_cars() to hard-exclude
#                                     # models that can never have a requested feature.
#       "jdm_force_trim":str|None,    # When not None, always force this trim in the
#                                     # scraper URL to avoid local variant flooding.
#                                     # e.g. "660cc" for Alto to avoid local Alto flood.
#   }
#
# MAINTENANCE RULES:
#   - A model belongs to exactly ONE primary body style (how PakWheels lists it).
#   - When a model is ambiguous (e.g. Vezel = Crossover on PakWheels Pakistan),
#     classify by the dominant listing category on PakWheels.
#   - Crossover = car-based unibody with raised ride height.
#   - SUV = body-on-frame OR large 7-seat unibody (Fortuner, Tucson, Palisade).
#   - To add a car: add one entry here. Everything else is automatic.
#   - To remove a car: delete its entry. It disappears from all filters.
# ---------------------------------------------------------------------------

CAR_REGISTRY: dict[str, dict] = {

    # ── Suzuki ───────────────────────────────────────────────────────────────
    "suzuki:mehran":           {"lo": 300_000,    "hi": 1_500_000,  "styles": {"Hatchback"},
                                "transmission": "both",   "tags": {"economy","city"},          "chinese": False, "priority": 2},
    "suzuki:alto":             {"lo": 700_000,    "hi": 3_600_000,  "styles": {"Hatchback"},
                                "transmission": "both",   "tags": {"economy","city"},          "chinese": False, "priority": 2},
    "suzuki:alto 660cc":       {"lo": 1_500_000,  "hi": 3_800_000,  "styles": {"Hatchback"},
                                "transmission": "both",   "tags": {"economy","city","jdm"},    "chinese": False, "priority": 2},
    "suzuki:cultus":           {"lo": 1_000_000,  "hi": 4_500_000,  "styles": {"Hatchback"},
                                "transmission": "both",   "tags": {"economy","city","family"}, "chinese": False, "priority": 2},
    "suzuki:wagon r":          {"lo": 1_500_000,  "hi": 3_500_000,  "styles": {"Hatchback"},
                                "transmission": "both",   "tags": {"economy","city","family"}, "chinese": False, "priority": 2},
    "suzuki:swift":            {"lo": 1_200_000,  "hi": 5_200_000,  "styles": {"Hatchback"},
                                "transmission": "both",   "tags": {"economy","city","sports"}, "chinese": False, "priority": 2},
    "suzuki:baleno":           {"lo": 1_000_000,  "hi": 2_500_000,  "styles": {"Sedan"},
                                "transmission": "both",   "tags": {"economy","city","family"}, "chinese": False, "priority": 3},
    "suzuki:liana":            {"lo": 1_200_000,  "hi": 2_800_000,  "styles": {"Sedan"},
                                "transmission": "both",   "tags": {"economy","family"},        "chinese": False, "priority": 3},
    "suzuki:hustler":          {"lo": 1_800_000,  "hi": 4_000_000,  "styles": {"Hatchback"},
                                "transmission": "auto",   "tags": {"economy","city","jdm"},    "chinese": False},
    "suzuki:spacia":           {"lo": 1_800_000,  "hi": 4_000_000,  "styles": {"Hatchback"},
                                "transmission": "auto",   "tags": {"economy","city","jdm","family"}, "chinese": False},
    "suzuki:solio":            {"lo": 2_000_000,  "hi": 4_500_000,  "styles": {"Hatchback"},
                                "transmission": "auto",   "tags": {"economy","city","jdm","family"}, "chinese": False},
    "suzuki:jimny":            {"lo": 2_500_000,  "hi": 8_500_000,  "styles": {"Crossover"},
                                "transmission": "both",   "tags": {"offroad","awd","jdm"},     "chinese": False},
    "suzuki:every":            {"lo": 1_000_000,  "hi": 3_000_000,  "styles": {"Van"},
                                "transmission": "both",   "tags": {"cargo","economy","jdm"},   "chinese": False},
    "suzuki:bolan":            {"lo": 500_000,    "hi": 2_000_000,  "styles": {"Van"},
                                "transmission": "manual", "tags": {"cargo","economy"},         "chinese": False},
    "suzuki:apv":              {"lo": 1_500_000,  "hi": 3_500_000,  "styles": {"Van"},
                                "transmission": "auto",   "tags": {"family","7seat"},          "chinese": False},

    # ── Legacy / Retro ──────────────────────────────────────────────────────────
    "suzuki:fx":               {"lo": 150_000,   "hi": 600_000,   "styles": {"Hatchback"},
                                "transmission": "manual", "tags": {"economy","city"},          "chinese": False, "priority": 3},
    "suzuki:khyber":           {"lo": 300_000,   "hi": 1_200_000, "styles": {"Hatchback"},
                                "transmission": "manual", "tags": {"economy","city"},          "chinese": False, "priority": 3},
    "suzuki:margalla":         {"lo": 400_000,   "hi": 1_500_000, "styles": {"Sedan"},
                                "transmission": "manual", "tags": {"economy","family"},        "chinese": False, "priority": 3},
    "daihatsu:charade":        {"lo": 250_000,   "hi": 1_000_000, "styles": {"Hatchback"},
                                "transmission": "both",   "tags": {"economy","city"},          "chinese": False, "priority": 3},
    "nissan:sunny":            {"lo": 500_000,   "hi": 1_800_000, "styles": {"Sedan"},
                                "transmission": "both",   "tags": {"economy","family"},        "chinese": False, "priority": 3},

    # ── Toyota ───────────────────────────────────────────────────────────────
    "toyota:vitz":             {"lo": 1_500_000,  "hi": 4_500_000,  "styles": {"Hatchback"},
                                "transmission": "auto",   "tags": {"economy","city","jdm"},    "chinese": False},
    "toyota:passo":            {"lo": 1_500_000,  "hi": 4_000_000,  "styles": {"Hatchback"},
                                "transmission": "auto",   "tags": {"economy","city","jdm"},    "chinese": False},
    "toyota:aqua":             {"lo": 2_500_000,  "hi": 6_500_000,  "styles": {"Hatchback"},
                                "transmission": "auto",   "tags": {"hybrid","economy","city","jdm"}, "chinese": False},
    "toyota:tank":             {"lo": 3_000_000,  "hi": 4_500_000,  "styles": {"Hatchback"},
                                "transmission": "auto",   "tags": {"economy","city","jdm","family"}, "chinese": False},
    "toyota:roomy":            {"lo": 3_000_000,  "hi": 5_000_000,  "styles": {"Hatchback"},
                                "transmission": "auto",   "tags": {"economy","city","jdm","family"}, "chinese": False},
    "toyota:probox":           {"lo": 2_000_000,  "hi": 4_500_000,  "styles": {"Van"},
                                "transmission": "both",   "tags": {"cargo","economy","jdm"},   "chinese": False},
    "toyota:corolla":          {"lo": 2_000_000,  "hi": 8_500_000,  "styles": {"Sedan"},
                                "transmission": "both",   "tags": {"family","city","economy","reliability","resale"}, "chinese": False, "priority": 1},
    "toyota:yaris":            {"lo": 3_500_000,  "hi": 6_000_000,  "styles": {"Sedan"},
                                "transmission": "auto",   "tags": {"family","city","reliability","resale"}, "chinese": False, "priority": 1},
    "toyota:allion":           {"lo": 3_000_000,  "hi": 8_000_000,  "styles": {"Sedan"},
                                "transmission": "auto",   "tags": {"family","jdm","city"},     "chinese": False, "priority": 2},
    "toyota:premio":           {"lo": 3_500_000,  "hi": 9_000_000,  "styles": {"Sedan"},
                                "transmission": "auto",   "tags": {"family","jdm","city"},     "chinese": False, "priority": 2},
    "toyota:mark x":           {"lo": 3_000_000,  "hi": 7_000_000,  "styles": {"Sedan"},
                                "transmission": "auto",   "tags": {"sports","jdm","performance"}, "chinese": False, "priority": 2},
    "toyota:fielder":          {"lo": 2_500_000,  "hi": 6_000_000,  "styles": {"Sedan"},
                                "transmission": "auto",   "tags": {"family","jdm","cargo"},    "chinese": False, "priority": 3},
    "toyota:prius":            {"lo": 2_500_000,  "hi": 12_000_000, "styles": {"Sedan"},
                                "transmission": "auto",   "tags": {"hybrid","economy","jdm"},  "chinese": False, "priority": 2},
    "toyota:crown":            {"lo": 4_000_000,  "hi": 25_000_000, "styles": {"Sedan"},
                                "transmission": "auto",   "tags": {"sports","jdm","luxury","status","performance"}, "chinese": False, "priority": 2},
    "toyota:camry":            {"lo": 7_000_000,  "hi": 18_000_000, "styles": {"Sedan"},
                                "transmission": "auto",   "tags": {"luxury","status","family"}, "chinese": False, "priority": 1},
    "toyota:sienta":           {"lo": 3_000_000,  "hi": 6_500_000,  "styles": {"Van"},
                                "transmission": "auto",   "tags": {"family","7seat","jdm"},    "chinese": False},
    "toyota:c-hr":             {"lo": 4_500_000,  "hi": 10_000_000, "styles": {"Crossover"},
                                "transmission": "auto",   "tags": {"city","jdm","sports"},     "chinese": False},
    "toyota:raize":            {"lo": 5_000_000,  "hi": 7_500_000,  "styles": {"Crossover"},
                                "transmission": "auto",   "tags": {"city","family","jdm"},     "chinese": False},
    "toyota:yaris cross":      {"lo": 6_000_000,  "hi": 9_500_000,  "styles": {"Crossover"},
                                "transmission": "auto",   "tags": {"city","hybrid","jdm"},     "chinese": False},
    "toyota:rush":             {"lo": 5_500_000,  "hi": 9_000_000,  "styles": {"SUV"},
                                "transmission": "auto",   "tags": {"family","7seat"},          "chinese": False},
    "toyota:fortuner":         {"lo": 9_000_000,  "hi": 21_000_000, "styles": {"SUV"},
                                "transmission": "auto",   "tags": {"family","offroad","status","7seat","reliability","resale"}, "chinese": False, "priority": 1},
    "toyota:hilux":            {"lo": 8_000_000,  "hi": 16_000_000, "styles": {"Pickup"},
                                "transmission": "both",   "tags": {"offroad","cargo","awd"},   "chinese": False, "priority": 1},
    "toyota:alphard":          {"lo": 6_000_000,  "hi": 35_000_000, "styles": {"Van"},
                                "transmission": "auto",   "tags": {"luxury","status","family","7seat","jdm"}, "chinese": False},
    "toyota:vellfire":         {"lo": 6_000_000,  "hi": 35_000_000, "styles": {"Van"},
                                "transmission": "auto",   "tags": {"luxury","status","family","7seat","jdm"}, "chinese": False},
    "toyota:hiace":            {"lo": 3_500_000,  "hi": 12_000_000, "styles": {"Van"},
                                "transmission": "both",   "tags": {"cargo","7seat","family"},  "chinese": False},
    "toyota:prado":            {"lo": 18_000_000, "hi": 48_000_000, "styles": {"SUV"},
                                "transmission": "auto",   "tags": {"luxury","status","offroad","awd","reliability","resale"}, "chinese": False, "priority": 1},
    "toyota:land cruiser":     {"lo": 35_000_000, "hi": 90_000_000, "styles": {"SUV"},
                                "transmission": "auto",   "tags": {"luxury","status","offroad","awd","reliability","resale"}, "chinese": False, "priority": 1},

    # ── Honda ────────────────────────────────────────────────────────────────
    "honda:n-box":             {"lo": 1_800_000,  "hi": 4_200_000,  "styles": {"Hatchback"},
                                "transmission": "auto",   "tags": {"economy","city","jdm"},    "chinese": False},
    "honda:n-wgn":             {"lo": 1_500_000,  "hi": 3_800_000,  "styles": {"Hatchback"},
                                "transmission": "auto",   "tags": {"economy","city","jdm"},    "chinese": False},
    "honda:fit":               {"lo": 2_000_000,  "hi": 5_500_000,  "styles": {"Hatchback"},
                                "transmission": "auto",   "tags": {"economy","city","jdm"},    "chinese": False},
    "honda:city":              {"lo": 1_500_000,  "hi": 6_000_000,  "styles": {"Sedan"},
                                "transmission": "both",   "tags": {"economy","family","city","reliability","resale"}, "chinese": False, "priority": 1},
    "honda:civic":             {"lo": 2_000_000,  "hi": 9_500_000,  "styles": {"Sedan"},
                                "transmission": "both",   "tags": {"family","city","sports","reliability","resale"},  "chinese": False, "priority": 1},
    "honda:grace":             {"lo": 3_500_000,  "hi": 6_500_000,  "styles": {"Sedan"},
                                "transmission": "auto",   "tags": {"family","hybrid","jdm"},   "chinese": False},
    "honda:insight":           {"lo": 2_500_000,  "hi": 6_500_000,  "styles": {"Sedan"},
                                "transmission": "auto",   "tags": {"hybrid","economy","jdm"},  "chinese": False},
    "honda:freed":             {"lo": 2_500_000,  "hi": 6_000_000,  "styles": {"Van"},
                                "transmission": "auto",   "tags": {"family","7seat","jdm"},    "chinese": False},
    "honda:shuttle":           {"lo": 3_500_000,  "hi": 7_000_000,  "styles": {"Van"},
                                "transmission": "auto",   "tags": {"family","hybrid","jdm"},   "chinese": False},
    "honda:stepwgn":           {"lo": 3_000_000,  "hi": 8_000_000,  "styles": {"Van"},
                                "transmission": "auto",   "tags": {"family","7seat","jdm"},    "chinese": False},
    "honda:br-v":              {"lo": 3_500_000,  "hi": 6_500_000,  "styles": {"Crossover"},
                                "transmission": "both",   "tags": {"family","7seat","city"},   "chinese": False},
    "honda:hr-v":              {"lo": 6_000_000,  "hi": 8_500_000,  "styles": {"Crossover"},
                                "transmission": "auto",   "tags": {"city","jdm"},              "chinese": False},
    "honda:vezel":             {"lo": 4_000_000,  "hi": 11_000_000, "styles": {"Crossover"},
                                "transmission": "auto",   "tags": {"city","hybrid","jdm"},     "chinese": False},
    "honda:cr-v":              {"lo": 6_000_000,  "hi": 14_000_000, "styles": {"SUV"},
                                "transmission": "auto",   "tags": {"family","awd","jdm"},      "chinese": False},
    "honda:accord":            {"lo": 4_500_000,  "hi": 12_000_000, "styles": {"Sedan"},
                                "transmission": "auto",   "tags": {"luxury","family","jdm"},   "chinese": False},

    # ── Hyundai ──────────────────────────────────────────────────────────────
    "hyundai:santro":          {"lo": 700_000,    "hi": 1_800_000,  "styles": {"Hatchback"},
                                "transmission": "both",   "tags": {"economy","city"},          "chinese": False},
    "hyundai:elantra":         {"lo": 5_000_000,  "hi": 7_500_000,  "styles": {"Sedan"},
                                "transmission": "auto",   "tags": {"family","city"},           "chinese": False},
    "hyundai:sonata":          {"lo": 7_500_000,  "hi": 11_000_000, "styles": {"Sedan"},
                                "transmission": "auto",   "tags": {"luxury","family"},         "chinese": False},
    "hyundai:tucson":          {"lo": 6_000_000,  "hi": 9_000_000,  "styles": {"SUV"},
                                "transmission": "auto",   "tags": {"family","city","awd"},     "chinese": False},
    "hyundai:porter":          {"lo": 2_500_000,  "hi": 4_000_000,  "styles": {"Van"},
                                "transmission": "both",   "tags": {"cargo"},                   "chinese": False},
    "hyundai:palisade":        {"lo": 18_000_000, "hi": 35_000_000, "styles": {"SUV"},
                                "transmission": "auto",   "tags": {"luxury","family","7seat","awd"}, "chinese": False},

    # ── Kia ──────────────────────────────────────────────────────────────────
    "kia:picanto":             {"lo": 2_500_000,  "hi": 3_800_000,  "styles": {"Hatchback"},
                                "transmission": "auto",   "tags": {"economy","city"},          "chinese": False},
    "kia:stonic":              {"lo": 4_500_000,  "hi": 6_000_000,  "styles": {"Crossover"},
                                "transmission": "auto",   "tags": {"city","family"},           "chinese": False},
    "kia:sportage":            {"lo": 5_500_000,  "hi": 10_000_000, "styles": {"SUV"},
                                "transmission": "auto",   "tags": {"family","city","awd"},     "chinese": False},
    "kia:sorento":             {"lo": 7_500_000,  "hi": 11_000_000, "styles": {"SUV"},
                                "transmission": "auto",   "tags": {"family","7seat","awd"},    "chinese": False},
    "kia:carnival":            {"lo": 9_000_000,  "hi": 18_000_000, "styles": {"Van"},
                                "transmission": "auto",   "tags": {"luxury","family","7seat"}, "chinese": False},

    # ── Daihatsu ─────────────────────────────────────────────────────────────
    "daihatsu:cuore":          {"lo": 600_000,    "hi": 1_600_000,  "styles": {"Hatchback"},
                                "transmission": "both",   "tags": {"economy","city"},          "chinese": False},
    "daihatsu:mira":           {"lo": 1_200_000,  "hi": 3_800_000,  "styles": {"Hatchback"},
                                "transmission": "auto",   "tags": {"economy","city","jdm"},    "chinese": False},
    "daihatsu:move":           {"lo": 1_200_000,  "hi": 3_500_000,  "styles": {"Hatchback"},
                                "transmission": "auto",   "tags": {"economy","city","jdm"},    "chinese": False},
    "daihatsu:tanto":          {"lo": 1_500_000,  "hi": 4_000_000,  "styles": {"Hatchback"},
                                "transmission": "auto",   "tags": {"economy","city","jdm","family"}, "chinese": False},
    "daihatsu:cast":           {"lo": 2_000_000,  "hi": 3_500_000,  "styles": {"Hatchback"},
                                "transmission": "auto",   "tags": {"economy","city","jdm"},    "chinese": False},
    "daihatsu:hijet":          {"lo": 1_000_000,  "hi": 2_500_000,  "styles": {"Van"},
                                "transmission": "both",   "tags": {"cargo","economy"},         "chinese": False},
    "daihatsu:rocky":          {"lo": 5_000_000,  "hi": 7_500_000,  "styles": {"Crossover"},
                                "transmission": "auto",   "tags": {"city","jdm"},              "chinese": False},
    "daihatsu:terios":         {"lo": 2_500_000,  "hi": 6_000_000,  "styles": {"Crossover"},
                                "transmission": "both",   "tags": {"offroad","family"},        "chinese": False},

    # ── Nissan ───────────────────────────────────────────────────────────────
    "nissan:dayz":             {"lo": 1_500_000,  "hi": 3_500_000,  "styles": {"Hatchback"},
                                "transmission": "auto",   "tags": {"economy","city","jdm"},    "chinese": False},
    "nissan:roox":             {"lo": 1_500_000,  "hi": 3_800_000,  "styles": {"Hatchback"},
                                "transmission": "auto",   "tags": {"economy","city","jdm"},    "chinese": False},
    "nissan:note":             {"lo": 3_500_000,  "hi": 6_500_000,  "styles": {"Sedan"},
                                "transmission": "auto",   "tags": {"hybrid","economy","jdm"},  "chinese": False},
    "nissan:juke":             {"lo": 3_500_000,  "hi": 8_000_000,  "styles": {"Crossover"},
                                "transmission": "auto",   "tags": {"city","sports","jdm"},     "chinese": False},
    "nissan:x-trail":          {"lo": 5_000_000,  "hi": 14_000_000, "styles": {"SUV"},
                                "transmission": "auto",   "tags": {"family","awd"},            "chinese": False},
    "nissan:patrol":           {"lo": 20_000_000, "hi": 55_000_000, "styles": {"SUV"},
                                "transmission": "auto",   "tags": {"luxury","status","offroad","awd"}, "chinese": False},

    # ── Mitsubishi ───────────────────────────────────────────────────────────
    "mitsubishi:mirage":       {"lo": 2_000_000,  "hi": 4_500_000,  "styles": {"Sedan"},
                                "transmission": "auto",   "tags": {"economy","city","jdm"},    "chinese": False},
    "mitsubishi:asx":          {"lo": 3_500_000,  "hi": 8_000_000,  "styles": {"Crossover"},
                                "transmission": "auto",   "tags": {"city","awd","jdm"},        "chinese": False},
    "mitsubishi:outlander":    {"lo": 5_000_000,  "hi": 14_000_000, "styles": {"SUV"},
                                "transmission": "auto",   "tags": {"family","awd"},            "chinese": False},
    "mitsubishi:pajero":       {"lo": 5_000_000,  "hi": 16_000_000, "styles": {"SUV"},
                                "transmission": "auto",   "tags": {"offroad","awd","status"},  "chinese": False},
    "mitsubishi:pajero sport": {"lo": 8_000_000,  "hi": 18_000_000, "styles": {"SUV"},
                                "transmission": "auto",   "tags": {"offroad","awd","status"},  "chinese": False},

    # ── Subaru ───────────────────────────────────────────────────────────────
    "subaru:impreza":          {"lo": 2_500_000,  "hi": 6_000_000,  "styles": {"Sedan"},
                                "transmission": "both",   "tags": {"sports","awd","jdm","performance"}, "chinese": False},
    "subaru:xv":               {"lo": 4_000_000,  "hi": 7_500_000,  "styles": {"Crossover"},
                                "transmission": "auto",   "tags": {"awd","city","jdm"},        "chinese": False},
    "subaru:forester":         {"lo": 4_500_000,  "hi": 9_000_000,  "styles": {"SUV"},
                                "transmission": "auto",   "tags": {"awd","family","offroad"},  "chinese": False},
    "subaru:brz":              {"lo": 4_500_000,  "hi": 10_000_000, "styles": {"Sedan"},
                                "transmission": "both",   "tags": {"sports","performance","jdm"}, "chinese": False},

    # ── Mazda ────────────────────────────────────────────────────────────────
    "mazda:demio":             {"lo": 2_500_000,  "hi": 4_500_000,  "styles": {"Hatchback"},
                                "transmission": "auto",   "tags": {"economy","city","jdm"},    "chinese": False},
    "mazda:mazda3":            {"lo": 3_000_000,  "hi": 7_000_000,  "styles": {"Sedan"},
                                "transmission": "auto",   "tags": {"sports","city","jdm"},     "chinese": False},
    "mazda:rx-8":              {"lo": 1_500_000,  "hi": 4_000_000,  "styles": {"Sedan"},
                                "transmission": "both",   "tags": {"sports","performance","jdm"}, "chinese": False},
    "mazda:cx-3":              {"lo": 4_000_000,  "hi": 7_000_000,  "styles": {"Crossover"},
                                "transmission": "auto",   "tags": {"city","jdm"},              "chinese": False},
    "mazda:cx-5":              {"lo": 5_500_000,  "hi": 9_500_000,  "styles": {"SUV"},
                                "transmission": "auto",   "tags": {"family","awd","jdm"},      "chinese": False},

    # ── Chinese & New Entrants ────────────────────────────────────────────────
    "mg:zs":                   {"lo": 4_500_000,  "hi": 6_500_000,  "styles": {"Crossover"},
                                "transmission": "auto",   "tags": {"city","economy"},          "chinese": True},
    "mg:zs ev":                {"lo": 7_000_000,  "hi": 11_000_000, "styles": {"Crossover"},
                                "transmission": "auto",   "tags": {"ev","city"},               "chinese": True},
    "mg:hs":                   {"lo": 6_000_000,  "hi": 8_500_000,  "styles": {"SUV"},
                                "transmission": "auto",   "tags": {"family","city"},           "chinese": True},
    "mg:rx5":                  {"lo": 4_500_000,  "hi": 9_000_000,  "styles": {"SUV"},
                                "transmission": "auto",   "tags": {"family","city"},           "chinese": True},
    "mg:cyberster":            {"lo": 15_000_000, "hi": 25_000_000, "styles": {"Sedan"},
                                "transmission": "auto",   "tags": {"ev","sports","luxury"},    "chinese": True},
    "changan:alsvin":          {"lo": 3_200_000,  "hi": 4_800_000,  "styles": {"Sedan"},
                                "transmission": "auto",   "tags": {"economy","city","family"}, "chinese": True},
    "changan:karvaan":         {"lo": 1_500_000,  "hi": 3_000_000,  "styles": {"Van"},
                                "transmission": "both",   "tags": {"cargo","family","economy"},"chinese": True},
    "changan:oshan x7":        {"lo": 7_000_000,  "hi": 9_500_000,  "styles": {"SUV"},
                                "transmission": "auto",   "tags": {"family","7seat"},          "chinese": True},
    "changan:uni-t":           {"lo": 8_000_000,  "hi": 11_000_000, "styles": {"SUV"},
                                "transmission": "auto",   "tags": {"family","city"},           "chinese": True},
    "changan:deepal s07":      {"lo": 13_000_000, "hi": 18_000_000, "styles": {"SUV"},
                                "transmission": "auto",   "tags": {"ev","luxury","family"},    "chinese": True},
    "changan:deepal l07":      {"lo": 13_000_000, "hi": 18_000_000, "styles": {"Sedan"},
                                "transmission": "auto",   "tags": {"ev","luxury"},             "chinese": True},
    "haval:jolion":            {"lo": 7_000_000,  "hi": 9_000_000,  "styles": {"SUV"},
                                "transmission": "auto",   "tags": {"family","city"},           "chinese": True},
    "haval:h6":                {"lo": 8_900_000,  "hi": 10_000_000, "styles": {"SUV"},
                                "transmission": "auto",   "tags": {"family","awd"},            "chinese": True},
    "haval:h6 hev":            {"lo": 11_400_000, "hi": 14_000_000, "styles": {"SUV"},
                                "transmission": "auto",   "tags": {"hybrid","family","awd"},   "chinese": True},
    "chery:tiggo 4 pro":       {"lo": 5_500_000,  "hi": 7_500_000,  "styles": {"Crossover"},
                                "transmission": "auto",   "tags": {"city","family"},           "chinese": True},
    "chery:tiggo 8 pro":       {"lo": 8_000_000,  "hi": 10_500_000, "styles": {"SUV"},
                                "transmission": "auto",   "tags": {"family","7seat"},          "chinese": True},
    "proton:saga":             {"lo": 2_500_000,  "hi": 3_800_000,  "styles": {"Sedan"},
                                "transmission": "auto",   "tags": {"economy","city","family"}, "chinese": True},
    "proton:x70":              {"lo": 6_000_000,  "hi": 8_000_000,  "styles": {"SUV"},
                                "transmission": "auto",   "tags": {"family","city"},           "chinese": True},
    "byd:dolphin":             {"lo": 9_000_000,  "hi": 12_000_000, "styles": {"Hatchback"},
                                "transmission": "auto",   "tags": {"ev","city","economy"},     "chinese": True},
    "byd:atto 3":              {"lo": 11_000_000, "hi": 15_000_000, "styles": {"SUV"},
                                "transmission": "auto",   "tags": {"ev","family"},             "chinese": True},
    "byd:seal":                {"lo": 16_000_000, "hi": 22_000_000, "styles": {"Sedan"},
                                "transmission": "auto",   "tags": {"ev","sports","luxury"},    "chinese": True},
    "gwm:ora 03":              {"lo": 8_000_000,  "hi": 11_000_000, "styles": {"Crossover"},
                                "transmission": "auto",   "tags": {"ev","city"},               "chinese": True},
    "gwm:tank 500":            {"lo": 35_000_000, "hi": 45_000_000, "styles": {"SUV"},
                                "transmission": "auto",   "tags": {"luxury","status","offroad","awd"}, "chinese": True},

    # ── European & Luxury ────────────────────────────────────────────────────
    "bmw:3 series":            {"lo": 6_000_000,  "hi": 25_000_000, "styles": {"Sedan"},
                                "transmission": "auto",   "tags": {"sports","luxury","status","performance"}, "chinese": False},
    "bmw:5 series":            {"lo": 8_000_000,  "hi": 35_000_000, "styles": {"Sedan"},
                                "transmission": "auto",   "tags": {"luxury","status","family"}, "chinese": False},
    "bmw:7 series":            {"lo": 15_000_000, "hi": 60_000_000, "styles": {"Sedan"},
                                "transmission": "auto",   "tags": {"luxury","status"},         "chinese": False},
    "bmw:x1":                  {"lo": 7_000_000,  "hi": 20_000_000, "styles": {"Crossover"},
                                "transmission": "auto",   "tags": {"city","luxury","awd"},     "chinese": False},
    "bmw:x3":                  {"lo": 9_000_000,  "hi": 30_000_000, "styles": {"SUV"},
                                "transmission": "auto",   "tags": {"luxury","awd","status"},   "chinese": False},
    "bmw:x5":                  {"lo": 12_000_000, "hi": 50_000_000, "styles": {"SUV"},
                                "transmission": "auto",   "tags": {"luxury","status","awd"},   "chinese": False},
    "bmw:x7":                  {"lo": 40_000_000, "hi": 80_000_000, "styles": {"SUV"},
                                "transmission": "auto",   "tags": {"luxury","status","7seat"}, "chinese": False},
    "bmw:i4":                  {"lo": 25_000_000, "hi": 35_000_000, "styles": {"Sedan"},
                                "transmission": "auto",   "tags": {"ev","luxury","performance"}, "chinese": False},
    "bmw:i7":                  {"lo": 60_000_000, "hi": 90_000_000, "styles": {"Sedan"},
                                "transmission": "auto",   "tags": {"ev","luxury","status"},    "chinese": False},
    "bmw:ix":                  {"lo": 35_000_000, "hi": 55_000_000, "styles": {"SUV"},
                                "transmission": "auto",   "tags": {"ev","luxury"},             "chinese": False},
    "mercedes-benz:cla":       {"lo": 7_000_000,  "hi": 18_000_000, "styles": {"Sedan"},
                                "transmission": "auto",   "tags": {"luxury","sports","status"}, "chinese": False},
    "mercedes-benz:c-class":   {"lo": 6_000_000,  "hi": 30_000_000, "styles": {"Sedan"},
                                "transmission": "auto",   "tags": {"luxury","status","family"}, "chinese": False},
    "mercedes-benz:e-class":   {"lo": 8_000_000,  "hi": 45_000_000, "styles": {"Sedan"},
                                "transmission": "auto",   "tags": {"luxury","status","family"}, "chinese": False},
    "mercedes-benz:s-class":   {"lo": 15_000_000, "hi": 80_000_000, "styles": {"Sedan"},
                                "transmission": "auto",   "tags": {"luxury","status"},         "chinese": False},
    "mercedes-benz:gla":       {"lo": 7_500_000,  "hi": 20_000_000, "styles": {"Crossover"},
                                "transmission": "auto",   "tags": {"luxury","city","awd"},     "chinese": False},
    "mercedes-benz:glc":       {"lo": 12_000_000, "hi": 35_000_000, "styles": {"SUV"},
                                "transmission": "auto",   "tags": {"luxury","status","awd"},   "chinese": False},
    "mercedes-benz:gle":       {"lo": 15_000_000, "hi": 50_000_000, "styles": {"SUV"},
                                "transmission": "auto",   "tags": {"luxury","status","awd"},   "chinese": False},
    "mercedes-benz:gls":       {"lo": 30_000_000, "hi": 75_000_000, "styles": {"SUV"},
                                "transmission": "auto",   "tags": {"luxury","status","7seat"}, "chinese": False},
    "audi:a3":                 {"lo": 5_000_000,  "hi": 12_000_000, "styles": {"Sedan","Hatchback"},
                                "transmission": "auto",   "tags": {"luxury","sports","city"},  "chinese": False},
    "audi:a4":                 {"lo": 6_500_000,  "hi": 20_000_000, "styles": {"Sedan"},
                                "transmission": "auto",   "tags": {"luxury","sports","status"}, "chinese": False},
    "audi:a5":                 {"lo": 8_000_000,  "hi": 25_000_000, "styles": {"Sedan"},
                                "transmission": "auto",   "tags": {"luxury","sports"},         "chinese": False},
    "audi:a6":                 {"lo": 9_000_000,  "hi": 35_000_000, "styles": {"Sedan"},
                                "transmission": "auto",   "tags": {"luxury","status","family"}, "chinese": False},
    "audi:a7":                 {"lo": 15_000_000, "hi": 45_000_000, "styles": {"Sedan"},
                                "transmission": "auto",   "tags": {"luxury","status"},         "chinese": False},
    "audi:q2":                 {"lo": 6_500_000,  "hi": 11_000_000, "styles": {"Crossover"},
                                "transmission": "auto",   "tags": {"luxury","city"},           "chinese": False},
    "audi:q3":                 {"lo": 7_500_000,  "hi": 15_000_000, "styles": {"Crossover"},
                                "transmission": "auto",   "tags": {"luxury","city","awd"},     "chinese": False},
    "audi:q5":                 {"lo": 10_000_000, "hi": 25_000_000, "styles": {"SUV"},
                                "transmission": "auto",   "tags": {"luxury","awd","status"},   "chinese": False},
    "audi:q7":                 {"lo": 15_000_000, "hi": 45_000_000, "styles": {"SUV"},
                                "transmission": "auto",   "tags": {"luxury","status","7seat"}, "chinese": False},
    "audi:q8":                 {"lo": 30_000_000, "hi": 60_000_000, "styles": {"SUV"},
                                "transmission": "auto",   "tags": {"luxury","status"},         "chinese": False},
    "audi:e-tron":             {"lo": 18_000_000, "hi": 35_000_000, "styles": {"SUV"},
                                "transmission": "auto",   "tags": {"ev","luxury"},             "chinese": False},
    "audi:e-tron gt":          {"lo": 35_000_000, "hi": 60_000_000, "styles": {"Sedan"},
                                "transmission": "auto",   "tags": {"ev","luxury","performance"}, "chinese": False},
    "porsche:macan":           {"lo": 20_000_000, "hi": 45_000_000, "styles": {"Crossover"},
                                "transmission": "auto",   "tags": {"luxury","sports","awd"},   "chinese": False},
    "porsche:cayenne":         {"lo": 25_000_000, "hi": 70_000_000, "styles": {"SUV"},
                                "transmission": "auto",   "tags": {"luxury","status","awd"},   "chinese": False},
    "porsche:panamera":        {"lo": 25_000_000, "hi": 60_000_000, "styles": {"Sedan"},
                                "transmission": "auto",   "tags": {"luxury","status","performance"}, "chinese": False},
    "porsche:taycan":          {"lo": 40_000_000, "hi": 85_000_000, "styles": {"Sedan"},
                                "transmission": "auto",   "tags": {"ev","luxury","performance"}, "chinese": False},
    "land rover:evoque":       {"lo": 9_000_000,  "hi": 25_000_000, "styles": {"Crossover"},
                                "transmission": "auto",   "tags": {"luxury","awd","status"},   "chinese": False},
    "land rover:velar":        {"lo": 20_000_000, "hi": 45_000_000, "styles": {"Crossover"},
                                "transmission": "auto",   "tags": {"luxury","status","awd"},   "chinese": False},
    "land rover:discovery":    {"lo": 15_000_000, "hi": 50_000_000, "styles": {"SUV"},
                                "transmission": "auto",   "tags": {"luxury","offroad","awd","7seat"}, "chinese": False},
    "land rover:range rover sport": {"lo": 20_000_000, "hi": 75_000_000, "styles": {"SUV"},
                                "transmission": "auto",   "tags": {"luxury","status","awd"},   "chinese": False},
    "land rover:defender":     {"lo": 35_000_000, "hi": 85_000_000, "styles": {"SUV"},
                                "transmission": "auto",   "tags": {"luxury","offroad","awd","status"}, "chinese": False},
    "land rover:range rover":  {"lo": 25_000_000, "hi": 95_000_000, "styles": {"SUV"},
                                "transmission": "auto",   "tags": {"luxury","status","awd"},   "chinese": False},
    "land rover:vogue":        {"lo": 25_000_000, "hi": 95_000_000, "styles": {"SUV"},
                                "transmission": "auto",   "tags": {"luxury","status","awd"},   "chinese": False},
    "lexus:ct200h":            {"lo": 4_000_000,  "hi": 7_500_000,  "styles": {"Hatchback"},
                                "transmission": "auto",   "tags": {"hybrid","luxury","city"},  "chinese": False},
    "lexus:is":                {"lo": 5_000_000,  "hi": 15_000_000, "styles": {"Sedan"},
                                "transmission": "auto",   "tags": {"luxury","sports","status"}, "chinese": False},
    "lexus:es":                {"lo": 8_000_000,  "hi": 25_000_000, "styles": {"Sedan"},
                                "transmission": "auto",   "tags": {"luxury","status","family"}, "chinese": False},
    "lexus:rx":                {"lo": 10_000_000, "hi": 35_000_000, "styles": {"SUV"},
                                "transmission": "auto",   "tags": {"luxury","status","awd"},   "chinese": False},
    "lexus:nx":                {"lo": 12_000_000, "hi": 28_000_000, "styles": {"Crossover"},
                                "transmission": "auto",   "tags": {"luxury","city","awd"},     "chinese": False},
    "lexus:lx570":             {"lo": 30_000_000, "hi": 75_000_000, "styles": {"SUV"},
                                "transmission": "auto",   "tags": {"luxury","status","offroad","awd"}, "chinese": False},
    "lexus:lx":                {"lo": 30_000_000, "hi": 75_000_000, "styles": {"SUV"},
                                "transmission": "auto",   "tags": {"luxury","status","offroad","awd"}, "chinese": False},
    "lexus:lx600":             {"lo": 90_000_000, "hi": 140_000_000,"styles": {"SUV"},
                                "transmission": "auto",   "tags": {"luxury","status","offroad","awd"}, "chinese": False},
}


# ---------------------------------------------------------------------------
# CANONICAL MODEL NAME MAP
# Normalizes LLM output variants to scraper-safe names for runner.py.
# ---------------------------------------------------------------------------

_CANONICAL_MODEL_MAP: dict[str, str] = {
    "land cruiser prado":        "Prado",
    "toyota land cruiser prado": "Prado",
    "lc prado":                  "Prado",
    "lc300":                     "Land Cruiser",
    "lc200":                     "Land Cruiser",
    "v8":                        "Land Cruiser",
    "revo hilux":                "Hilux",
    "hilux revo":                "Hilux",
    "corolla altis":             "Corolla",
    "corolla grande":            "Corolla",
    "corolla xli":               "Corolla",
    "corolla gli":               "Corolla",
    "markx":                     "Mark X",
    "yaris cross":               "Yaris Cross",
    "civic fc":                  "Civic",
    "civic oriel":               "Civic",
    "civic vti":                 "Civic",
    "city aspire":               "City",
    "city prosmatec":            "City",
    "br-v":                      "BR-V",
    "brv":                       "BR-V",
    "hr-v":                      "HR-V",
    "hrv":                       "HR-V",
    "cr-v":                      "CR-V",
    "crv":                       "CR-V",
    "n-box":                     "N-Box",
    "nbox":                      "N-Box",
    "n-wgn":                     "N-WGN",
    "nwgn":                      "N-WGN",
    "step wgn":                  "StepWGN",
    "wagon r":                   "Wagon R",
    "wagonr":                    "Wagon R",
    "alto 660":                  "Alto 660cc",
    "x-trail":                   "X-Trail",
    "xtrail":                    "X-Trail",
    "note e-power":              "Note e-Power",
    "rx-8":                      "RX-8",
    "rx8":                       "RX-8",
    "cx-5":                      "CX-5",
    "cx5":                       "CX-5",
    "mazda2":                    "Demio",
    "demio/mazda2":              "Demio",
    "zs ev":                     "ZS EV",
    "oshan x7":                  "Oshan X7",
    "uni-t":                     "Uni-T",
    "deepal s07":                "Deepal S07",
    "deepal l07":                "Deepal L07",
    "h6 hev":                    "H6 HEV",
    "tiggo 4 pro":               "Tiggo 4 Pro",
    "tiggo 8 pro":               "Tiggo 8 Pro",
    "atto 3":                    "Atto 3",
    "tank 500":                  "Tank 500",
    "ora 03":                    "Ora 03",
    "3 series":                  "3 Series",
    "5 series":                  "5 Series",
    "7 series":                  "7 Series",
    "c-class":                   "C-Class",
    "e-class":                   "E-Class",
    "s-class":                   "S-Class",
    "range rover":               "Range Rover",
    "range rover sport":         "Range Rover Sport",
    "vogue":                     "Vogue",
    "evoque":                    "Evoque",
    "velar":                     "Velar",
    "e-tron":                    "e-tron",
    "e-tron gt":                 "e-tron GT",
    "lx 570":                    "LX570",
    "lx 600":                    "LX600",
    "pajero sport":              "Pajero Sport",
}


# ---------------------------------------------------------------------------
# USE-CASE PRINCIPLES
#
# Replaces few-shot examples that taught copying specific cars.
# These are generalised reasoning rules the LLM applies to whatever cars
# are in the eligible list — so they work for any budget and any edge case.
#
# Structure: use_case keyword → principle text
# The LLM receives only the principles relevant to the buyer's use_case.
# If no use_case is specified, the "general" block is used.
# ---------------------------------------------------------------------------

_USE_CASE_PRINCIPLES: dict[str, str] = {

    "family": """
USE-CASE PRINCIPLES — Family / Daily:
  - PAKISTANI MARKET REALITY: "Family car" means Sedan with a trunk ("diggi"). Pakistani families strongly prefer Sedans (Corolla, City, Civic) over hatchbacks for boot space and social status.
  - Rank 1st: Sedans with reliable service networks — Corolla, City, Civic, Yaris, Allion, Premio.
  - Rank 2nd: Crossovers that double as family haulers — BR-V, Vezel, Sportage.
  - Rank 3rd: 7-seat dedicated options IF buyer mentions "7 seater" or "multiple passengers" — Rush, Sorento, Carnival.
  - HARD RULE: DO NOT recommend Vans (APV, Bolan, Every, Hiace, Sienta) for a "family car" query UNLESS the user EXPLICITLY asks for "7 seater", "van", or "multiple passengers". A van is not a family sedan.
  - HARD RULE: DO NOT recommend hatchbacks (Wagon R, Cultus, N-Box) when budget allows a sedan. Budget >= PKR 15 lacs always has sedan options.
  - Rank higher: Toyota and Honda over other brands — best reliability track record, widest service network, highest resale in Pakistan.
  - Rank higher: cars with known sunroof trims if user mentions sunroof (Corolla Grande, Civic RS, Mark X).
  - Avoid: sports-tuned cars (RX-8, BRZ) — stiff ride and no boot space.
""",

    "city": """
USE-CASE PRINCIPLES — City Commute:
  - Prioritise: fuel economy, parking ease (shorter wheelbase), maneuverability
  - Rank higher: hatchbacks and small crossovers over large sedans for tight city streets
  - For budgets under PKR 30 lacs: hatchbacks (Swift, Vitz, Passo) beat sedans on practicality
  - For budgets PKR 30–60 lacs: Vezel, C-HR, Stonic offer the best city crossover experience
  - Automatic transmission is strongly preferred for stop-and-go Lahore/Karachi traffic
  - Avoid: large body-on-frame SUVs (Fortuner, Prado) — fuel costs are punishing for city-only use
  - Avoid: sports cars with stiff suspension — Pakistani road conditions punish ride quality
""",

    "offroad": """
USE-CASE PRINCIPLES — Off-road / Rugged:
  - HARD RULE: body-on-frame or proven AWD/4WD ONLY — Fortuner, Prado, Land Cruiser, Patrol, Hilux, Pajero
  - Unibody crossovers (Vezel, Stonic, C-HR) are NOT suitable — do not recommend them for offroad use
  - Rank higher: cars with locking differentials and proper 4L mode
  - Ground clearance matters: minimum 200mm for serious offroad
  - Budget reality: capable 4x4s start at PKR 80 lacs — if budget is under 60 lacs, be honest that options are limited and suggest Pajero or Jimny as entry-level capable options
  - Avoid: road-tuned AWD (Subaru XV, Tucson) for genuine offroad — they are road-biased
""",

    "sports": """
USE-CASE PRINCIPLES — Sports / Performance / Fun Driving:
  - Prioritise: rear-wheel drive, manual option, engine character, suspension tuning
  - JDM hierarchy for sports (budget ascending): RX-8 → Subaru BRZ/Impreza WRX → Mark X V6 → Crown Athlete → BMW 3 Series M-Sport
  - For budgets under PKR 50 lacs: Mark X (V6, RWD) and Subaru Impreza (WRX, AWD) are the top choices
  - Mazda3 is sporty but FWD — mention this limitation in rationale
  - Avoid: recommending Corolla, City, or Civic as "sports" picks — they are commuter cars
  - If automatic requested for sports: Mark X, Crown Athlete, BMW 3 Series — all auto
  - If manual allowed: Impreza WRX, BRZ, RX-8 have genuine manual options
""",

    "luxury": """
USE-CASE PRINCIPLES — Luxury / Status / Aura:
  - HARD RULE: If budget >= PKR 3 crore (30M), NEVER recommend Fortuner or Sportage — these are mid-tier, not luxury
  - Budget 1–3 crore: Prado, Patrol, BMW X5, Lexus RX are the correct status picks
  - Budget 3–8 crore: Land Cruiser, Range Rover, BMW X7, Porsche Cayenne territory
  - Budget above 8 crore: LX600, Range Rover Vogue, Defender, high-spec LC300
  - Pakistani status hierarchy (SUVs): Mehran < Cultus < Civic < Corolla < Fortuner < Prado < Land Cruiser < LX600/Range Rover
  - For sedans with luxury: BMW 3/5 Series, Mercedes C/E Class, Audi A4/A6, Porsche Panamera
  - Avoid: recommending non-luxury brands (Suzuki, Kia Stonic, Haval) for luxury-intent queries regardless of what's on the eligible list
""",

    "ride_sharing": """
USE-CASE PRINCIPLES — Ride Sharing / Commercial:
  - Prioritise: fuel economy, low maintenance cost, spacious cabin for passengers
  - Most important for ride share: diesel or hybrid variants have lowest per-km cost
  - Corolla, City, Civic have highest passenger perception for Uber/Careem premium
  - For economy ride share: Vitz, Cultus, Passo keep costs minimal
  - Avoid: sports cars, kei cars (too small for backseat passengers)
  - Automatic preferred — driver spends 8+ hours in the car daily
""",

    "general": """
USE-CASE PRINCIPLES — General (no specific use case stated):
  - Default to reliability and resale value as primary ranking factors
  - RELIABILITY HIERARCHY in Pakistan: Toyota > Honda > Suzuki > Kia/Hyundai > Chinese brands
  - RESALE VALUE HIERARCHY: Toyota Corolla/Civic/City hold the best resale in their respective segments
  - Toyota and Honda get a reliability/resale bonus — prefer them over equally-priced alternatives
  - Prefer models with established parts supply chains in major Pakistani cities (Lahore, Karachi, Islamabad)
  - If budget is wide, pick 1 reliable mainstream (Toyota/Honda) + 1 alternative make to show diversity
  - Never recommend niche sports or offroad cars for unspecified use cases
""",
}


def _get_relevant_principles(use_case: str | None, is_luxury: bool) -> str:
    """
    Returns the principle block most relevant to the buyer's use case.
    Combines luxury principles when is_luxury_request is True even if
    the stated use_case is something else (e.g., "family" + luxury = both).
    """
    if not use_case:
        block = _USE_CASE_PRINCIPLES["general"]
    else:
        # Map loose use_case strings to principle keys
        uc_lower = use_case.lower()
        if any(w in uc_lower for w in ["family", "daily", "school", "kids", "children"]):
            block = _USE_CASE_PRINCIPLES["family"]
        elif any(w in uc_lower for w in ["city", "commute", "urban", "traffic"]):
            block = _USE_CASE_PRINCIPLES["city"]
        elif any(w in uc_lower for w in ["offroad", "off-road", "4x4", "adventure", "rugged", "mountain"]):
            block = _USE_CASE_PRINCIPLES["offroad"]
        elif any(w in uc_lower for w in ["sport", "performance", "fun", "fast", "racing", "drift"]):
            block = _USE_CASE_PRINCIPLES["sports"]
        elif any(w in uc_lower for w in ["luxury", "premium", "vip", "aura", "status", "boss"]):
            block = _USE_CASE_PRINCIPLES["luxury"]
        elif any(w in uc_lower for w in ["ride", "uber", "careem", "commercial", "taxi"]):
            block = _USE_CASE_PRINCIPLES["ride_sharing"]
        else:
            block = _USE_CASE_PRINCIPLES["general"]

    # Always append luxury principles if explicitly requested
    if is_luxury and "luxury" not in (use_case or "").lower():
        block += _USE_CASE_PRINCIPLES["luxury"]

    return block.strip()


# ---------------------------------------------------------------------------
# MODEL-FEATURE KNOWLEDGE MAP
#
# Answers: "Does this model have feature X in any trim?"
# Used by get_eligible_cars() to HARD-EXCLUDE models that can NEVER satisfy
# a required feature — before the LLM ever sees them.
#
# Format: "make:model" → { "feature_key": trim_list_or_None }
#   trim_list = list of trims that have the feature (can be ["any"] if all do)
#   None      = this model NEVER has this feature in any trim
#
# Feature keys should match _FEATURE_KEYWORDS keys in recommend_normalizer.py.
# ---------------------------------------------------------------------------

MODEL_FEATURE_KNOWLEDGE: dict[str, dict[str, list[str] | None]] = {
    # ── Sunroof availability by model ────────────────────────────────────────
    # None = no trim of this model has factory sunroof
    # ["any"] = all/most trims have it
    # ["Trim1","Trim2"] = only these trims have it
    "toyota:corolla":          {"sunroof": ["Grande", "Altis Grande", "X Corolla"]},
    "toyota:yaris":            {"sunroof": None},        # Yaris has no sunroof in any trim
    "toyota:aqua":             {"sunroof": None},
    "toyota:vitz":             {"sunroof": None},
    "toyota:passo":            {"sunroof": None},
    "toyota:probox":           {"sunroof": None},        # cargo van — never
    "toyota:rush":             {"sunroof": None},        # Rush has no factory sunroof
    "toyota:fortuner":         {"sunroof": ["VRZ", "Sigma3", "Legender"]},
    "toyota:hilux":            {"sunroof": None},
    "toyota:prado":            {"sunroof": ["any"]},
    "toyota:land cruiser":     {"sunroof": ["any"]},
    "toyota:camry":            {"sunroof": ["any"]},
    "toyota:crown":            {"sunroof": ["any"]},
    "toyota:mark x":           {"sunroof": ["250G", "300G", "350G", "any"]},
    "toyota:allion":           {"sunroof": ["A20", "A25", "250G"]},
    "toyota:premio":           {"sunroof": ["F L Package", "G L Package", "250G"]},
    "toyota:c-hr":             {"sunroof": ["any"]},
    "toyota:raize":            {"sunroof": ["Z", "G"]},
    "toyota:yaris cross":      {"sunroof": ["any"]},
    "toyota:alphard":          {"sunroof": ["any"]},
    "toyota:vellfire":         {"sunroof": ["any"]},
    "honda:city":              {"sunroof": ["Aspire", "1.5 Aspire", "RS"]},
    "honda:civic":             {"sunroof": ["RS", "Oriel 1.5T", "VTi Oriel Prosmatec 1.8"]},
    "honda:br-v":              {"sunroof": None},
    "honda:hr-v":              {"sunroof": ["any"]},
    "honda:vezel":             {"sunroof": ["RS", "Z", "e:HEV Z"]},
    "honda:accord":            {"sunroof": ["any"]},
    "honda:cr-v":              {"sunroof": ["any"]},
    "honda:fit":               {"sunroof": None},
    "honda:freed":             {"sunroof": None},
    "honda:grace":             {"sunroof": ["Hybrid EX"]},
    "honda:n-box":             {"sunroof": None},        # kei car — no sunroof
    "honda:n-wgn":             {"sunroof": None},
    "suzuki:baleno":           {"sunroof": None},        # local Baleno never had sunroof
    "suzuki:liana":            {"sunroof": None},
    "suzuki:swift":            {"sunroof": None},        # local swift no sunroof
    "suzuki:cultus":           {"sunroof": None},
    "suzuki:wagon r":          {"sunroof": None},
    "suzuki:alto":             {"sunroof": None},
    "suzuki:alto 660cc":       {"sunroof": None},        # JDM kei — no sunroof
    "suzuki:jimny":            {"sunroof": None},
    "kia:sportage":            {"sunroof": ["Alpha AWD", "FWD Alpha", "FWD"]},
    "kia:stonic":              {"sunroof": None},
    "kia:sorento":             {"sunroof": ["any"]},
    "hyundai:tucson":          {"sunroof": ["any"]},
    "hyundai:elantra":         {"sunroof": ["GLS", "GL"]},
    "mitsubishi:pajero sport": {"sunroof": ["GLS", "Exceed"]},
    "mitsubishi:pajero":       {"sunroof": ["GLS", "3.5 V6"]},
    "nissan:patrol":           {"sunroof": ["any"]},
    "nissan:x-trail":          {"sunroof": ["any"]},
    "subaru:forester":         {"sunroof": ["any"]},
    "subaru:xv":               {"sunroof": ["any"]},
    "mazda:cx-5":              {"sunroof": ["any"]},
    "bmw:3 series":            {"sunroof": ["any"]},
    "bmw:5 series":            {"sunroof": ["any"]},
    "bmw:x3":                  {"sunroof": ["any"]},
    "bmw:x5":                  {"sunroof": ["any"]},
    "mercedes-benz:c-class":   {"sunroof": ["any"]},
    "mercedes-benz:e-class":   {"sunroof": ["any"]},
    "mercedes-benz:glc":       {"sunroof": ["any"]},
    "mercedes-benz:gle":       {"sunroof": ["any"]},
    "audi:a4":                 {"sunroof": ["any"]},
    "audi:q5":                 {"sunroof": ["any"]},
    "lexus:rx":                {"sunroof": ["any"]},
    "lexus:es":                {"sunroof": ["any"]},
    "land rover:range rover":  {"sunroof": ["any"]},
    "land rover:defender":     {"sunroof": ["any"]},
    "porsche:cayenne":         {"sunroof": ["any"]},
    "daihatsu:mira":           {"sunroof": None},
    "daihatsu:move":           {"sunroof": None},
    "daihatsu:tanto":          {"sunroof": None},
    "daihatsu:rocky":          {"sunroof": ["G", "Premium"]},
    "nissan:dayz":             {"sunroof": None},
    "nissan:roox":             {"sunroof": None},
    "mg:hs":                   {"sunroof": ["any"]},
    "mg:zs":                   {"sunroof": None},
    "haval:jolion":            {"sunroof": ["any"]},
    "haval:h6":                {"sunroof": ["any"]},
    "changan:alsvin":          {"sunroof": None},
}

# ---------------------------------------------------------------------------
# ELIGIBLE CAR LIST BUILDER
# Single function — derives everything from CAR_REGISTRY.
#
# v2.0 additions:
#   - priority field: breaks fit-score ties. Priority 1 beats priority 2
#     at the same budget fit. Prevents Liana ranking above Corolla at 22 lacs.
#   - feature_filter: when required_features contains a feature that requires
#     sunroof/specific trim, hard-excludes models that can NEVER have it.
#     Models not in MODEL_FEATURE_KNOWLEDGE pass through (unknown = allow).
#   - JDM Alto protection: when "suzuki:alto 660cc" is selected, sets
#     jdm_force_trim flag in the display so LLM knows to use trim="660cc".
#   - is_youth_query: when use_case implies young buyer, deprioritises
#     kei box vans (Wagon R, Bolan, Every) even if budget-eligible.
# ---------------------------------------------------------------------------

def get_eligible_cars(
    max_budget: int,
    min_budget: int,
    allow_chinese: bool,
    body_style: str | None = None,
    is_apex_luxury: bool = False,
    transmission_req: str | None = None,
    excluded_models: list[str] | None = None,
    required_features: list[str] | None = None,
    is_youth_query: bool = False,
) -> str:
    """
    Returns a priority-weighted, fit-score-sorted eligible car list as a prompt string.

    Filters applied (in order, all deterministic Python):
      1. Body style       — hard match against CAR_REGISTRY styles set
      2. Chinese gate     — drop chinese=True unless allow_chinese=True
      3. Transmission     — drop manual-only when user requests Automatic
      4. Budget overlap   — [min_budget,max_budget] must intersect [lo,hi]
      5. Apex luxury gate — drop cars too cheap for a luxury budget
      6. Feature gate     — drop models that CAN NEVER have a required feature
                            (e.g. Rush has no factory sunroof → excluded for sunroof query)
      7. Exclusion gate   — drop already-tried/shown models

    Scoring (composite — higher = shown first to LLM):
      fit_score    = 0.6 × budget_coverage + 0.4 × budget_centrality
      priority_boost = (3 - priority) × 0.15  → priority 1 gets +0.30, priority 2 gets +0.15
      youth_penalty  = -0.20 for kei box vans when is_youth_query=True
      final_score    = fit_score + priority_boost + youth_penalty

    JDM Alto protection:
      When "suzuki:alto 660cc" appears in the list, it is annotated with
      "(JDM 660cc — use trim='660cc' in scraper)" to prevent the LLM from
      picking it as plain "Alto" which would flood local Alto listings.
    """
    excluded_lower = {m.lower() for m in (excluded_models or [])}

    # Build set of features that require sunroof capability
    needs_sunroof = False
    if required_features:
        sunroof_keywords = {"sunroof", "panoramic sunroof", "moonroof", "panoramic"}
        needs_sunroof = any(
            any(kw in feat.lower() for kw in sunroof_keywords)
            for feat in required_features
        )

    # Kei box vans that look awkward for young buyers
    _KEI_BOX_VANS = {"suzuki:wagon r", "suzuki:every", "suzuki:bolan",
                     "honda:n-wgn", "honda:n-box", "daihatsu:move",
                     "daihatsu:tanto", "nissan:roox", "nissan:dayz"}

    scored: list[tuple[float, str, int, int, str]] = []  # (score, display, lo, hi, note)

    for key, info in CAR_REGISTRY.items():
        lo    = info["lo"]
        hi    = info["hi"]
        make, model = key.split(":", 1)

        # 1. Body style gate
        if body_style and body_style not in info["styles"]:
            continue

        # 2. Chinese gate
        if info["chinese"] and not allow_chinese:
            continue

        # 3. Transmission gate
        if transmission_req == "Automatic" and info["transmission"] == "manual":
            continue

        # 4. Budget overlap
        if max_budget > 0 and max_budget < lo * 0.80:
            continue
        if min_budget > 0 and hi < min_budget * 0.80:
            continue

        # 5. Apex luxury gate
        if is_apex_luxury and max_budget > 0 and hi < max_budget * 0.55:
            continue

        # 6. Feature gate — hard exclude models that CAN NEVER have sunroof
        if needs_sunroof:
            feature_info = MODEL_FEATURE_KNOWLEDGE.get(key, {})
            sunroof_trims = feature_info.get("sunroof", [])  # default [] = unknown = pass
            if sunroof_trims is None:
                # None explicitly means this model has no factory sunroof in any trim
                continue

        # 7. Exclusion gate
        display_lower = f"{make} {model}".lower()
        if any(ex in display_lower for ex in excluded_lower):
            continue

        # Fit score
        if max_budget > 0:
            midpoint  = (lo + hi) / 2
            centered  = 1.0 - abs(max_budget - midpoint) / max(midpoint, 1)
            overlap   = max(0, min(max_budget, hi) - max(min_budget, lo))
            coverage  = overlap / max(hi - lo, 1)
            fit_score = 0.6 * coverage + 0.4 * max(0.0, min(1.0, centered))
        else:
            fit_score = 0.5

        # Priority boost — prevents Liana/Baleno ranking above Corolla/Civic
        # Reliability/resale bonus — Toyota/Honda with "reliability" tag get +0.10 extra
        priority       = info.get("priority", 2)
        priority_boost = (3 - priority) * 0.15   # priority 1 → +0.30, 2 → +0.15, 3 → 0
        tags = info.get("tags", set())
        reliability_bonus = 0.10 if ("reliability" in tags and "resale" in tags) else 0.0
        priority_boost += reliability_bonus

        # Youth penalty — kei box vans deprioritised for young buyer queries
        youth_penalty = -0.20 if (is_youth_query and key in _KEI_BOX_VANS) else 0.0

        final_score = fit_score + priority_boost + youth_penalty

        # Display string with JDM annotation
        display = f"{make.title()} {model.title()}"
        note    = ""
        if key == "suzuki:alto 660cc":
            note = " [JDM — always use trim='660cc' to avoid local Alto flood]"
        elif needs_sunroof:
            feature_info  = MODEL_FEATURE_KNOWLEDGE.get(key, {})
            sunroof_trims = feature_info.get("sunroof", [])
            if sunroof_trims and sunroof_trims != ["any"]:
                note = f" [sunroof only in: {', '.join(sunroof_trims)}]"
            elif sunroof_trims == ["any"]:
                note = " [sunroof: all trims]"

        scored.append((final_score, display, lo, hi, note))

    if not scored:
        style_note = f" matching body style '{body_style}'" if body_style else ""
        feat_note  = " with sunroof" if needs_sunroof else ""
        return (
            f"No eligible cars found{style_note}{feat_note} for this budget. "
            "Return an empty array []."
        )

    # Sort by final_score descending — best fit + highest priority appears first
    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:15]

    lines = [
        f"  {display}: PKR {lo:,} – {hi:,}{note}"
        for _, display, lo, hi, note in top
    ]

    budget_note  = f"PKR {min_budget:,} – {max_budget:,}" if max_budget > 0 else "no budget limit"
    style_note   = f", body style: {body_style}" if body_style else ""
    feat_note    = ", requires sunroof" if needs_sunroof else ""
    total_note   = f"{len(scored)} eligible" + (f" (showing top {len(top)})" if len(scored) > 15 else "")

    suffix = ""
    if needs_sunroof:
        suffix = (
            "\nSUNROOF NOTE: Cars marked '[sunroof only in: X]' must be "
            "recommended with that specific trim. Cars marked '[sunroof: all trims]' "
            "are safe to recommend without specifying trim.\n"
        )

    return (
        f"ELIGIBLE CARS ({total_note}, budget {budget_note}{style_note}{feat_note}):\n"
        + "\n".join(lines)
        + "\n\nPick ONLY from this list. "
        "These are pre-verified against budget, body style, transmission, and feature availability.\n"
        + suffix
    )


# ---------------------------------------------------------------------------
# POST-SELECTION VALIDATOR
# Second line of defence — should rarely fire since get_eligible_cars()
# already filtered, but catches edge cases where LLM ignores the list.
# ---------------------------------------------------------------------------

def _validate_targets(targets: list, constraints: dict) -> list:
    max_budget    = constraints.get("max_budget", 0)
    min_budget    = constraints.get("min_budget", 0)
    allow_chinese = constraints.get("allow_chinese", False)
    body_style    = constraints.get("body_style")
    is_apex       = constraints.get("is_apex_luxury", False)

    valid = []
    for t in targets:
        make_lower  = t.make.lower().strip()
        model_lower = t.model.lower().strip()
        key         = f"{make_lower}:{model_lower}"
        info        = CAR_REGISTRY.get(key)

        # Chinese gate
        if info and info["chinese"] and not allow_chinese:
            print(f"[Validator] Dropping {t.make} {t.model} — Chinese brand not requested")
            continue

        # Body style gate (second line of defence)
        if info and body_style and body_style not in info["styles"]:
            print(f"[Validator] Dropping {t.make} {t.model} — not a {body_style}")
            continue

        # Budget gates
        if info and max_budget > 0:
            lo, hi = info["lo"], info["hi"]
            if max_budget < lo * 0.85:
                print(f"[Validator] Dropping {t.make} {t.model} — floor PKR {lo:,} unreachable")
                continue
            if min_budget > 0 and hi < min_budget * 0.80:
                print(f"[Validator] Dropping {t.make} {t.model} — ceiling PKR {hi:,} below budget floor")
                continue

        # Apex luxury gate
        if is_apex and info and max_budget > 0:
            if info["hi"] < max_budget * 0.55:
                print(f"[Validator] Dropping {t.make} {t.model} — too cheap for apex luxury query")
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
    max_budget:        Optional[int]                                                                 = None
    body_style:        Optional[Literal["SUV", "Sedan", "Hatchback", "Pickup", "Crossover", "Van"]] = None
    transmission:      Optional[Literal["Automatic", "Manual"]]                                     = None
    use_case:          Optional[str]                                                                 = None
    origin_pref:       Optional[Literal["JDM", "Local", "European", "Chinese"]]                     = None
    is_luxury_request: bool                                                                          = False
    required_features: list[str]                                                                     = Field(default_factory=list)


async def extract_intent(user_prompt: str) -> UserIntent:
    """Phase 1 LLM call — pure signal extraction, temperature 0.0."""
    prompt = (
        f"Extract the user's car search intent from this query: '{user_prompt}'\n\n"
        "Rules:\n"
        "- Convert Pakistani currency precisely:\n"
        "  '1 crore' -> 10000000,  '5 crore'  -> 50000000,  '10 crore' -> 100000000\n"
        "  '20 lacs' -> 2000000,   '50 lacs'  -> 5000000,   '80 lacs'  -> 8000000\n"
        "  Always convert — never leave as text.\n"
        "- use_case: brief phrase — 'family daily', 'city commute', 'offroad adventure',\n"
        "  'sports driving', 'ride sharing'. Infer from context if clear.\n"
        "- is_luxury_request: true ONLY for explicit words: 'luxury', 'premium', 'aura',\n"
        "  'VIP', 'boss car', 'status symbol', 'high-end', 'shaan'.\n"
        "- required_features: only features EXPLICITLY mentioned. Never infer.\n"
        "- body_style: 'car' or 'sedan' -> Sedan. 'SUV' or '4x4' -> SUV.\n"
        "  'small car' or 'hatchback' -> Hatchback. 'pickup' or 'truck' -> Pickup.\n"
        "  'crossover' or 'compact SUV' -> Crossover.\n"
        "- origin_pref: 'Japanese' or 'JDM' -> JDM. 'European' -> European. "
        "'Chinese' -> Chinese. 'local' -> Local.\n"
        "- Leave null if not clearly stated — do not guess."
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
    Phase 1 Python gate — budget floor + derived flags only.
    No tiers in the constraints dict — tier logic lives in get_eligible_cars()
    via the is_apex_luxury flag and the fit-score sorting.
    """
    max_budget = intent.max_budget or 0
    min_budget = 0

    if max_budget > 0:
        # Wider floor for luxury — heavy depreciation on high-end cars
        floor_pct  = 0.50 if max_budget >= 30_000_000 else 0.70
        min_budget = int(max_budget * floor_pct)

    # Apex luxury: 3 crore+ OR explicit luxury signal at 1 crore+
    is_apex_luxury = (
        max_budget >= 30_000_000
        or (intent.is_luxury_request and max_budget >= 10_000_000)
    )

    return {
        "min_budget":        min_budget,
        "max_budget":        max_budget,
        "min_year":          0,
        "is_apex_luxury":    is_apex_luxury,
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
    Phase 2 LLM call — ranking and judgment only.

    Prompt structure:
      1. Use-case principles — generalised reasoning rules (not example copying)
      2. Eligible car list   — Python-filtered, fit-score sorted, hard-gated
      3. Buyer profile       — this specific buyer's constraints
      4. Ranking rules       — concise instructions for what to do
    """
    max_budget        = constraints.get("max_budget", 0)
    min_budget        = constraints.get("min_budget", 0)
    allow_chinese     = constraints.get("allow_chinese", False)
    body_style        = constraints.get("body_style")
    transmission      = constraints.get("transmission")
    use_case          = constraints.get("use_case")
    is_apex_luxury    = constraints.get("is_apex_luxury", False)
    is_luxury         = constraints.get("is_luxury_request", False)
    origin_pref       = constraints.get("origin_pref")
    required_features = constraints.get("required_features", [])

    # Detect youth/university buyer from use_case for kei box van deprioritisation
    is_youth_query = bool(use_case and any(
        w in use_case.lower()
        for w in ["university", "student", "young", "youth", "college", "boy", "boys", "youngster"]
    ))

    eligible_list = get_eligible_cars(
        max_budget=max_budget,
        min_budget=min_budget,
        allow_chinese=allow_chinese,
        body_style=body_style,
        is_apex_luxury=is_apex_luxury,
        transmission_req=transmission,
        excluded_models=None,
        required_features=required_features,
        is_youth_query=is_youth_query,
    )

    principles = _get_relevant_principles(use_case, is_luxury)

    budget_str = (
        f"PKR {min_budget:,} – {max_budget:,}" if max_budget > 0
        else "No budget stated"
    )

    buyer_profile = {
        "budget":             budget_str,
        "body_style":         body_style         or "No preference",
        "transmission":       transmission       or "No preference",
        "use_case":           use_case           or "General",
        "origin_pref":        origin_pref        or "No preference (default: Japanese/Korean)",
        "is_luxury_request":  is_luxury,
        "is_apex_luxury":     is_apex_luxury,
        "required_features":  required_features,
    }

    # Build sunroof trim instruction if needed
    sunroof_rule = ""
    if required_features and any(
        "sunroof" in f.lower() or "panoramic" in f.lower()
        for f in required_features
    ):
        sunroof_rule = (
            "\nSUNROOF RULE: The buyer requires a sunroof. "
            "Cars marked '[sunroof only in: X]' MUST be recommended with that specific trim. "
            "Do NOT recommend a car marked '[sunroof only in: X]' without setting trim to one of those values. "
            "Cars marked '[sunroof: all trims]' are safe without trim specification.\n"
        )

    prompt = (
        f"{principles}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{eligible_list}\n"
        f"{sunroof_rule}"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "TASK: You are a Pakistani used car expert. "
        "From the eligible list above, pick the best 1–3 cars for this buyer.\n\n"
        f"BUYER PROFILE:\n{json.dumps(buyer_profile, indent=2)}\n\n"
        "RANKING RULES:\n"
        "1. LIST ONLY: Never suggest a car not in the eligible list. "
        "The list is pre-verified by Python — trust it completely.\n"
        "2. PRINCIPLES FIRST: Apply the use-case principles above when ranking. "
        "They encode real Pakistani market knowledge — follow them.\n"
        "3. PRIORITY ORDER: Cars listed higher in the eligible list are ranked higher "
        "by budget fit AND market standing. Prefer them unless the buyer's use-case "
        "clearly makes a lower-ranked car more suitable.\n"
        "4. ORIGIN: If origin_pref is JDM, prefer JDM cars and specify exact trim "
        "(e.g. trim='G Grade', trim='RS Advance'). If European, prefer BMW/Audi/Mercedes.\n"
        "5. JDM ALTO PROTECTION: If recommending 'Suzuki Alto 660cc', ALWAYS set "
        "trim='660cc' — this prevents flooding with local Suzuki Alto listings.\n"
        "6. DIVERSITY: Pick from 2–3 different makes when the list allows. "
        "Avoid all-Toyota or all-Honda picks unless the list genuinely forces it.\n"
        "7. QUANTITY: Return EXACTLY 3 targets if 3 or more eligible cars exist in the list. "
        "Only return fewer than 3 if the eligible list physically has fewer than 3 cars.\n"
        "8. TRIM: For sunroof-required queries, use the trim specified in the list. "
        "Otherwise leave empty unless a trim meaningfully changes the car.\n"
        "9. RATIONALE: 1 buyer-friendly sentence — explain WHY this specific car "
        "fits this specific buyer. No generic descriptions."
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


def _deduplicate_and_format(
    raw_targets: list[CarTargetRaw],
    constraints: dict,
) -> list[dict]:
    """Phase 2 Python gate — validate, canonicalize, deduplicate, format to 9-key contract."""
    validated = _validate_targets(raw_targets, constraints)

    seen:      set[tuple[str, str]] = set()
    formatted: list[dict]           = []

    for raw in validated:
        make_lower      = raw.make.lower().strip()
        model_raw       = raw.model.strip()
        canonical_model = _CANONICAL_MODEL_MAP.get(model_raw.lower(), model_raw)

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
# PUBLIC ALIAS — recommend_routes.py imports _deduplicate_and_format_targets
# Keep this alias so the route file doesn't need changes.
# ---------------------------------------------------------------------------
_deduplicate_and_format_targets = _deduplicate_and_format


# ---------------------------------------------------------------------------
# PHASE 3: FALLBACK & EXTENSION PIPELINES
# ---------------------------------------------------------------------------

async def get_fallback_recommendations(
    constraints: dict,
    excluded_models: list[str],
) -> list[dict]:
    """Fires on NORMALIZER_ZERO — returns exactly 1 replacement."""
    max_budget      = constraints.get("max_budget", 0)
    min_budget      = constraints.get("min_budget", 0)
    allow_chinese   = constraints.get("allow_chinese", False)
    body_style      = constraints.get("body_style")
    is_apex_luxury  = constraints.get("is_apex_luxury", False)
    transmission    = constraints.get("transmission")
    use_case        = constraints.get("use_case")
    is_luxury       = constraints.get("is_luxury_request", False)

    required_features = constraints.get("required_features", [])
    eligible_list = get_eligible_cars(
        max_budget=max_budget,
        min_budget=min_budget,
        allow_chinese=allow_chinese,
        body_style=body_style,
        is_apex_luxury=is_apex_luxury,
        transmission_req=transmission,
        excluded_models=excluded_models,
        required_features=required_features,
    )

    principles = _get_relevant_principles(use_case, is_luxury)

    budget_str = (
        f"PKR {min_budget:,} – {max_budget:,}" if max_budget > 0
        else "No budget stated"
    )

    prompt = (
        f"{principles}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{eligible_list}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "TASK: Pick exactly 1 replacement car. Previous picks had zero listings.\n\n"
        f"  Budget: {budget_str}\n"
        f"  Body style: {body_style or 'No preference'}\n"
        f"  Transmission: {transmission or 'No preference'}\n"
        f"  Use case: {use_case or 'General'}\n"
        f"  Required features: {json.dumps(required_features)}\n\n"
        f"Already tried (excluded from list above): {json.dumps(excluded_models)}\n\n"
        "Return exactly 1 target. Pick only from the eligible list. "
        "Apply the principles above. "
        "If the list is empty return []."
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
        valid = [CarTargetRaw.model_validate(item) for item in raw_list]
        valid = _validate_targets(valid, constraints)
        return _deduplicate_and_format(valid, constraints)
    except Exception as e:
        print(f"[FallbackMapper] Failed: {e}")
        traceback.print_exc()
        return []


async def get_extended_recommendations(
    original_constraints: dict,
    excluded_models: list[str],
) -> list[dict]:
    """Powers the 'Show More Options' button — returns 1-3 alternatives."""
    max_budget      = original_constraints.get("max_budget", 0)
    min_budget      = original_constraints.get("min_budget", 0)
    allow_chinese   = original_constraints.get("allow_chinese", False)
    body_style      = original_constraints.get("body_style")
    is_apex_luxury  = original_constraints.get("is_apex_luxury", False)
    transmission    = original_constraints.get("transmission")
    use_case        = original_constraints.get("use_case")
    is_luxury       = original_constraints.get("is_luxury_request", False)

    required_features = original_constraints.get("required_features", [])
    eligible_list = get_eligible_cars(
        max_budget=max_budget,
        min_budget=min_budget,
        allow_chinese=allow_chinese,
        body_style=body_style,
        is_apex_luxury=is_apex_luxury,
        transmission_req=transmission,
        excluded_models=excluded_models,
        required_features=required_features,
    )

    principles = _get_relevant_principles(use_case, is_luxury)

    budget_str = (
        f"PKR {min_budget:,} – {max_budget:,}" if max_budget > 0
        else "No budget stated"
    )

    prompt = (
        f"{principles}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{eligible_list}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "TASK: Pick 1–3 alternative 'Show More' cars from the eligible list above.\n\n"
        f"  Budget: {budget_str}\n"
        f"  Body style: {body_style or 'No preference'}\n"
        f"  Transmission: {transmission or 'No preference'}\n"
        f"  Use case: {use_case or 'General'}\n"
        f"  Required features: {json.dumps(required_features)}\n\n"
        f"Already shown (excluded from list above): {json.dumps(excluded_models)}\n\n"
        "Pick from different makes than already shown. "
        "Apply the principles above for ranking. "
        "Return 1 if only 1 good option exists. "
        "If none remain return []."
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
        valid = [CarTargetRaw.model_validate(item) for item in raw_list]
        valid = _validate_targets(valid, original_constraints)
        return _deduplicate_and_format(valid, original_constraints)
    except Exception as e:
        print(f"[ExtendedMapper] Failed: {e}")
        traceback.print_exc()
        return []