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

_GEMINI_MODEL = "gemini-3.5-flash-lite"   # DO NOT CHANGE — gemini-2.0-flash-lite is dead


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
    "suzuki:fx":               {"lo": 150_000,    "hi": 600_000,    "styles": {"Hatchback"}, "drive": "FWD", "transmission": "manual", "tags": {"economy","city"}, "chinese": False},
    "suzuki:khyber":           {"lo": 300_000,    "hi": 1_200_000,  "styles": {"Hatchback"}, "drive": "FWD", "transmission": "manual", "tags": {"economy","city"}, "chinese": False},
    "suzuki:margalla":         {"lo": 400_000,    "hi": 1_500_000,  "styles": {"Sedan"},     "drive": "FWD", "transmission": "manual", "tags": {"economy","family"}, "chinese": False},
    "daihatsu:charade":        {"lo": 250_000,    "hi": 1_000_000,  "styles": {"Hatchback"}, "drive": "FWD", "transmission": "both",   "tags": {"economy","city"}, "chinese": False},
    "nissan:sunny":            {"lo": 500_000,    "hi": 1_800_000,  "styles": {"Sedan"},     "drive": "FWD", "transmission": "both",   "tags": {"economy","family"}, "chinese": False},
    "suzuki:mehran":           {"lo": 300_000, "hi": 1_500_000, "styles": {"Hatchback"}, "drive": "FWD", "transmission": "both",   "tags": {"economy","city"},          "chinese": False},
    "suzuki:alto":             {"lo": 700_000, "hi": 3_600_000, "styles": {"Hatchback"}, "drive": "FWD", "transmission": "both",   "tags": {"economy","city"},          "chinese": False},
    "suzuki:alto 660cc":       {"lo": 1_500_000, "hi": 3_800_000, "styles": {"Hatchback"}, "drive": "FWD", "transmission": "both",   "tags": {"economy","city","jdm"},    "chinese": False},
    "suzuki:cultus":           {"lo": 1_000_000, "hi": 4_500_000, "styles": {"Hatchback"}, "drive": "FWD", "transmission": "both",   "tags": {"economy","city","family"}, "chinese": False},
    "suzuki:wagon r":          {"lo": 1_500_000, "hi": 3_500_000, "styles": {"Hatchback"}, "drive": "FWD", "transmission": "both",   "tags": {"economy","city","family"}, "chinese": False},
    "suzuki:swift":            {"lo": 1_200_000, "hi": 5_200_000, "styles": {"Hatchback"}, "drive": "FWD", "transmission": "both",   "tags": {"economy","city","sports"}, "chinese": False},
    "suzuki:baleno":           {"lo": 1_000_000, "hi": 2_500_000, "styles": {"Sedan"}, "drive": "FWD", "transmission": "both",   "tags": {"economy","city","family"}, "chinese": False},
    "suzuki:liana":            {"lo": 1_200_000, "hi": 2_800_000, "styles": {"Sedan"}, "drive": "FWD", "transmission": "both",   "tags": {"economy","family"},        "chinese": False},
    "suzuki:hustler":          {"lo": 1_800_000, "hi": 4_000_000, "styles": {"Hatchback"}, "drive": "FWD", "transmission": "auto",   "tags": {"economy","city","jdm"},    "chinese": False},
    "suzuki:spacia":           {"lo": 1_800_000, "hi": 4_000_000, "styles": {"Hatchback"}, "drive": "FWD", "transmission": "auto",   "tags": {"economy","city","jdm","family"}, "chinese": False},
    "suzuki:solio":            {"lo": 2_000_000, "hi": 4_500_000, "styles": {"Hatchback"}, "drive": "FWD", "transmission": "auto",   "tags": {"economy","city","jdm","family"}, "chinese": False},
    "suzuki:jimny":            {"lo": 2_500_000, "hi": 8_500_000, "styles": {"Crossover"}, "drive": "4x4", "transmission": "both",   "tags": {"offroad","awd","jdm"},     "chinese": False},
    "suzuki:every":            {"lo": 1_000_000, "hi": 3_000_000, "styles": {"Van"}, "drive": "FWD", "transmission": "both",   "tags": {"cargo","economy","jdm"},   "chinese": False},
    "suzuki:bolan":            {"lo": 500_000, "hi": 2_000_000, "styles": {"Van"}, "drive": "RWD", "transmission": "manual", "tags": {"cargo","economy"},         "chinese": False},
    "suzuki:apv":              {"lo": 1_500_000, "hi": 3_500_000, "styles": {"Van"}, "drive": "FWD", "transmission": "auto",   "tags": {"family","7seat"},          "chinese": False},

    # ── Toyota ───────────────────────────────────────────────────────────────
    "toyota:vitz":             {"lo": 1_500_000, "hi": 4_500_000, "styles": {"Hatchback"}, "drive": "FWD", "transmission": "auto",   "tags": {"economy","city","jdm"},    "chinese": False},
    "toyota:passo":            {"lo": 1_500_000, "hi": 4_000_000, "styles": {"Hatchback"}, "drive": "FWD", "transmission": "auto",   "tags": {"economy","city","jdm"},    "chinese": False},
    "toyota:aqua":             {"lo": 2_500_000, "hi": 6_500_000, "styles": {"Hatchback"}, "drive": "FWD", "transmission": "auto",   "tags": {"hybrid","economy","city","jdm"}, "chinese": False},
    "toyota:tank":             {"lo": 3_000_000, "hi": 4_500_000, "styles": {"Hatchback"}, "drive": "FWD", "transmission": "auto",   "tags": {"economy","city","jdm","family"}, "chinese": False},
    "toyota:roomy":            {"lo": 3_000_000, "hi": 5_000_000, "styles": {"Hatchback"}, "drive": "FWD", "transmission": "auto",   "tags": {"economy","city","jdm","family"}, "chinese": False},
    "toyota:probox":           {"lo": 2_000_000, "hi": 4_500_000, "styles": {"Van"}, "drive": "FWD", "transmission": "both",   "tags": {"cargo","economy","jdm"},   "chinese": False},
    "toyota:corolla":          {"lo": 2_000_000, "hi": 8_500_000, "styles": {"Sedan"}, "drive": "FWD", "transmission": "both",   "tags": {"family","city","economy"}, "chinese": False},
    "toyota:yaris":            {"lo": 3_500_000, "hi": 6_000_000, "styles": {"Sedan"}, "drive": "FWD", "transmission": "auto",   "tags": {"family","city"},           "chinese": False},
    "toyota:allion":           {"lo": 3_000_000, "hi": 8_000_000, "styles": {"Sedan"}, "drive": "FWD", "transmission": "auto",   "tags": {"family","jdm","city"},     "chinese": False},
    "toyota:premio":           {"lo": 3_500_000, "hi": 9_000_000, "styles": {"Sedan"}, "drive": "FWD", "transmission": "auto",   "tags": {"family","jdm","city"},     "chinese": False},
    "toyota:mark x":           {"lo": 3_000_000, "hi": 7_000_000, "styles": {"Sedan"}, "drive": "RWD", "transmission": "auto",   "tags": {"sports","jdm","performance"}, "chinese": False},
    "toyota:fielder":          {"lo": 2_500_000, "hi": 6_000_000, "styles": {"Sedan"}, "drive": "FWD", "transmission": "auto",   "tags": {"family","jdm","cargo"},    "chinese": False},
    "toyota:prius":            {"lo": 2_500_000, "hi": 12_000_000, "styles": {"Sedan"}, "drive": "FWD", "transmission": "auto",   "tags": {"hybrid","economy","jdm"},  "chinese": False},
    "toyota:crown":            {"lo": 4_000_000, "hi": 25_000_000, "styles": {"Sedan"}, "drive": "RWD", "transmission": "auto",   "tags": {"sports","jdm","luxury","status","performance"}, "chinese": False},
    "toyota:camry":            {"lo": 7_000_000, "hi": 18_000_000, "styles": {"Sedan"}, "drive": "FWD", "transmission": "auto",   "tags": {"luxury","status","family"}, "chinese": False},
    "toyota:sienta":           {"lo": 3_000_000, "hi": 6_500_000, "styles": {"Van"}, "drive": "FWD", "transmission": "auto",   "tags": {"family","7seat","jdm"},    "chinese": False},
    "toyota:c-hr":             {"lo": 4_500_000, "hi": 10_000_000, "styles": {"Crossover"}, "drive": "FWD", "transmission": "auto",   "tags": {"city","jdm","sports"},     "chinese": False},
    "toyota:raize":            {"lo": 5_000_000, "hi": 7_500_000, "styles": {"Crossover"}, "drive": "FWD", "transmission": "auto",   "tags": {"city","family","jdm"},     "chinese": False},
    "toyota:yaris cross":      {"lo": 6_000_000, "hi": 9_500_000, "styles": {"Crossover"}, "drive": "FWD", "transmission": "auto",   "tags": {"city","hybrid","jdm"},     "chinese": False},
    "toyota:rush":             {"lo": 5_500_000, "hi": 9_000_000, "styles": {"SUV"}, "drive": "FWD", "transmission": "auto",   "tags": {"family","7seat"},          "chinese": False},
    "toyota:fortuner":         {"lo": 9_000_000, "hi": 21_000_000, "styles": {"SUV"}, "drive": "4x4", "transmission": "auto",   "tags": {"family","offroad","status","7seat"}, "chinese": False},
    "toyota:hilux":            {"lo": 8_000_000, "hi": 16_000_000, "styles": {"Pickup"}, "drive": "4x4", "transmission": "both",   "tags": {"offroad","cargo","awd"},   "chinese": False},
    "toyota:alphard":          {"lo": 6_000_000, "hi": 35_000_000, "styles": {"Van"}, "drive": "FWD", "transmission": "auto",   "tags": {"luxury","status","family","7seat","jdm"}, "chinese": False},
    "toyota:vellfire":         {"lo": 6_000_000, "hi": 35_000_000, "styles": {"Van"}, "drive": "FWD", "transmission": "auto",   "tags": {"luxury","status","family","7seat","jdm"}, "chinese": False},
    "toyota:hiace":            {"lo": 3_500_000, "hi": 12_000_000, "styles": {"Van"}, "drive": "RWD", "transmission": "both",   "tags": {"cargo","7seat","family"},  "chinese": False},
    "toyota:prado":            {"lo": 2_500_000, "hi": 48_000_000, "styles": {"SUV"}, "drive": "4x4", "transmission": "auto",   "tags": {"luxury","status","offroad","awd"}, "chinese": False},
    "toyota:land cruiser":     {"lo": 2_500_000, "hi": 90_000_000, "styles": {"SUV"}, "drive": "4x4", "transmission": "auto",   "tags": {"luxury","status","offroad","awd"}, "chinese": False},

    # ── Honda ────────────────────────────────────────────────────────────────
    "honda:n-box":             {"lo": 1_800_000, "hi": 4_200_000, "styles": {"Hatchback"}, "drive": "FWD", "transmission": "auto",   "tags": {"economy","city","jdm"},    "chinese": False},
    "honda:n-wgn":             {"lo": 1_500_000, "hi": 3_800_000, "styles": {"Hatchback"}, "drive": "FWD", "transmission": "auto",   "tags": {"economy","city","jdm"},    "chinese": False},
    "honda:fit":               {"lo": 2_000_000, "hi": 5_500_000, "styles": {"Hatchback"}, "drive": "FWD", "transmission": "auto",   "tags": {"economy","city","jdm"},    "chinese": False},
    "honda:city":              {"lo": 1_500_000, "hi": 6_000_000, "styles": {"Sedan"}, "drive": "FWD", "transmission": "both",   "tags": {"economy","family","city"}, "chinese": False},
    "honda:civic":             {"lo": 2_000_000, "hi": 9_500_000, "styles": {"Sedan"}, "drive": "FWD", "transmission": "both",   "tags": {"family","city","sports"},  "chinese": False},
    "honda:grace":             {"lo": 3_500_000, "hi": 6_500_000, "styles": {"Sedan"}, "drive": "FWD", "transmission": "auto",   "tags": {"family","hybrid","jdm"},   "chinese": False},
    "honda:insight":           {"lo": 2_500_000, "hi": 6_500_000, "styles": {"Sedan"}, "drive": "FWD", "transmission": "auto",   "tags": {"hybrid","economy","jdm"},  "chinese": False},
    "honda:freed":             {"lo": 2_500_000, "hi": 6_000_000, "styles": {"Van"}, "drive": "FWD", "transmission": "auto",   "tags": {"family","7seat","jdm"},    "chinese": False},
    "honda:shuttle":           {"lo": 3_500_000, "hi": 7_000_000, "styles": {"Van"}, "drive": "FWD", "transmission": "auto",   "tags": {"family","hybrid","jdm"},   "chinese": False},
    "honda:stepwgn":           {"lo": 3_000_000, "hi": 8_000_000, "styles": {"Van"}, "drive": "FWD", "transmission": "auto",   "tags": {"family","7seat","jdm"},    "chinese": False},
    "honda:br-v":              {"lo": 3_500_000, "hi": 6_500_000, "styles": {"Crossover"}, "drive": "FWD", "transmission": "both",   "tags": {"family","7seat","city"},   "chinese": False},
    "honda:hr-v":              {"lo": 6_000_000, "hi": 8_500_000, "styles": {"Crossover"}, "drive": "FWD", "transmission": "auto",   "tags": {"city","jdm"},              "chinese": False},
    "honda:vezel":             {"lo": 4_000_000, "hi": 11_000_000, "styles": {"Crossover"}, "drive": "FWD", "transmission": "auto",   "tags": {"city","hybrid","jdm"},     "chinese": False},
    "honda:cr-v":              {"lo": 6_000_000, "hi": 14_000_000, "styles": {"SUV"}, "drive": "AWD", "transmission": "auto",   "tags": {"family","awd","jdm"},      "chinese": False},
    "honda:accord":            {"lo": 4_500_000, "hi": 12_000_000, "styles": {"Sedan"}, "drive": "FWD", "transmission": "auto",   "tags": {"luxury","family","jdm"},   "chinese": False},

    # ── Hyundai ──────────────────────────────────────────────────────────────
    "hyundai:santro":          {"lo": 700_000, "hi": 1_800_000, "styles": {"Hatchback"}, "drive": "FWD", "transmission": "both",   "tags": {"economy","city"},          "chinese": False},
    "hyundai:i10":             {"lo": 1_200_000, "hi": 3_000_000, "styles": {"Hatchback"}, "drive": "FWD", "transmission": "both",   "tags": {"economy","city"},          "chinese": False},
    "hyundai:elantra":         {"lo": 5_000_000, "hi": 7_500_000, "styles": {"Sedan"}, "drive": "FWD", "transmission": "auto",   "tags": {"family","city"},           "chinese": False},
    "hyundai:sonata":          {"lo": 7_500_000, "hi": 11_000_000, "styles": {"Sedan"}, "drive": "FWD", "transmission": "auto",   "tags": {"luxury","family"},         "chinese": False},
    "hyundai:tucson":          {"lo": 6_000_000, "hi": 9_000_000, "styles": {"SUV"}, "drive": "AWD", "transmission": "auto",   "tags": {"family","city","awd"},     "chinese": False},
    "hyundai:porter":          {"lo": 2_500_000, "hi": 4_000_000, "styles": {"Van"}, "drive": "FWD", "transmission": "both",   "tags": {"cargo"},                   "chinese": False},
    "hyundai:palisade":        {"lo": 18_000_000, "hi": 35_000_000, "styles": {"SUV"}, "drive": "AWD", "transmission": "auto",   "tags": {"luxury","family","7seat","awd"}, "chinese": False},

    # ── Kia ──────────────────────────────────────────────────────────────────
    "kia:picanto":             {"lo": 2_500_000, "hi": 3_800_000, "styles": {"Hatchback"}, "drive": "FWD", "transmission": "auto",   "tags": {"economy","city"},          "chinese": False},
    "kia:stonic":              {"lo": 4_500_000, "hi": 6_000_000, "styles": {"Crossover"}, "drive": "FWD", "transmission": "auto",   "tags": {"city","family"},           "chinese": False},
    "kia:sportage":            {"lo": 5_500_000, "hi": 10_000_000, "styles": {"SUV"}, "drive": "AWD", "transmission": "auto",   "tags": {"family","city","awd"},     "chinese": False},
    "kia:sorento":             {"lo": 7_500_000, "hi": 11_000_000, "styles": {"SUV"}, "drive": "AWD", "transmission": "auto",   "tags": {"family","7seat","awd"},    "chinese": False},
    "kia:carnival":            {"lo": 9_000_000, "hi": 18_000_000, "styles": {"Van"}, "drive": "FWD", "transmission": "auto",   "tags": {"luxury","family","7seat"}, "chinese": False},

    # ── Daihatsu ─────────────────────────────────────────────────────────────
    "daihatsu:cuore":          {"lo": 600_000, "hi": 1_600_000, "styles": {"Hatchback"}, "drive": "FWD", "transmission": "both",   "tags": {"economy","city"},          "chinese": False},
    "daihatsu:mira":           {"lo": 1_200_000, "hi": 3_800_000, "styles": {"Hatchback"}, "drive": "FWD", "transmission": "auto",   "tags": {"economy","city","jdm"},    "chinese": False},
    "daihatsu:move":           {"lo": 1_200_000, "hi": 3_500_000, "styles": {"Hatchback"}, "drive": "FWD", "transmission": "auto",   "tags": {"economy","city","jdm"},    "chinese": False},
    "daihatsu:tanto":          {"lo": 1_500_000, "hi": 4_000_000, "styles": {"Hatchback"}, "drive": "FWD", "transmission": "auto",   "tags": {"economy","city","jdm","family"}, "chinese": False},
    "daihatsu:cast":           {"lo": 2_000_000, "hi": 3_500_000, "styles": {"Hatchback"}, "drive": "FWD", "transmission": "auto",   "tags": {"economy","city","jdm"},    "chinese": False},
    "daihatsu:hijet":          {"lo": 1_000_000, "hi": 2_500_000, "styles": {"Van"}, "drive": "FWD", "transmission": "both",   "tags": {"cargo","economy"},         "chinese": False},
    "daihatsu:rocky":          {"lo": 5_000_000, "hi": 7_500_000, "styles": {"Crossover"}, "drive": "FWD", "transmission": "auto",   "tags": {"city","jdm"},              "chinese": False},
    "daihatsu:terios":         {"lo": 2_500_000, "hi": 6_000_000, "styles": {"Crossover"}, "drive": "AWD", "transmission": "both",   "tags": {"offroad","family"},        "chinese": False},

    # ── Nissan ───────────────────────────────────────────────────────────────
    "nissan:dayz":             {"lo": 1_500_000, "hi": 3_500_000, "styles": {"Hatchback"}, "drive": "FWD", "transmission": "auto",   "tags": {"economy","city","jdm"},    "chinese": False},
    "nissan:roox":             {"lo": 1_500_000, "hi": 3_800_000, "styles": {"Hatchback"}, "drive": "FWD", "transmission": "auto",   "tags": {"economy","city","jdm"},    "chinese": False},
    "nissan:note":             {"lo": 3_500_000, "hi": 6_500_000, "styles": {"Sedan"}, "drive": "FWD", "transmission": "auto",   "tags": {"hybrid","economy","jdm"},  "chinese": False},
    "nissan:juke":             {"lo": 3_500_000, "hi": 8_000_000, "styles": {"Crossover"}, "drive": "FWD", "transmission": "auto",   "tags": {"city","sports","jdm"},     "chinese": False},
    "nissan:x-trail":          {"lo": 5_000_000, "hi": 14_000_000, "styles": {"SUV"}, "drive": "AWD", "transmission": "auto",   "tags": {"family","awd"},            "chinese": False},
    "nissan:patrol":           {"lo": 20_000_000, "hi": 55_000_000, "styles": {"SUV"}, "drive": "4x4", "transmission": "auto",   "tags": {"luxury","status","offroad","awd"}, "chinese": False},

    # ── Mitsubishi ───────────────────────────────────────────────────────────
    "mitsubishi:mirage":       {"lo": 2_000_000, "hi": 4_500_000, "styles": {"Sedan"}, "drive": "FWD", "transmission": "auto",   "tags": {"economy","city","jdm"},    "chinese": False},
    "mitsubishi:asx":          {"lo": 3_500_000, "hi": 8_000_000, "styles": {"Crossover"}, "drive": "AWD", "transmission": "auto",   "tags": {"city","awd","jdm"},        "chinese": False},
    "mitsubishi:outlander":    {"lo": 5_000_000, "hi": 14_000_000, "styles": {"SUV"}, "drive": "AWD", "transmission": "auto",   "tags": {"family","awd"},            "chinese": False},
    "mitsubishi:pajero":       {"lo": 1_800_000, "hi": 16_000_000, "styles": {"SUV"}, "drive": "4x4", "transmission": "auto",   "tags": {"offroad","awd","status"},  "chinese": False},
    "mitsubishi:pajero sport": {"lo": 8_000_000, "hi": 18_000_000, "styles": {"SUV"}, "drive": "4x4", "transmission": "auto",   "tags": {"offroad","awd","status"},  "chinese": False},

    # ── Subaru ───────────────────────────────────────────────────────────────
    "subaru:impreza":          {"lo": 2_500_000, "hi": 6_000_000, "styles": {"Sedan"}, "drive": "AWD", "transmission": "both",   "tags": {"sports","awd","jdm","performance"}, "chinese": False},
    "subaru:xv":               {"lo": 4_000_000, "hi": 7_500_000, "styles": {"Crossover"}, "drive": "AWD", "transmission": "auto",   "tags": {"awd","city","jdm"},        "chinese": False},
    "subaru:forester":         {"lo": 4_500_000, "hi": 9_000_000, "styles": {"SUV"}, "drive": "AWD", "transmission": "auto",   "tags": {"awd","family","offroad"},  "chinese": False},
    "subaru:brz":              {"lo": 4_500_000, "hi": 10_000_000, "styles": {"Sedan"}, "drive": "FWD", "transmission": "both",   "tags": {"sports","performance","jdm"}, "chinese": False},

    # ── Mazda ────────────────────────────────────────────────────────────────
    "mazda:demio":             {"lo": 2_500_000, "hi": 4_500_000, "styles": {"Hatchback"}, "drive": "FWD", "transmission": "auto",   "tags": {"economy","city","jdm"},    "chinese": False},
    "mazda:mazda3":            {"lo": 3_000_000, "hi": 7_000_000, "styles": {"Sedan"}, "drive": "FWD", "transmission": "auto",   "tags": {"sports","city","jdm"},     "chinese": False},
    "mazda:rx-8":              {"lo": 1_500_000, "hi": 4_000_000, "styles": {"Sedan"}, "drive": "RWD", "transmission": "both",   "tags": {"sports","performance","jdm"}, "chinese": False},
    "mazda:cx-3":              {"lo": 4_000_000, "hi": 7_000_000, "styles": {"Crossover"}, "drive": "FWD", "transmission": "auto",   "tags": {"city","jdm"},              "chinese": False},
    "mazda:cx-5":              {"lo": 5_500_000, "hi": 9_500_000, "styles": {"SUV"}, "drive": "AWD", "transmission": "auto",   "tags": {"family","awd","jdm"},      "chinese": False},

    # ── Chinese & New Entrants ────────────────────────────────────────────────
    "mg:zs":                   {"lo": 4_500_000, "hi": 6_500_000, "styles": {"Crossover"}, "drive": "FWD", "transmission": "auto",   "tags": {"city","economy"},          "chinese": True},
    "mg:zs ev":                {"lo": 7_000_000, "hi": 11_000_000, "styles": {"Crossover"}, "drive": "FWD", "transmission": "auto",   "tags": {"ev","city"},               "chinese": True},
    "mg:hs":                   {"lo": 6_000_000, "hi": 8_500_000, "styles": {"SUV"}, "drive": "FWD", "transmission": "auto",   "tags": {"family","city"},           "chinese": True},
    "mg:rx5":                  {"lo": 4_500_000, "hi": 9_000_000, "styles": {"SUV"}, "drive": "FWD", "transmission": "auto",   "tags": {"family","city"},           "chinese": True},
    "mg:cyberster":            {"lo": 15_000_000, "hi": 25_000_000, "styles": {"Sedan"}, "drive": "FWD", "transmission": "auto",   "tags": {"ev","sports","luxury"},    "chinese": True},
    "changan:alsvin":          {"lo": 3_200_000, "hi": 4_800_000, "styles": {"Sedan"}, "drive": "FWD", "transmission": "auto",   "tags": {"economy","city","family"}, "chinese": True},
    "changan:karvaan":         {"lo": 1_500_000, "hi": 3_000_000, "styles": {"Van"}, "drive": "FWD", "transmission": "both",   "tags": {"cargo","family","economy"},"chinese": True},
    "changan:oshan x7":        {"lo": 7_000_000, "hi": 9_500_000, "styles": {"SUV"}, "drive": "FWD", "transmission": "auto",   "tags": {"family","7seat"},          "chinese": True},
    "changan:uni-t":           {"lo": 8_000_000, "hi": 11_000_000, "styles": {"SUV"}, "drive": "FWD", "transmission": "auto",   "tags": {"family","city"},           "chinese": True},
    "changan:deepal s07":      {"lo": 13_000_000, "hi": 18_000_000, "styles": {"SUV"}, "drive": "FWD", "transmission": "auto",   "tags": {"ev","luxury","family"},    "chinese": True},
    "changan:deepal l07":      {"lo": 13_000_000, "hi": 18_000_000, "styles": {"Sedan"}, "drive": "FWD", "transmission": "auto",   "tags": {"ev","luxury"},             "chinese": True},
    "haval:jolion":            {"lo": 7_000_000, "hi": 9_000_000, "styles": {"SUV"}, "drive": "FWD", "transmission": "auto",   "tags": {"family","city"},           "chinese": True},
    "haval:h6":                {"lo": 8_900_000, "hi": 10_000_000, "styles": {"SUV"}, "drive": "AWD", "transmission": "auto",   "tags": {"family","awd"},            "chinese": True},
    "haval:h6 hev":            {"lo": 11_400_000, "hi": 14_000_000, "styles": {"SUV"}, "drive": "AWD", "transmission": "auto",   "tags": {"hybrid","family","awd"},   "chinese": True},
    "chery:tiggo 4 pro":       {"lo": 5_500_000, "hi": 7_500_000, "styles": {"Crossover"}, "drive": "FWD", "transmission": "auto",   "tags": {"city","family"},           "chinese": True},
    "chery:tiggo 8 pro":       {"lo": 8_000_000, "hi": 10_500_000, "styles": {"SUV"}, "drive": "FWD", "transmission": "auto",   "tags": {"family","7seat"},          "chinese": True},
    "proton:saga":             {"lo": 2_500_000, "hi": 3_800_000, "styles": {"Sedan"}, "drive": "FWD", "transmission": "auto",   "tags": {"economy","city","family"}, "chinese": True},
    "proton:x70":              {"lo": 6_000_000, "hi": 8_000_000, "styles": {"SUV"}, "drive": "FWD", "transmission": "auto",   "tags": {"family","city"},           "chinese": True},
    "byd:dolphin":             {"lo": 9_000_000, "hi": 12_000_000, "styles": {"Hatchback"}, "drive": "FWD", "transmission": "auto",   "tags": {"ev","city","economy"},     "chinese": True},
    "byd:atto 3":              {"lo": 11_000_000, "hi": 15_000_000, "styles": {"SUV"}, "drive": "FWD", "transmission": "auto",   "tags": {"ev","family"},             "chinese": True},
    "byd:seal":                {"lo": 16_000_000, "hi": 22_000_000, "styles": {"Sedan"}, "drive": "FWD", "transmission": "auto",   "tags": {"ev","sports","luxury"},    "chinese": True},
    "gwm:ora 03":              {"lo": 8_000_000, "hi": 11_000_000, "styles": {"Crossover"}, "drive": "FWD", "transmission": "auto",   "tags": {"ev","city"},               "chinese": True},
    "gwm:tank 500":            {"lo": 35_000_000, "hi": 45_000_000, "styles": {"SUV"}, "drive": "AWD", "transmission": "auto",   "tags": {"luxury","status","offroad","awd"}, "chinese": True},

    # ── European & Luxury ────────────────────────────────────────────────────
    "bmw:3 series":            {"lo": 6_000_000, "hi": 25_000_000, "styles": {"Sedan"}, "drive": "FWD", "transmission": "auto",   "tags": {"sports","luxury","status","performance"}, "chinese": False},
    "bmw:5 series":            {"lo": 8_000_000, "hi": 35_000_000, "styles": {"Sedan"}, "drive": "FWD", "transmission": "auto",   "tags": {"luxury","status","family"}, "chinese": False},
    "bmw:7 series":            {"lo": 15_000_000, "hi": 60_000_000, "styles": {"Sedan"}, "drive": "FWD", "transmission": "auto",   "tags": {"luxury","status"},         "chinese": False},
    "bmw:x1":                  {"lo": 7_000_000, "hi": 20_000_000, "styles": {"Crossover"}, "drive": "AWD", "transmission": "auto",   "tags": {"city","luxury","awd"},     "chinese": False},
    "bmw:x3":                  {"lo": 9_000_000, "hi": 30_000_000, "styles": {"SUV"}, "drive": "AWD", "transmission": "auto",   "tags": {"luxury","awd","status"},   "chinese": False},
    "bmw:x5":                  {"lo": 12_000_000, "hi": 50_000_000, "styles": {"SUV"}, "drive": "AWD", "transmission": "auto",   "tags": {"luxury","status","awd"},   "chinese": False},
    "bmw:x7":                  {"lo": 40_000_000, "hi": 80_000_000, "styles": {"SUV"}, "drive": "FWD", "transmission": "auto",   "tags": {"luxury","status","7seat"}, "chinese": False},
    "bmw:i4":                  {"lo": 25_000_000, "hi": 35_000_000, "styles": {"Sedan"}, "drive": "FWD", "transmission": "auto",   "tags": {"ev","luxury","performance"}, "chinese": False},
    "bmw:i7":                  {"lo": 60_000_000, "hi": 90_000_000, "styles": {"Sedan"}, "drive": "FWD", "transmission": "auto",   "tags": {"ev","luxury","status"},    "chinese": False},
    "bmw:ix":                  {"lo": 35_000_000, "hi": 55_000_000, "styles": {"SUV"}, "drive": "FWD", "transmission": "auto",   "tags": {"ev","luxury"},             "chinese": False},
    "mercedes-benz:cla":       {"lo": 7_000_000, "hi": 18_000_000, "styles": {"Sedan"}, "drive": "FWD", "transmission": "auto",   "tags": {"luxury","sports","status"}, "chinese": False},
    "mercedes-benz:c-class":   {"lo": 6_000_000, "hi": 30_000_000, "styles": {"Sedan"}, "drive": "FWD", "transmission": "auto",   "tags": {"luxury","status","family"}, "chinese": False},
    "mercedes-benz:e-class":   {"lo": 8_000_000, "hi": 45_000_000, "styles": {"Sedan"}, "drive": "FWD", "transmission": "auto",   "tags": {"luxury","status","family"}, "chinese": False},
    "mercedes-benz:s-class":   {"lo": 15_000_000, "hi": 80_000_000, "styles": {"Sedan"}, "drive": "FWD", "transmission": "auto",   "tags": {"luxury","status"},         "chinese": False},
    "mercedes-benz:gla":       {"lo": 7_500_000, "hi": 20_000_000, "styles": {"Crossover"}, "drive": "AWD", "transmission": "auto",   "tags": {"luxury","city","awd"},     "chinese": False},
    "mercedes-benz:glc":       {"lo": 12_000_000, "hi": 35_000_000, "styles": {"SUV"}, "drive": "AWD", "transmission": "auto",   "tags": {"luxury","status","awd"},   "chinese": False},
    "mercedes-benz:gle":       {"lo": 15_000_000, "hi": 50_000_000, "styles": {"SUV"}, "drive": "AWD", "transmission": "auto",   "tags": {"luxury","status","awd"},   "chinese": False},
    "mercedes-benz:gls":       {"lo": 30_000_000, "hi": 75_000_000, "styles": {"SUV"}, "drive": "FWD", "transmission": "auto",   "tags": {"luxury","status","7seat"}, "chinese": False},
    "audi:a3":                 {"lo": 5_000_000, "hi": 12_000_000, "styles": {"Sedan","Hatchback"}, "drive": "FWD", "transmission": "auto",   "tags": {"luxury","sports","city"},  "chinese": False},
    "audi:a4":                 {"lo": 6_500_000, "hi": 20_000_000, "styles": {"Sedan"}, "drive": "FWD", "transmission": "auto",   "tags": {"luxury","sports","status"}, "chinese": False},
    "audi:a5":                 {"lo": 8_000_000, "hi": 25_000_000, "styles": {"Sedan"}, "drive": "FWD", "transmission": "auto",   "tags": {"luxury","sports"},         "chinese": False},
    "audi:a6":                 {"lo": 9_000_000, "hi": 35_000_000, "styles": {"Sedan"}, "drive": "FWD", "transmission": "auto",   "tags": {"luxury","status","family"}, "chinese": False},
    "audi:a7":                 {"lo": 15_000_000, "hi": 45_000_000, "styles": {"Sedan"}, "drive": "FWD", "transmission": "auto",   "tags": {"luxury","status"},         "chinese": False},
    "audi:q2":                 {"lo": 6_500_000, "hi": 11_000_000, "styles": {"Crossover"}, "drive": "FWD", "transmission": "auto",   "tags": {"luxury","city"},           "chinese": False},
    "audi:q3":                 {"lo": 7_500_000, "hi": 15_000_000, "styles": {"Crossover"}, "drive": "AWD", "transmission": "auto",   "tags": {"luxury","city","awd"},     "chinese": False},
    "audi:q5":                 {"lo": 10_000_000, "hi": 25_000_000, "styles": {"SUV"}, "drive": "AWD", "transmission": "auto",   "tags": {"luxury","awd","status"},   "chinese": False},
    "audi:q7":                 {"lo": 15_000_000, "hi": 45_000_000, "styles": {"SUV"}, "drive": "FWD", "transmission": "auto",   "tags": {"luxury","status","7seat"}, "chinese": False},
    "audi:q8":                 {"lo": 30_000_000, "hi": 60_000_000, "styles": {"SUV"}, "drive": "FWD", "transmission": "auto",   "tags": {"luxury","status"},         "chinese": False},
    "audi:e-tron":             {"lo": 18_000_000, "hi": 35_000_000, "styles": {"SUV"}, "drive": "FWD", "transmission": "auto",   "tags": {"ev","luxury"},             "chinese": False},
    "audi:e-tron gt":          {"lo": 35_000_000, "hi": 60_000_000, "styles": {"Sedan"}, "drive": "FWD", "transmission": "auto",   "tags": {"ev","luxury","performance"}, "chinese": False},
    "porsche:macan":           {"lo": 20_000_000, "hi": 45_000_000, "styles": {"Crossover"}, "drive": "AWD", "transmission": "auto",   "tags": {"luxury","sports","awd"},   "chinese": False},
    "porsche:cayenne":         {"lo": 25_000_000, "hi": 70_000_000, "styles": {"SUV"}, "drive": "AWD", "transmission": "auto",   "tags": {"luxury","status","awd"},   "chinese": False},
    "porsche:panamera":        {"lo": 25_000_000, "hi": 60_000_000, "styles": {"Sedan"}, "drive": "FWD", "transmission": "auto",   "tags": {"luxury","status","performance"}, "chinese": False},
    "porsche:taycan":          {"lo": 40_000_000, "hi": 85_000_000, "styles": {"Sedan"}, "drive": "FWD", "transmission": "auto",   "tags": {"ev","luxury","performance"}, "chinese": False},
    "land rover:evoque":       {"lo": 9_000_000, "hi": 25_000_000, "styles": {"Crossover"}, "drive": "AWD", "transmission": "auto",   "tags": {"luxury","awd","status"},   "chinese": False},
    "land rover:velar":        {"lo": 20_000_000, "hi": 45_000_000, "styles": {"Crossover"}, "drive": "AWD", "transmission": "auto",   "tags": {"luxury","status","awd"},   "chinese": False},
    "land rover:discovery":    {"lo": 15_000_000, "hi": 50_000_000, "styles": {"SUV"}, "drive": "AWD", "transmission": "auto",   "tags": {"luxury","offroad","awd","7seat"}, "chinese": False},
    "land rover:range rover sport": {"lo": 20_000_000, "hi": 75_000_000, "styles": {"SUV"}, "drive": "AWD", "transmission": "auto",   "tags": {"luxury","status","awd"},   "chinese": False},
    "land rover:defender":     {"lo": 35_000_000, "hi": 85_000_000, "styles": {"SUV"}, "drive": "4x4", "transmission": "auto",   "tags": {"luxury","offroad","awd","status"}, "chinese": False},
    "land rover:range rover":  {"lo": 25_000_000, "hi": 95_000_000, "styles": {"SUV"}, "drive": "AWD", "transmission": "auto",   "tags": {"luxury","status","awd"},   "chinese": False},
    "land rover:vogue":        {"lo": 25_000_000, "hi": 95_000_000, "styles": {"SUV"}, "drive": "AWD", "transmission": "auto",   "tags": {"luxury","status","awd"},   "chinese": False},
    "lexus:ct200h":            {"lo": 4_000_000, "hi": 7_500_000, "styles": {"Hatchback"}, "drive": "FWD", "transmission": "auto",   "tags": {"hybrid","luxury","city"},  "chinese": False},
    "lexus:is":                {"lo": 5_000_000, "hi": 15_000_000, "styles": {"Sedan"}, "drive": "FWD", "transmission": "auto",   "tags": {"luxury","sports","status"}, "chinese": False},
    "lexus:es":                {"lo": 8_000_000, "hi": 25_000_000, "styles": {"Sedan"}, "drive": "FWD", "transmission": "auto",   "tags": {"luxury","status","family"}, "chinese": False},
    "lexus:rx":                {"lo": 10_000_000, "hi": 35_000_000, "styles": {"SUV"}, "drive": "AWD", "transmission": "auto",   "tags": {"luxury","status","awd"},   "chinese": False},
    "lexus:nx":                {"lo": 12_000_000, "hi": 28_000_000, "styles": {"Crossover"}, "drive": "AWD", "transmission": "auto",   "tags": {"luxury","city","awd"},     "chinese": False},
    "lexus:lx570":             {"lo": 30_000_000, "hi": 75_000_000, "styles": {"SUV"}, "drive": "AWD", "transmission": "auto",   "tags": {"luxury","status","offroad","awd"}, "chinese": False},
    "lexus:lx":                {"lo": 30_000_000, "hi": 75_000_000, "styles": {"SUV"}, "drive": "AWD", "transmission": "auto",   "tags": {"luxury","status","offroad","awd"}, "chinese": False},
    "lexus:lx600":             {"lo": 90_000_000, "hi": 140_000_000, "styles": {"SUV"}, "drive": "AWD", "transmission": "auto",   "tags": {"luxury","status","offroad","awd"}, "chinese": False},
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
  - PAKISTANI MARKET REALITY: Families heavily prefer SEDANS over hatchbacks due to boot space ("diggi") and status.
  - If budget >= PKR 1,500_000 (15 Lacs), ALWAYS prioritize Sedans (Corolla, City, Civic, Liana, Baleno) over small hatchbacks (Passo, Wagon R, Vitz) unless the user explicitly requested a hatchback.
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
  - HARD SEPARATION: True SUVs (Land Cruiser, Prado, Pajero, Patrol, Fortuner) have ladder-frame chassis or true 4x4 systems.
  - Crossovers (Sportage, Tucson, Vezel, Rush) are unibody city cars — NEVER recommend crossovers when the user asks for a true SUV or rugged 4x4.
  - Old Land Cruisers (LC80/LC100), Prados, and Pajeros from 1990-2005 are extremely popular in Pakistan for rough terrain and Northern trips. Recommend them if budget allows!
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
  - Toyota > Honda for reliability track record in Pakistan market
  - Prefer models with established parts supply chains in major cities
  - If budget is wide, pick 1 reliable mainstream + 1 alternative make to show diversity
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
# ELIGIBLE CAR LIST BUILDER
# Single function — replaces the old get_budget_eligible_cars() + separate maps.
# Derives everything from CAR_REGISTRY.
# ---------------------------------------------------------------------------

