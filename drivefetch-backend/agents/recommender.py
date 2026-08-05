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
import re
from dotenv import load_dotenv
from google import genai
from google.genai import types
from typing import Optional, Literal
from pydantic import BaseModel, Field

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
client = genai.Client(api_key=GEMINI_API_KEY)

from agents.config import generate_content_resilient


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
                                "drive": "FWD", "transmission": "both",   "tags": {"economy","city"},          "chinese": False, "priority": 2},
    "suzuki:alto":             {"lo": 700_000,    "hi": 3_600_000,  "styles": {"Hatchback"},
                                "drive": "FWD", "transmission": "both",   "tags": {"economy","city"},          "chinese": False, "priority": 2},
    "suzuki:alto 660cc":       {"lo": 1_500_000,  "hi": 3_800_000,  "styles": {"Hatchback"},
                                "drive": "FWD", "transmission": "both",   "tags": {"economy","city","jdm"},    "chinese": False, "priority": 2},
    "suzuki:cultus":           {"lo": 1_000_000,  "hi": 4_500_000,  "styles": {"Hatchback"},
                                "drive": "FWD", "transmission": "both",   "tags": {"economy","city","family"}, "chinese": False, "priority": 2},
    "suzuki:wagon r":          {"lo": 1_500_000,  "hi": 3_500_000,  "styles": {"Hatchback"},
                                "drive": "FWD", "transmission": "both",   "tags": {"economy","city","family"}, "chinese": False, "priority": 2},
    "suzuki:swift":            {"lo": 1_200_000,  "hi": 5_200_000,  "styles": {"Hatchback"},
                                "drive": "FWD", "transmission": "both",   "tags": {"economy","city","sports"}, "chinese": False, "priority": 2},
    "suzuki:baleno":           {"lo": 800_000,    "hi": 1_500_000,  "styles": {"Sedan"},
                                "drive": "FWD", "transmission": "both",   "tags": {"economy","city","family"}, "chinese": False, "priority": 3},
    "suzuki:liana":            {"lo": 1_000_000,  "hi": 1_700_000,  "styles": {"Sedan"},
                                "drive": "FWD", "transmission": "both",   "tags": {"economy","family"},        "chinese": False, "priority": 3},
    "suzuki:hustler":          {"lo": 1_800_000,  "hi": 4_000_000,  "styles": {"Hatchback"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"economy","city","jdm"},    "chinese": False},
    "suzuki:spacia":           {"lo": 1_800_000,  "hi": 4_000_000,  "styles": {"Hatchback"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"economy","city","jdm","family"}, "chinese": False},
    "suzuki:solio":            {"lo": 2_000_000,  "hi": 4_500_000,  "styles": {"Hatchback"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"economy","city","jdm","family"}, "chinese": False},
    "suzuki:jimny":            {"lo": 2_500_000,  "hi": 8_500_000,  "styles": {"Crossover", "Mini SUV"},
                                "drive": "4x4", "transmission": "both",   "tags": {"offroad","awd","jdm"},     "chinese": False},
    "suzuki:every":            {"lo": 1_000_000,  "hi": 3_000_000,  "styles": {"Van"},
                                "drive": "FWD", "transmission": "both",   "tags": {"cargo","economy","jdm"},   "chinese": False},
    "suzuki:bolan":            {"lo": 500_000,    "hi": 2_000_000,  "styles": {"Van"},
                                "drive": "RWD", "transmission": "manual", "tags": {"cargo","economy"},         "chinese": False},
    "suzuki:apv":              {"lo": 1_500_000,  "hi": 3_500_000,  "styles": {"Van", "MPV"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"commercial","7seat"},      "chinese": False},

    # ── Legacy / Retro ──────────────────────────────────────────────────────────
    "suzuki:fx":               {"lo": 150_000,   "hi": 600_000,   "styles": {"Hatchback"},
                                "drive": "FWD", "transmission": "manual", "tags": {"economy","city"},          "chinese": False, "priority": 2},
    "suzuki:khyber":           {"lo": 300_000,   "hi": 1_200_000, "styles": {"Hatchback"},
                                "drive": "FWD", "transmission": "manual", "tags": {"economy","city"},          "chinese": False, "priority": 2},
    "suzuki:margalla":         {"lo": 400_000,   "hi": 1_200_000, "styles": {"Sedan"},
                                "drive": "FWD", "transmission": "manual", "tags": {"economy","family"},        "chinese": False, "priority": 2},
    "daihatsu:charade":        {"lo": 250_000,   "hi": 800_000,  "styles": {"Hatchback"},
                                "drive": "FWD", "transmission": "both",   "tags": {"economy","city"},          "chinese": False, "priority": 2},
    "nissan:sunny":            {"lo": 500_000,   "hi": 1_500_000, "styles": {"Sedan"},
                                "drive": "FWD", "transmission": "both",   "tags": {"economy","family"},        "chinese": False, "priority": 2},

    # ── Toyota ───────────────────────────────────────────────────────────────
    "toyota:vitz":             {"lo": 1_500_000,  "hi": 4_500_000,  "styles": {"Hatchback"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"economy","city","jdm"},    "chinese": False},
    "toyota:passo":            {"lo": 1_500_000,  "hi": 4_000_000,  "styles": {"Hatchback"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"economy","city","jdm"},    "chinese": False},
    "toyota:aqua":             {"lo": 2_500_000,  "hi": 6_500_000,  "styles": {"Hatchback"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"hybrid","economy","city","jdm"}, "chinese": False},
    "toyota:tank":             {"lo": 3_000_000,  "hi": 4_500_000,  "styles": {"Hatchback"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"economy","city","jdm","family"}, "chinese": False},
    "toyota:roomy":            {"lo": 3_000_000,  "hi": 5_000_000,  "styles": {"Hatchback"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"economy","city","jdm","family"}, "chinese": False},
    "toyota:probox":           {"lo": 2_000_000,  "hi": 4_500_000,  "styles": {"Van"},
                                "drive": "FWD", "transmission": "both",   "tags": {"cargo","economy","jdm"},   "chinese": False},
    "toyota:corolla":          {"lo": 800_000,    "hi": 8_500_000,  "styles": {"Sedan"},
                                "drive": "FWD", "transmission": "both",   "tags": {"family","city","economy","reliability","resale"}, "chinese": False, "priority": 1},
    "toyota:yaris":            {"lo": 3_500_000,  "hi": 6_000_000,  "styles": {"Sedan"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"family","city","reliability","resale"}, "chinese": False, "priority": 1},
    "toyota:allion":           {"lo": 3_000_000,  "hi": 8_000_000,  "styles": {"Sedan"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"family","jdm","city"},     "chinese": False, "priority": 2},
    "toyota:premio":           {"lo": 3_500_000,  "hi": 9_000_000,  "styles": {"Sedan"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"family","jdm","city"},     "chinese": False, "priority": 2},
    "toyota:mark x":           {"lo": 3_000_000,  "hi": 7_000_000,  "styles": {"Sedan"},
                                "drive": "RWD", "transmission": "auto",   "tags": {"sports","jdm","performance"}, "chinese": False, "priority": 2},
    "toyota:fielder":          {"lo": 2_500_000,  "hi": 6_000_000,  "styles": {"Sedan"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"family","jdm","cargo"},    "chinese": False, "priority": 3},
    "toyota:prius":            {"lo": 2_500_000,  "hi": 12_000_000, "styles": {"Hatchback"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"hybrid","economy","jdm"},  "chinese": False, "priority": 2},
    "toyota:crown":            {"lo": 4_000_000,  "hi": 25_000_000, "styles": {"Sedan"},
                                "drive": "RWD", "transmission": "auto",   "tags": {"sports","jdm","luxury","status","performance"}, "chinese": False, "priority": 2},
    "toyota:camry":            {"lo": 7_000_000,  "hi": 18_000_000, "styles": {"Sedan"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"luxury","status","family"}, "chinese": False, "priority": 1},
    "toyota:sienta":           {"lo": 3_000_000,  "hi": 6_500_000,  "styles": {"Van"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"family","7seat","jdm"},    "chinese": False},
    "toyota:c-hr":             {"lo": 4_500_000,  "hi": 10_000_000,  "styles": {"Crossover"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"city","jdm","sports"},     "chinese": False},
    "toyota:raize":            {"lo": 5_000_000,  "hi": 7_500_000,  "styles": {"Crossover", "Hatchback"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"city","family","jdm"},     "chinese": False},
    "toyota:yaris cross":      {"lo": 6_000_000,  "hi": 9_500_000,  "styles": {"Crossover", "Hatchback"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"city","hybrid","jdm"},     "chinese": False},
    "toyota:rush":             {"lo": 5_500_000,  "hi": 9_000_000,  "styles": {"Crossover", "Hatchback", "MPV"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"family","7seat"},          "chinese": False},
    "toyota:fortuner":         {"lo": 9_000_000,  "hi": 21_000_000, "styles": {"SUV"},
                                "drive": "4x4", "transmission": "auto",   "tags": {"family","offroad","status","7seat","reliability","resale"}, "chinese": False, "priority": 1},
    "toyota:hilux":            {"lo": 8_000_000,  "hi": 16_000_000, "styles": {"Pickup"},
                                "drive": "4x4", "transmission": "both",   "tags": {"offroad","cargo","awd"},   "chinese": False, "priority": 1},
    "toyota:alphard":          {"lo": 6_000_000,  "hi": 35_000_000, "styles": {"Van"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"luxury","status","family","7seat","jdm"}, "chinese": False},
    "toyota:vellfire":         {"lo": 6_000_000,  "hi": 35_000_000, "styles": {"Van"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"luxury","status","family","7seat","jdm"}, "chinese": False},
    "toyota:hiace":            {"lo": 3_500_000,  "hi": 12_000_000, "styles": {"Van"},
                                "drive": "RWD", "transmission": "both",   "tags": {"cargo","7seat","family"},  "chinese": False},
    "toyota:prado":            {"lo": 2_500_000, "hi": 48_000_000, "styles": {"SUV"},
                                "drive": "4x4", "transmission": "auto",   "tags": {"luxury","status","offroad","awd","reliability","resale"}, "chinese": False, "priority": 1},
    "toyota:land cruiser":     {"lo": 2_500_000, "hi": 90_000_000, "styles": {"SUV"},
                                "drive": "4x4", "transmission": "auto",   "tags": {"luxury","status","offroad","awd","reliability","resale"}, "chinese": False, "priority": 1},

    # ── Honda ────────────────────────────────────────────────────────────────
    "honda:n-box":             {"lo": 1_800_000,  "hi": 4_200_000,  "styles": {"Hatchback"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"economy","city","jdm"},    "chinese": False},
    "honda:n-wgn":             {"lo": 1_500_000,  "hi": 3_800_000,  "styles": {"Hatchback"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"economy","city","jdm"},    "chinese": False},
    "honda:fit":               {"lo": 2_000_000,  "hi": 5_500_000,  "styles": {"Hatchback"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"economy","city","jdm"},    "chinese": False},
    "honda:city":              {"lo": 1_000_000,  "hi": 6_000_000,  "styles": {"Sedan"},
                                "drive": "FWD", "transmission": "both",   "tags": {"economy","family","city","reliability","resale"}, "chinese": False, "priority": 1},
    "honda:civic":             {"lo": 1_000_000,  "hi": 9_500_000,  "styles": {"Sedan"},
                                "drive": "FWD", "transmission": "both",   "tags": {"family","city","sports","reliability","resale"},  "chinese": False, "priority": 1},
    "honda:grace":             {"lo": 3_500_000,  "hi": 6_500_000,  "styles": {"Sedan"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"family","hybrid","jdm"},   "chinese": False},
    "honda:insight":           {"lo": 2_500_000,  "hi": 6_500_000,  "styles": {"Sedan"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"hybrid","economy","jdm"},  "chinese": False},
    "honda:freed":             {"lo": 2_500_000,  "hi": 6_000_000,  "styles": {"Van"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"family","7seat","jdm"},    "chinese": False},
    "honda:shuttle":           {"lo": 3_500_000,  "hi": 7_000_000,  "styles": {"Van"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"family","hybrid","jdm"},   "chinese": False},
    "honda:stepwgn":           {"lo": 3_000_000,  "hi": 8_000_000,  "styles": {"Van"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"family","7seat","jdm"},    "chinese": False},
    "honda:br-v":              {"lo": 3_500_000,  "hi": 6_500_000,  "styles": {"Crossover"},
                                "drive": "FWD", "transmission": "both",   "tags": {"family","7seat","city"},   "chinese": False},
    "honda:hr-v":              {"lo": 6_000_000,  "hi": 8_500_000,  "styles": {"Crossover"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"city","jdm"},              "chinese": False},
    "honda:vezel":             {"lo": 4_000_000,  "hi": 11_000_000, "styles": {"Crossover"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"city","hybrid","jdm"},     "chinese": False},
    "honda:cr-v":              {"lo": 6_000_000,  "hi": 14_000_000, "styles": {"Crossover"},
                                "drive": "AWD", "transmission": "auto",   "tags": {"family","awd","jdm"},      "chinese": False},
    "honda:accord":            {"lo": 4_500_000,  "hi": 12_000_000, "styles": {"Sedan"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"luxury","family","jdm"},   "chinese": False},

    # ── Hyundai ──────────────────────────────────────────────────────────────
    "hyundai:santro":          {"lo": 700_000,    "hi": 1_800_000,  "styles": {"Hatchback"},
                                "drive": "FWD", "transmission": "both",   "tags": {"economy","city"},          "chinese": False},
    "hyundai:elantra":         {"lo": 5_000_000,  "hi": 7_500_000,  "styles": {"Sedan"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"family","city"},           "chinese": False},
    "hyundai:sonata":          {"lo": 7_500_000,  "hi": 11_000_000, "styles": {"Sedan"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"luxury","family"},         "chinese": False},
    "hyundai:tucson":          {"lo": 6_000_000,  "hi": 9_000_000,  "styles": {"Crossover"},
                                "drive": "AWD", "transmission": "auto",   "tags": {"family","city","awd"},     "chinese": False},
    "hyundai:santa fe":        {"lo": 12_000_000, "hi": 20_000_000, "styles": {"Crossover"}, 
                                "drive": "AWD", "transmission": "auto", "tags": {"family", "luxury", "7seat"}, "chinese": False, "priority": 2},
    "hyundai:porter":          {"lo": 2_500_000,  "hi": 4_000_000,  "styles": {"Van"},
                                "drive": "FWD", "transmission": "both",   "tags": {"cargo"},                   "chinese": False},
    "hyundai:palisade":        {"lo": 18_000_000, "hi": 35_000_000, "styles": {"Crossover"},
                                "drive": "AWD", "transmission": "auto",   "tags": {"luxury","family","7seat","awd"}, "chinese": False},

    # ── Kia ──────────────────────────────────────────────────────────────────
    "kia:picanto":             {"lo": 2_500_000,  "hi": 3_800_000,  "styles": {"Hatchback"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"economy","city"},          "chinese": False},
    "kia:stonic":              {"lo": 4_500_000,  "hi": 6_000_000,  "styles": {"Crossover"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"city","family"},           "chinese": False},
    "kia:sportage":            {"lo": 5_500_000,  "hi": 10_000_000, "styles": {"Crossover"},
                                "drive": "AWD", "transmission": "auto",   "tags": {"family","city","awd"},     "chinese": False},
    "kia:sorento":             {"lo": 7_500_000,  "hi": 11_000_000, "styles": {"Crossover"},
                                "drive": "AWD", "transmission": "auto",   "tags": {"family","7seat","awd"},    "chinese": False},
    "kia:carnival":            {"lo": 9_000_000,  "hi": 18_000_000, "styles": {"Van", "MPV"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"luxury","family","7seat"}, "chinese": False},

    # ── Daihatsu ─────────────────────────────────────────────────────────────
    "daihatsu:cuore":          {"lo": 600_000,    "hi": 1_600_000,  "styles": {"Hatchback"},
                                "drive": "FWD", "transmission": "both",   "tags": {"economy","city"},          "chinese": False},
    "daihatsu:mira":           {"lo": 1_200_000,  "hi": 3_800_000,  "styles": {"Hatchback"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"economy","city","jdm"},    "chinese": False},
    "daihatsu:move":           {"lo": 1_200_000,  "hi": 3_500_000,  "styles": {"Hatchback"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"economy","city","jdm"},    "chinese": False},
    "daihatsu:tanto":          {"lo": 1_500_000,  "hi": 4_000_000,  "styles": {"Hatchback"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"economy","city","jdm","family"}, "chinese": False},
    "daihatsu:cast":           {"lo": 2_000_000,  "hi": 3_500_000,  "styles": {"Hatchback"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"economy","city","jdm"},    "chinese": False},
    "daihatsu:hijet":          {"lo": 1_000_000,  "hi": 2_500_000,  "styles": {"Van"},
                                "drive": "FWD", "transmission": "both",   "tags": {"cargo","economy"},         "chinese": False},
    "daihatsu:rocky":          {"lo": 5_000_000,  "hi": 7_500_000,  "styles": {"Crossover", "Mini SUV", "Hatchback"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"city","jdm"},              "chinese": False},
    "daihatsu:terios":         {"lo": 2_500_000,  "hi": 6_000_000,  "styles": {"Crossover", "Mini SUV"},
                                "drive": "AWD", "transmission": "both",   "tags": {"offroad","family"},        "chinese": False},

    # ── Nissan ───────────────────────────────────────────────────────────────
    "nissan:clipper":          {"lo": 1_200_000,  "hi": 2_600_000,  "styles": {"Van"},
                                "drive": "FWD", "transmission": "both",   "tags": {"cargo","economy","jdm"},   "chinese": False, "cc": 660},
    "nissan:dayz":             {"lo": 1_500_000,  "hi": 3_500_000,  "styles": {"Hatchback"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"economy","city","jdm"},    "chinese": False},
    "nissan:roox":             {"lo": 1_500_000,  "hi": 3_800_000,  "styles": {"Hatchback"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"economy","city","jdm"},    "chinese": False},
    "nissan:note":             {"lo": 3_500_000,  "hi": 6_500_000,  "styles": {"Hatchback"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"hybrid","economy","jdm"},  "chinese": False},
    "nissan:juke":             {"lo": 3_500_000,  "hi": 8_000_000,  "styles": {"Crossover"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"city","sports","jdm"},     "chinese": False},
    "nissan:x-trail":          {"lo": 5_000_000,  "hi": 14_000_000, "styles": {"Crossover"},
                                "drive": "AWD", "transmission": "auto",   "tags": {"family","awd"},            "chinese": False},
    "nissan:patrol":           {"lo": 20_000_000, "hi": 55_000_000, "styles": {"SUV"},
                                "drive": "4x4", "transmission": "auto",   "tags": {"luxury","status","offroad","awd"}, "chinese": False},

    # ── Mitsubishi ───────────────────────────────────────────────────────────
    "mitsubishi:mirage":       {"lo": 2_000_000,  "hi": 4_500_000,  "styles": {"Hatchback"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"economy","city","jdm"},    "chinese": False},
    "mitsubishi:mini pajero":  {"lo": 800_000,    "hi": 2_500_000,  "styles": {"Mini SUV", "Crossover"},
                                "drive": "4x4", "transmission": "both", "tags": {"offroad", "city", "economy"}, "chinese": False, "priority": 2},
    "mitsubishi:asx":          {"lo": 3_500_000,  "hi": 8_000_000,  "styles": {"Crossover"},
                                "drive": "AWD", "transmission": "auto",   "tags": {"city","awd","jdm"},        "chinese": False},
    "mitsubishi:outlander":    {"lo": 5_000_000,  "hi": 14_000_000, "styles": {"Crossover"},
                                "drive": "AWD", "transmission": "auto",   "tags": {"family","awd"},            "chinese": False},
    "mitsubishi:pajero":       {"lo": 1_800_000,  "hi": 16_000_000, "styles": {"SUV"},
                                "drive": "4x4", "transmission": "auto",   "tags": {"offroad","awd","status"},  "chinese": False},
    "mitsubishi:pajero sport": {"lo": 8_000_000,  "hi": 18_000_000, "styles": {"SUV"},
                                "drive": "4x4", "transmission": "auto",   "tags": {"offroad","awd","status"},  "chinese": False},

    # ── Subaru ───────────────────────────────────────────────────────────────
    "subaru:impreza":          {"lo": 2_500_000,  "hi": 6_000_000,  "styles": {"Sedan"},
                                "drive": "AWD", "transmission": "both",   "tags": {"sports","awd","jdm","performance"}, "chinese": False},
    "subaru:xv":               {"lo": 4_000_000,  "hi": 7_500_000,  "styles": {"Crossover"},
                                "drive": "AWD", "transmission": "auto",   "tags": {"awd","city","jdm"},        "chinese": False},
    "subaru:forester":         {"lo": 4_500_000,  "hi": 9_000_000,  "styles": {"Crossover"},
                                "drive": "AWD", "transmission": "auto",   "tags": {"awd","family","offroad"},  "chinese": False},
    "subaru:brz":              {"lo": 4_500_000,  "hi": 10_000_000, "styles": {"Coupe"},
                                "drive": "RWD", "transmission": "both",   "tags": {"sports","performance","jdm"}, "chinese": False},

    # ── Mazda ────────────────────────────────────────────────────────────────
    "mazda:scrum":             {"lo": 1_200_000,  "hi": 2_500_000,  "styles": {"Van"},
                                "drive": "FWD", "transmission": "both",   "tags": {"cargo","economy","jdm"},   "chinese": False, "cc": 660},
    "mazda:demio":             {"lo": 2_500_000,  "hi": 4_500_000,  "styles": {"Hatchback"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"economy","city","jdm"},    "chinese": False},
    "mazda:mazda3":            {"lo": 3_000_000,  "hi": 7_000_000,  "styles": {"Sedan"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"sports","city","jdm"},     "chinese": False},
    "mazda:rx-8":              {"lo": 1_500_000,  "hi": 4_000_000,  "styles": {"Coupe"},
                                "drive": "RWD", "transmission": "both",   "tags": {"sports","performance","jdm"}, "chinese": False},
    "mazda:cx-3":              {"lo": 4_000_000,  "hi": 7_000_000,  "styles": {"Crossover"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"city","jdm"},              "chinese": False},
    "mazda:cx-5":              {"lo": 5_500_000,  "hi": 9_500_000,  "styles": {"Crossover"},
                                "drive": "AWD", "transmission": "auto",   "tags": {"family","awd","jdm"},      "chinese": False},

    # ── Chinese & New Entrants ────────────────────────────────────────────────
    "mg:zs":                   {"lo": 4_500_000,  "hi": 6_500_000,  "styles": {"Crossover"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"city","economy"},          "chinese": True},
    "mg:zs ev":                {"lo": 7_000_000,  "hi": 11_000_000, "styles": {"Crossover"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"ev","city"},               "chinese": True},
    "mg:hs":                   {"lo": 6_000_000,  "hi": 8_500_000,  "styles": {"Crossover"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"family","city"},           "chinese": True},
    "mg:rx5":                  {"lo": 4_500_000,  "hi": 9_000_000,  "styles": {"Crossover"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"family","city"},           "chinese": True},
    "mg:cyberster":            {"lo": 15_000_000, "hi": 25_000_000, "styles": {"Coupe"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"ev","sports","luxury"},    "chinese": True},
    "changan:alsvin":          {"lo": 3_200_000,  "hi": 4_800_000,  "styles": {"Sedan"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"economy","city","family"}, "chinese": True},
    "changan:karvaan":         {"lo": 1_500_000,  "hi": 3_000_000,  "styles": {"Van"},
                                "drive": "FWD", "transmission": "both",   "tags": {"cargo","family","economy"},"chinese": True},
    "changan:oshan x7":        {"lo": 7_000_000,  "hi": 9_500_000,  "styles": {"Crossover"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"family","7seat"},          "chinese": True},
    "changan:uni-t":           {"lo": 8_000_000,  "hi": 11_000_000, "styles": {"Crossover"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"family","city"},           "chinese": True},
    "changan:deepal s07":      {"lo": 13_000_000, "hi": 18_000_000, "styles": {"Crossover"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"ev","luxury","family"},    "chinese": True},
    "changan:deepal l07":      {"lo": 13_000_000, "hi": 18_000_000, "styles": {"Sedan"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"ev","luxury"},             "chinese": True},
    "haval:jolion":            {"lo": 7_000_000,  "hi": 9_000_000,  "styles": {"Crossover"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"family","city"},           "chinese": True},
    "haval:h6":                {"lo": 8_900_000,  "hi": 10_000_000, "styles": {"Crossover"},
                                "drive": "AWD", "transmission": "auto",   "tags": {"family","awd"},            "chinese": True},
    "haval:h6 hev":            {"lo": 11_400_000, "hi": 14_000_000, "styles": {"Crossover"},
                                "drive": "AWD", "transmission": "auto",   "tags": {"hybrid","family","awd"},   "chinese": True},
    "chery:tiggo 4 pro":       {"lo": 5_500_000,  "hi": 7_500_000,  "styles": {"Crossover"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"city","family"},           "chinese": True},
    "chery:tiggo 8 pro":       {"lo": 8_000_000,  "hi": 10_500_000, "styles": {"Crossover"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"family","7seat"},          "chinese": True},
    "proton:saga":             {"lo": 2_500_000,  "hi": 3_800_000,  "styles": {"Sedan"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"economy","city","family"}, "chinese": True},
    "proton:x70":              {"lo": 6_000_000,  "hi": 8_000_000,  "styles": {"Crossover"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"family","city"},           "chinese": True},
    "byd:dolphin":             {"lo": 9_000_000,  "hi": 12_000_000, "styles": {"Hatchback"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"ev","city","economy"},     "chinese": True},
    "byd:atto 3":              {"lo": 11_000_000, "hi": 15_000_000, "styles": {"Crossover"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"ev","family"},             "chinese": True},
    "byd:seal":                {"lo": 16_000_000, "hi": 22_000_000, "styles": {"Sedan"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"ev","sports","luxury"},    "chinese": True},
    "gwm:ora 03":              {"lo": 8_000_000,  "hi": 11_000_000, "styles": {"Crossover"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"ev","city"},               "chinese": True},
    "gwm:tank 500":            {"lo": 35_000_000, "hi": 45_000_000, "styles": {"SUV"},
                                "drive": "AWD", "transmission": "auto",   "tags": {"luxury","status","offroad","awd"}, "chinese": True},

    # ── Budget Micro-EVs ─────────────────────────────────────────────────────
    "honri:ve":                {"lo": 2_000_000,  "hi": 3_200_000,  "styles": {"Hatchback"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"ev","city","economy"},      "chinese": True},
    "rinco:aria":              {"lo": 2_200_000,  "hi": 3_000_000,  "styles": {"Hatchback"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"ev","city"},                "chinese": True},
    "metro:enfon":             {"lo": 1_800_000,  "hi": 2_500_000,  "styles": {"Hatchback"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"ev","city"},                "chinese": True},
    "jac:t8":                  {"lo": 7_000_000,  "hi": 10_000_000, "styles": {"Pickup"},
                                "drive": "4x4", "transmission": "both",   "tags": {"cargo","offroad"},          "chinese": True},
    "jac:t9":                  {"lo": 8_500_000,  "hi": 12_000_000, "styles": {"Pickup"},
                                "drive": "4x4", "transmission": "both",   "tags": {"cargo","offroad"},          "chinese": True},
    "mg:4 ev":                 {"lo": 10_000_000, "hi": 14_000_000, "styles": {"Hatchback"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"ev","city","sports"},       "chinese": True},
    "nissan:note e-power":     {"lo": 4_000_000,  "hi": 7_000_000,  "styles": {"Hatchback"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"hybrid","economy","city","jdm"}, "chinese": False, "priority": 2},
    "nissan:serena e-power":   {"lo": 6_000_000,  "hi": 10_000_000, "styles": {"Van", "MPV"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"hybrid","family","7seat","jdm"}, "chinese": False},

    # ── European & Luxury ────────────────────────────────────────────────────
    "bmw:3 series":            {"lo": 6_000_000,  "hi": 25_000_000, "styles": {"Sedan"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"sports","luxury","status","performance"}, "chinese": False},
    "bmw:5 series":            {"lo": 8_000_000,  "hi": 35_000_000, "styles": {"Sedan"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"luxury","status","family"}, "chinese": False},
    "bmw:7 series":            {"lo": 15_000_000, "hi": 60_000_000, "styles": {"Sedan"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"luxury","status"},         "chinese": False},
    "bmw:x1":                  {"lo": 7_000_000,  "hi": 20_000_000, "styles": {"Crossover"},
                                "drive": "AWD", "transmission": "auto",   "tags": {"city","luxury","awd"},     "chinese": False},
    "bmw:x3":                  {"lo": 9_000_000,  "hi": 30_000_000, "styles": {"Crossover"},
                                "drive": "AWD", "transmission": "auto",   "tags": {"luxury","awd","status"},   "chinese": False},
    "bmw:x5":                  {"lo": 12_000_000, "hi": 50_000_000, "styles": {"Crossover"},
                                "drive": "AWD", "transmission": "auto",   "tags": {"luxury","status","awd"},   "chinese": False},
    "bmw:x7":                  {"lo": 40_000_000, "hi": 80_000_000, "styles": {"SUV"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"luxury","status","7seat"}, "chinese": False},
    "bmw:i4":                  {"lo": 25_000_000, "hi": 35_000_000, "styles": {"Sedan"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"ev","luxury","performance"}, "chinese": False},
    "bmw:i7":                  {"lo": 60_000_000, "hi": 90_000_000, "styles": {"Sedan"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"ev","luxury","status"},    "chinese": False},
    "bmw:ix":                  {"lo": 35_000_000, "hi": 55_000_000, "styles": {"Crossover"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"ev","luxury"},             "chinese": False},
    "mercedes-benz:cla":       {"lo": 7_000_000,  "hi": 18_000_000, "styles": {"Sedan"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"luxury","sports","status"}, "chinese": False},
    "mercedes-benz:c-class":   {"lo": 6_000_000,  "hi": 30_000_000, "styles": {"Sedan"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"luxury","status","family"}, "chinese": False},
    "mercedes-benz:e-class":   {"lo": 8_000_000,  "hi": 45_000_000, "styles": {"Sedan"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"luxury","status","family"}, "chinese": False},
    "mercedes-benz:s-class":   {"lo": 15_000_000, "hi": 80_000_000, "styles": {"Sedan"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"luxury","status"},         "chinese": False},
    "mercedes-benz:gla":       {"lo": 7_500_000,  "hi": 20_000_000, "styles": {"Crossover"},
                                "drive": "AWD", "transmission": "auto",   "tags": {"luxury","city","awd"},     "chinese": False},
    "mercedes-benz:glc":       {"lo": 12_000_000, "hi": 35_000_000, "styles": {"Crossover"},
                                "drive": "AWD", "transmission": "auto",   "tags": {"luxury","status","awd"},   "chinese": False},
    "mercedes-benz:gle":       {"lo": 15_000_000, "hi": 50_000_000, "styles": {"Crossover"},
                                "drive": "AWD", "transmission": "auto",   "tags": {"luxury","status","awd"},   "chinese": False},
    "mercedes-benz:gls":       {"lo": 30_000_000, "hi": 75_000_000, "styles": {"SUV"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"luxury","status","7seat"}, "chinese": False},
    "audi:a3":                 {"lo": 5_000_000,  "hi": 12_000_000, "styles": {"Sedan","Hatchback"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"luxury","sports","city"},  "chinese": False},
    "audi:a4":                 {"lo": 6_500_000,  "hi": 20_000_000, "styles": {"Sedan"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"luxury","sports","status"}, "chinese": False},
    "audi:a5":                 {"lo": 8_000_000,  "hi": 25_000_000, "styles": {"Sedan"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"luxury","sports"},         "chinese": False},
    "audi:a6":                 {"lo": 9_000_000,  "hi": 35_000_000, "styles": {"Sedan"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"luxury","status","family"}, "chinese": False},
    "audi:a7":                 {"lo": 15_000_000, "hi": 45_000_000, "styles": {"Sedan"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"luxury","status"},         "chinese": False},
    "audi:q2":                 {"lo": 6_500_000,  "hi": 11_000_000, "styles": {"Crossover"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"luxury","city"},           "chinese": False},
    "audi:q3":                 {"lo": 7_500_000,  "hi": 15_000_000, "styles": {"Crossover"},
                                "drive": "AWD", "transmission": "auto",   "tags": {"luxury","city","awd"},     "chinese": False},
    "audi:q5":                 {"lo": 10_000_000, "hi": 25_000_000, "styles": {"Crossover"},
                                "drive": "AWD", "transmission": "auto",   "tags": {"luxury","awd","status"},   "chinese": False},
    "audi:q7":                 {"lo": 15_000_000, "hi": 45_000_000, "styles": {"Crossover"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"luxury","status","7seat"}, "chinese": False},
    "audi:q8":                 {"lo": 30_000_000, "hi": 60_000_000, "styles": {"Crossover"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"luxury","status"},         "chinese": False},
    "audi:e-tron":             {"lo": 18_000_000, "hi": 35_000_000, "styles": {"Crossover"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"ev","luxury"},             "chinese": False},
    "audi:e-tron gt":          {"lo": 35_000_000, "hi": 60_000_000, "styles": {"Sedan"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"ev","luxury","performance"}, "chinese": False},
    "porsche:macan":           {"lo": 20_000_000, "hi": 45_000_000, "styles": {"Crossover"},
                                "drive": "AWD", "transmission": "auto",   "tags": {"luxury","sports","awd"},   "chinese": False},
    "porsche:cayenne":         {"lo": 25_000_000, "hi": 70_000_000, "styles": {"Crossover"},
                                "drive": "AWD", "transmission": "auto",   "tags": {"luxury","status","awd"},   "chinese": False},
    "porsche:panamera":        {"lo": 25_000_000, "hi": 60_000_000, "styles": {"Sedan"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"luxury","status","performance"}, "chinese": False},
    "porsche:taycan":          {"lo": 40_000_000, "hi": 85_000_000, "styles": {"Sedan"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"ev","luxury","performance"}, "chinese": False},
    "porsche:cayman":          {"lo": 20_000_000, "hi": 40_000_000, "styles": {"Coupe"},
                                "drive": "RWD", "transmission": "both",   "tags": {"sports","performance","luxury"}, "chinese": False, "priority": 2},
    "toyota:supra":            {"lo": 15_000_000, "hi": 30_000_000, "styles": {"Coupe"},
                                "drive": "RWD", "transmission": "both",   "tags": {"sports","performance","jdm"}, "chinese": False, "priority": 2},
    "nissan:fairlady z":       {"lo": 8_000_000,  "hi": 20_000_000, "styles": {"Coupe"},
                                "drive": "RWD", "transmission": "both",   "tags": {"sports","performance","jdm"}, "chinese": False, "priority": 2},
    "nissan:350z":             {"lo": 5_000_000,  "hi": 12_000_000, "styles": {"Coupe"},
                                "drive": "RWD", "transmission": "both",   "tags": {"sports","performance","jdm"}, "chinese": False, "priority": 2},
    "nissan:370z":             {"lo": 8_000_000,  "hi": 18_000_000, "styles": {"Coupe"},
                                "drive": "RWD", "transmission": "both",   "tags": {"sports","performance","jdm"}, "chinese": False, "priority": 2},
    "bmw:m3":                  {"lo": 15_000_000, "hi": 40_000_000, "styles": {"Sedan"},
                                "drive": "RWD", "transmission": "both",   "tags": {"sports","performance","luxury"}, "chinese": False, "priority": 1},
    "land rover:evoque":       {"lo": 9_000_000,  "hi": 25_000_000, "styles": {"Crossover"},
                                "drive": "AWD", "transmission": "auto",   "tags": {"luxury","awd","status"},   "chinese": False},
    "land rover:velar":        {"lo": 20_000_000, "hi": 45_000_000, "styles": {"Crossover"},
                                "drive": "AWD", "transmission": "auto",   "tags": {"luxury","status","awd"},   "chinese": False},
    "land rover:discovery":    {"lo": 15_000_000, "hi": 50_000_000, "styles": {"SUV"},
                                "drive": "AWD", "transmission": "auto",   "tags": {"luxury","offroad","awd","7seat"}, "chinese": False},
    "land rover:range rover sport": {"lo": 20_000_000, "hi": 75_000_000, "styles": {"SUV"},
                                "drive": "AWD", "transmission": "auto",   "tags": {"luxury","status","awd"},   "chinese": False},
    "land rover:defender":     {"lo": 35_000_000, "hi": 85_000_000, "styles": {"SUV"},
                                "drive": "4x4", "transmission": "auto",   "tags": {"luxury","offroad","awd","status"}, "chinese": False},
    "land rover:range rover":  {"lo": 25_000_000, "hi": 95_000_000, "styles": {"SUV"},
                                "drive": "AWD", "transmission": "auto",   "tags": {"luxury","status","awd"},   "chinese": False},
    "land rover:vogue":        {"lo": 25_000_000, "hi": 95_000_000, "styles": {"SUV"},
                                "drive": "AWD", "transmission": "auto",   "tags": {"luxury","status","awd"},   "chinese": False},
    "lexus:ct200h":            {"lo": 4_000_000,  "hi": 7_500_000,  "styles": {"Hatchback"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"hybrid","luxury","city"},  "chinese": False},
    "lexus:is":                {"lo": 5_000_000,  "hi": 15_000_000, "styles": {"Sedan"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"luxury","sports","status"}, "chinese": False},
    "lexus:es":                {"lo": 8_000_000,  "hi": 25_000_000, "styles": {"Sedan"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"luxury","status","family"}, "chinese": False},
    "lexus:rx":                {"lo": 10_000_000, "hi": 35_000_000, "styles": {"Crossover"},
                                "drive": "AWD", "transmission": "auto",   "tags": {"luxury","status","awd"},   "chinese": False},
    "lexus:nx":                {"lo": 12_000_000, "hi": 28_000_000, "styles": {"Crossover"},
                                "drive": "AWD", "transmission": "auto",   "tags": {"luxury","city","awd"},     "chinese": False},
    "lexus:lx570":             {"lo": 30_000_000, "hi": 75_000_000, "styles": {"SUV"},
                                "drive": "AWD", "transmission": "auto",   "tags": {"luxury","status","offroad","awd"}, "chinese": False},
    "lexus:lx":                {"lo": 30_000_000, "hi": 75_000_000, "styles": {"SUV"},
                                "drive": "AWD", "transmission": "auto",   "tags": {"luxury","status","offroad","awd"}, "chinese": False},
    "lexus:lx600":             {"lo": 90_000_000, "hi": 140_000_000,"styles": {"SUV"},
                                "drive": "AWD", "transmission": "auto",   "tags": {"luxury","status","offroad","awd"}, "chinese": False},
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
    "clipper":                   "Clipper",
    "nissan clipper":            "Clipper",
    "scrum":                     "Scrum",
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
    "note e-power":              "Note e-Power",
    "serena e-power":            "Serena e-Power",
    "honri ve":                  "VE",
    "rinco aria":                "Aria",
    "metro enfon":               "Enfon",
    "t8":                        "T8",
    "t9":                        "T9",
    "4 ev":                      "4 EV",
    "mg 4":                      "4 EV",
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
    "m3":                        "M3",
    "bmw m3":                    "M3",
    "supra":                     "Supra",
    "fairlady z":                "Fairlady Z",
    "350z":                      "350Z",
    "370z":                      "370Z",
    "cayman":                    "Cayman",
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
  - PAKISTANI MARKET REALITY: "Family car" strongly means a SEDAN with a trunk ("diggi"). 
  - BUDGET & GENERATION HIERARCHY FOR FAMILY SEDANS:
    • Under 15 Lacs: Suzuki Liana, Suzuki Baleno, Suzuki Margalla, Nissan Sunny (Budget entry sedans).
    • 18–28 Lacs: Toyota Corolla 9th Gen ("Anda Shape" GLi/XLi/Altis), Honda Civic 7th Gen ("Eagle Eye" VTi/EXi), Honda City 5th Gen (i-DSI / Vario).
    • 28–42 Lacs: Toyota Corolla 10th Gen (Gli/Altis), Honda Civic 8th Gen ("Reborn") / 9th Gen ("Rebirth"), Honda City (Aspire 1.5).
    • 42–75 Lacs: Toyota Corolla Grande (11th Gen), Honda Civic X (10th Gen Turbo RS / Oriel), Hyundai Elantra.
  - STRICT HARD VETO: NEVER recommend Suzuki Liana, Baleno, or Margalla if the user's budget is 18 Lacs or higher. At 18+ Lacs, Toyota Corolla (Anda shape), Honda Civic (Eagle Eye), and Honda City are the absolute "bosses" of the family segment in Pakistan.
  - HARD RULE: DO NOT recommend Vans or MPVs (APV, Bolan, Every) for "family" unless the user EXPLICITLY requests "7 seater" or "van".
  - Prioritise: boot space, rear legroom, air conditioning effectiveness, reliability.
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
USE-CASE PRINCIPLES — SUV / Off-road / Northern Areas:
  - HARD SEPARATION: True SUVs (Land Cruiser, Prado, Pajero, Patrol, Fortuner, Revo) have ladder-frame chassis or true 4x4 systems.
  - Crossovers (Sportage, Tucson, Vezel, Rush) are unibody city cars — NEVER recommend crossovers when the user asks for a true SUV or rugged 4x4.
  - Old Land Cruisers (LC80/LC100), Prados, and Pajeros from 1990-2005 are extremely popular in Pakistan for rough terrain. Recommend them if budget is under 5 crore!
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

    "student_economy": """
USE-CASE PRINCIPLES — Student / University / Fuel Economy:
  - HARD RULE: NEVER recommend Civic, Corolla, or City for a student asking for fuel-efficient transport.
    These cars cost 2–5x more to run monthly than a 660cc kei car.
  - PRIORITY ORDER for 660–800cc kei hatchbacks: Suzuki Alto 660cc, Nissan Dayz, Daihatsu Mira/Move, Suzuki Every
  - For budgets under PKR 20 lacs: Suzuki Alto, Cultus, Wagon R, Passo are the correct picks
  - For budgets PKR 20–40 lacs: Toyota Vitz, Honda Fit, Suzuki Swift (all have >15km/l highway)
  - AUTOMATIC PREFERRED: Students in stop-and-go traffic benefit enormously from auto/AGS transmission
  - Avoid: Sedans (heavy, expensive, poor fuel economy for city use)
  - Avoid: Large hatchbacks (Honda Freed, Stepwgn) — too big, too costly
  - Avoid: APV, Bolan, Every (vans) — these are commercial, not student cars
  - Mention fuel economy figures in rationale if known (Alto ~20km/l, Vitz ~15km/l city)
""",

    "student_sports": """
USE-CASE PRINCIPLES — Student / Youth / Sports & Style:
  - PAKISTANI MARKET REALITY: Honda Civic and Suzuki Swift are the ultimate "youth / student / boy" cars in Pakistan.
  - Civic Generation Brackets for Young Buyers:
    • Budget PKR 12–18 Lacs: Honda Civic Eagle Eye (2004–2006 VTi/EXi) & Suzuki Swift
    • Budget PKR 18–28 Lacs: Honda Civic Reborn (2007–2012 i-VTEC / Hardtop / Oriel)
    • Budget PKR 28–42 Lacs: Honda Civic Rebirth (2013–2016 i-VTEC) & Honda Fit RS
    • Budget PKR 42–70 Lacs: Honda Civic X (2016–2021 Turbo RS / Oriel) & Toyota Mark X
  - HARD RULE: For young/student buyers seeking style, sports, or looks, ALWAYS prioritize Honda Civic and Suzuki Swift over "uncle/family" cars.
  - STRICTLY AVOID: Suzuki Liana, Suzuki Baleno, Suzuki Margalla, or Toyota Corolla GLi/XLi for young/youth style queries — these are family/uncle commuter cars in Pakistan with zero youth appeal.
  - Manual transmission is highly preferred for young sporty drivers.
""",

    "first_car": """
USE-CASE PRINCIPLES — First Car / New Driver:
  - HARD RULE: First car = small, automatic, cheap to repair. New drivers WILL have minor accidents.
  - PRIORITY: Suzuki Alto, Suzuki Cultus AGS, Toyota Passo, Daihatsu Mira (small, forgiving, cheap panels)
  - AUTOMATIC ONLY: Manual transmission is dangerous for new drivers in Pakistani city traffic
  - Cheap parts essential — avoid anything where a minor panel job costs 50K+
  - Avoid: Civic, Corolla (too expensive to repair after inevitable dings)
  - Avoid: Large body (Vezel, Sportage) — hard to park for beginners
  - Mention insurance and low repair cost in rationale
""",

    "commercial_cargo": """
USE-CASE PRINCIPLES — Commercial / Cargo / Loader:
  - User needs a cargo carrier, not a passenger car
  - PRIORITY: Suzuki Bolan (payload king, cheap), Suzuki Every (bigger, more modern), Suzuki APV (passenger+cargo)
  - For heavier loads: Toyota Hiace is the correct answer regardless of higher price
  - Avoid: passenger hatchbacks and sedans — they have no cargo capacity
  - Avoid: premium vans (Alphard, Vellfire) — wrong segment entirely
  - Mention payload/cargo floor dimensions in rationale if known
""",

    "highway_touring": """
USE-CASE PRINCIPLES — Highway / Long Route / Touring:
  - Highway use = fuel economy at 100–120km/h, ride comfort, boot space for luggage
  - PRIORITY SEDANS: Corolla (most proven), City (comfortable), Premio/Allion (smooth highway ride)
  - HYBRID BONUS: Aqua, Prius excel at 20–25km/l on highway — mention this
  - Avoid: kei cars (Alto, Vitz) for long highway — uncomfortable at highway speed
  - Avoid: heavy SUVs (Fortuner, Prado) unless the route involves mountain/off-road sections
  - Automatic preferred for relaxed long-distance driving
  - Mention expected km/l and approximate Lahore-Islamabad fuel cost in rationale if known
""",

    "hybrid_ev": """
USE-CASE PRINCIPLES — Hybrid / Series Hybrid / EV:
  - CRITICAL DISTINCTION: Series Hybrids (Nissan Note e-Power, Serena e-Power) use a petrol engine ONLY as a generator — the wheels are ALWAYS driven by an electric motor. This gives EV-like driving feel.
  - Parallel Hybrids (Toyota Aqua, Prius, Honda Grace, Vezel) have both petrol engine and electric motor driving the wheels together.
  - When user asks for "series hybrid" or "e-Power" → prioritize Nissan Note e-Power and Serena e-Power.
  - When user asks for "hybrid" generically → include both types, but note the distinction in rationale.
  - For EV queries: ONLY show cars with 'ev' tag. Budget micro-EVs (Honri VE, Rinco Aria, Metro Enfon) are valid for under 35 lacs.
  - Avoid: Recommending petrol-only cars for hybrid/EV queries — this is a critical error.
""",

    "accessibility": """
USE-CASE PRINCIPLES — Accessibility / Disabled Driver:
  - AUTOMATIC ONLY: Hand controls are incompatible with manual clutch operation
  - Spacious cabin entry: look for wider door openings (Corolla, City, Civic)
  - Avoid: kei cars (very difficult for wheelchair transfer, low roofline)
  - Avoid: sports cars (low ride height makes entry/exit painful)
  - Prefer: Sedans with high ride height and wide doors
  - If 7-seat accessible needed: Kia Carnival or Toyota Hiace
""",

    "monsoon": """
USE-CASE PRINCIPLES — Monsoon / Flood / High Ground Clearance:
  - The user is worried about urban flooding and waterlogged streets.
  - PRIORITY: Crossovers and Mini SUVs with 170mm+ ground clearance.
  - BEST PICKS: Suzuki Jimny, Daihatsu Terios, Honda Vezel, Kia Stonic, Daihatsu Rocky, Honda BR-V, Toyota C-HR.
  - For SUV budgets: Fortuner, Pajero, Prado have the best wading depth.
  - AVOID: Low-clearance sedans (Corolla, Civic, City) — they will hydro-lock in 1-foot standing water.
  - AVOID: Kei hatchbacks (Alto, Mira) — extremely vulnerable to water ingress.
  - Mention ground clearance in rationale if known.
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
        elif any(w in uc_lower for w in ["ride", "uber", "careem", "commercial", "taxi", "sawari", "kiraya"]):
            block = _USE_CASE_PRINCIPLES["ride_sharing"]
        elif "student_economy" in uc_lower:
            block = _USE_CASE_PRINCIPLES["student_economy"]
        elif "student_sports" in uc_lower:
            block = _USE_CASE_PRINCIPLES["student_sports"]
        elif "first_car" in uc_lower:
            block = _USE_CASE_PRINCIPLES["first_car"]
        elif "commercial_cargo" in uc_lower:
            block = _USE_CASE_PRINCIPLES["commercial_cargo"]
        elif "highway_touring" in uc_lower:
            block = _USE_CASE_PRINCIPLES["highway_touring"]
        elif any(w in uc_lower for w in ["monsoon", "flood", "waterlogging"]):
            block = _USE_CASE_PRINCIPLES["monsoon"]
        elif "accessibility" in uc_lower:
            block = _USE_CASE_PRINCIPLES["accessibility"]
        elif any(w in uc_lower for w in ["hybrid", "ev", "electric", "e-power"]):
            block = _USE_CASE_PRINCIPLES["hybrid_ev"]
        else:
            block = _USE_CASE_PRINCIPLES["general"]

    # Always append luxury principles if explicitly requested
    if is_luxury and "luxury" not in (use_case or "").lower():
        block += _USE_CASE_PRINCIPLES["luxury"]

    return block.strip()




# ---------------------------------------------------------------------------
# KEYWORD INTENT MAP
#
# Python-level query intent interceptor that runs BEFORE the LLM sees anything.
# Maps raw user phrase patterns to hard constraints that override LLM guesses.
#
# Architecture:
#   1. apply_keyword_intent() is called in resolve_constraints() with user_prompt.
#   2. It scans prompt for keyword matches and injects overrides into constraints.
#   3. Overrides take precedence over LLM-extracted body_style and use_case.
#
# Rule design:
#   - keywords: ANY of these in prompt (lowercase) triggers the intent
#   - exclude_keywords: if ANY of these are also present, intent is NOT triggered
#     (allows disambiguation between overlapping intents)
#   - force_body_style: hard-overrides body_style in constraints dict
#   - use_case_override: replaces use_case in constraints dict
#   - force_transmission: hard-overrides transmission
#   - max_budget_cap: if stated budget exceeds this, cap it (prevents luxury
#     cars surfacing for frugal use cases)
#   - append_features: adds to required_features list
#
# Add new intents here as you discover new failure patterns in production.
# ---------------------------------------------------------------------------

KEYWORD_INTENT_MAP: list[dict] = [
    {
        "intent_id":        "hyper_miler",
        "keywords":         ["20 km/l", "20km/l", "25 km/l", "maximum average", "best average", "30 km/l", "kam fuel"],
        "exclude_keywords": [],
        "force_body_style":  None,
        "use_case_override": "student_economy",
        "force_transmission": None,
        "max_budget_cap":    None,
        "append_features":   [],
    },

    # ── 1. Student / University — Sports & Style (CHECKED FIRST) ─────────────
    # Triggers on sports/performance/slang keywords for young drivers
    {
        "intent_id":        "student_sports",
        "keywords":         ["pick", "pick achi", "pick acchi", "maza", "zara maza", 
                             "shashka", "chaska", "bhagane", "bhaganay", "sporty", 
                             "fast", "looks", "style", "drifting", "racing", "fun driving", "speed"],
        "exclude_keywords": ["petrol kam", "fuel efficient", "fuel economy", "mileage",
                             "average", "km per litre", "bachane wali", "sasta"],
        "force_body_style":  None,    # Allow sporty hatchbacks (Swift/Vitz) or sedans
        "use_case_override": "student_sports",
        "force_transmission": None,
        "max_budget_cap":    None,
        "append_features":   [],
    },

    # ── 2. Student / University — Fuel Economy ───────────────────────────────
    # MUST contain explicit fuel-saving keywords
    {
        "intent_id":        "student_fuel_economy",
        "keywords":         ["petrol kam", "fuel efficient", "fuel economy", "mileage", 
                             "km per litre", "km/litre", "fuel mileage", "bachane wali",
                             "sasta chalana", "cheap to run", "avg kam"],
        "exclude_keywords": ["sports", "fast", "sporty", "powerful", "looks", "style",
                             "drifting", "racing", "turbo", "pick", "maza"],
        "force_body_style":  "Hatchback",
        "use_case_override": "student_economy",
        "force_transmission": None,
        "max_budget_cap":    None,
        "append_features":   [],
    },

    # ── First Car / New Driver ────────────────────────────────────────────────
    # Trigger: first car, new driver, learning, beginner keywords
    # Result: force small Hatchback, automatic preferred for safety
    # New drivers in Pakistan should not be in large sedans or SUVs.
    {
        "intent_id":        "first_car",
        "keywords":         ["first car", "pehli gaari", "new driver", "abhi seekhna",
                             "beginner", "learning to drive", "practice car", "driving school",
                             "sikhna hai", "abhi license"],
        "exclude_keywords": [],
        "force_body_style":  "Hatchback",
        "use_case_override": "first_car",
        "force_transmission": "Automatic",   # auto easier for learners
        "max_budget_cap":    None,
        "append_features":   [],
    },

    # ── Rickshaw / Loader Replacement — Commercial ────────────────────────────
    # Trigger: loader, cargo, goods, dukaan, shop delivery keywords
    # Result: force Van body_style, commercial use_case
    {
        "intent_id":        "commercial_cargo",
        "keywords":         ["loader", "cargo", "goods", "delivery", "dukaan", "shop",
                             "saman uthana", "commercial", "suzuki loader", "redi", "redi gaari"],
        "exclude_keywords": ["family", "passenger", "7 seater", "school run"],
        "force_body_style":  "Van",
        "use_case_override": "commercial_cargo",
        "force_transmission": None,
        "max_budget_cap":    None,
        "append_features":   [],
    },

    # ── School Run / Kids Pickup ──────────────────────────────────────────────
    # Trigger: kids, school, pickup kids keywords
    # Result: family use_case, small crossover or sedan (NOT van unless 7-seat)
    {
        "intent_id":        "school_run",
        "keywords":         ["school run", "kids pickup", "bachon ko", "bachon ki",
                             "pickup kids", "school ke baad", "school drop"],
        "exclude_keywords": ["7 seater", "van", "8 seater"],
        "force_body_style":  "Sedan",
        "use_case_override": "family",
        "force_transmission": None,
        "max_budget_cap":    None,
        "append_features":   [],
    },

    # ── Fuel Station / Rural Long Route ──────────────────────────────────────
    # Trigger: highway, long route, motorway, petrol pump, rural keywords
    # Result: fuel economy use_case, no body style force (sedan fine for highway)
    {
        "intent_id":        "highway_long_route",
        "keywords":         ["highway", "motorway", "long route", "lahore karachi",
                             "islamabad lahore", "long drive", "out of city", "tour",
                             "saffari", "petrol pump se dur", "rural"],
        "exclude_keywords": ["offroad", "4x4", "mountain", "northern"],
        "force_body_style":  None,
        "use_case_override": "highway_touring",
        "force_transmission": None,
        "max_budget_cap":    None,
        "append_features":   [],
    },

    # ── Northern Areas / Mountains / Offroad ─────────────────────────────────
    # Trigger: northern areas, KPK, AJK, mountains, bumpy road keywords
    # Result: force SUV + offroad use_case
    # LLM sometimes picks Crossover/Vezel for "northern areas" queries.
    # This forces true SUVs instead.
    {
        "intent_id":        "northern_offroad",
        "keywords":         ["northern areas", "naran", "kaghan", "hunza", "gilgit",
                             "azad kashmir", "ajk", "murree", "kpk", "khyber",
                             "mountain road", "bumpy road", "rough road", "off road",
                             "offroad", "jungle", "dirt road", "kaccha rasta"],
        "exclude_keywords": [],
        "force_body_style":  "SUV",
        "use_case_override": "offroad",
        "force_transmission": None,
        "max_budget_cap":    None,
        "append_features":   [],
    },

    # ── Monsoon / Flood / Ground Clearance ────────────────────────────────
    # Trigger: flood, monsoon, waterlogging, ground clearance keywords
    # Result: force Crossover/SUV/Mini SUV, avoid low-clearance cars
    {
        "intent_id":        "monsoon_flood",
        "keywords":         ["flood", "flooded", "monsoon", "waterlogging", "pani", "paani",
                             "rain water", "hydro-lock", "ground clearance", "oonchi gaari",
                             "high clearance", "water logged"],
        "exclude_keywords": [],
        "force_body_style":  "Crossover",
        "use_case_override": "city",
        "force_transmission": None,
        "max_budget_cap":    None,
        "append_features":   [],
    },

    # ── Uber / Careem / Ride Sharing ─────────────────────────────────────────
    # Trigger: uber, careem, taxi, ride sharing keywords
    # Result: ride_sharing use_case, no body_style force (sedan preferred but let LLM confirm)
    {
        "intent_id":        "ride_sharing",
        "keywords":         ["uber", "careem", "indriver", "bykea", "ride share",
                             "ride-sharing", "taxi", "cab service", "passenger service",
                             "kiraya car", "sawari"],
        "exclude_keywords": [],
        "force_body_style":  None,
        "use_case_override": "ride_sharing",
        "force_transmission": None,
        "max_budget_cap":    None,
        "append_features":   [],
    },

    # ── Wife / Lady Driver ────────────────────────────────────────────────────
    # Trigger: wife, lady, female, begum, amma driving keywords
    # Result: automatic preferred, small body, city use_case
    {
        "intent_id":        "lady_driver",
        "keywords":         ["wife", "begum", "lady driver", "female driver", "amma",
                             "mother driving", "baji driving", "aurat"],
        "exclude_keywords": ["sports", "fast", "powerful"],
        "force_body_style":  "Hatchback",
        "use_case_override": "city",
        "force_transmission": "Automatic",
        "max_budget_cap":    None,
        "append_features":   [],
    },

    # ── Disabled / Accessibility ──────────────────────────────────────────────
    # Trigger: wheelchair, disabled, hand controls, accessibility keywords
    # Result: automatic forced, spacious body preferred
    {
        "intent_id":        "accessibility",
        "keywords":         ["wheelchair", "disabled", "hand controls", "specially abled",
                             "disability", "physically challenged", "hand operated"],
        "exclude_keywords": [],
        "force_body_style":  None,
        "use_case_override": "accessibility",
        "force_transmission": "Automatic",
        "max_budget_cap":    None,
        "append_features":   [],
    },
]


def apply_keyword_intent(user_prompt: str, constraints: dict) -> dict:
    """
    Scans user_prompt against KEYWORD_INTENT_MAP and injects hard overrides
    into the constraints dict. Called at the END of resolve_constraints().

    Priority: first matching intent wins (list is ordered by specificity).
    If no intent matches, constraints are returned unchanged.

    Overrides applied:
      - force_body_style   → constraints["body_style"]
      - use_case_override  → constraints["use_case"]
      - force_transmission → constraints["transmission"]
      - max_budget_cap     → clips constraints["max_budget"] if over cap
      - append_features    → extends constraints["required_features"]

    Also injects "intent_id" into constraints so downstream functions
    (e.g. _get_relevant_principles) can detect the triggered intent.
    """
    prompt_lower = user_prompt.lower()

    # ── Explicit Constraint Detection ──────────────────────────────────
    # If the user EXPLICITLY typed a body style, transmission, or seating
    # capacity, those override any implicit keyword heuristics.
    # E.g. "student" + "sedan" → sedan wins over hatchback heuristic.
    _EXPLICIT_SEDAN_KW = {"sedan", "diggi", "diggy", "trunk", "car with trunk", "big car"}
    _EXPLICIT_HATCHBACK_KW = {"hatchback", "small car", "choti gaari"}
    _EXPLICIT_SUV_KW = {"suv", "jeep", "4x4"}
    _EXPLICIT_VAN_KW = {"van", "mpv", "hiace", "7 seater", "8 seater", "9 seater", "11 seater"}
    _EXPLICIT_MANUAL_KW = {"manual", "stick shift", "gear wali"}
    _EXPLICIT_SEATING_KW = {"9 people", "9 log", "10 people", "11 people", "9 seater", "10 seater", "11 seater"}
    
    has_explicit_sedan = any(kw in prompt_lower for kw in _EXPLICIT_SEDAN_KW)
    has_explicit_hatch = any(kw in prompt_lower for kw in _EXPLICIT_HATCHBACK_KW)
    has_explicit_suv   = any(kw in prompt_lower for kw in _EXPLICIT_SUV_KW)
    has_explicit_van   = any(kw in prompt_lower for kw in _EXPLICIT_VAN_KW)
    has_explicit_manual = any(kw in prompt_lower for kw in _EXPLICIT_MANUAL_KW)
    has_explicit_body = has_explicit_sedan or has_explicit_hatch or has_explicit_suv or has_explicit_van

    for intent in KEYWORD_INTENT_MAP:
        keywords         = intent.get("keywords", [])
        exclude_keywords = intent.get("exclude_keywords", [])

        # Check if ANY keyword matches
        if not any(kw in prompt_lower for kw in keywords):
            continue

        # Check if ANY exclusion keyword also matches — if so, skip this intent
        if exclude_keywords and any(ex in prompt_lower for ex in exclude_keywords):
            continue

        # ── Apply all overrides ───────────────────────────────────────────────
        intent_id = intent["intent_id"]
        print(f"[IntentMapper] Triggered intent: '{intent_id}' from prompt: '{user_prompt[:60]}'")

        if intent.get("force_body_style"):
            # NEVER override an explicit body style from the user
            if not has_explicit_body:
                constraints["body_style"] = intent["force_body_style"]
            else:
                print(f"[IntentMapper] Skipping body_style override '{intent['force_body_style']}' — user explicitly stated a body style")

        if intent.get("use_case_override"):
            constraints["use_case"] = intent["use_case_override"]

        if intent.get("force_transmission"):
            # NEVER override an explicit manual request
            if not has_explicit_manual:
                constraints["transmission"] = intent["force_transmission"]
            else:
                print(f"[IntentMapper] Skipping transmission override — user explicitly requested Manual")

        if intent.get("max_budget_cap") and constraints.get("max_budget", 0) > intent["max_budget_cap"]:
            constraints["max_budget"] = intent["max_budget_cap"]
            constraints["min_budget"] = int(intent["max_budget_cap"] * 0.70)

        if intent.get("append_features"):
            existing = constraints.get("required_features", [])
            for feat in intent["append_features"]:
                if feat not in existing:
                    existing.append(feat)
            constraints["required_features"] = existing

        if intent_id == "hyper_miler":
            # If they have the budget for a hybrid, force hybrid. Otherwise, force max 1000cc.
            if constraints.get("max_budget", 0) >= 2_500_000:
                constraints["powertrain"] = "hybrid"
            else:
                constraints["max_cc"] = 1000

        constraints["intent_id"] = intent_id
        return constraints  # first match wins

    return constraints

# ---------------------------------------------------------------------------
# ADVISORY DISCLAIMER GENERATOR
#
# Scans user prompt + constraints for known conflict patterns and injects
# human-readable safety/budget/feasibility warnings into the SSE payload.
# Called at the end of resolve_constraints() after apply_keyword_intent().
# ---------------------------------------------------------------------------

_HYBRID_MODELS = {"toyota:aqua", "toyota:prius", "toyota:yaris cross", "honda:vezel",
                  "honda:insight", "honda:grace", "honda:shuttle", "honda:freed",
                  "haval:h6 hev", "lexus:ct200h"}

_DELUSIONAL_LUXURY_MODELS = {"toyota:land cruiser", "land rover:range rover", "land rover:vogue",
                             "land rover:defender", "audi:e-tron gt", "porsche:taycan",
                             "bmw:7 series", "bmw:i7", "lexus:lx600", "mercedes-benz:s-class"}

_BUDGET_HATCHBACKS_NO_ADAS = {"suzuki:mehran", "suzuki:alto", "suzuki:cultus", "suzuki:wagon r",
                              "suzuki:fx", "suzuki:khyber", "daihatsu:cuore", "daihatsu:charade"}


def generate_disclaimers(user_prompt: str, constraints: dict) -> list[str]:
    """
    Scans for known conflict patterns and returns a list of advisory disclaimers.
    These are informational — they do NOT block the pipeline.
    """
    disclaimers: list[str] = []
    prompt_lower = user_prompt.lower()

    # 1. CNG + Hybrid conflict
    has_cng = "cng" in prompt_lower
    has_hybrid_kw = any(w in prompt_lower for w in ["hybrid", "aqua", "prius", "vezel"])
    if has_cng and has_hybrid_kw:
        disclaimers.append(
            "⚠️ Warning: Installing CNG on a Japanese Hybrid system (Aqua/Vezel) "
            "can damage the hybrid battery and is a serious safety hazard."
        )

    # 2. Disabled + Manual conflict
    has_disability = any(w in prompt_lower for w in ["disabled", "wheelchair", "disability",
                                                     "hand controls", "specially abled",
                                                     "physically challenged"])
    has_manual = any(w in prompt_lower for w in ["manual", "stick shift", "gear wali"])
    if has_disability and has_manual:
        disclaimers.append(
            "⚠️ Safety Note: Manual clutch operation is difficult with left-leg impairment. "
            "Automatics have been prioritized for safety with hand controls."
        )

    # 3. Delusional budget
    max_budget = constraints.get("max_budget", 0)
    luxury_kws = ["land cruiser", "v8", "range rover", "defender", "audi e-tron",
                  "porsche", "taycan", "lexus lx", "bmw 7 series", "s-class"]
    has_luxury_car_name = any(kw in prompt_lower for kw in luxury_kws)
    if has_luxury_car_name and 0 < max_budget < 30_000_000:
        disclaimers.append(
            "⚠️ Budget Notice: Land Cruiser V8 and Range Rover start well above 1 Crore. "
            "Showing Pajero/Surf as the closest budget SUV alternatives."
        )

    # 4. 9+ Passenger seating
    seating_kws = ["9 people", "9 log", "10 people", "10 log", "11 people",
                   "9 seater", "10 seater", "11 seater", "12 seater"]
    if any(kw in prompt_lower for kw in seating_kws):
        disclaimers.append(
            "⚠️ Seating Notice: SUVs like Prado/Land Cruiser only seat up to 7 passengers. "
            "For 9+ people, passenger vans (Hiace/APV) or multiple vehicles are required."
        )

    # 5. Impossible features on budget hatchbacks
    impossible_feat_kws = ["panoramic sunroof", "panoramic", "lane assist", "lane keep",
                           "adaptive cruise", "blind spot monitor"]
    budget_car_kws = ["mehran", "cultus", "alto", "khyber", "fx", "charade"]
    has_impossible_feat = any(kw in prompt_lower for kw in impossible_feat_kws)
    has_budget_car_name = any(kw in prompt_lower for kw in budget_car_kws)
    if has_impossible_feat and has_budget_car_name:
        disclaimers.append(
            "⚠️ Feature Notice: Suzuki Mehran/Cultus do not feature factory "
            "Panoramic Sunroofs or Lane Assist in Pakistan."
        )

    # 7. EV Infrastructure Warning
    # Replace raw "ev" substring checks with regex word boundary matching \bev\b
    has_ev_kw = bool(re.search(r'\bev\b', prompt_lower)) or any(
        w in prompt_lower for w in ["electric", "battery car", "zero emission", "fully electric", "bev"]
    )
    if has_ev_kw or constraints.get("powertrain") == "ev":
        disclaimers.append(
            "⚠️ EV Infrastructure Notice: Public DC fast chargers are currently limited across Pakistan. "
            "Ensure you have provisions for a 7kW/11kW home AC wallbox charger (ideally with solar net-metering) "
            "for reliable daily urban commuting."
        )

    # 8. Panoramic vs. Single-Pane Sunroof Confusion
    if "panoramic" in prompt_lower and any(w in prompt_lower for w in ["grande", "civic", "vezel", "raize"]):
        disclaimers.append(
            "⚠️ Specification Notice: Corolla Grande, Civic Oriel, and Honda Vezel feature standard "
            "single-pane sunroofs in Pakistan. Recommending MG HS, Haval Jolion, or Oshan X7 for "
            "full panoramic glass roofs."
        )

    return disclaimers

# ---------------------------------------------------------------------------
# MODEL-FEATURE KNOWLEDGE MAP
#
# Answers: "Which models CAN NEVER have feature X in ANY trim?"
# Used by get_eligible_cars() to hard-exclude impossible cars before the LLM sees the list.
#
# Philosophy: only put a car here if you are 100% certain it NEVER has the feature.
# Unknown = pass through (LLM decides). Wrong exclusions hurt results more than
# missing inclusions.
#
# Feature keys must match keys in _FEATURE_KEYWORDS in recommend_normalizer.py.
# ---------------------------------------------------------------------------

_FEATURE_IMPOSSIBLE: dict[str, set[str]] = {

    # ── Sunroof / Panoramic ──────────────────────────────────────────────────
    "sunroof": {
        "suzuki:mehran", "suzuki:alto", "suzuki:alto 660cc", "suzuki:cultus",
        "suzuki:wagon r", "suzuki:swift", "suzuki:liana", "suzuki:baleno",
        "suzuki:khyber", "suzuki:fx", "daihatsu:charade",
        "suzuki:every", "suzuki:bolan", "suzuki:apv", "suzuki:hustler", "suzuki:spacia",
        "toyota:vitz", "toyota:passo", "toyota:probox", "toyota:hiace",
        "toyota:yaris", "toyota:aqua", "toyota:rush", "toyota:hilux",
        "honda:n-box", "honda:n-wgn", "honda:fit", "honda:freed", "honda:br-v",
        "hyundai:santro",
        "daihatsu:cuore", "daihatsu:mira", "daihatsu:move", "daihatsu:tanto",
        "daihatsu:cast", "daihatsu:hijet",
        "nissan:dayz", "nissan:roox",
        "kia:picanto", "kia:stonic",
        "mitsubishi:mirage",
        "changan:alsvin", "changan:karvaan",
        "proton:saga",
        "mazda:demio",
    },
    "panoramic sunroof": {
        "suzuki:mehran", "suzuki:alto", "suzuki:alto 660cc", "suzuki:cultus",
        "suzuki:wagon r", "suzuki:swift", "suzuki:liana", "suzuki:baleno",
        "suzuki:khyber", "suzuki:fx", "daihatsu:charade",
        "suzuki:every", "suzuki:bolan", "suzuki:apv", "suzuki:hustler", "suzuki:spacia",
        "toyota:vitz", "toyota:passo", "toyota:probox", "toyota:hiace",
        "toyota:yaris", "toyota:aqua", "toyota:rush", "toyota:hilux",
        "toyota:corolla",   # Grande has regular single-pane sunroof, NOT panoramic
        "toyota:raize",     # single-pane sunroof only in Z grade
        "toyota:c-hr",      # single-pane sunroof only
        "toyota:allion", "toyota:premio", "toyota:mark x",
        "honda:n-box", "honda:n-wgn", "honda:fit", "honda:freed", "honda:br-v",
        "honda:city", "honda:civic",    # regular single-pane sunroof only in PK spec
        "honda:vezel",      # single-pane sunroof only in Z/RS grade
        "honda:hr-v",       # single-pane sunroof only in PK CKD
        "hyundai:santro", "hyundai:elantra",
        "kia:sportage",                 # regular single-pane sunroof only in PK CKD
        "kia:picanto", "kia:stonic",
        "daihatsu:cuore", "daihatsu:mira", "daihatsu:move", "daihatsu:tanto",
        "daihatsu:cast", "daihatsu:hijet",
        "nissan:dayz", "nissan:roox",
        "subaru:xv",        # single-pane sunroof only
        "mazda:cx-5",       # single-pane sunroof only in PK
        "mazda:cx-3",       # single-pane sunroof only
        "changan:alsvin", "changan:karvaan",
        "proton:saga", "mazda:demio", "mitsubishi:mirage", "suzuki:jimny",
    },

    # ── Push Start / Keyless Entry ───────────────────────────────────────────
    "push start": {
        "suzuki:mehran", "suzuki:bolan",
        "suzuki:wagon r",   # local Pak Suzuki Wagon R uses key ignition only
        "suzuki:cultus",    # local Pak Suzuki Cultus uses key ignition only
        "suzuki:alto",      # local Pak Suzuki Alto uses key ignition only
        "daihatsu:cuore", "daihatsu:hijet",
        "hyundai:santro", "toyota:probox", "changan:karvaan",
    },
    "keyless entry": {
        "suzuki:mehran", "suzuki:bolan",
        "suzuki:wagon r",   # local Pak Suzuki Wagon R uses key ignition only
        "suzuki:cultus",    # local Pak Suzuki Cultus uses key ignition only
        "suzuki:alto",      # local Pak Suzuki Alto uses key ignition only
        "daihatsu:cuore", "daihatsu:hijet",
        "hyundai:santro", "toyota:probox", "changan:karvaan",
    },

    # ── ADAS Features ────────────────────────────────────────────────────────
    "lane assist": {
        "suzuki:mehran", "suzuki:alto", "suzuki:alto 660cc", "suzuki:cultus",
        "suzuki:liana", "suzuki:baleno", "suzuki:swift", "suzuki:wagon r",
        "suzuki:every", "suzuki:bolan", "suzuki:apv", "suzuki:hustler", "suzuki:spacia",
        "toyota:vitz", "toyota:passo", "toyota:probox", "toyota:hiace",
        "toyota:corolla", "toyota:yaris", "toyota:hilux",
        "honda:n-box", "honda:n-wgn", "honda:fit", "honda:freed",
        "honda:city", "honda:civic", "honda:br-v",
        "hyundai:santro", "hyundai:i10",
        "kia:picanto",
        "daihatsu:cuore", "daihatsu:mira", "daihatsu:move", "daihatsu:tanto",
        "daihatsu:cast", "daihatsu:hijet",
        "nissan:dayz", "nissan:roox",
        "mitsubishi:mirage",
        "changan:alsvin", "changan:karvaan",
        "proton:saga", "mazda:demio", "subaru:impreza",
    },
    "adaptive cruise control": {
        "suzuki:mehran", "suzuki:alto", "suzuki:alto 660cc", "suzuki:cultus",
        "suzuki:liana", "suzuki:baleno", "suzuki:swift", "suzuki:wagon r",
        "suzuki:every", "suzuki:bolan", "suzuki:apv", "suzuki:hustler", "suzuki:spacia",
        "toyota:vitz", "toyota:passo", "toyota:probox", "toyota:hiace",
        "toyota:corolla", "toyota:yaris", "toyota:hilux",
        "toyota:allion", "toyota:premio", "toyota:mark x",
        "honda:n-box", "honda:n-wgn", "honda:fit", "honda:freed",
        "honda:city", "honda:civic", "honda:br-v", "honda:grace",
        "hyundai:santro", "hyundai:elantra",
        "kia:picanto", "kia:stonic",
        "daihatsu:cuore", "daihatsu:mira", "daihatsu:move", "daihatsu:tanto",
        "daihatsu:cast", "daihatsu:hijet",
        "nissan:dayz", "nissan:roox",
        "mitsubishi:mirage", "mitsubishi:asx",
        "changan:alsvin", "changan:karvaan",
        "proton:saga", "mazda:demio", "mazda:mazda3", "subaru:impreza", "mg:zs",
    },
    "auto parking": {
        # Only very recent luxury imports — BMW 5/7 series 2019+,
        # Mercedes E/S class 2019+, Audi A6/A8, Porsche Cayenne 2020+
        "suzuki:mehran", "suzuki:alto", "suzuki:alto 660cc", "suzuki:cultus",
        "suzuki:liana", "suzuki:baleno", "suzuki:swift", "suzuki:wagon r",
        "suzuki:every", "suzuki:bolan", "suzuki:apv", "suzuki:hustler", "suzuki:spacia",
        "suzuki:jimny",
        "toyota:vitz", "toyota:passo", "toyota:probox", "toyota:hiace",
        "toyota:corolla", "toyota:yaris", "toyota:hilux", "toyota:allion",
        "toyota:premio", "toyota:mark x", "toyota:aqua", "toyota:rush",
        "toyota:fortuner", "toyota:c-hr", "toyota:raize", "toyota:camry",
        "toyota:prado",
        "honda:n-box", "honda:n-wgn", "honda:fit", "honda:freed",
        "honda:city", "honda:civic", "honda:br-v", "honda:grace",
        "honda:vezel", "honda:hr-v", "honda:accord", "honda:cr-v",
        "hyundai:santro", "hyundai:elantra", "hyundai:sonata", "hyundai:tucson",
        "kia:picanto", "kia:stonic", "kia:sportage", "kia:sorento",
        "daihatsu:cuore", "daihatsu:mira", "daihatsu:move", "daihatsu:tanto",
        "daihatsu:cast", "daihatsu:hijet", "daihatsu:rocky", "daihatsu:terios",
        "nissan:dayz", "nissan:roox", "nissan:juke", "nissan:x-trail", "nissan:patrol",
        "mitsubishi:mirage", "mitsubishi:asx", "mitsubishi:outlander",
        "mitsubishi:pajero", "mitsubishi:pajero sport",
        "changan:alsvin", "changan:karvaan", "changan:uni-t", "changan:oshan x7",
        "proton:saga", "proton:x70",
        "mazda:demio", "mazda:mazda3", "mazda:rx-8", "mazda:cx-3", "mazda:cx-5",
        "subaru:impreza", "subaru:xv", "subaru:forester", "subaru:brz",
        "mg:zs", "mg:zs ev", "mg:hs", "mg:rx5",
        "haval:jolion", "haval:h6", "chery:tiggo 4 pro", "chery:tiggo 8 pro",
        "land rover:evoque",
        "bmw:3 series", "bmw:x1", "bmw:x3",
        "mercedes-benz:cla", "mercedes-benz:c-class", "mercedes-benz:glc",
        "audi:a3", "audi:a4", "audi:q3", "audi:q5",
        "lexus:is", "lexus:nx", "lexus:rx",
    },

    # ── Parking Sensors ──────────────────────────────────────────────────────
    "parking sensors": {
        "suzuki:mehran", "suzuki:bolan",
        "daihatsu:cuore", "daihatsu:hijet",
        "hyundai:santro", "toyota:probox", "changan:karvaan",
    },

    # ── Back Camera ─────────────────────────────────────────────────────────
    "back camera": {
        "suzuki:mehran", "suzuki:bolan",
        "daihatsu:cuore", "daihatsu:hijet",
        "hyundai:santro", "toyota:probox", "changan:karvaan",
    },

    # ── Heated Seats ────────────────────────────────────────────────────────
    "heated seats": {
        "suzuki:mehran", "suzuki:alto", "suzuki:alto 660cc", "suzuki:cultus",
        "suzuki:liana", "suzuki:baleno", "suzuki:swift", "suzuki:wagon r",
        "suzuki:every", "suzuki:bolan", "suzuki:apv", "suzuki:jimny",
        "toyota:vitz", "toyota:passo", "toyota:probox", "toyota:hiace",
        "toyota:corolla", "toyota:yaris", "toyota:allion", "toyota:premio",
        "toyota:mark x", "toyota:aqua", "toyota:rush", "toyota:hilux",
        "toyota:c-hr", "toyota:raize",
        "honda:n-box", "honda:n-wgn", "honda:fit", "honda:freed",
        "honda:city", "honda:civic", "honda:br-v", "honda:grace",
        "honda:vezel", "honda:hr-v",
        "hyundai:santro", "hyundai:elantra",
        "kia:picanto", "kia:stonic", "kia:sportage",
        "daihatsu:cuore", "daihatsu:mira", "daihatsu:move", "daihatsu:tanto",
        "daihatsu:cast", "daihatsu:hijet", "daihatsu:rocky",
        "nissan:dayz", "nissan:roox", "nissan:juke",
        "mitsubishi:mirage", "mitsubishi:asx",
        "changan:alsvin", "changan:karvaan",
        "proton:saga", "mazda:demio", "mazda:cx-3",
        "subaru:impreza", "subaru:xv",
        "mg:zs", "mg:hs", "haval:jolion", "chery:tiggo 4 pro",
    },

    # ── Leather Seats ───────────────────────────────────────────────────────
    "leather seats": {
        "suzuki:mehran", "suzuki:bolan",
        "daihatsu:cuore", "daihatsu:hijet",
        "hyundai:santro", "toyota:probox", "changan:karvaan",
        "suzuki:alto", "suzuki:wagon r",
    },

    # ── 4WD / AWD ───────────────────────────────────────────────────────────
    "4wd": {
        "suzuki:mehran", "suzuki:alto", "suzuki:alto 660cc", "suzuki:cultus",
        "suzuki:liana", "suzuki:baleno", "suzuki:swift", "suzuki:wagon r",
        "suzuki:every", "suzuki:bolan", "suzuki:apv",
        "toyota:vitz", "toyota:passo", "toyota:probox", "toyota:hiace",
        "toyota:corolla", "toyota:yaris", "toyota:allion", "toyota:premio",
        "toyota:mark x", "toyota:aqua", "toyota:camry",
        "honda:n-box", "honda:n-wgn", "honda:fit", "honda:freed",
        "honda:city", "honda:civic", "honda:br-v", "honda:grace", "honda:accord",
        "hyundai:santro", "hyundai:elantra", "hyundai:sonata",
        "kia:picanto",
        "daihatsu:cuore", "daihatsu:mira", "daihatsu:move", "daihatsu:tanto",
        "daihatsu:cast", "daihatsu:hijet",
        "nissan:dayz", "nissan:roox",
        "mitsubishi:mirage",
        "changan:alsvin", "changan:karvaan",
        "proton:saga", "mazda:demio", "mazda:mazda3", "mazda:rx-8",
        "subaru:brz",   # BRZ is RWD
        "mg:zs",        # FWD only in PK
        "mercedes-benz:cla", "audi:a3",
    },

    # ── Hybrid ───────────────────────────────────────────────────────────────
    "hybrid": {
        "suzuki:mehran", "suzuki:cultus", "suzuki:liana", "suzuki:baleno",
        "suzuki:swift", "suzuki:wagon r", "suzuki:every", "suzuki:bolan",
        "suzuki:apv", "suzuki:jimny",
        "toyota:probox", "toyota:hiace", "toyota:hilux",
        "toyota:corolla", "toyota:yaris", "toyota:allion", "toyota:premio",
        "toyota:mark x", "toyota:rush", "toyota:fortuner",
        "honda:n-box", "honda:n-wgn", "honda:br-v",
        "honda:city", "honda:civic",
        "hyundai:santro", "kia:picanto",
        "daihatsu:cuore", "daihatsu:hijet",
        "mitsubishi:mirage", "mitsubishi:pajero",
        "changan:alsvin", "changan:karvaan",
        "proton:saga", "mazda:rx-8", "subaru:brz",
        "mg:zs",    # mg:zs is petrol; mg:zs ev is separate
    },

    # ── Blind Spot Monitor ──────────────────────────────────────────────────
    "blind spot monitor": {
        "suzuki:mehran", "suzuki:alto", "suzuki:alto 660cc", "suzuki:cultus",
        "suzuki:liana", "suzuki:baleno", "suzuki:swift", "suzuki:wagon r",
        "suzuki:every", "suzuki:bolan", "suzuki:apv",
        "toyota:vitz", "toyota:passo", "toyota:probox", "toyota:hiace",
        "toyota:corolla", "toyota:yaris", "toyota:hilux", "toyota:allion",
        "toyota:premio", "toyota:mark x", "toyota:aqua", "toyota:rush",
        "honda:n-box", "honda:n-wgn", "honda:fit", "honda:freed",
        "honda:city", "honda:civic", "honda:br-v", "honda:grace",
        "hyundai:santro", "hyundai:elantra",
        "kia:picanto", "kia:stonic",
        "daihatsu:cuore", "daihatsu:mira", "daihatsu:move", "daihatsu:tanto",
        "daihatsu:cast", "daihatsu:hijet",
        "nissan:dayz", "nissan:roox",
        "mitsubishi:mirage",
        "changan:alsvin", "changan:karvaan",
        "proton:saga", "mazda:demio", "subaru:impreza",
    },

    # ── Memory Seats ─────────────────────────────────────────────────────────
    # Pakistani CKD assemblers (Lucky Motors, Hyundai Nishat) explicitly omit
    # driver seat memory buttons from local spec. International specs ≠ PK spec.
    "memory seats": {
        "suzuki:mehran", "suzuki:alto", "suzuki:alto 660cc", "suzuki:cultus",
        "suzuki:liana", "suzuki:baleno", "suzuki:swift", "suzuki:wagon r",
        "suzuki:every", "suzuki:bolan", "suzuki:apv", "suzuki:jimny",
        "toyota:vitz", "toyota:passo", "toyota:probox", "toyota:hiace",
        "toyota:corolla", "toyota:yaris", "toyota:hilux", "toyota:aqua",
        "toyota:rush", "toyota:raize", "toyota:allion", "toyota:premio",
        "honda:n-box", "honda:n-wgn", "honda:fit", "honda:freed",
        "honda:city", "honda:civic", "honda:br-v", "honda:grace",
        "honda:vezel", "honda:hr-v",
        "hyundai:santro", "hyundai:elantra",
        "hyundai:tucson",   # PK CKD explicitly omits memory seats
        "kia:picanto", "kia:stonic",
        "kia:sportage",     # PK CKD explicitly omits memory seats
        "daihatsu:cuore", "daihatsu:mira", "daihatsu:move", "daihatsu:tanto",
        "daihatsu:cast", "daihatsu:hijet",
        "nissan:dayz", "nissan:roox",
        "mitsubishi:mirage",
        "changan:alsvin", "changan:karvaan",
        "proton:saga", "mazda:demio",
    },
}

# ---------------------------------------------------------------------------
# SUNROOF TRIM KNOWLEDGE
# Retained from MODEL_FEATURE_KNOWLEDGE — trim-level hint for sunroof queries.
# Injected as inline notes in the eligible list so the LLM knows which trim
# to specify. Only sunroof has trim-level data; all other features use the
# impossible-gate approach above which is sufficient.
# ---------------------------------------------------------------------------

_SUNROOF_TRIM_KNOWLEDGE: dict[str, list[str]] = {
    # ["any"] = all trims, [] / missing = unknown
    "toyota:corolla":          ["Grande", "Altis Grande", "X Corolla"],
    "toyota:fortuner":         ["VRZ", "Sigma3", "Legender"],
    "toyota:prado":            ["any"],
    "toyota:land cruiser":     ["any"],
    "toyota:camry":            ["any"],
    "toyota:crown":            ["any"],
    "toyota:mark x":           ["250G", "300G", "350G"],
    "toyota:allion":           ["A20", "A25", "250G"],
    "toyota:premio":           ["F L Package", "G L Package", "250G"],
    "toyota:c-hr":             ["any"],
    "toyota:raize":            ["Z", "G"],
    "toyota:yaris cross":      ["any"],
    "toyota:alphard":          ["any"],
    "toyota:vellfire":         ["any"],
    "honda:city":              ["Aspire", "1.5 Aspire", "RS"],
    "honda:civic":             ["RS", "Oriel 1.5T"],
    "honda:hr-v":              ["any"],
    "honda:vezel":             ["RS", "Z", "e:HEV Z"],
    "honda:accord":            ["any"],
    "honda:cr-v":              ["any"],
    "honda:grace":             ["Hybrid EX"],
    "kia:sportage":            ["Alpha AWD", "FWD Alpha"],
    "kia:sorento":             ["any"],
    "hyundai:tucson":          ["any"],
    "hyundai:elantra":         ["GLS", "GL"],
    "mitsubishi:pajero sport": ["GLS", "Exceed"],
    "mitsubishi:pajero":       ["GLS", "3.5 V6"],
    "nissan:patrol":           ["any"],
    "nissan:x-trail":          ["any"],
    "subaru:forester":         ["any"],
    "subaru:xv":               ["any"],
    "mazda:cx-5":              ["any"],
    "bmw:3 series":            ["any"],
    "bmw:5 series":            ["any"],
    "bmw:x3":                  ["any"],
    "bmw:x5":                  ["any"],
    "mercedes-benz:c-class":   ["any"],
    "mercedes-benz:e-class":   ["any"],
    "mercedes-benz:glc":       ["any"],
    "mercedes-benz:gle":       ["any"],
    "audi:a4":                 ["any"],
    "audi:q5":                 ["any"],
    "lexus:rx":                ["any"],
    "lexus:es":                ["any"],
    "land rover:range rover":  ["any"],
    "land rover:defender":     ["any"],
    "porsche:cayenne":         ["any"],
    "daihatsu:rocky":          ["G", "Premium"],
    "mg:hs":                   ["any"],
    "haval:jolion":            ["any"],
    "haval:h6":                ["any"],
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
    drive_req: str | None = None,
    powertrain_req: str | None = None,
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
      8. Drive gate       — strictly matches requested drive layout (AWD/4x4/FWD/RWD)

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

    # Normalise required_features strings → canonical _FEATURE_IMPOSSIBLE keys
    _FEAT_NORMALISE: dict[str, str] = {
        "sunroof":                 "sunroof",
        "moonroof":                "sunroof",
        "panoramic":               "panoramic sunroof",
        "panoramic sunroof":       "panoramic sunroof",
        "push start":              "push start",
        "push-start":              "push start",
        "button start":            "push start",
        "keyless":                 "keyless entry",
        "keyless entry":           "keyless entry",
        "keyless start":           "push start",
        "smart key":               "push start",
        "lane assist":             "lane assist",
        "lane departure":          "lane assist",
        "lane keep":               "lane assist",
        "lkas":                    "lane assist",
        "adaptive cruise":         "adaptive cruise control",
        "adaptive cruise control": "adaptive cruise control",
        "acc":                     "adaptive cruise control",
        "auto parking":            "auto parking",
        "self parking":            "auto parking",
        "automatic parking":       "auto parking",
        "parking sensors":         "parking sensors",
        "parking sensor":          "parking sensors",
        "pdc":                     "parking sensors",
        "back camera":             "back camera",
        "rear camera":             "back camera",
        "reverse camera":          "back camera",
        "parking camera":          "back camera",
        "backup camera":           "back camera",
        "heated seats":            "heated seats",
        "seat warmer":             "heated seats",
        "ventilated seats":        "heated seats",
        "leather seats":           "leather seats",
        "leather":                 "leather seats",
        "4wd":                     "4wd",
        "4x4":                     "4wd",
        "awd":                     "4wd",
        "four wheel drive":        "4wd",
        "all wheel drive":         "4wd",
        "hybrid":                  "hybrid",
        "hev":                     "hybrid",
        "phev":                    "hybrid",
        "blind spot":              "blind spot monitor",
        "bsm":                     "blind spot monitor",
        "blind spot monitor":      "blind spot monitor",
        "memory seats":            "memory seats",
        "memory seat":             "memory seats",
        "seat memory":             "memory seats",
        "driver memory":           "memory seats",
        "driver seat memory":      "memory seats",
    }

    active_feature_gates: set[str] = set()
    if required_features:
        for feat in required_features:
            feat_lower = feat.lower().strip()
            normalised = _FEAT_NORMALISE.get(feat_lower)
            if normalised:
                active_feature_gates.add(normalised)
            else:
                # Substring scan for partial matches (e.g. "adaptive cruise control")
                for raw, norm in _FEAT_NORMALISE.items():
                    if raw in feat_lower:
                        active_feature_gates.add(norm)
                        break

    # Convenience flag for sunroof-specific trim hint logic
    needs_sunroof = bool(
        active_feature_gates & {"sunroof", "panoramic sunroof"}
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
        if transmission_req == "Manual" and info["transmission"] == "auto":
            continue

        # 3b. Powertrain gate (Hybrid/EV)
        if powertrain_req:
            car_tags = info.get("tags", set())
            if powertrain_req == "hybrid" and "hybrid" not in car_tags:
                continue
            if powertrain_req == "ev" and "ev" not in car_tags:
                continue

        # 4. Drive type filtering
        if drive_req and info.get("drive") != drive_req:
            # Allow 4x4 when AWD is requested, but do NOT allow FWD for 4x4 queries
            if drive_req == "4x4" and info.get("drive") != "4x4":
                continue
            elif drive_req == "AWD" and info.get("drive") not in {"AWD", "4x4"}:
                continue
            elif drive_req == "FWD" and info.get("drive") != "FWD":
                continue

        # 5. Budget overlap
        if max_budget > 0 and max_budget < lo * 0.80:
            continue
        if min_budget > 0 and hi < min_budget * 0.80:
            continue

        # 6. Apex luxury gate
        if is_apex_luxury and max_budget > 0 and hi < max_budget * 0.55:
            continue

        # 6b. Ultra-luxury tier — exclude Prado at 4+ crore budgets
        # At 4-5 crore, only Lexus LX600, LC300, Range Rover, Defender, BMW X7, Mercedes GLS
        if max_budget >= 40_000_000 and key == "toyota:prado":
            continue

        # 7. Feature impossible gate — hard exclude models that can NEVER have
        #    any of the requested features. Uses _FEATURE_IMPOSSIBLE dict.
        #    Models not in the dict for a given feature pass through (unknown = allow).
        if active_feature_gates:
            skip = False
            for feat_key in active_feature_gates:
                impossible_set = _FEATURE_IMPOSSIBLE.get(feat_key, set())
                if key in impossible_set:
                    skip = True
                    break
            if skip:
                continue

        # 8. Exclusion gate
        display_lower = f"{make} {model}".lower()
        if any(ex in display_lower for ex in excluded_lower):
            continue

        # Fit score (Generation-Aware Affordability Logic)
        # A multi-generation car (Corolla 8L-85L) should score high at 20L because
        # older generations (Anda Shape) are physically affordable at that budget.
        if max_budget > 0:
            if max_budget >= lo:
                # Budget covers at least the entry generation of this model
                bracket_span = max(hi - lo, 1)
                affordability = (max_budget - lo) / bracket_span

                # Base score for any car where the budget covers at least the entry generation
                fit_score = 0.85

                # If budget is extremely high relative to a cheap car (e.g., 50L budget for Mehran/Liana),
                # penalize so the user gets recommended cars matching their status/budget, not cheap economy cars.
                if max_budget > hi * 1.3:
                    fit_score = max(0.20, 0.85 - ((max_budget - hi) / max_budget))
            else:
                # Budget is slightly below 'lo' floor (passed 80% leniency check)
                fit_score = 0.40
        else:
            fit_score = 0.50

        # Priority boost — prevents Liana/Baleno ranking above Corolla/Civic
        # Reliability/resale bonus — Toyota/Honda with "reliability" tag get +0.10 extra
        priority       = info.get("priority", 2)
        priority_boost = (3 - priority) * 0.15   # priority 1 → +0.30, 2 → +0.15, 3 → 0
        tags = info.get("tags", set())
        reliability_bonus = 0.10 if ("reliability" in tags and "resale" in tags) else 0.0
        priority_boost += reliability_bonus

        # Youth penalty — kei box vans deprioritised for young buyer queries
        youth_penalty = -0.20 if (is_youth_query and key in _KEI_BOX_VANS) else 0.0

        # Sedan tiering: boost C-segment/mid-size sedans for higher budgets
        sedan_tier_boost = 0.0
        if body_style == "Sedan" and max_budget >= 3_500_000:
            _C_SEGMENT_SEDANS = {
                "toyota:corolla", "honda:civic", "toyota:premio", "toyota:allion",
                "hyundai:elantra", "hyundai:sonata", "honda:accord", "toyota:camry",
                "toyota:mark x", "toyota:crown", "mazda:mazda3", "subaru:impreza",
            }
            if key in _C_SEGMENT_SEDANS:
                sedan_tier_boost = 0.20

        # Youth Sports/Style Boost & Penalty
        youth_style_score = 0.0
        if is_youth_query:
            _YOUTH_PREFERRED = {"honda:civic", "suzuki:swift", "toyota:vitz", "toyota:mark x", "subaru:impreza"}
            _YOUTH_DISLIKED   = {"suzuki:liana", "suzuki:baleno", "suzuki:margalla"}
            
            if key in _YOUTH_PREFERRED:
                youth_style_score = +0.25  # Boost Civic/Swift/Vitz to the top for young buyers
            elif key in _YOUTH_DISLIKED:
                youth_style_score = -0.35  # Heavily penalize boring uncle cars

        # 18 Lacs+ Uncle Car Penalty
        # Pakistani buyers spending 18+ Lacs expect Corolla/Civic/City, not Liana/Baleno
        budget_tier_penalty = 0.0
        if max_budget >= 1_800_000:
            _ENTRY_LEVEL_SEDANS = {"suzuki:liana", "suzuki:baleno", "suzuki:margalla", "nissan:sunny"}
            if key in _ENTRY_LEVEL_SEDANS:
                budget_tier_penalty = -0.50  # Heavy penalty: wipes out Liana/Baleno for 18L+ budgets

        final_score = fit_score + priority_boost + youth_penalty + sedan_tier_boost + youth_style_score + budget_tier_penalty

        # Display string with JDM / feature trim annotations
        display = f"{make.title()} {model.title()}"
        note    = ""
        if key == "suzuki:alto 660cc":
            note = " [JDM — always use trim='660cc' to avoid local Alto flood]"
        elif needs_sunroof:
            sunroof_trims = _SUNROOF_TRIM_KNOWLEDGE.get(key, [])
            if sunroof_trims and sunroof_trims != ["any"]:
                note = f" [sunroof only in: {', '.join(sunroof_trims)}]"
            elif sunroof_trims == ["any"]:
                note = " [sunroof: all trims]"
            # No note if not in _SUNROOF_TRIM_KNOWLEDGE — LLM uses its own knowledge

        scored.append((final_score, display, lo, hi, note))

    if not scored:
        # If feature gates blocked everything, retry WITHOUT feature gates
        # and inject a warning into the output string
        if active_feature_gates:
            # Re-run the loop without feature filtering
            for key, info in CAR_REGISTRY.items():
                lo = info["lo"]
                hi = info["hi"]
                make, model = key.split(":", 1)
                if body_style and body_style not in info["styles"]:
                    continue
                if info["chinese"] and not allow_chinese:
                    continue
                if transmission_req == "Automatic" and info["transmission"] == "manual":
                    continue
                if transmission_req == "Manual" and info["transmission"] == "auto":
                    continue
                if powertrain_req:
                    car_tags = info.get("tags", set())
                    if powertrain_req == "hybrid" and "hybrid" not in car_tags:
                        continue
                    if powertrain_req == "ev" and "ev" not in car_tags:
                        continue
                if max_budget > 0 and max_budget < lo * 0.80:
                    continue
                if min_budget > 0 and hi < min_budget * 0.80:
                    continue
                if key.lower() in excluded_lower:
                    continue
                display = f"{make.title()} {model.title()}"
                scored.append((0.5, display, lo, hi, " [feature not available — showing closest alternative]"))
            scored.sort(key=lambda x: x[0], reverse=True)

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

    feat_labels  = sorted(active_feature_gates) if active_feature_gates else []
    budget_note  = f"PKR {min_budget:,} – {max_budget:,}" if max_budget > 0 else "no budget limit"
    style_note   = f", body style: {body_style}" if body_style else ""
    feat_note    = f", requires: {', '.join(feat_labels)}" if feat_labels else ""
    total_note   = f"{len(scored)} eligible" + (f" (showing top {len(top)})" if len(scored) > 15 else "")

    suffix = ""
    if active_feature_gates:
        feat_str = ", ".join(feat_labels)
        suffix = (
            f"\nFEATURE NOTE: This query requires [{feat_str}]. "
            "Cars in this list have passed the impossible-feature gate — "
            "they are physically capable of having these features in some trim. "
        )
        if needs_sunroof:
            suffix += (
                "For sunroof: use the trim hint shown next to each car. "
                "Cars marked '[sunroof only in: X]' MUST be recommended with that trim. "
                "Cars marked '[sunroof: all trims]' are safe without trim specification. "
            )
        if active_feature_gates & {"lane assist", "adaptive cruise control", "blind spot monitor"}:
            suffix += (
                "For ADAS features (lane assist, adaptive cruise, blind spot): "
                "prefer 2019+ models and specify higher trims "
                "(e.g. Sigma3, VRZ, Alpha AWD, RS, Z grade). "
            )
        if "heated seats" in active_feature_gates:
            suffix += (
                "For heated seats: only luxury/premium trims have this — "
                "specify top trim variant. "
            )
        suffix += "The normalizer will verify feature presence in actual listing titles.\n"

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

        # Transmission gate (second line of defence)
        transmission_req = constraints.get("transmission")
        if info and transmission_req:
            car_trans = info.get("transmission", "both")
            if transmission_req == "Manual" and car_trans == "auto":
                print(f"[Validator] Dropping {t.make} {t.model} — auto-only, user wants Manual")
                continue
            if transmission_req == "Automatic" and car_trans == "manual":
                print(f"[Validator] Dropping {t.make} {t.model} — manual-only, user wants Automatic")
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
    body_style:        Optional[Literal["SUV", "Mini SUV", "Sedan", "Hatchback", "Pickup", "Crossover", "Van", "MPV", "Coupe"]] = None
    transmission:      Optional[Literal["Automatic", "Manual"]]                                     = None
    drive:             Optional[Literal["4x4", "AWD", "FWD", "RWD"]]                                = None
    powertrain:        Optional[Literal["hybrid", "ev"]]                                             = None
    use_case:          Optional[str]                                                                 = None
    origin_pref:       Optional[Literal["JDM", "Local", "European", "Chinese"]]                     = None
    direct_model:      Optional[str]                                                                 = Field(default=None, description="Explicitly mentioned car model (e.g. 'Civic', 'Vitz', 'Prado')")
    is_luxury_request: bool                                                                          = False
    required_features: list[str]                                                                     = Field(default_factory=list)
    strategy_summary:  str                                                                           = Field(default="", description="A friendly 2-sentence summary explaining the search interpretation and car strategy.")
    disclaimers:       list[str]                                                                     = Field(default_factory=list)
    current_car:       Optional[str]                                                                 = None
    user_prompt:       str                                                                           = Field(default="", exclude=True)  # injected post-extraction, never sent to LLM


async def extract_intent(user_prompt: str) -> UserIntent:
    """
    Phase 1 LLM call — pure signal extraction, temperature 0.0.

    After this returns, the CALLER (recommend_routes.py) must inject:
        intent.user_prompt = user_prompt
    before calling resolve_constraints(intent), so apply_keyword_intent()
    has the raw string available for Python-level intent overrides.
    """
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
        "- body_style: CRITICAL - You MUST extract this if the user mentions any car type.\n"
        "  Map 'suv', 'jeep', '4x4' -> SUV.\n"
        "  Map 'crossover', 'compact suv' -> Crossover.\n"
        "  Map 'mini suv', 'compact 4x4' -> Mini SUV.\n"
        "  Map 'car', 'sedan', 'diggi', 'big trunk' -> Sedan.\n"
        "  Map 'small car', 'hatchback' -> Hatchback.\n"
        "  Map 'pickup', 'truck', 'dala' -> Pickup.\n"
        "  Map 'van', 'mpv', '11 seater', '7 seater' -> MPV or Van.\n"
        "  Map 'sports car', '2 door', 'coupe', 'rx8', '350z', 'supra', 'brz' -> Coupe.\n"
        "- origin_pref: 'Japanese' or 'JDM' -> JDM. 'European' -> European. "
        "'Chinese' -> Chinese. 'local' -> Local.\n"
        "- current_car: If the user states they currently own, are upgrading from, or are replacing a specific car (e.g., 'upgrading from Bolan', 'replacing my Mehran'), extract that model name here (e.g. 'Bolan', 'Mehran').\n"
        "- direct_model: If the user explicitly mentions a specific car model (e.g. 'Civic', 'Vitz', 'Prado'), capture it here.\n"
        "- powertrain: 'hybrid' if user mentions hybrid/HEV/e-power/aqua/prius. "
        "'ev' if user mentions electric/EV/battery car/BEV. Leave null otherwise.\n"
        "- strategy_summary: Write a friendly 2-sentence summary explaining how you "
        "interpreted the request and what kind of cars you will prioritize. "
        "Example: 'You are looking for a fun daily driver for campus commutes with "
        "responsive acceleration under PKR 25 Lacs. We have prioritized punchy 1.3L "
        "automatic hatchbacks like the Suzuki Swift and Toyota Vitz over sluggish 660cc "
        "eco-cars or high-maintenance project vehicles.' Always be specific to the "
        "user's actual request — never generic.\n"
        "  IMPORTANT: If the user asks for a mathematically impossible combination in the Pakistani market "
        "(e.g., a 7-seater sports car with <5s 0-100 under 25 Lakhs, or a brand new luxury SUV under 30 Lakhs), "
        "you MUST explicitly state in this summary which constraints you had to drop or trade-off to find realistic options.\n"
        "- Leave null if not clearly stated — do not guess."
    )
    response_text = await generate_content_resilient(
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=UserIntent,
            temperature=0.0,
        ),
    )
    return UserIntent.model_validate_json(response_text)


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

    excluded_models = []
    if intent.current_car:
        excluded_models.append(intent.current_car)

    constraints = {
        "min_budget":        min_budget,
        "max_budget":        max_budget,
        "min_year":          0,
        "is_apex_luxury":    is_apex_luxury,
        "allow_chinese":     intent.origin_pref == "Chinese",
        "body_style":        intent.body_style,
        "transmission":      intent.transmission,
        "drive":             intent.drive,
        "use_case":          intent.use_case,
        "origin_pref":       intent.origin_pref,
        "is_luxury_request": intent.is_luxury_request,
        "required_features":  intent.required_features,
        "strategy_summary":   intent.strategy_summary or "",
        "intent_id":          None,
        "excluded_models":    excluded_models,
    }

    # Apply keyword intent overrides — must receive raw user_prompt.
    # Called here so body_style/use_case/transmission overrides propagate
    # through the full pipeline (get_eligible_cars, select_car_targets, normalizer).
    # user_prompt is injected by the caller (recommend_routes.py) via intent.user_prompt.
    raw_prompt = getattr(intent, "user_prompt", "") or ""
    if raw_prompt:
        constraints = apply_keyword_intent(raw_prompt, constraints)

    # Detect powertrain from LLM extraction or prompt heuristics
    powertrain = intent.powertrain
    if not powertrain and raw_prompt:
        prompt_lower_pt = raw_prompt.lower()
        if any(w in prompt_lower_pt for w in ["electric", "100% electric", "battery car", "fully electric", " ev ", "bev"]):
            powertrain = "ev"
        elif any(w in prompt_lower_pt for w in ["hybrid", "e-power", "hev"]):
            powertrain = "hybrid"
    constraints["powertrain"] = powertrain

    # Auto-enable Chinese gate for EV queries (most budget EVs are Chinese)
    if powertrain == "ev":
        constraints["allow_chinese"] = True

    # Generate advisory disclaimers based on prompt + constraints
    if raw_prompt:
        constraints["disclaimers"] = generate_disclaimers(raw_prompt, constraints)
    else:
        constraints["disclaimers"] = []

    # Detect direct model request and override strategy summary
    if intent.direct_model:
        model_lower = intent.direct_model.lower().strip()
        # Direct lookup first, or fallback to the provided string if not in the alias map
        mapped_model = _CANONICAL_MODEL_MAP.get(model_lower, intent.direct_model)
        if mapped_model:
            constraints["strategy_summary"] = f"You specifically asked for a {mapped_model.title()}. We've included budget-eligible variants of the {mapped_model.title()} alongside its closest market competitors to give you a complete picture."

    return constraints


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
    drive             = constraints.get("drive")
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
        drive_req=drive,
        powertrain_req=constraints.get("powertrain"),
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
        "7. QUANTITY: CRITICAL INSTRUCTION — You MUST return EXACTLY 3 distinct targets if 3 or more eligible options exist in the list. Do NOT return 2. Only return fewer than 3 if the eligible list physically contains 1 or 2 cars.\n"
        "8. TRIM: For sunroof-required queries, use the trim specified in the list. "
        "Otherwise leave empty unless a trim meaningfully changes the car.\n"
        "9. RATIONALE: 1 buyer-friendly sentence — explain WHY this specific car "
        "fits this specific buyer. No generic descriptions.\n"
        "10. PANORAMIC SUNROOF RULE: A 'Panoramic Sunroof' is a full-length glass roof spanning "
        "most of the cabin ceiling. In Pakistan, Corolla Altis Grande, Civic Oriel, Honda Vezel, "
        "Toyota Raize, Subaru XV, and Mazda CX-5 feature SINGLE-PANE sunroofs only. You MUST NOT "
        "recommend them when a Panoramic Sunroof is requested. Pick true panoramic options like "
        "MG HS, Haval Jolion, Haval H6, or Changan Oshan X7.\n"
        "11. PUSH START RULE: Local Pak Suzuki models (Wagon R VXL/AGS, Cultus VXL/AGS, Alto VXL AGS) "
        "use traditional key ignition — NEVER recommend them for Push Start queries. For Toyota Vitz, "
        "base 'F 1.0' uses key ignition; you MUST explicitly set trim to 'Jewela', 'F Safety Edition', "
        "or 'U Grade' when Push Start is required.\n"
        "12. MEMORY SEATS CKD RULE: Locally assembled Kia Sportage and Hyundai Tucson in Pakistan "
        "DO NOT feature driver seat memory buttons — this feature was explicitly omitted by local "
        "assemblers. For memory seat queries under 1 Crore, restrict picks to Haval Jolion/H6, "
        "Changan Oshan X7 FutureSense, Hyundai Sonata 2.5L, or luxury imports."
    )

    response_text = await generate_content_resilient(
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=list[CarTargetRaw],
            temperature=0.2,
        ),
    )

    try:
        return [CarTargetRaw.model_validate(item) for item in json.loads(response_text)]
    except Exception as e:
        print(f"[Selector] Parse failed: {e}\nRaw: {response_text[:300]}")
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
    drive           = constraints.get("drive")
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
        drive_req=drive,
        powertrain_req=constraints.get("powertrain"),
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
        response_text = await generate_content_resilient(
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=list[CarTargetRaw],
                temperature=0.25,
            ),
        )
        raw_list = json.loads(response_text)
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
    drive           = original_constraints.get("drive")
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
        drive_req=drive,
        powertrain_req=original_constraints.get("powertrain"),
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
        response_text = await generate_content_resilient(
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=list[CarTargetRaw],
                temperature=0.3,
            ),
        )
        raw_list = json.loads(response_text)
        valid = [CarTargetRaw.model_validate(item) for item in raw_list]
        valid = _validate_targets(valid, original_constraints)
        return _deduplicate_and_format(valid, original_constraints)
    except Exception as e:
        print(f"[ExtendedMapper] Failed: {e}")
        traceback.print_exc()
        return []