def get_eligible_cars(
    max_budget: int,
    min_budget: int,
    allow_chinese: bool,
    body_style: str | None = None,
    is_apex_luxury: bool = False,
    transmission_req: str | None = None,
    excluded_models: list[str] | None = None,
    drive_req: str | None = None,
) -> str:
    """
    Returns a fit-score-sorted eligible car list as a prompt string.

    Filters applied (in order, all deterministic Python):
      1. Body style  — hard match against CAR_REGISTRY styles set
      2. Chinese gate — drop chinese=True unless allow_chinese=True
      3. Transmission — drop manual-only when user wants Automatic
      4. Budget overlap — [min_budget,max_budget] must intersect [lo,hi]
      5. Apex luxury gate — if is_apex_luxury, drop cars whose price
         ceiling is below max_budget * 0.55 (too cheap for the budget)
      6. Exclusion gate — drop already-tried/shown models
      7. Fit score — sort by budget-centrality so best-fitting cars appear
         first in the list the LLM reads

    The LLM then picks 1–3 from this pre-approved, pre-sorted list.
    """
    excluded_lower = {m.lower() for m in (excluded_models or [])}

    scored: list[tuple[float, str, int, int]] = []   # (fit_score, display, lo, hi)

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

        # 3. Transmission gate — only filter if user explicitly wants Automatic
        if transmission_req == "Automatic" and info["transmission"] == "manual":
            continue

        # Drive type filtering
        if drive_req and info.get("drive") != drive_req:
            # Allow 4x4 when AWD is requested, but do NOT allow FWD for 4x4 queries
            if drive_req == "4x4" and info.get("drive") != "4x4":
                continue
            elif drive_req == "AWD" and info.get("drive") not in {"AWD", "4x4"}:
                continue
            elif drive_req == "FWD" and info.get("drive") != "FWD":
                continue

        # 4. Budget overlap
        if max_budget > 0 and max_budget < lo * 0.80:
            continue   # budget can't reach floor
        if min_budget > 0 and hi < min_budget * 0.80:
            continue   # model ceiling below budget floor

        # 5. Apex luxury gate — prevents Fortuner appearing in 5-crore queries
        if is_apex_luxury and max_budget > 0 and hi < max_budget * 0.55:
            continue

        # 6. Exclusion gate
        display_lower = f"{make} {model}".lower()
        if any(ex in display_lower for ex in excluded_lower):
            continue

        # 7. Fit score — higher = budget more centered in this car's range
        if max_budget > 0:
            midpoint  = (lo + hi) / 2
            centered  = 1.0 - abs(max_budget - midpoint) / max(midpoint, 1)
            overlap   = max(0, min(max_budget, hi) - max(min_budget, lo))
            coverage  = overlap / max(hi - lo, 1)
            fit_score = 0.6 * coverage + 0.4 * max(0.0, min(1.0, centered))
        else:
            fit_score = 0.5   # no budget — neutral score

        display = f"{make.title()} {model.title()}"
        scored.append((fit_score, display, lo, hi))

    if not scored:
        style_note = f" matching body style '{body_style}'" if body_style else ""
        return (
            f"No eligible cars found{style_note} for this budget. "
            "Return an empty array []."
        )

    # Sort by fit score descending — best fit appears first
    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:15]   # cap at 15 to keep prompt lean

    lines = [
        f"  {display}: PKR {lo:,} – {hi:,}"
        for _, display, lo, hi in top
    ]

    budget_note = (
        f"PKR {min_budget:,} – {max_budget:,}" if max_budget > 0 else "no budget limit"
    )
    style_note  = f", body style: {body_style}" if body_style else ""
    total_note  = f"{len(scored)} eligible" + (f" (showing top {len(top)})" if len(scored) > 15 else "")

    return (
        f"ELIGIBLE CARS ({total_note}, budget {budget_note}{style_note}):\n"
        + "\n".join(lines)
        + "\n\nPick ONLY from this list. "
        "These are pre-verified against budget, body style, and transmission.\n"
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
    drive:             Optional[Literal["4x4", "AWD", "FWD", "RWD"]]                                = None
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
        "drive":             intent.drive,
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
    max_budget      = constraints.get("max_budget", 0)
    min_budget      = constraints.get("min_budget", 0)
    allow_chinese   = constraints.get("allow_chinese", False)
    body_style      = constraints.get("body_style")
    transmission    = constraints.get("transmission")
    drive           = constraints.get("drive")
    use_case        = constraints.get("use_case")
    is_apex_luxury  = constraints.get("is_apex_luxury", False)
    is_luxury       = constraints.get("is_luxury_request", False)
    origin_pref     = constraints.get("origin_pref")

    eligible_list = get_eligible_cars(
        max_budget=max_budget,
        min_budget=min_budget,
        allow_chinese=allow_chinese,
        body_style=body_style,
        is_apex_luxury=is_apex_luxury,
        transmission_req=transmission,
        excluded_models=None,
        drive_req=drive,
    )

    principles = _get_relevant_principles(use_case, is_luxury)

    budget_str = (
        f"PKR {min_budget:,} – {max_budget:,}" if max_budget > 0
        else "No budget stated"
    )

    buyer_profile = {
        "budget":            budget_str,
        "body_style":        body_style        or "No preference",
        "transmission":      transmission      or "No preference",
        "use_case":          use_case          or "General",
        "origin_pref":       origin_pref       or "No preference (default: Japanese/Korean)",
        "is_luxury_request": is_luxury,
        "is_apex_luxury":    is_apex_luxury,
        "required_features": constraints.get("required_features", []),
    }

    prompt = (
        f"{principles}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{eligible_list}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "TASK: You are a Pakistani used car expert. "
        "From the eligible list above, pick the best 1–3 cars for this buyer.\n\n"
        f"BUYER PROFILE:\n{json.dumps(buyer_profile, indent=2)}\n\n"
        "RANKING RULES:\n"
        "1. LIST ONLY: Never suggest a car not in the eligible list. "
        "The list is pre-verified by Python — trust it completely.\n"
        "2. PRINCIPLES FIRST: Apply the use-case principles above when ranking. "
        "They encode real Pakistani market knowledge — follow them.\n"
        "3. ORIGIN: If origin_pref is JDM, prefer JDM cars and specify exact trim "
        "(e.g. trim='G Grade', trim='RS Advance'). If European, prefer BMW/Audi/Mercedes/Porsche.\n"
        "4. DIVERSITY: Pick from 2–3 different makes when the list allows. "
        "Avoid all-Toyota or all-Honda picks unless the list genuinely forces it.\n"
        "8. QUANTITY: Always return 3 distinct targets if 3 or more eligible options exist in the list. Only return fewer than 3 if the eligible candidate list physically contains fewer than 3 cars.\n"
        "6. TRIM: Leave empty unless a specific trim meaningfully changes the car "
        "(e.g. WRX vs base Impreza). Do not invent trim names.\n"
        "7. RATIONALE: 1 buyer-friendly sentence — explain WHY this specific car "
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
    drive           = constraints.get("drive")
    use_case        = constraints.get("use_case")
    is_luxury       = constraints.get("is_luxury_request", False)

    eligible_list = get_eligible_cars(
        max_budget=max_budget,
        min_budget=min_budget,
        allow_chinese=allow_chinese,
        body_style=body_style,
        is_apex_luxury=is_apex_luxury,
        transmission_req=transmission,
        excluded_models=excluded_models,
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
        f"  Use case: {use_case or 'General'}\n\n"
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

    eligible_list = get_eligible_cars(
        max_budget=max_budget,
        min_budget=min_budget,
        allow_chinese=allow_chinese,
        body_style=body_style,
        is_apex_luxury=is_apex_luxury,
        transmission_req=transmission,
        excluded_models=excluded_models,
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
        f"  Use case: {use_case or 'General'}\n\n"
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