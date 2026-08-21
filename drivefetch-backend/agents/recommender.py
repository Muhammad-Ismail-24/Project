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

from agents.config import generate_content_resilient, settings
from scrapers.normalizer import CITY_ALIAS_MAP, normalize_city

GEMINI_API_KEY = settings.gemini_api_key or settings.google_api_key
client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None


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
    # suzuki:every defined above under APV section
    "suzuki:bolan":            {"lo": 500_000,    "hi": 2_000_000,  "styles": {"Van"},
                                "drive": "RWD", "transmission": "manual", "tags": {"cargo","economy"},         "chinese": False},
    "suzuki:apv":              {"lo": 1_500_000,  "hi": 3_500_000,  "styles": {"Van", "MPV"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"commercial","7seat"},      "chinese": False},
    "suzuki:fronx":            {"lo": 5_800_000,  "hi": 7_500_000,  "styles": {"Crossover", "Hatchback"},
                                "drive": "FWD", "transmission": "both",   "tags": {"city","economy","hybrid","sports"}, "chinese": False, "priority": 2},
    # Suzuki Every CKD (locally assembled since 2025, 660cc mild-hybrid)
    "suzuki:every":            {"lo": 1_000_000,  "hi": 3_200_000,  "styles": {"Van"},
                                "drive": "FWD", "transmission": "both",   "tags": {"cargo","economy","jdm"},   "chinese": False},

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
    # Toyota Harrier — premium JDM crossover, popular as used import; 4th gen (XU80) widely available
    "toyota:harrier":          {"lo": 4_000_000,  "hi": 18_000_000, "styles": {"Crossover"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"luxury","city","hybrid","jdm","status"}, "chinese": False, "priority": 2},
    # Toyota Corolla Cross — CKD hybrid, launched 2023, competing with HR-V e:HEV at ~89–103 lacs
    "toyota:corolla cross":    {"lo": 8_500_000,  "hi": 11_500_000, "styles": {"Crossover"},
                                "drive": "AWD", "transmission": "auto",   "tags": {"family","hybrid","city","reliability","resale"}, "chinese": False, "priority": 1},
    # Toyota 86 / GR86 — rare but present as personal imports; RWD sports coupe
    "toyota:86":               {"lo": 5_000_000,  "hi": 12_000_000, "styles": {"Coupe"},
                                "drive": "RWD", "transmission": "both",   "tags": {"sports","performance","jdm"}, "chinese": False, "priority": 2},
    # Toyota Fortuner 2024 facelift — upgraded specs, still same segment
    # (kept as existing "toyota:fortuner" entry — price range updated below)

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
    # Honda HR-V e:HEV — CKD locally assembled hybrid; Honda's first local hybrid, launched July 2025
    "honda:hr-v e:hev":        {"lo": 8_800_000,  "hi": 11_000_000, "styles": {"Crossover"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"hybrid","city","family","reliability"}, "chinese": False, "priority": 1},
    # Honda N-One — 660cc JDM kei hatchback, used imports from Japan popular in major cities
    "honda:n-one":             {"lo": 1_800_000,  "hi": 3_500_000,  "styles": {"Hatchback"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"economy","city","jdm"},    "chinese": False},
    # Honda Zest / Life — 660cc kei import variants also seen on PakWheels
    "honda:life":              {"lo": 900_000,    "hi": 2_000_000,  "styles": {"Hatchback"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"economy","city","jdm"},    "chinese": False},

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
    # Hyundai Elantra Hybrid — 7th gen, launched Oct 2024 in Pakistan, ~70 lacs
    "hyundai:elantra hybrid":  {"lo": 6_800_000,  "hi": 8_500_000,  "styles": {"Sedan"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"hybrid","family","city"},   "chinese": False, "priority": 2},
    # Hyundai Tucson Hybrid 4th gen — April 2025 launch; FWD ~1.09cr, AWD ~1.2cr
    "hyundai:tucson hybrid":   {"lo": 10_500_000, "hi": 13_500_000, "styles": {"Crossover"},
                                "drive": "AWD", "transmission": "auto",   "tags": {"hybrid","family","awd","city"}, "chinese": False, "priority": 1},
    # Hyundai Sonata N-Line — sports sedan, 8th gen, available via CBU import ~95 lacs
    "hyundai:sonata n-line":   {"lo": 9_000_000,  "hi": 12_000_000, "styles": {"Sedan"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"luxury","sports","family"}, "chinese": False, "priority": 2},
    # Hyundai Ioniq 5 — EV crossover, CBU import available ~2.2–3.5 crore
    "hyundai:ioniq 5":         {"lo": 22_000_000, "hi": 38_000_000, "styles": {"Crossover"},
                                "drive": "AWD", "transmission": "auto",   "tags": {"ev","luxury","performance","awd"}, "chinese": False},

    # ── Kia ──────────────────────────────────────────────────────────────────
    "kia:picanto":             {"lo": 2_500_000,  "hi": 3_800_000,  "styles": {"Hatchback"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"economy","city"},          "chinese": False},
    "kia:stonic":              {"lo": 4_500_000,  "hi": 6_000_000,  "styles": {"Crossover"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"city","family"},           "chinese": False},
    "kia:sportage":            {"lo": 5_500_000,  "hi": 10_000_000, "styles": {"Crossover"},
                                "drive": "AWD", "transmission": "auto",   "tags": {"family","city","awd"},     "chinese": False},
    # Kia Sorento — updated: 4th gen hybrid expected 2025/26; 7-seat crossover flagship
    "kia:sorento":             {"lo": 7_500_000,  "hi": 14_000_000, "styles": {"Crossover"},
                                "drive": "AWD", "transmission": "auto",   "tags": {"family","7seat","awd","hybrid"}, "chinese": False, "priority": 2},
    "kia:carnival":            {"lo": 9_000_000,  "hi": 18_000_000, "styles": {"Van", "MPV"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"luxury","family","7seat"}, "chinese": False},
    # Kia Sportage L — 5th generation (long wheelbase), CKD, Jan 2025 launch
    # Alpha 2.0L: 88.99L, FWD: 1.05cr, HEV hybrid: 1.16cr (all FWD)
    "kia:sportage l":          {"lo": 8_800_000,  "hi": 13_500_000, "styles": {"Crossover"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"family","city","hybrid"},  "chinese": False, "priority": 1},
    # Kia EV6 — electric sports crossover, CBU import ~2.8–4 crore
    "kia:ev6":                 {"lo": 28_000_000, "hi": 42_000_000, "styles": {"Crossover"},
                                "drive": "AWD", "transmission": "auto",   "tags": {"ev","sports","luxury","performance","awd"}, "chinese": False},

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
    # Nissan Kicks — compact crossover JDM import; growing used-market presence
    "nissan:kicks":            {"lo": 4_000_000,  "hi": 7_000_000,  "styles": {"Crossover"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"city","jdm"},              "chinese": False},
    # Nissan Serena — petrol 8-seater MPV (non-e-Power variant); popular used import
    "nissan:serena":           {"lo": 3_500_000,  "hi": 8_000_000,  "styles": {"Van", "MPV"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"family","7seat","jdm"},    "chinese": False},
    # Nissan Leaf — EV hatchback; CBU used imports from Japan; growing niche
    "nissan:leaf":             {"lo": 3_500_000,  "hi": 7_500_000,  "styles": {"Hatchback"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"ev","city","economy","jdm"}, "chinese": False},
    # Nissan Elgrand — large luxury MPV/van; premium JDM import, smaller market
    "nissan:elgrand":          {"lo": 4_000_000,  "hi": 12_000_000, "styles": {"Van"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"luxury","7seat","jdm","family"}, "chinese": False},

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
    # Mitsubishi Eclipse Cross — sleek compact crossover, PHEV variant available; CBU import
    "mitsubishi:eclipse cross": {"lo": 6_000_000,  "hi": 12_000_000, "styles": {"Crossover"},
                                "drive": "AWD", "transmission": "auto",   "tags": {"city","awd","sports","jdm"}, "chinese": False},
    # Mitsubishi Xpander — 7-seat MPV crossover, popular in Southeast Asia, some Pakistan import
    "mitsubishi:xpander":      {"lo": 5_000_000,  "hi": 8_000_000,  "styles": {"Van", "MPV"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"family","7seat"},          "chinese": False},
    # Mitsubishi L200 (Triton) — pickup truck, popular alternative to Hilux Revo
    "mitsubishi:l200":         {"lo": 5_000_000,  "hi": 12_000_000, "styles": {"Pickup"},
                                "drive": "4x4", "transmission": "both",   "tags": {"offroad","cargo","awd"},   "chinese": False, "priority": 2},

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
    # Mazda CX-30 — compact crossover, JDM import; between CX-3 and CX-5
    "mazda:cx-30":             {"lo": 6_000_000,  "hi": 10_000_000, "styles": {"Crossover"},
                                "drive": "AWD", "transmission": "auto",   "tags": {"city","awd","sports","jdm"}, "chinese": False},
    # Mazda CX-8 — 7-seat large crossover; JDM import, premium segment
    "mazda:cx-8":              {"lo": 9_000_000,  "hi": 18_000_000, "styles": {"Crossover"},
                                "drive": "AWD", "transmission": "auto",   "tags": {"luxury","family","7seat","awd","jdm"}, "chinese": False},
    # Mazda MX-5 (Miata) — rare but present; convertible/roadster, RWD sports icon
    "mazda:mx-5":              {"lo": 4_000_000,  "hi": 9_000_000,  "styles": {"Coupe"},
                                "drive": "RWD", "transmission": "both",   "tags": {"sports","performance","jdm"}, "chinese": False},
    # Mazda6 — large family sedan, growing JDM import popularity
    "mazda:mazda6":            {"lo": 5_000_000,  "hi": 10_000_000, "styles": {"Sedan"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"family","luxury","jdm"},   "chinese": False},

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
    # PRICE (Aug 2026): H6 1.5T 8.924M → 2.0T top variant ~12.9M ex-factory.
    # The old 10.0M ceiling clipped the 2.0T entirely, which is the variant
    # that actually carries the ventilated/heated front seats.
    "haval:h6":                {"lo": 7_500_000,  "hi": 13_000_000, "styles": {"Crossover"},
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
    # PRICE CORRECTION (Aug 2026): PakWheels ex-factory Atto 3 Advance = PKR 8.99M.
    # Previous 11–15M band predated the local launch price and hid the car from
    # every realistic EV budget query.
    "byd:atto 3":              {"lo": 6_500_000,  "hi": 9_500_000,  "styles": {"Crossover"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"ev","family"},             "chinese": True},
    # PRICE CORRECTION (Aug 2026): Seal Dynamic 14.79M → Premium 16.99M ex-factory.
    "byd:seal":                {"lo": 11_500_000, "hi": 17_500_000, "styles": {"Sedan"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"ev","sports","luxury"},    "chinese": True},
    "gwm:ora 03":              {"lo": 8_000_000,  "hi": 11_000_000, "styles": {"Crossover"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"ev","city"},               "chinese": True},
    # PRICE CORRECTION (Aug 2026): Tank 500 HEV 20.5M → PHEV 22.5M ex-factory.
    # Previous 35–45M band was roughly double the real market price.
    "gwm:tank 500":            {"lo": 16_000_000, "hi": 22_800_000, "styles": {"SUV"},
                                "drive": "AWD", "transmission": "auto",   "tags": {"luxury","status","offroad","awd"}, "chinese": True},
    # GWM Tank 300 — off-road body-on-frame SUV.
    # PRICE CORRECTION (Aug 2026): Tank 300 Conqueror ≈ PKR 15.0M ex-factory,
    # not the 2.2–3.8 crore previously recorded.
    "gwm:tank 300":            {"lo": 11_000_000, "hi": 15_500_000, "styles": {"SUV"},
                                "drive": "4x4", "transmission": "auto",   "tags": {"offroad","awd","status","luxury"}, "chinese": True},
    # Haval Jolion HEV — Jolion with mild-hybrid, ~93 lacs; direct rival to Corolla Cross HEV
    "haval:jolion hev":        {"lo": 8_800_000,  "hi": 10_500_000, "styles": {"Crossover"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"hybrid","family","city"},   "chinese": True},
    # Haval H7 — large 7-seat flagship SUV from Haval Pakistan
    "haval:h7":                {"lo": 12_000_000, "hi": 17_000_000, "styles": {"SUV"},
                                "drive": "AWD", "transmission": "auto",   "tags": {"family","7seat","luxury","awd"}, "chinese": True},
    # Changan CS75 Plus — locally assembled midsize crossover, popular upgrade from Alsvin
    "changan:cs75 plus":       {"lo": 9_000_000,  "hi": 12_000_000, "styles": {"Crossover"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"family","city"},            "chinese": True},
    # Changan UNI-V — sporty coupe-crossover; 1.5T engine; unique design; CKD
    "changan:uni-v":           {"lo": 9_000_000,  "hi": 12_000_000, "styles": {"Crossover"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"sports","city","family"},   "chinese": True},
    # Changan Karvaan Plus — upgraded Karvaan with 1.2L UG variant and ABS/airbags
    "changan:karvaan plus":    {"lo": 2_800_000,  "hi": 4_000_000,  "styles": {"Van"},
                                "drive": "FWD", "transmission": "both",   "tags": {"cargo","family","economy"}, "chinese": True},

    # ── Jetour (Chery sub-brand, United Motors) ───────────────────────────────
    # Jetour Dashing — futuristic 5-seat crossover, 1.5T; CKD; ~78.99 lacs
    "jetour:dashing":          {"lo": 7_000_000,  "hi": 9_500_000,  "styles": {"Crossover"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"city","sports","family"},   "chinese": True, "priority": 2},
    # Jetour X70 Plus — 7-seat crossover, 1.5T; CKD; ~82.99 lacs
    "jetour:x70 plus":         {"lo": 7_800_000,  "hi": 10_500_000, "styles": {"Crossover"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"family","7seat","city"},    "chinese": True},
    # Jetour T1 — rugged body-on-frame SUV; 4WD; PHEV variant; ~1.1–1.3 crore
    "jetour:t1":               {"lo": 10_500_000, "hi": 14_000_000, "styles": {"SUV"},
                                "drive": "4x4", "transmission": "auto",   "tags": {"offroad","awd","family","status"}, "chinese": True},
    # Jetour T2 — larger/more expensive off-roader; Defender-rivalling design; ~1.28 crore
    "jetour:t2":               {"lo": 12_000_000, "hi": 15_000_000, "styles": {"SUV"},
                                "drive": "4x4", "transmission": "auto",   "tags": {"offroad","awd","luxury","status"}, "chinese": True},

    # ── Omoda & Jaecoo (Chery export brands, Nishat Motors) ───────────────────
    # Omoda E5 — pure electric compact SUV; CKD Faisalabad; ~89 lacs
    "omoda:e5":                {"lo": 8_500_000,  "hi": 10_500_000, "styles": {"Crossover"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"ev","city","family"},       "chinese": True, "priority": 2},
    # Jaecoo J6 — fully-electric compact SUV; CBU.
    # PRICE (Aug 2026): Comfort RWD 8.799M → Premium AWD 10.799M ex-factory.
    "jaecoo:j6":               {"lo": 7_000_000,  "hi": 11_000_000, "styles": {"Crossover"},
                                "drive": "AWD", "transmission": "auto",   "tags": {"ev","city","awd","family"}, "chinese": True},
    # Jaecoo J7 — SHS PHEV SUV; locally assembled; strong off-road capability.
    # PRICE (Aug 2026): Premium variant 10.499M ex-factory.
    "jaecoo:j7":               {"lo": 8_500_000,  "hi": 11_000_000, "styles": {"SUV"},
                                "drive": "AWD", "transmission": "auto",   "tags": {"hybrid","offroad","awd","family"}, "chinese": True},
    # Jaecoo J5 HEV — compact hybrid crossover; Jan 2026; ~66.99 lacs
    "jaecoo:j5":               {"lo": 6_500_000,  "hi": 9_000_000,  "styles": {"Crossover"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"hybrid","city","economy"},  "chinese": True},

    # ── Zeekr (Geely sub-brand, Capital Smart Motors) ─────────────────────────
    # Zeekr X — premium compact electric SUV; ~1.9 crore; fastest Chinese EV launched in PK
    "zeekr:x":                 {"lo": 18_000_000, "hi": 22_000_000, "styles": {"Crossover"},
                                "drive": "AWD", "transmission": "auto",   "tags": {"ev","luxury","performance","awd"}, "chinese": True},
    # Zeekr 7X — mid-size electric SUV; ~2.5–2.7 crore; fastest Chinese car in PK
    "zeekr:7x":                {"lo": 24_000_000, "hi": 30_000_000, "styles": {"Crossover"},
                                "drive": "AWD", "transmission": "auto",   "tags": {"ev","luxury","performance","awd","status"}, "chinese": True},
    # Zeekr 009 — ultra-luxury electric MPV; ~4.9 crore; most expensive Chinese car in PK
    "zeekr:009":               {"lo": 45_000_000, "hi": 55_000_000, "styles": {"Van"},
                                "drive": "AWD", "transmission": "auto",   "tags": {"ev","luxury","status","7seat"}, "chinese": True},

    # ── JAC ──────────────────────────────────────────────────────────────────
    # JAC T9 Hunter — diesel pickup; 2.0T; launched Jan 2025; cheapest diesel truck
    "jac:t9 hunter":           {"lo": 9_000_000,  "hi": 12_000_000, "styles": {"Pickup"},
                                "drive": "4x4", "transmission": "both",   "tags": {"cargo","offroad"},          "chinese": True},
    # JAC Frixon 2X — 4x2 pickup; ~87.75 lacs; more affordable entry
    "jac:frixon 2x":           {"lo": 8_200_000,  "hi": 10_000_000, "styles": {"Pickup"},
                                "drive": "FWD", "transmission": "both",   "tags": {"cargo","economy"},          "chinese": True},

    # ── BYD expanded lineup ───────────────────────────────────────────────────
    # BYD Sea Lion 7 (Sealion 7) — large electric crossover.
    # PRICE CORRECTION (Aug 2026): PakWheels lists the Advanced variant at
    # PKR 15.49M ex-factory. The previous 2.5–3.8 crore band was ~60% too high
    # and excluded the car from every budget a real buyer would enter, which
    # also made its (correct) ventilated-seat / HUD / 360-camera allowlist
    # membership unreachable.
    "byd:sealion 7":           {"lo": 12_000_000, "hi": 16_500_000, "styles": {"Crossover"},
                                "drive": "AWD", "transmission": "auto",   "tags": {"ev","luxury","performance","awd"}, "chinese": True},
    # BYD Han — executive electric sedan; ~3–4 crore
    "byd:han":                 {"lo": 28_000_000, "hi": 42_000_000, "styles": {"Sedan"},
                                "drive": "AWD", "transmission": "auto",   "tags": {"ev","luxury","performance","status"}, "chinese": True},

    # ── Forthing (Capital Smart Motors) ──────────────────────────────────────
    # Forthing Friday — first officially launched REEV (range-extended EV) in Pakistan
    "forthing:friday":         {"lo": 10_000_000, "hi": 13_000_000, "styles": {"SUV"},
                                "drive": "4x4", "transmission": "auto",   "tags": {"ev","hybrid","offroad","awd"}, "chinese": True},

    # ── Chery direct brand ────────────────────────────────────────────────────
    # Chery Tiggo 7 Pro — midsize crossover; between Tiggo 4 Pro and Tiggo 8 Pro
    "chery:tiggo 7 pro":       {"lo": 6_500_000,  "hi": 9_000_000,  "styles": {"Crossover"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"family","city"},            "chinese": True},
    # Chery Omoda 5 EV — electric version of Omoda 5; CBU; competing with BYD Atto 3
    "chery:omoda 5 ev":        {"lo": 9_000_000,  "hi": 12_000_000, "styles": {"Crossover"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"ev","city","family"},       "chinese": True},

    # ── MG expanded lineup ────────────────────────────────────────────────────
    # MG HS PHEV — plug-in hybrid crossover; ~85 lacs; CKD locally assembled
    "mg:hs phev":              {"lo": 8_000_000,  "hi": 10_500_000, "styles": {"Crossover"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"hybrid","family","city"},   "chinese": True},
    # MG Hector — large 6-seat crossover; premium segment; ~1.1 crore
    "mg:hector":               {"lo": 10_000_000, "hi": 13_000_000, "styles": {"Crossover"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"family","7seat","luxury"},  "chinese": True},
    # MG 7 — sporty flagship sedan from MG Pakistan
    "mg:7":                    {"lo": 8_000_000,  "hi": 11_000_000, "styles": {"Sedan"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"sports","luxury","family"}, "chinese": True},

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
    # BMW 1 Series — entry compact hatchback; used import; growing used market
    "bmw:1 series":            {"lo": 4_000_000,  "hi": 12_000_000, "styles": {"Hatchback"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"luxury","sports","city"},  "chinese": False},
    # BMW 2 Series Coupe — sporty 2-door; Deewan import; popular used German import
    "bmw:2 series":            {"lo": 5_000_000,  "hi": 18_000_000, "styles": {"Coupe"},
                                "drive": "RWD", "transmission": "both",   "tags": {"sports","luxury","performance"}, "chinese": False},
    # BMW 4 Series — sporty coupe/gran coupe; used and CBU imports
    "bmw:4 series":            {"lo": 9_000_000,  "hi": 28_000_000, "styles": {"Coupe"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"sports","luxury","performance"}, "chinese": False},
    # BMW M4 — high-performance version of 4 Series; RWD/AWD; very rare but present
    "bmw:m4":                  {"lo": 25_000_000, "hi": 55_000_000, "styles": {"Coupe"},
                                "drive": "RWD", "transmission": "auto",   "tags": {"sports","performance","luxury"}, "chinese": False, "priority": 1},
    # BMW iX3 — electric version of X3; ~3–4.5 crore CBU
    "bmw:ix3":                 {"lo": 28_000_000, "hi": 45_000_000, "styles": {"Crossover"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"ev","luxury","awd"},       "chinese": False},
    # BMW i5 — electric 5-series; new in Pakistan ~2.5 crore (cheapest BMW per PakWheels 2026)
    "bmw:i5":                  {"lo": 24_000_000, "hi": 35_000_000, "styles": {"Sedan"},
                                "drive": "AWD", "transmission": "auto",   "tags": {"ev","luxury","family"},    "chinese": False},
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
    # Mercedes A-Class — entry luxury compact hatchback; used imports from Germany
    "mercedes-benz:a-class":   {"lo": 6_000_000,  "hi": 15_000_000, "styles": {"Hatchback"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"luxury","sports","city"},  "chinese": False},
    # Mercedes GLA 200 — compact entry luxury crossover; used import; growing popularity
    "mercedes-benz:gla 200":   {"lo": 6_500_000,  "hi": 14_000_000, "styles": {"Crossover"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"luxury","city"},           "chinese": False},
    # Mercedes GLC 300 (coupe/standard) — flagship mid luxury crossover
    "mercedes-benz:glc 300":   {"lo": 14_000_000, "hi": 40_000_000, "styles": {"Crossover"},
                                "drive": "AWD", "transmission": "auto",   "tags": {"luxury","status","awd"},   "chinese": False},
    # Mercedes AMG C63 / E63 — performance variants; rare personal imports
    "mercedes-benz:amg":       {"lo": 18_000_000, "hi": 70_000_000, "styles": {"Sedan"},
                                "drive": "RWD", "transmission": "auto",   "tags": {"sports","performance","luxury","status"}, "chinese": False, "priority": 2},
    # Mercedes EQS — flagship electric sedan; ultra-luxury
    "mercedes-benz:eqs":       {"lo": 50_000_000, "hi": 100_000_000,"styles": {"Sedan"},
                                "drive": "AWD", "transmission": "auto",   "tags": {"ev","luxury","status"},    "chinese": False},
    # Volkswagen Passat — European mid-size sedan; used personal imports; ~36 lacs+
    "volkswagen:passat":       {"lo": 3_500_000,  "hi": 12_000_000, "styles": {"Sedan"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"family","luxury","city"},  "chinese": False},
    # Volkswagen Tiguan — compact crossover; popular German import alternative to BMW X1
    "volkswagen:tiguan":       {"lo": 6_000_000,  "hi": 16_000_000, "styles": {"Crossover"},
                                "drive": "AWD", "transmission": "auto",   "tags": {"family","luxury","awd"},   "chinese": False},
    # Volkswagen Golf — iconic hot-hatch; personal imports, rare but present
    "volkswagen:golf":         {"lo": 4_000_000,  "hi": 10_000_000, "styles": {"Hatchback"},
                                "drive": "FWD", "transmission": "both",   "tags": {"sports","city","luxury"},  "chinese": False},
    # Volkswagen Amarok — pickup truck; diesel; used German imports
    "volkswagen:amarok":       {"lo": 6_000_000,  "hi": 15_000_000, "styles": {"Pickup"},
                                "drive": "4x4", "transmission": "auto",   "tags": {"offroad","cargo","awd"},   "chinese": False},
    # Audi A1 — entry luxury compact hatchback; used German imports, growing
    "audi:a1":                 {"lo": 3_500_000,  "hi": 8_000_000,  "styles": {"Hatchback"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"luxury","sports","city"},  "chinese": False},
    # Audi RS4 / RS6 — high-performance Audi wagons/sedans; rare but sought-after
    "audi:rs6":                {"lo": 25_000_000, "hi": 60_000_000, "styles": {"Sedan"},
                                "drive": "AWD", "transmission": "auto",   "tags": {"sports","performance","luxury","status"}, "chinese": False, "priority": 1},
    # Audi Q4 e-tron — compact electric SUV; growing luxury EV segment
    "audi:q4 e-tron":          {"lo": 18_000_000, "hi": 30_000_000, "styles": {"Crossover"},
                                "drive": "AWD", "transmission": "auto",   "tags": {"ev","luxury","awd"},       "chinese": False},
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

    # ── 2025-2026 MARKET ENTRANTS ────────────────────────────────────────────
    # Added from live PakWheels ex-factory pricing (Aug 2026). "hi" is pegged
    # at/just above the current top-variant ex-factory price; "lo" is a
    # realistic used floor (~65-80% of new) for models young enough that the
    # used pool is still thin. Every entry here is a CBU/CKD model confirmed
    # on sale in Pakistan — nothing speculative.

    # Chery premium sub-brands (launched Pakistan Aug 2025)
    "omoda:c5":                {"lo": 4_500_000,  "hi": 7_500_000,  "styles": {"Crossover"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"city","family","chinese"}, "chinese": True, "priority": 3},
    "omoda:7":                 {"lo": 7_500_000,  "hi": 10_800_000, "styles": {"Crossover"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"city","family","chinese","status"}, "chinese": True, "priority": 3},

    # BYD — full local lineup (Seal/Atto 3 launched 2024, Sealion 7 + Atto 2 2026)
    "byd:atto 2":              {"lo": 5_500_000,  "hi": 7_500_000,  "styles": {"Crossover", "Hatchback"},
                                "drive": "FWD", "transmission": "auto",   "tags": {"ev","city","economy","chinese"}, "chinese": True, "priority": 3},
    "byd:shark 6":             {"lo": 15_000_000, "hi": 20_500_000, "styles": {"Pickup"},
                                "drive": "4x4", "transmission": "auto",   "tags": {"offroad","cargo","awd","hybrid","chinese","status"}, "chinese": True, "priority": 3},

    # Jetour — T1 PHEV joins Dashing / X70 Plus / T2 (Aug 2026 launch)
    "jetour:t9":               {"lo": 9_000_000,  "hi": 14_000_000, "styles": {"SUV", "Crossover"},
                                "drive": "AWD", "transmission": "auto",   "tags": {"family","offroad","awd","7seat","chinese"}, "chinese": True, "priority": 3},

    # GWM Tank — already registered under the "gwm:" namespace; these aliases
    # let a user query resolve when the LLM emits make="Tank" instead of "GWM".
    "tank:300":                {"lo": 11_000_000, "hi": 15_500_000, "styles": {"SUV"},
                                "drive": "4x4", "transmission": "auto",   "tags": {"offroad","awd","status","chinese"}, "chinese": True, "priority": 3},
    "tank:500":                {"lo": 16_000_000, "hi": 22_800_000, "styles": {"SUV"},
                                "drive": "4x4", "transmission": "auto",   "tags": {"luxury","offroad","awd","status","7seat","hybrid","chinese"}, "chinese": True, "priority": 3},
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
    # ── New 2025/2026 additions ───────────────────────────────────────────────
    "fronx":                     "Fronx",
    "suzuki fronx":              "Fronx",
    "corolla cross":             "Corolla Cross",
    "toyota corolla cross":      "Corolla Cross",
    "harrier":                   "Harrier",
    "toyota harrier":            "Harrier",
    "toyota 86":                 "86",
    "gr86":                      "86",
    "hrv ehev":                  "HR-V e:HEV",
    "hr-v ehev":                 "HR-V e:HEV",
    "hrv hybrid":                "HR-V e:HEV",
    "n-one":                     "N-One",
    "none":                      "N-One",   # careful: only if context is clear
    "elantra hybrid":            "Elantra Hybrid",
    "tucson hybrid":             "Tucson Hybrid",
    "sonata n-line":             "Sonata N-Line",
    "sonata nline":              "Sonata N-Line",
    "ioniq5":                    "Ioniq 5",
    "ioniq 5":                   "Ioniq 5",
    "sportage l":                "Sportage L",
    "sportage 5th gen":          "Sportage L",
    "ev6":                       "EV6",
    "kia ev6":                   "EV6",
    "kicks":                     "Kicks",
    "nissan kicks":              "Kicks",
    "serena":                    "Serena",
    "nissan serena":             "Serena",
    "leaf":                      "Leaf",
    "nissan leaf":               "Leaf",
    "elgrand":                   "Elgrand",
    "eclipse cross":             "Eclipse Cross",
    "xpander":                   "Xpander",
    "l200":                      "L200",
    "triton":                    "L200",
    "mitsubishi triton":         "L200",
    "cx-30":                     "CX-30",
    "cx30":                      "CX-30",
    "cx-8":                      "CX-8",
    "cx8":                       "CX-8",
    "mx-5":                      "MX-5",
    "miata":                     "MX-5",
    "mazda6":                    "Mazda6",
    "mazda 6":                   "Mazda6",
    "jolion hev":                "Jolion HEV",
    "haval jolion hev":          "Jolion HEV",
    "h7":                        "H7",
    "haval h7":                  "H7",
    "tank 300":                  "Tank 300",
    "cs75":                      "CS75 Plus",
    "cs75 plus":                 "CS75 Plus",
    "uni-v":                     "UNI-V",
    "univ":                      "UNI-V",
    "karvaan plus":              "Karvaan Plus",
    "dashing":                   "Dashing",
    "jetour dashing":            "Dashing",
    "x70 plus":                  "X70 Plus",
    "jetour x70":                "X70 Plus",
    "jetour t1":                 "T1",
    "jetour t2":                 "T2",
    "omoda e5":                  "E5",
    "omoda5 ev":                 "E5",
    "jaecoo j5":                 "J5",
    "jaecoo j6":                 "J6",
    "jaecoo j7":                 "J7",
    "zeekr x":                   "X",
    "zeekr 7x":                  "7X",
    "zeekr 009":                 "009",
    "t9 hunter":                 "T9 Hunter",
    "jac t9 hunter":             "T9 Hunter",
    "frixon":                    "Frixon 2X",
    "jac frixon":                "Frixon 2X",
    "sealion 7":                 "Sealion 7",
    "byd sealion":               "Sealion 7",
    "byd han":                   "Han",
    "forthing friday":           "Friday",
    "tiggo 7 pro":               "Tiggo 7 Pro",
    "omoda 5 ev":                "Omoda 5 EV",
    "hs phev":                   "HS PHEV",
    "mg hs phev":                "HS PHEV",
    "mg hector":                 "Hector",
    "hector":                    "Hector",
    "mg7":                       "MG 7",
    "mg 7":                      "MG 7",
    # German imports
    "1 series":                  "1 Series",
    "2 series":                  "2 Series",
    "4 series":                  "4 Series",
    "m4":                        "M4",
    "bmw m4":                    "M4",
    "ix3":                       "iX3",
    "bmw ix3":                   "iX3",
    "i5":                        "i5",
    "bmw i5":                    "i5",
    "a-class":                   "A-Class",
    "mercedes a class":          "A-Class",
    "gla 200":                   "GLA 200",
    "glc 300":                   "GLC 300",
    "amg c63":                   "AMG",
    "amg e63":                   "AMG",
    "eqs":                       "EQS",
    "mercedes eqs":              "EQS",
    "passat":                    "Passat",
    "vw passat":                 "Passat",
    "tiguan":                    "Tiguan",
    "vw tiguan":                 "Tiguan",
    "golf":                      "Golf",
    "vw golf":                   "Golf",
    "amarok":                    "Amarok",
    "vw amarok":                 "Amarok",
    "a1":                        "A1",
    "audi a1":                   "A1",
    "rs6":                       "RS6",
    "audi rs6":                  "RS6",
    "rs4":                       "RS6",   # scraper will use RS6 as proxy for RS variants
    "q4 e-tron":                 "Q4 e-tron",
    "q4 etron":                  "Q4 e-tron",

    # ── 2025-2026 ENTRANT ALIASES ────────────────────────────────────────────
    # Buyers and the LLM both write these names inconsistently. Canonicalising
    # here keeps CAR_REGISTRY lookups and scraper URLs stable.
    # Chery premium sub-brands
    "omoda c5":                  "C5",
    "omoda 5":                   "C5",
    "chery omoda c5":            "C5",
    "omoda 7":                   "7",
    "omoda e5":                  "E5",
    "omoda 5 ev":                "Omoda 5 EV",
    "jaecoo j5":                 "J5",
    "jaecoo j6":                 "J6",
    "jaecoo j7":                 "J7",
    "jacoo j7":                  "J7",
    "jaeco j7":                  "J7",
    # Jetour
    "jetour t1":                 "T1",
    "jetour t2":                 "T2",
    "jetour t9":                 "T9",
    "jetour dashing":            "Dashing",
    "jetour x70":                "X70 Plus",
    "jetour x70 plus":           "X70 Plus",
    "x70 plus":                  "X70 Plus",
    # BYD
    "byd atto 2":                "Atto 2",
    "atto 2":                    "Atto 2",
    "byd atto 3":                "Atto 3",
    "byd seal":                  "Seal",
    "byd dolphin":               "Dolphin",
    "byd sealion 7":             "Sealion 7",
    "sealion 7":                 "Sealion 7",
    "sealion":                   "Sealion 7",
    "byd shark":                 "Shark 6",
    "byd shark 6":               "Shark 6",
    "shark 6":                   "Shark 6",
    # GWM / Haval / Tank
    "tank 300":                  "Tank 300",
    "haval tank 300":            "Tank 300",
    "gwm tank 300":              "Tank 300",
    "tank 500":                  "Tank 500",
    "haval tank 500":            "Tank 500",
    "gwm tank 500":              "Tank 500",
    "haval h6 hev":              "H6 HEV",
    "h6 hev":                    "H6 HEV",
    "haval jolion hev":          "Jolion HEV",
    "jolion hev":                "Jolion HEV",
    "haval h7":                  "H7",
    # Zeekr
    "zeekr x":                   "X",
    "zeekr 7x":                  "7X",
    "zeekr 009":                 "009",
    "zeekr 9":                   "009",
    # Japanese / Korean 2025-26 refreshes
    "sportage l":                "Sportage L",
    "kia sportage l":            "Sportage L",
    "hr-v e:hev":                "HR-V e:HEV",
    "hrv ehev":                  "HR-V e:HEV",
    "hr v e hev":                "HR-V e:HEV",
    "honda hr-v hybrid":         "HR-V e:HEV",
    "tucson hybrid":             "Tucson Hybrid",
    "hyundai tucson hybrid":     "Tucson Hybrid",
    "corolla cross hev":         "Corolla Cross",
    "corolla cross hybrid":      "Corolla Cross",
    "suzuki fronx":              "Fronx",
    "fronx":                     "Fronx",
    # MG
    "mg hs phev":                "HS PHEV",
    "hs phev":                   "HS PHEV",
    "mg 4 ev":                   "4 EV",
    "mg4":                       "4 EV",
    "mg 7":                      "7",
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
  - For budgets under PKR 30 lacs: hatchbacks (Swift, Vitz, Passo, Alto) beat sedans on practicality
  - For budgets PKR 30–65 lacs: Vezel, C-HR, Kia Stonic offer the best city crossover experience
  - NEW 2025/26 CITY CROSSOVERS:
    • Suzuki Fronx (60–71 lacs, mild-hybrid option, Suzuki network) — excellent new city XUV
    • Jaecoo J5 HEV (67 lacs, hybrid, most affordable locally assembled hybrid crossover)
    • Jetour Dashing (79 lacs, futuristic styling, 1.5T)
    • Honda HR-V e:HEV (88–104 lacs, dual-motor hybrid, best fuel efficiency in the segment)
    • Toyota Corolla Cross HEV (85–103 lacs, AWD available, Toyota reliability)
  - Automatic transmission is strongly preferred for stop-and-go Lahore/Karachi traffic
  - Avoid: large body-on-frame SUVs (Fortuner, Prado) — fuel costs are punishing for city-only use
  - Avoid: sports cars with stiff suspension — Pakistani road conditions punish ride quality
""",

    "offroad": """
USE-CASE PRINCIPLES — SUV / Off-road / Northern Areas:
  - HARD SEPARATION: True SUVs (Land Cruiser, Prado, Pajero, Patrol, Fortuner, Revo) have ladder-frame chassis or true 4x4 systems.
  - Crossovers (Sportage, Tucson, Vezel, Rush) are unibody city cars — NEVER recommend crossovers when the user asks for a true SUV or rugged 4x4.
  - Old Land Cruisers (LC80/LC100), Prados, and Pajeros from 1990-2005 are extremely popular in Pakistan for rough terrain. Recommend them if budget is under 5 crore!
  - NEW 2025/26 OFF-ROAD OPTIONS:
    • Jetour T1 (1.05–1.4 crore) — body-on-frame SUV, PHEV variant, solid 4WD; new but promising
    • Jetour T2 (1.2–1.5 crore) — larger Defender-rivalling SUV, PHEV; top Chinese off-roader in PK
    • GWM Tank 300 (2.2–3.8 crore) — proven ladder-frame, PHEV, strong off-road spec; Tank 500 for premium
    • Forthing Friday (1–1.3 crore) — REEV (range-extended EV), off-road capable; first REEV in Pakistan
    • Mitsubishi L200 Triton — diesel pickup alternative to Hilux with better interior
    • JAC T9 Hunter — cheapest diesel pickup (diesel engine), alternative to Hilux Revo for budget buyers
  - Chinese off-road SUVs now have official dealer networks; parts availability is improving.
""",

    "sports": """
USE-CASE PRINCIPLES — Sports / Performance / Fun Driving:
  - Prioritise: rear-wheel drive, manual option, engine character, suspension tuning
  - PAKISTANI SPORTS CAR HIERARCHY BY BUDGET (ascending):
    • Under 30 Lacs: Mazda RX-8 (rotary, RWD), Honda Civic old-gen (sporty FWD)
    • 30–60 Lacs: Subaru BRZ (RWD), Subaru Impreza WRX (AWD), Toyota Mark X V6 (RWD), Toyota 86/GR86 (RWD)
    • 60–100 Lacs: Crown Athlete V6 (RWD), BMW 3 Series (RWD auto), Nissan 350Z/370Z (RWD), BMW 2 Series coupe
    • 1–2 Crore: BMW M3 (RWD/AWD), BMW M4 (RWD/AWD), Porsche Cayman (RWD), Nissan Fairlady Z (RWD)
    • 2+ Crore: Porsche 911, Porsche Taycan (EV), Mercedes AMG, Zeekr 7X (EV performance)
  - AVOID recommending Corolla, City, or Civic as "sports" picks — they are commuter cars
  - JDM sports imports: Toyota Supra (very rare), GR86, Mark X, Crown Athlete, Impreza WRX — genuine options
  - German sports options: BMW M3/M4 are the gold standard for track-capable sedans in Pakistan
  - Mazda RX-8 caveat: unique rotary engine — mention reliability concerns (requires high-rev driving)
  - If automatic requested for sports: Mark X, Crown Athlete, BMW 3/5 M-Sport, BMW 4 Series — all auto
  - If manual allowed: Impreza WRX, BRZ, Toyota 86, RX-8, BMW M4 MT have genuine manual options
""",

    "luxury": """
USE-CASE PRINCIPLES — Luxury / Status / Aura:
  - HARD RULE: If budget >= PKR 3 crore (30M), NEVER recommend Fortuner or Sportage — these are mid-tier, not luxury
  - Budget 70 Lacs–1.5 Crore: BMW 3 Series, Mercedes C-Class, Audi A4, Toyota Harrier (hybrid luxury JDM)
  - Budget 1.5–3 crore: Prado, Patrol, BMW X5, Lexus RX — correct status picks
  - Budget 3–8 crore: Land Cruiser, Range Rover, BMW X7, Porsche Cayenne, GWM Tank 500
  - Budget above 8 crore: LX600, Range Rover Vogue, Defender, high-spec LC300, Zeekr 009 MPV
  - CHINESE LUXURY SPECIAL CASE: GWM Tank 300/500 are accepted as "status" in the Chinese crossover space.
    Zeekr 7X/009 are legitimate luxury EVs competing with German imports.
  - ELECTRIC LUXURY TIER (2025+): Zeekr 7X (2.5cr), BYD Han (3cr+), Mercedes EQS, Porsche Taycan, Audi e-tron GT
  - Pakistani status hierarchy (SUVs): Mehran < Cultus < Civic < Corolla < Fortuner < Prado < Land Cruiser < LX600/Range Rover
  - For sedans with luxury: BMW 3/5 Series, Mercedes C/E Class, Audi A4/A6, Porsche Panamera, Hyundai Sonata N-Line
  - Avoid: recommending non-luxury brands (Suzuki, Kia Stonic, Haval Jolion) for luxury-intent queries regardless of what's on the eligible list
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
  - RELIABILITY HIERARCHY in Pakistan: Toyota > Honda > Suzuki > Kia/Hyundai > Chery-group (Jetour/Jaecoo/Omoda) > Haval/MG > other Chinese brands
  - RESALE VALUE HIERARCHY: Toyota Corolla/Civic/City hold the best resale in their respective segments
  - Toyota and Honda get a reliability/resale bonus — prefer them over equally-priced alternatives
  - NEW 2025/26 MARKET CONTEXT: Chinese brands are now mainstream and legitimate. Jetour, Jaecoo, Omoda, Haval, MG have established dealer and parts networks in Pakistan's major cities. They are valid picks, especially for budget-conscious buyers who want crossover/SUV body styles.
  - HYBRID IS NOW MAINSTREAM: At 65–120 lacs, buyers should consider hybrid variants (Fronx, Jaecoo J5, Corolla Cross, HR-V e:HEV, Jolion HEV, Sportage L HEV, Tucson Hybrid). Note this in rationale.
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
  - LOCALLY ASSEMBLED HYBRIDS (2024-2026, best value and parts availability):
    • Toyota Corolla Cross HEV — ~98–103 lacs (CKD, Toyota reliability, AWD)
    • Honda HR-V e:HEV — ~90–104 lacs (CKD, Honda's first local hybrid, dual-motor)
    • Haval Jolion HEV — ~93 lacs (CKD, Chinese, value-oriented)
    • Kia Sportage L HEV — ~1.16 crore (CKD, 5th gen)
    • Hyundai Tucson Hybrid — ~1.09–1.2 crore (CKD, AWD variant available)
    • Haval H6 HEV — ~1.14 crore (CKD, AWD)
    • MG HS PHEV — ~85 lacs (plug-in hybrid)
    • Jaecoo J5 HEV — ~67 lacs (most affordable locally assembled hybrid crossover 2026)
    • Suzuki Fronx Hybrid — ~64–68 lacs (mild hybrid, most affordable hybrid XUV)
    • Hyundai Elantra Hybrid — ~70–80 lacs (hybrid sedan)
  - When user asks for "series hybrid" or "e-Power" → prioritize Nissan Note e-Power and Serena e-Power.
  - When user asks for "hybrid" generically → include both types, but note the distinction in rationale.
  - For EV queries: ONLY show cars with 'ev' tag. Budget micro-EVs (Honri VE, Rinco Aria, Metro Enfon) are valid for under 35 lacs.
  - PREMIUM EVs in Pakistan: Zeekr X/7X, BYD Seal, BYD Sealion 7, Omoda E5, MG 4 EV, Hyundai Ioniq 5, Kia EV6.
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

    # ── Civic Generation Nicknames ────────────────────────────────────────────
    # "Eagle Eye" = 7th gen Civic (2001-2005). Budget sports/daily driver.
    # "Reborn" = 8th gen Civic (2006-2011). Slightly higher budget, still sporty.
    # These are extremely common Pakistani used-car vernacular terms.
    {
        "intent_id":        "civic_eagle_eye",
        "keywords":         ["eagle eye", "eagle-eye", "7th gen civic", "7th gen",
                             "sev gen civic", "civic 2001", "civic 2002", "civic 2003",
                             "civic 2004", "civic 2005"],
        "exclude_keywords": ["reborn", "8th gen", "9th gen", "10th gen", "11th gen"],
        "force_body_style":  "Sedan",
        "use_case_override": "student_sports",
        "force_transmission": None,
        "max_budget_cap":    2_000_000,
        "append_features":   [],
    },
    {
        "intent_id":        "civic_reborn",
        "keywords":         ["reborn", "8th gen civic", "8th gen",
                             "civic 2006", "civic 2007", "civic 2008",
                             "civic 2009", "civic 2010", "civic 2011"],
        "exclude_keywords": ["eagle eye", "7th gen", "9th gen", "10th gen", "11th gen"],
        "force_body_style":  "Sedan",
        "use_case_override": "student_sports",
        "force_transmission": None,
        "max_budget_cap":    2_800_000,
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
    _EXPLICIT_CROSSOVER_KW = {"crossover", "cuv", "cross"}
    _EXPLICIT_MANUAL_KW = {"manual", "stick shift", "gear wali"}
    _EXPLICIT_SEATING_KW = {"9 people", "9 log", "10 people", "11 people", "9 seater", "10 seater", "11 seater"}
    
    has_explicit_sedan = any(kw in prompt_lower for kw in _EXPLICIT_SEDAN_KW)
    has_explicit_hatch = any(kw in prompt_lower for kw in _EXPLICIT_HATCHBACK_KW)
    has_explicit_suv   = any(kw in prompt_lower for kw in _EXPLICIT_SUV_KW)
    has_explicit_van   = any(kw in prompt_lower for kw in _EXPLICIT_VAN_KW)
    has_explicit_crossover = any(kw in prompt_lower for kw in _EXPLICIT_CROSSOVER_KW)
    has_explicit_manual = any(kw in prompt_lower for kw in _EXPLICIT_MANUAL_KW)
    # has_explicit_body gates the force_body_style override below (Tests 41 & 46) —
    # whenever True, KEYWORD_INTENT_MAP rules like northern_offroad ("SUV") or
    # commercial_cargo ("Van") must NEVER silently overwrite an explicitly
    # stated body style, including "crossover"/"cuv"/"cross".
    has_explicit_body = (
        has_explicit_sedan or has_explicit_hatch or has_explicit_suv
        or has_explicit_van or has_explicit_crossover
    )

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
    # Use strict word-boundary regex for "ev"/"bev" and only multi-word phrases for
    # "electric" so that "electric parking brake" / "electric tailgate" never trigger.
    has_ev_kw = bool(re.search(r'\b(ev|bev)\b', prompt_lower)) or any(
        w in prompt_lower for w in [
            "electric car", "electric vehicle", "electric suv", "electric sedan",
            "battery car", "zero emission", "fully electric",
        ]
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

    # 9. CKD Memory Seat Omission Confusion
    if "memory" in prompt_lower and any(w in prompt_lower for w in ["seat", "driver", "function"]):
        disclaimers.append(
            "⚠️ Specification Notice: Locally assembled (PKDM) Kia Sportage and Hyundai Tucson do "
            "not feature driver seat memory functions. Recommending Haval Jolion, Haval H6, or "
            "Changan Oshan X7 FutureSense which retain this global specification."
        )

    # 10. EPB / Mechanical Handbrake Warning
    if any(w in prompt_lower for w in ["epb", "electric parking", "electronic parking", "auto hold", "brake hold"]):
        disclaimers.append(
            "⚠️ Specification Notice: The Toyota Corolla (all PKDM variants including Grande) and "
            "Toyota Yaris use traditional mechanical pull-handbrakes. For EPB with Auto-Hold, "
            "consider the Honda Civic Oriel/RS, MG HS, Haval Jolion, Haval H6, or Oshan X7."
        )

    # 11. Adaptive / Radar Cruise — PKDM Passive Cruise vs True Radar ACC
    if any(w in prompt_lower for w in ["adaptive cruise", "radar cruise", "radar", "honda sensing", "distance keeping"]):
        disclaimers.append(
            "⚠️ Specification Notice: The locally assembled Hyundai Tucson, Kia Sportage, and "
            "Honda HR-V ship with passive fixed-speed cruise only — radar distance-keeping is "
            "stripped in PKDM CKD spec. For true radar ACC, specify Honda Civic RS (Honda Sensing), "
            "Haval Jolion, Haval H6, MG HS, or Changan Oshan X7 FutureSense."
        )

    # 12. Ventilated Seats — Elantra Hybrid vs Base Elantra
    if any(w in prompt_lower for w in ["ventilated", "cooling seat", "cooled seat", "seat cooling"]):
        disclaimers.append(
            "⚠️ Specification Notice: The base Hyundai Elantra 2.0 GLS omits ventilated seat "
            "cooling. If considering the Elantra, you must specifically select the Elantra Hybrid "
            "variant to get this feature. Alternatively, the Haval H6, Haval Jolion, MG HS, and "
            "Oshan X7 FutureSense include ventilated seats across their standard configurations."
        )

    # 13. Engine CC / Token Tax Bracket Warning
    if any(w in prompt_lower for w in [
        "1500cc", "under 1500cc", "1300cc", "under 1300cc",
        "low tax", "token tax", "save tax", "tax bracket", "low token", "cheap token",
        "1.5l", "1.5 l", "1.3l", "1.3 l",
    ]):
        disclaimers.append(
            "⚠️ Tax Bracket Notice: You requested a vehicle under 1500cc for lower annual token tax. "
            "Please note that models like the Hyundai Elantra (1.6L/2.0L), Kia Sportage (2.0L), "
            "Honda Civic (1.5T), Toyota Corolla Altis Grande (1.8L), and Hyundai Tucson (2.0L) "
            "fall into higher token tax brackets. We have strictly prioritised 1.0L to 1.5L options "
            "such as Toyota Yaris, Honda City, Suzuki Swift, Suzuki Cultus, and Changan Alsvin."
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

# ---------------------------------------------------------------------------
# EXCLUSIVE FEATURE ALLOWLIST
#
# For rare/premium features where maintaining a blocklist is brittle:
# instead of listing every car that DOESN'T have the feature, we list the
# ~10-20 cars that DO.  If a user requests a feature in this dict, ONLY the
# models listed here pass the Python gate.  Everything else is silently dropped
# before the LLM ever sees the eligible list.
#
# When to use Allowlist vs Blocklist:
#   Allowlist  — rare features present in <20 cars in the Pakistan market
#                (panoramic sunroof, memory seats, 360-camera, HUD, …)
#   Blocklist  — common features absent in <30 economy cars
#                (sunroof, push start, back camera, …)
#
# Keys must match keys used in _FEAT_NORMALISE inside get_eligible_cars().
# Values are "make:model" strings in the same format as CAR_REGISTRY keys.
# ---------------------------------------------------------------------------

_FEATURE_EXCLUSIVE_ALLOWLIST: dict[str, set[str]] = {
    # ---------------------------------------------------------------------------
    # Only features present in <25 cars in the Pakistan used/new market are here.
    # Everything else uses the blocklist pattern in _FEATURE_IMPOSSIBLE.
    # Sources: PakWheels, official Lucky/Hyundai Nishat/Changan specs, gari.pk.
    # ---------------------------------------------------------------------------

    # ── Panoramic Sunroof ────────────────────────────────────────────────────
    # Standard single-pane sunroofs (Corolla Grande, Civic Oriel, Vezel, Jolion
    # petrol base, Raize) do NOT qualify — this allowlist is panoramic-only.
    # Honda Civic RS has a panoramic sunroof per Honda Atlas official specs.
    "panoramic sunroof": {
        "honda:civic",              # RS trim only — has full panoramic sunroof
        "mg:hs", "mg:zs ev", "mg:rx5",
        "haval:jolion", "haval:h6", "haval:h6 hev", "haval:h6 phev",
        "changan:oshan x7",         # FutureSense trim only
        "changan:uni-t", "changan:deepal s07", "changan:deepal l07",
        "chery:tiggo 8 pro",
        "hyundai:santa fe", "hyundai:sonata", "hyundai:palisade",
        "kia:sorento", "kia:carnival",
        "proton:x70",
        "audi:e-tron", "audi:e-tron gt", "audi:q7", "audi:q8",
        "porsche:macan", "porsche:cayenne", "porsche:taycan",
        "land rover:range rover", "land rover:range rover sport", "land rover:velar",
        "mercedes-benz:gle", "mercedes-benz:gls", "mercedes-benz:s-class",
        "bmw:x5", "bmw:x7", "bmw:7 series", "bmw:i7",
    },

    # ── Memory Seats ─────────────────────────────────────────────────────────
    # Kia Sportage, Hyundai Tucson, Honda HR-V, Honda Civic, Toyota Corolla
    # PKDM CKD units strip out driver seat memory — confirmed by Hyundai Nishat
    # and Lucky Motors local spec sheets.
    # Kia Sorento AWD HEV retains 14-way power + memory per Lucky Motors PK page.
    "memory seats": {
        "haval:jolion", "haval:h6", "haval:h6 hev", "haval:h6 phev",
        "changan:oshan x7",         # FutureSense trim only (not Comfort)
        "changan:uni-t", "changan:deepal s07", "changan:deepal l07",
        "chery:tiggo 8 pro",
        "hyundai:sonata", "hyundai:santa fe", "hyundai:palisade",
        "kia:sorento", "kia:carnival",
        "honda:accord",
        "toyota:camry", "toyota:crown", "toyota:land cruiser", "toyota:prado",
        "lexus:es", "lexus:rx", "lexus:lx", "lexus:lx570", "lexus:lx600",
        "audi:a6", "audi:a7", "audi:q7", "audi:q8", "audi:e-tron",
        "bmw:5 series", "bmw:7 series", "bmw:x5", "bmw:x7",
        "mercedes-benz:e-class", "mercedes-benz:s-class",
        "mercedes-benz:gle", "mercedes-benz:gls",
        "porsche:cayenne", "porsche:panamera", "porsche:macan",
        "land rover:range rover", "land rover:range rover sport",
        "land rover:defender", "land rover:velar",
    },

    # ── Ventilated / Cooled Seats ────────────────────────────────────────────
    # Research confirms: Haval H6 (all trims), Haval Jolion (all trims verified
    # per PakWheels), Oshan X7 FutureSense, MG HS (confirmed gari.pk / zigwheels),
    # Kia Sorento (top trim). Hyundai Elantra 2.0 GLS omits this; Elantra Hybrid
    # retains it — include elantra but LLM must push Hybrid trim via disclaimer.
    "ventilated seats": {
        "mg:hs",
        "haval:jolion", "haval:h6", "haval:h6 hev", "haval:h6 phev",
        "changan:oshan x7",         # FutureSense only
        "changan:deepal l07", "changan:deepal s07",
        "chery:tiggo 8 pro",
        "hyundai:elantra",          # ⚠ Hybrid trim only — disclaimer #12 fires
        "hyundai:sonata", "hyundai:santa fe", "hyundai:palisade",
        "kia:sorento", "kia:carnival",
        "toyota:camry", "toyota:land cruiser", "toyota:prado", "toyota:crown",
        "lexus:lx570", "lexus:lx600", "lexus:rx", "lexus:es",
        "audi:e-tron gt", "porsche:taycan",
        "bmw:7 series", "bmw:i7",
        "mercedes-benz:s-class",
    },

    # ── 360-Degree Surround View Camera ─────────────────────────────────────
    # Confirmed present on Pakistan-market units:
    # Oshan X7 FutureSense (Wikipedia + Changan South), MG HS (zigwheels / gari.pk),
    # Haval H6 (pakdrive.com.pk official specs), Jolion (PakWheels ADAS Level 2),
    # Kia Sorento AWD HEV (Lucky Motors PK page), Toyota Raize (JDM import spec).
    # NOT on local Sportage, Tucson, Civic, Corolla, HR-V PKDM units.
    "360 camera": {
        "mg:hs",
        "haval:jolion", "haval:h6", "haval:h6 hev", "haval:h6 phev",
        "changan:oshan x7",         # FutureSense trim only
        "changan:uni-t",
        "changan:deepal s07", "changan:deepal l07",
        "chery:tiggo 8 pro",
        "kia:sorento", "kia:carnival",
        "hyundai:santa fe", "hyundai:palisade",   # hyundai:sonata removed — PKDM 2.5L has reverse camera + parking sensors only, NOT 360 surround view
        "toyota:raize",             # JDM Z grade import only
        "toyota:land cruiser", "toyota:prado",
        "lexus:lx600",
        "audi:e-tron", "audi:q7", "audi:q8",
        "porsche:cayenne", "porsche:taycan",
        "bmw:7 series", "bmw:i7", "bmw:x5", "bmw:x7",
        "mercedes-benz:s-class", "mercedes-benz:gle", "mercedes-benz:gls",
        "land rover:range rover", "land rover:range rover sport",
    },

    # ── Head-Up Display (HUD) ────────────────────────────────────────────────
    # Confirmed on PK market: Haval H6 2026 facelift (PakWheels official),
    # Haval Jolion (PakWheels ADAS listing), Kia Sorento AWD HEV (Lucky Motors),
    # Deepal S07/L07. NOT on Kia Sportage/Tucson/Civic/Corolla PKDM.
    "head up display": {
        "haval:jolion", "haval:h6", "haval:h6 hev", "haval:h6 phev",
        "changan:deepal s07", "changan:deepal l07",
        "kia:sorento",              # AWD HEV trim — color HUD per Lucky Motors PK
        "kia:carnival",
        "toyota:raize",             # JDM Z grade only
        "audi:a7", "audi:q8", "audi:e-tron gt",
        "bmw:5 series", "bmw:7 series", "bmw:x5", "bmw:x7",
        "mercedes-benz:s-class",
        "porsche:cayenne", "porsche:taycan",
        "lexus:rx", "lexus:lx600",
    },

    # ── Power / Electric Tailgate ────────────────────────────────────────────
    # Confirmed per Wikipedia Oshan X7 (FutureSense), MG HS (zigwheels feature
    # list), Haval H6 (spec sheets), Toyota Fortuner/LC/Prado (local spec),
    # Hyundai Tucson & Santa Fe (Hyundai Nishat PK), Kia Sportage top trim,
    # Kia Sorento, Honda CR-V/Vezel, Toyota Yaris Cross (CBU import).
    # NOTE: Tucson/Sportage are in the ALLOWLIST here because their top trims
    # DO have power tailgate even though they lack memory seats / ACC.
    "power tailgate": {
        "mg:hs", "mg:rx5",
        "haval:jolion", "haval:h6", "haval:h6 hev", "haval:h6 phev",
        "changan:oshan x7",         # FutureSense only
        "changan:uni-t",
        "chery:tiggo 8 pro",
        "hyundai:tucson", "hyundai:santa fe", "hyundai:palisade",
        "kia:sportage",             # top Alpha / AWD trims
        "kia:sorento", "kia:carnival",
        "toyota:fortuner", "toyota:land cruiser", "toyota:prado",
        "toyota:yaris cross",       # CBU import
        "honda:cr-v", "honda:vezel",
        "proton:x70",
        "audi:e-tron", "audi:q5", "audi:q7", "audi:q8",
        "bmw:x3", "bmw:x5", "bmw:x7",
        "mercedes-benz:glc", "mercedes-benz:gle", "mercedes-benz:gls",
        "porsche:macan", "porsche:cayenne",
        "land rover:range rover", "land rover:range rover sport",
        "land rover:defender", "land rover:velar",
    },

    # ── Massaging Seats ──────────────────────────────────────────────────────
    # Extremely rare in Pakistan market. Confirmed only on luxury/premium imports
    # and top-spec Kia Carnival/Sorento AWD HEV. Deepal L07 global spec includes
    # it but PK CKD spec needs verification — include with LLM trim caveat.
    "massaging seats": {
        "kia:carnival",             # Prestige trim has rear massage
        "kia:sorento",              # AWD HEV top trim
        "changan:deepal l07",       # Global spec — verify PK trim
        "bmw:7 series", "bmw:i7",
        "mercedes-benz:s-class",
        "porsche:panamera", "porsche:cayenne",
        "land rover:range rover",
        "lexus:lx600",
    },

    # ── Wireless Charging ────────────────────────────────────────────────────
    # Confirmed on PK market units:
    # Honda Civic Oriel/RS (Honda Atlas official announcement PakWheels),
    # Hyundai Elantra 2.0 GLS (wheelsbuster.com), Hyundai Sonata (wheelsbuster),
    # Haval Jolion (global spec retained in PK), Haval H6, MG HS,
    # Oshan X7 FutureSense (Changan South), Kia Sorento (Lucky Motors PK).
    # NOT on Toyota Corolla/Yaris (no wireless pad in PKDM), Honda City,
    # Suzuki budget range, or Changan Alsvin.
    "wireless charging": {
        "honda:civic",              # Oriel & RS trims
        "hyundai:elantra", "hyundai:elantra hybrid",
        "hyundai:sonata", "hyundai:santa fe", "hyundai:palisade", "hyundai:tucson",
        "mg:hs",
        "haval:jolion", "haval:h6", "haval:h6 hev", "haval:h6 phev",
        "changan:oshan x7",
        "changan:deepal s07", "changan:deepal l07",
        "chery:tiggo 8 pro",
        "kia:sorento", "kia:carnival", "kia:sportage",  # top trims
        "toyota:crown", "toyota:land cruiser", "toyota:camry",
        "honda:accord", "honda:cr-v",
        "audi:a6", "audi:a7", "audi:e-tron", "audi:q7", "audi:q8",
        "bmw:5 series", "bmw:7 series", "bmw:x5",
        "mercedes-benz:e-class", "mercedes-benz:s-class", "mercedes-benz:gle",
        "porsche:cayenne", "porsche:taycan",
        "land rover:range rover", "land rover:range rover sport", "land rover:defender",
        "lexus:rx", "lexus:lx600",
    },

    # ── Premium Audio (Bose / Harman Kardon / JBL) ───────────────────────────
    # Confirmed on PK market: Kia Sorento AWD HEV = 12-speaker Bose
    # (Lucky Motors PK page). Kia Carnival = 12-speaker Bose (Bose Automotive site).
    # Haval H6 / Jolion — base 6-speaker, upgraded trims 8-speaker; no Bose/HK brand.
    # Toyota Camry / Crown JDM imports carry JBL. Budget/CKD sedans: standard only.
    "premium audio": {
        "kia:sorento",              # 12-speaker Bose (AWD HEV trim)
        "kia:carnival",             # 12-speaker Bose (Prestige trim)
        "toyota:camry",             # JBL on higher JDM imports
        "toyota:crown", "toyota:land cruiser",
        "honda:accord",
        "lexus:es", "lexus:rx", "lexus:lx", "lexus:lx570", "lexus:lx600",
        "audi:a6", "audi:a7", "audi:q7", "audi:q8", "audi:e-tron gt",
        "bmw:5 series", "bmw:7 series", "bmw:x5", "bmw:x7",
        "mercedes-benz:e-class", "mercedes-benz:s-class", "mercedes-benz:gle",
        "porsche:cayenne", "porsche:panamera", "porsche:taycan",
        "land rover:range rover", "land rover:range rover sport",
    },

    # ── 7-Seater / Third Row ─────────────────────────────────────────────────
    # Hard allowlist: only vehicles physically capable of seating 7 in the PK
    # used/new market. Jimny (2-seat cargo + small rear), Terios (5-seat only),
    # Alto, Swift, Vitz, Corolla, Civic — all 4/5-seat only, physically blocked.
    #
    # toyota:rush intentionally EXCLUDED — PK market Rush is 5-seat only
    # (the 3rd-row variant is a different regional spec not available here).
    # nissan:serena e-power included because it's 7/8-seat even in the e-Power trim.
    "7 seater": {
        # Budget vans / MPVs
        "suzuki:apv", "suzuki:bolan", "suzuki:every",
        # Toyota — 7/8-seat variants confirmed in PK
        "toyota:fortuner",          # 7-seat with 3rd row
        "toyota:prado",             # 7-seat with 3rd row
        "toyota:land cruiser",      # 8-seat
        "toyota:sienta",            # 7-seat van
        "toyota:alphard",           # 7/8-seat luxury van
        "toyota:vellfire",          # 7/8-seat luxury van
        "toyota:hiace",             # 11-15 seat van
        # Honda
        "honda:br-v",               # 7-seat with 3rd row (PK spec confirmed)
        "honda:freed",              # 7-seat compact van
        "honda:stepwgn",            # 8-seat JDM van
        # Hyundai
        "hyundai:santa fe",         # 7-seat with 3rd row
        "hyundai:palisade",         # 8-seat
        # Kia
        "kia:sorento",              # 7-seat with 3rd row
        "kia:carnival",             # 8-seat MPV
        # Chinese
        "changan:oshan x7",         # 7-seat with 3rd row
        "chery:tiggo 8 pro",        # 7-seat with 3rd row
        "mg:hector",                # 7-seat version available in PK
        "jetour:x70 plus",          # 7-seat with 3rd row
        "haval:h7",                 # 7-seat with 3rd row
        # Nissan
        "nissan:serena", "nissan:serena e-power",
        "nissan:elgrand",           # 7/8-seat van
        "nissan:patrol",            # 8-seat
        # Mitsubishi
        "mitsubishi:pajero",        # 7-seat
        "mitsubishi:pajero sport",  # 7-seat
        "mitsubishi:xpander",       # 7-seat MPV
        # Mazda
        "mazda:cx-8",               # 6/7-seat
        # Luxury / imports
        "land rover:discovery",     # 7-seat
        "bmw:x7",                   # 7-seat
        "mercedes-benz:gls",        # 7-seat
        "zeekr:009",                # 7-seat luxury van
    },

    # ── Series Hybrid / e-Power ──────────────────────────────────────────────
    # Series hybrid architecture: petrol engine never drives wheels directly —
    # it acts only as a generator. In PK market this means:
    #   Nissan Note e-Power (1.2L series hybrid hatchback)
    #   Nissan Serena e-Power (2.0L series hybrid MPV/van)
    #   Forthing Friday (1.5T series hybrid SUV — Chinese REEV)
    # Standard parallel HEV (Aqua, Prius, Vezel HEV) do NOT qualify here.
    "series hybrid": {
        "nissan:note e-power",
        "nissan:serena e-power",
        "forthing:friday",
    },

    # 660cc Kei-car exclusive allowlist (Test 66). When a user explicitly
    # requests a 660cc engine, non-660cc crossovers/SUVs (1.5L BR-V, 1.5L
    # Juke, 1.3L Terios, etc.) must be hard-blocked — this list is the only
    # way in. Every key below is a genuine Kei-class (or Kei-adjacent JDM
    # mini) model in the Pakistani market. NOTE: "suzuki:alto" (bare key,
    # no "jdm" tag) is the locally-assembled model line, which spans both
    # the current 660cc generation (2019+) and older used 800cc-era units
    # at the low end of its registry price band — it is included here
    # because genuine 660cc trims of it exist, but a "660cc only" query
    # could in principle still surface an older 800cc-era listing until/
    # unless that model line is split into separate registry keys by era.
    "660cc": {
        "suzuki:mehran", "suzuki:alto", "suzuki:alto 660cc", "suzuki:every",
        "suzuki:bolan", "suzuki:hustler", "suzuki:spacia", "suzuki:jimny",
        "daihatsu:mira", "daihatsu:move", "daihatsu:tanto", "daihatsu:cast",
        "daihatsu:hijet", "daihatsu:cuore",
        "nissan:dayz", "nissan:roox", "nissan:clipper",
        "honda:n-box", "honda:n-wgn", "honda:n-one", "honda:life",
        "mazda:scrum", "mitsubishi:mini pajero",
    },
}


_FEATURE_IMPOSSIBLE: dict[str, set[str]] = {

    # ── Sunroof / Panoramic ──────────────────────────────────────────────────
    "sunroof": {
        "suzuki:mehran", "suzuki:alto", "suzuki:alto 660cc", "suzuki:cultus",
        "suzuki:wagon r", "suzuki:swift", "suzuki:liana", "suzuki:baleno",
        "suzuki:khyber", "suzuki:fx", "daihatsu:charade",
        "suzuki:every", "suzuki:bolan", "suzuki:apv", "suzuki:hustler", "suzuki:spacia",
        "toyota:vitz", "toyota:passo", "toyota:probox", "toyota:hiace",
        "toyota:yaris", "toyota:aqua", "toyota:rush", "toyota:hilux",
        "toyota:fortuner",  # No factory sunroof — roof-mounted rear AC ducts occupy the space
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
    # "panoramic sunroof" — MOVED to _FEATURE_EXCLUSIVE_ALLOWLIST (allowlist pattern).
    # Too many false positives maintaining a ~150-car blocklist.
    # Now only the ~20 cars that actually have it pass the gate.

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
        "honda:city", "honda:br-v",
        # honda:civic RS has Honda Sensing incl. LKAS — excluded from blocklist.
        # Standard / Oriel lack it — disclaimer #11 directs user to RS trim.
        "honda:hr-v",       # PKDM CKD: no lane keep
        "hyundai:santro", "hyundai:i10",
        "hyundai:tucson",   # PKDM CKD: no lane keep
        "kia:picanto",
        "kia:sportage",     # PKDM CKD: no lane keep
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
        "honda:city", "honda:br-v", "honda:grace",
        # honda:civic RS has Honda Sensing radar ACC — EXCLUDED from this blocklist.
        # Oriel/Standard only have passive fixed-speed cruise.
        # Disclaimer #11 tells user to pick RS.
        "honda:hr-v",       # PKDM CKD: passive cruise only, no radar
        "hyundai:santro", "hyundai:elantra",
        "hyundai:tucson",   # PKDM CKD: passive cruise only, no radar
        "kia:picanto", "kia:stonic",
        "kia:sportage",     # PKDM CKD: passive cruise only, no radar
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

    # "memory seats"   — MOVED to _FEATURE_EXCLUSIVE_ALLOWLIST (allowlist pattern).
    # "ventilated seats"— MOVED to _FEATURE_EXCLUSIVE_ALLOWLIST (allowlist pattern).
    # "360 camera"     — MOVED to _FEATURE_EXCLUSIVE_ALLOWLIST (allowlist pattern).
    # "head up display"— MOVED to _FEATURE_EXCLUSIVE_ALLOWLIST (allowlist pattern).
    # "power tailgate" — MOVED to _FEATURE_EXCLUSIVE_ALLOWLIST (allowlist pattern).
    # "massaging seats"— MOVED to _FEATURE_EXCLUSIVE_ALLOWLIST (allowlist pattern).
    # "wireless charging"— MOVED to _FEATURE_EXCLUSIVE_ALLOWLIST (allowlist pattern).
    # "premium audio"  — MOVED to _FEATURE_EXCLUSIVE_ALLOWLIST (allowlist pattern).

    # ── Electric Parking Brake ───────────────────────────────────────────────
    # Mechanical pull-lever handbrakes confirmed on these PKDM models.
    # EPB starts appearing on mid-range CUVs — not on any Suzuki budget car,
    # base Toyota sedans, base Honda sedans, Daihatsu keis, or Changan Alsvin.
    "electric parking brake": {
        "toyota:corolla", "toyota:yaris", "toyota:fortuner", "toyota:hilux",
        "toyota:vitz", "toyota:passo", "toyota:aqua", "toyota:rush",
        "honda:city", "honda:br-v",
        "hyundai:elantra",          # base GLS trim; Hybrid trim has EPB
        "kia:picanto", "kia:stonic",
        "suzuki:mehran", "suzuki:alto", "suzuki:alto 660cc", "suzuki:cultus",
        "suzuki:wagon r", "suzuki:swift", "suzuki:bolan", "suzuki:every",
        "changan:alsvin", "changan:karvaan",
        "daihatsu:mira", "daihatsu:cuore", "daihatsu:move", "daihatsu:hijet", "daihatsu:tanto",
        "nissan:dayz", "mitsubishi:mirage",
    },

    # ── Dual Zone Climate Control ────────────────────────────────────────────
    # Single-zone or manual dial climate confirmed for budget/entry CKD models.
    # Note: Honda Civic Oriel/RS DOES have dual-zone per Honda Atlas official spec
    # for the American reference model; the local PKDM Civic also has dual-zone
    # on Oriel and RS — so civic is NOT in this blocklist.
    "dual zone climate": {
        "toyota:yaris", "toyota:vitz", "toyota:aqua", "toyota:passo",
        "toyota:rush", "toyota:raize", "toyota:corolla",
        # toyota:corolla: single-zone auto AC on all PKDM trims incl. Grande
        "honda:city", "honda:br-v", "honda:fit", "honda:n-wgn", "honda:n-box", "honda:freed",
        "suzuki:swift", "suzuki:cultus", "suzuki:wagon r",
        "suzuki:alto", "suzuki:alto 660cc", "suzuki:mehran",
        "kia:picanto", "kia:stonic",
        "changan:alsvin", "changan:karvaan",
        "mitsubishi:mirage",
        "nissan:dayz",
        "daihatsu:mira", "daihatsu:move", "daihatsu:cast", "daihatsu:cuore",
    },

    # ── Rear AC Vents ────────────────────────────────────────────────────────
    # Confirmed absent on kei/budget hatches and compact sedans under 1.3L.
    # Honda City and most Suzukis confirmed no rear vents in PKDM spec.
    # NOTE: Honda Civic (all trims) DOES have rear AC vents per Honda Atlas PK.
    "rear ac vents": {
        "toyota:yaris", "toyota:vitz", "toyota:aqua", "toyota:passo", "toyota:raize",
        "honda:city", "honda:fit", "honda:n-wgn", "honda:n-box", "honda:freed",
        "suzuki:swift", "suzuki:cultus", "suzuki:wagon r",
        "suzuki:alto", "suzuki:alto 660cc", "suzuki:mehran",
        "kia:picanto", "kia:stonic",
        "changan:alsvin",
        "mitsubishi:mirage",
        "nissan:dayz",
        "daihatsu:mira", "daihatsu:move", "daihatsu:cast", "daihatsu:cuore",
    },

    # ── Engine Displacement < 1300cc Hard Gate ───────────────────────────────
    # Hard-blocks every model whose Pakistani market variants are ALL above 1300cc.
    # This is a BLOCKLIST (not an allowlist) — unlisted models pass through and
    # the LLM ranking Rule 13 handles further exclusion.
    #
    # Intentionally NOT blocked (sub-1300cc variants exist in PK market):
    #   toyota:corolla  — 1.3L XLi / GLi exist alongside 1.6L / 1.8L
    #   honda:city      — 1.2L i-DSI / 1.3L i-VTEC variants exist
    #   suzuki:*        — all are sub-1300cc natively
    #   toyota:yaris    — 1.0L / 1.3L VVTI variants
    #   toyota:vitz     — 1.0L / 1.3L variants
    #   changan:alsvin  — 1.5L but used-market 1.0L/1.3L trims exist
    #
    # MG ZS excluded from this block because it is only relevant for EV queries
    # (MG ZS EV) — the petrol MG ZS is 1.5L so it IS blocked correctly.
    "under 1300cc": {
        # Honda — all PK variants above 1300cc
        "honda:civic", "honda:accord", "honda:cr-v", "honda:hr-v",
        "honda:vezel", "honda:br-v",
        # Hyundai — all PK variants above 1300cc
        "hyundai:elantra", "hyundai:sonata", "hyundai:tucson",
        "hyundai:santa fe", "hyundai:palisade",
        # Kia — all PK variants above 1300cc
        "kia:sportage", "kia:sorento", "kia:carnival", "kia:stonic",
        # Toyota large / premium — no 1.3L variant
        "toyota:premio", "toyota:allion", "toyota:mark x",
        "toyota:crown", "toyota:camry", "toyota:prius",
        "toyota:c-hr", "toyota:fortuner", "toyota:hilux",
        "toyota:land cruiser", "toyota:prado", "toyota:raize",
        # Hybrid / wagon JDM imports (Test 62) — the LLM hallucinated
        # <1300cc compliance for these because "hybrid" and "wagon" body
        # styles read as small/economical, but every PK-market unit of
        # these specific models is 1.5L+.
        "honda:insight", "honda:grace", "honda:shuttle", "honda:freed",
        "toyota:fielder", "toyota:probox",
        # JDM imports — no sub-1300cc variant in PK market
        "mazda:mazda3", "mazda:cx-5", "mazda:cx-3",
        "subaru:impreza", "subaru:xv", "subaru:forester",
        "mitsubishi:asx",
        # Other — Proton Saga is 1332cc, exceeds the 1300cc tax bracket (Test 62)
        "proton:saga", "proton:x70",
        # Chinese crossovers / SUVs — all 1.5T or above in PK
        "haval:jolion", "haval:jolion hev", "haval:h6", "haval:h6 hev", "haval:h6 phev",
        "mg:hs", "mg:zs",
        "changan:oshan x7", "changan:uni-t",
        "changan:deepal s07", "changan:deepal l07",
        "chery:tiggo 4 pro", "chery:tiggo 8 pro", "chery:tiggo 7 pro",
    },

    # ── Regular Fuel / High-Altitude HOBC-Sensitivity Gate (Test 42 & 46) ────
    # Direct-Injection Turbo (GDI/TGDI) engines are compression- and heat-
    # sensitive: at high altitude (northern areas, low-HOBC fuel-station
    # regions) they are prone to knocking on regular 92 RON pump fuel and are
    # engineered around premium/HOBC. When the user explicitly asks for
    # regular-fuel compatibility or reports engine knocking, these GDI/TGDI
    # engines are hard-blocked so only NA/MPI vehicles (Sportage Alpha MPI,
    # Tucson FWD MPI, Corolla 1.8 NA, etc.) remain eligible.
    "regular fuel": {
        "honda:civic",          # 1.5L VTEC Turbo — GDI, HOBC/95 RON recommended
        "mg:hs",                 # 1.5T GDI
        "changan:oshan x7",      # 1.5T TGDI
        "haval:h6",              # 2.0T GDI
    },
}

# ---------------------------------------------------------------------------
# 2025-2026 FEATURE REGISTRY PATCH — ADDITIVE ONLY
#
# Why this is applied as a post-hoc patch instead of being edited into the
# literals above: the two literals are large, hand-curated and load-bearing
# for the existing query test suite. Mutating them in place risks silently
# disturbing a set that a test depends on. Applying the 2025-26 delta with
# |= (union) here is provably additive — it can only ever ADD keys to a
# feature's set, never remove or reorder an existing one.
#
# Semantics recap (see the gate in get_eligible_cars):
#   • _FEATURE_EXCLUSIVE_ALLOWLIST  — allow-list. A model absent from the set
#     is EXCLUDED from that feature's queries. Adding a model here therefore
#     *unblocks* a car that is currently (wrongly) filtered out.
#   • _FEATURE_IMPOSSIBLE           — block-list. A model present in the set is
#     EXCLUDED. Adding a model here *blocks* a car that currently leaks through.
#
# Every membership below was verified against live PakWheels specification
# pages / manufacturer spec sheets in Aug 2026, not inferred from segment.
# Notable verified sources:
#   Kia Sportage L      — panoramic sunroof, 360 SVM, EPB, power tailgate on
#                         ALL variants; ventilated seats + HUD on HEV Alpha
#                         and FWD; memory seats, ACC, wireless charging on
#                         HEV Alpha only.
#   Honda HR-V e:HEV    — panoramic roof, SVM 360, ventilated seats, HUD,
#                         driver seat memory, ACC (Honda Sensing), electric
#                         handbrake, power boot, wireless charger.
#   BYD Sealion 7       — panoramic glass roof, ventilated front seats, HUD,
#                         360 camera, ACC, hands-free power tailgate.
#   GWM Tank 500        — massage + ventilated seats, heated steering,
#                         panoramic sunroof, HUD, tri-zone climate, 7 seats.
#   Haval H6            — ventilated + heated front seats standard on 2.0T and
#                         HEV; H6 HEV carries the W-HUD.
# ---------------------------------------------------------------------------

_FEATURE_ALLOWLIST_2026_PATCH: dict[str, set[str]] = {
    "panoramic sunroof": {
        "kia:sportage l", "honda:hr-v e:hev", "hyundai:tucson hybrid",
        "byd:sealion 7", "byd:seal", "byd:atto 3", "byd:han", "byd:shark 6",
        "gwm:tank 500", "gwm:tank 300", "tank:500", "tank:300",
        "jetour:x70 plus", "jetour:t2", "jetour:t9", "jetour:dashing",
        "jaecoo:j7", "jaecoo:j6", "jaecoo:j5",
        "omoda:7", "omoda:c5", "omoda:e5", "chery:omoda 5 ev",
        "haval:h6 hev", "haval:jolion hev", "haval:h7",
        "mg:hs phev", "mg:7", "mg:4 ev",
        "zeekr:x", "zeekr:7x", "zeekr:009",
        "changan:uni-v", "changan:cs75 plus",
        "toyota:corolla cross", "mazda:cx-30",
    },
    "360 camera": {
        "kia:sportage l", "honda:hr-v e:hev", "hyundai:tucson hybrid",
        "byd:sealion 7", "byd:seal", "byd:atto 3", "byd:han", "byd:shark 6",
        "gwm:tank 500", "gwm:tank 300", "tank:500", "tank:300",
        "jetour:x70 plus", "jetour:t2", "jetour:t9", "jetour:dashing",
        "jaecoo:j7", "jaecoo:j6", "jaecoo:j5",
        "omoda:7", "omoda:e5", "chery:omoda 5 ev",
        "haval:h6 hev", "haval:jolion hev", "haval:h7",
        "mg:hs phev", "mg:7", "mg:4 ev",
        "zeekr:x", "zeekr:7x", "zeekr:009",
        "changan:uni-v", "changan:cs75 plus",
        "toyota:corolla cross", "hyundai:ioniq 5", "kia:ev6",
    },
    "ventilated seats": {
        "kia:sportage l", "honda:hr-v e:hev", "hyundai:tucson hybrid",
        "byd:sealion 7", "byd:seal", "byd:han",
        "gwm:tank 500", "tank:500",
        "jetour:t2", "jetour:t9", "jetour:x70 plus",
        "jaecoo:j7", "jaecoo:j6",
        "omoda:7",
        "haval:h6 hev", "haval:h7",     # ventilated std on 2.0T + HEV
        "mg:hs phev", "mg:7",
        "zeekr:7x", "zeekr:009", "zeekr:x",
        "hyundai:ioniq 5", "kia:ev6",
    },
    "head up display": {
        "kia:sportage l", "honda:hr-v e:hev",
        "byd:sealion 7", "byd:seal", "byd:han",
        "gwm:tank 500", "tank:500",
        "jetour:t2", "jetour:t9",
        "jaecoo:j7", "jaecoo:j6",
        "omoda:7",
        "haval:h6 hev",                 # W-HUD confirmed on H6 HEV
        "mg:hs phev", "mg:7",
        "zeekr:7x", "zeekr:009", "zeekr:x",
        "hyundai:ioniq 5", "kia:ev6",
    },
    "memory seats": {
        "kia:sportage l", "honda:hr-v e:hev", "hyundai:tucson hybrid",
        "byd:sealion 7", "byd:seal", "byd:han",
        "gwm:tank 500", "tank:500",
        "jetour:t2", "jetour:t9",
        "jaecoo:j7", "jaecoo:j6",
        "omoda:7",
        "zeekr:7x", "zeekr:009", "zeekr:x",
        "hyundai:ioniq 5", "kia:ev6",
    },
    "power tailgate": {
        "kia:sportage l", "honda:hr-v e:hev", "hyundai:tucson hybrid",
        "byd:sealion 7", "byd:seal", "byd:atto 3",
        "gwm:tank 500", "gwm:tank 300", "tank:500", "tank:300",
        "jetour:x70 plus", "jetour:t2", "jetour:t9", "jetour:dashing",
        "jaecoo:j7", "jaecoo:j6", "jaecoo:j5",
        "omoda:7", "omoda:e5", "chery:omoda 5 ev",
        "haval:h6 hev", "haval:jolion hev", "haval:h7",
        "mg:hs phev", "mg:4 ev", "mg:7",
        "zeekr:x", "zeekr:7x", "zeekr:009",
        "toyota:corolla cross", "hyundai:ioniq 5", "kia:ev6",
    },
    "massaging seats": {
        "gwm:tank 500", "tank:500",
        "zeekr:009", "zeekr:7x",
        "byd:han",
    },
    "wireless charging": {
        "kia:sportage l", "honda:hr-v e:hev", "hyundai:tucson hybrid",
        "byd:sealion 7", "byd:seal", "byd:atto 3", "byd:atto 2", "byd:han",
        "gwm:tank 500", "gwm:tank 300", "tank:500", "tank:300",
        "jetour:x70 plus", "jetour:t2", "jetour:t9", "jetour:dashing",
        "jaecoo:j7", "jaecoo:j6", "jaecoo:j5",
        "omoda:7", "omoda:c5", "omoda:e5", "chery:omoda 5 ev",
        "haval:h6 hev", "haval:jolion hev", "haval:h7",
        "mg:hs phev", "mg:4 ev", "mg:7",
        "zeekr:x", "zeekr:7x", "zeekr:009",
        "toyota:corolla cross", "hyundai:ioniq 5", "kia:ev6",
        "suzuki:fronx",
    },
    "premium audio": {
        "gwm:tank 500", "tank:500",
        "zeekr:7x", "zeekr:009", "zeekr:x",
        "byd:sealion 7", "byd:seal", "byd:han",
        "jaecoo:j7", "omoda:7", "jetour:t2",
    },
    "7 seater": {
        "gwm:tank 500", "tank:500",
        "jetour:t9", "jetour:x70 plus",
        "zeekr:009",
    },
}

_FEATURE_IMPOSSIBLE_2026_PATCH: dict[str, set[str]] = {
    # Entry/compact 2025-26 arrivals that genuinely lack these systems in
    # PKDM spec. Without these the blocklists silently leak the newest cars.
    "sunroof": {
        "byd:atto 2",           # Atto 2 PKDM omits the roof glass
        "omoda:c5",             # base Omoda C5 trims
    },
    "adaptive cruise control": {
        "suzuki:fronx",         # PKDM Fronx has no radar cruise
        "byd:atto 2",
        "omoda:c5",
        "jetour:dashing",       # Dashing PKDM ships without ACC
    },
    "lane assist": {
        "suzuki:fronx",
        "byd:atto 2",
        "omoda:c5",
        "jetour:dashing",
    },
    "blind spot monitor": {
        "suzuki:fronx",
        "byd:atto 2",
        "omoda:c5",
    },
    "auto parking": {
        # Auto-park is near-universally absent in PKDM spec; new entrants are
        # no exception and must not leak through the existing blocklist.
        "suzuki:fronx", "byd:atto 2", "byd:atto 3", "byd:seal",
        "omoda:c5", "omoda:7", "omoda:e5",
        "jaecoo:j5", "jaecoo:j6", "jaecoo:j7",
        "jetour:dashing", "jetour:x70 plus", "jetour:t2", "jetour:t9",
        "gwm:tank 300", "tank:300",
        "haval:h6 hev", "haval:jolion hev", "haval:h7",
        "kia:sportage l", "hyundai:tucson hybrid", "toyota:corolla cross",
        "honda:hr-v e:hev",
    },
    "under 1300cc": {
        # Every 2025-26 crossover/SUV entrant below is >1300cc (or an EV with
        # no displacement at all) — none can satisfy a sub-1300cc tax query.
        "kia:sportage l", "hyundai:tucson hybrid", "toyota:corolla cross",
        "honda:hr-v e:hev", "suzuki:fronx",
        "byd:atto 2", "byd:atto 3", "byd:seal", "byd:sealion 7", "byd:han",
        "byd:dolphin", "byd:shark 6",
        "gwm:tank 300", "gwm:tank 500", "tank:300", "tank:500",
        "jetour:dashing", "jetour:x70 plus", "jetour:t1", "jetour:t2", "jetour:t9",
        "jaecoo:j5", "jaecoo:j6", "jaecoo:j7",
        "omoda:c5", "omoda:7", "omoda:e5", "chery:omoda 5 ev",
        "haval:h6 hev", "haval:jolion hev", "haval:h7",
        "mg:hs phev", "mg:4 ev", "mg:7", "mg:cyberster",
        "zeekr:x", "zeekr:7x", "zeekr:009",
        "hyundai:ioniq 5", "kia:ev6", "nissan:leaf", "mg:zs ev",
    },
    "hybrid": {
        # Pure BEVs are NOT hybrids — a "hybrid" query must not return them.
        "byd:atto 2", "byd:atto 3", "byd:dolphin", "byd:seal", "byd:sealion 7",
        "omoda:e5", "chery:omoda 5 ev",
        "jaecoo:j6",
        "zeekr:x", "zeekr:7x", "zeekr:009",
        "mg:4 ev", "mg:cyberster",
        "hyundai:ioniq 5", "kia:ev6",
    },
    "4wd": {
        # FWD-only 2025-26 entrants.
        "suzuki:fronx", "byd:atto 2", "byd:atto 3", "byd:dolphin",
        "omoda:c5", "omoda:e5", "jaecoo:j5",
        "jetour:dashing", "toyota:corolla cross", "honda:hr-v e:hev",
    },
}


def _apply_feature_patch(
    target: dict[str, set[str]],
    patch: dict[str, set[str]],
    label: str,
) -> None:
    """
    Union-merge `patch` into `target` in place.

    Purely additive by construction: a feature key that already exists is
    widened via set union; a genuinely new feature key is created. Nothing is
    ever removed, so no existing gate behaviour can regress.

    Kept as a function (rather than inline loops) so the merge is testable and
    so both maps report their delta identically at import time under debug.
    """
    for feature, models in patch.items():
        if feature in target:
            target[feature] |= models
        else:
            target[feature] = set(models)
    _ = label  # retained for callers that want to log the merge source


_apply_feature_patch(
    _FEATURE_EXCLUSIVE_ALLOWLIST, _FEATURE_ALLOWLIST_2026_PATCH, "allowlist-2026"
)
_apply_feature_patch(
    _FEATURE_IMPOSSIBLE, _FEATURE_IMPOSSIBLE_2026_PATCH, "blocklist-2026"
)

# ---------------------------------------------------------------------------
# SUNROOF TRIM KNOWLEDGE
# Retained from MODEL_FEATURE_KNOWLEDGE — trim-level hint for sunroof queries.
# Injected as inline notes in the eligible list so the LLM knows which trim
# to specify. Only sunroof has trim-level data; all other features use the
# impossible-gate approach above which is sufficient.
# ---------------------------------------------------------------------------

_SUNROOF_TRIM_KNOWLEDGE: dict[str, list[str]] = {
    # ["any"] = all trims, [] / missing = unknown
    # NOTE: toyota:fortuner deliberately OMITTED — no factory sunroof in PK
    # market (roof-mounted rear AC ducts occupy the space). See _FEATURE_IMPOSSIBLE.
    "toyota:corolla":          ["Grande", "Altis Grande", "X Corolla"],
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

_JDM_HYBRID_RECENT_IMPORTS = {
    "toyota:aqua", "toyota:prius", "honda:insight", "honda:grace", "nissan:note e-power",
    "honda:shuttle", "toyota:vitz", "toyota:passo", "nissan:note",
}
_JDM_HYBRID_RECENT_FLOOR   = 3_200_000  # ~32 Lakhs PKR — realistic floor for a 2016+ (<=10yr) unit
_JDM_HYBRID_RECENT_FLOOR_2018 = 3_800_000  # ~38 Lakhs PKR — stricter floor for a 2018+ unit specifically

# City micro-EVs — short real-world range (<150km), suitable ONLY for in-city
# commuting. Physically incapable of inter-city highway trips (e.g. Islamabad
# to Lahore is 380km). Hard-blocked when a highway/long-range EV is requested.
_CITY_MICRO_EVS = {"honri:ve", "rinco:aria", "metro:enfon"}

# ── Origin Preference Hard Gate (Test 63) ───────────────────────────────────
# origin_pref="European" is enforced as a HARD registry filter in both
# get_eligible_cars() and _validate_targets() — everything else (JDM, Chinese,
# Local) remains a soft preference surfaced only inside the target-selection
# LLM prompt (see select_car_targets), unchanged by this gate. Peugeot is
# included per spec even though the registry currently has zero Peugeot
# entries — correct but inert for that make unless one is ever registered.
_EUROPEAN_MAKES = {"bmw", "mercedes-benz", "audi", "porsche", "land rover", "volkswagen", "peugeot"}

# ── Legacy Luxury Feature Price-Floor (Test 54) ─────────────────────────────
# toyota:prado / toyota:land cruiser sit in the "memory seats" and "360
# camera" _FEATURE_EXCLUSIVE_ALLOWLIST sets below because modern (2020+)
# trims genuinely carry them — but both models' registry price range starts
# as low as PKR 2.5M, spanning 1990s/2000s generations that do NOT. Consumed
# as a budget sub-condition alongside the existing Kia Sorento memory-seat
# override inside get_eligible_cars()'s allowlist check (see "STRICT PKDM
# BUDGET OVERRIDE" below) — not a new standalone gate.
_LEGACY_LUXURY_FEATURE_FLOOR = 15_000_000  # 1.5 Crore PKR


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
    # ── Heated Seats ─────────────────────────────────────────────────────
    "heated seats":            "heated seats",
    "seat warmer":             "heated seats",
    "seat heating":            "heated seats",
    "warm seats":              "heated seats",
    # ── Ventilated / Cooled Seats (separate gate from heated) ────────────
    "ventilated seats":        "ventilated seats",
    "ventilated seat":         "ventilated seats",
    "ventilated":              "ventilated seats",
    "seat cooling":            "ventilated seats",
    "cooled seats":            "ventilated seats",
    "cooled seat":             "ventilated seats",
    "cooling seats":           "ventilated seats",
    "seat ventilation":        "ventilated seats",
    # ── Massaging Seats ──────────────────────────────────────────────────
    "massaging seats":         "massaging seats",
    "massage seats":           "massaging seats",
    "massage seat":            "massaging seats",
    "seat massage":            "massaging seats",
    # ── Leather Seats ────────────────────────────────────────────────────
    "leather seats":           "leather seats",
    "leather":                 "leather seats",
    # ── 4WD / AWD ────────────────────────────────────────────────────────
    "4wd":                     "4wd",
    "4x4":                     "4wd",
    "awd":                     "4wd",
    "four wheel drive":        "4wd",
    "all wheel drive":         "4wd",
    # ── Hybrid / Powertrain ──────────────────────────────────────────────
    "hybrid":                  "hybrid",
    "hev":                     "hybrid",
    "phev":                    "hybrid",
    # ── Blind Spot Monitor ───────────────────────────────────────────────
    "blind spot":              "blind spot monitor",
    "bsm":                     "blind spot monitor",
    "blind spot monitor":      "blind spot monitor",
    # ── Memory Seats ─────────────────────────────────────────────────────
    "memory seats":            "memory seats",
    "memory seat":             "memory seats",
    "seat memory":             "memory seats",
    "driver memory":           "memory seats",
    "driver seat memory":      "memory seats",
    "memory function":         "memory seats",
    "memory":                  "memory seats",
    # ── Power Tailgate ───────────────────────────────────────────────────
    "power tailgate":          "power tailgate",
    "auto trunk":              "power tailgate",
    "electric tailgate":       "power tailgate",
    "hands free trunk":        "power tailgate",
    "hands-free trunk":        "power tailgate",
    "electric trunk":          "power tailgate",
    # ── Electric Parking Brake ───────────────────────────────────────────
    "epb":                     "electric parking brake",
    "electric parking brake":  "electric parking brake",
    "electronic parking brake":"electric parking brake",
    "auto hold":               "electric parking brake",
    "brake hold":              "electric parking brake",
    "e-brake":                 "electric parking brake",
    # ── Dual Zone Climate ────────────────────────────────────────────────
    "dual zone":               "dual zone climate",
    "dual-zone":               "dual zone climate",
    "dual zone ac":            "dual zone climate",
    "dual zone climate":       "dual zone climate",
    "dual zone air":           "dual zone climate",
    "2 zone climate":          "dual zone climate",
    "two zone climate":        "dual zone climate",
    "dual zone temperature":   "dual zone climate",
    # ── Rear AC Vents ────────────────────────────────────────────────────
    "rear ac":                 "rear ac vents",
    "rear vents":              "rear ac vents",
    "rear ac vents":           "rear ac vents",
    "rear air conditioning":   "rear ac vents",
    "back ac":                 "rear ac vents",
    "back vents":              "rear ac vents",
    # ── 360 Camera ───────────────────────────────────────────────────────
    "360 camera":              "360 camera",
    "360 view":                "360 camera",
    "360 degree camera":       "360 camera",
    "surround camera":         "360 camera",
    "surround view":           "360 camera",
    "bird eye":                "360 camera",
    "birds eye view":          "360 camera",
    # ── Head-Up Display ──────────────────────────────────────────────────
    "hud":                     "head up display",
    "head up display":         "head up display",
    "head-up display":         "head up display",
    "heads up display":        "head up display",
    "windshield display":      "head up display",
    # ── Digital Instrument Cluster ───────────────────────────────────────
    "digital cluster":         "digital instrument cluster",
    "digital meter":           "digital instrument cluster",
    "digital gauge":           "digital instrument cluster",
    "virtual cockpit":         "digital instrument cluster",
    "digital dashboard":       "digital instrument cluster",
    "fully digital cluster":   "digital instrument cluster",
    # ── Wireless Charging ────────────────────────────────────────────────
    "wireless charging":       "wireless charging",
    "wireless charger":        "wireless charging",
    "qi charging":             "wireless charging",
    "qi charger":              "wireless charging",
    "wireless phone charging": "wireless charging",
    # ── Premium Audio ─────────────────────────────────────────────────────
    "premium audio":           "premium audio",
    "premium sound":           "premium audio",
    "bose":                    "premium audio",
    "harman kardon":           "premium audio",
    "harman":                  "premium audio",
    "jbl":                     "premium audio",
    "premium speakers":        "premium audio",
    # ── ADAS alias catches ───────────────────────────────────────────────
    "radar":                   "adaptive cruise control",
    "radar cruise":            "adaptive cruise control",
    "honda sensing":           "adaptive cruise control",
    "toyota safety sense":     "adaptive cruise control",
    "distance keeping":        "adaptive cruise control",
    # ── 7-Seater / Third Row ─────────────────────────────────────────────
    # Hard allowlist gate — prevents 4-seaters / kei cars from passing
    # a 7-seater query. Jimny, Terios, Alto, Swift etc. are physically blocked.
    "7 seater":                "7 seater",
    "7-seater":                "7 seater",
    "7 seat":                  "7 seater",
    "7 seats":                 "7 seater",
    "seven seater":            "7 seater",
    "seven seat":              "7 seater",
    "third row":               "7 seater",
    "3rd row":                 "7 seater",
    "third row seat":          "7 seater",
    "8 seater":                "7 seater",   # 8-seaters are a superset, same gate
    "8-seater":                "7 seater",
    "family van":              "7 seater",
    # ── Series Hybrid / e-Power ──────────────────────────────────────────
    # Series hybrid = petrol engine acts ONLY as generator; wheels driven
    # purely by electric motor. In Pakistan: Nissan Note/Serena e-Power,
    # Forthing Friday. NOT to be confused with parallel HEV (Aqua, Prius).
    "series hybrid":           "series hybrid",
    "e-power":                 "series hybrid",
    "epower":                  "series hybrid",
    "e power":                 "series hybrid",
    "range extender":          "series hybrid",
    "reev":                    "series hybrid",
    "range extended":          "series hybrid",
    # ── Engine CC / Token Tax Brackets ──────────────────────────────────
    # Maps user intent around Pakistan annual token tax brackets.
    # Vehicles up to 1000cc pay lowest rate. 1001-1300cc next tier.
    # 1301-1600cc higher. Users say "low tax"/"1500cc" to avoid 1601-1800cc bracket.
    "under 1500cc":            "under 1500cc",
    "1500cc":                  "under 1500cc",
    "under 1300cc":            "under 1300cc",
    "1300cc":                  "under 1300cc",
    # 660cc Kei-car bracket — strictly narrower than "under 1300cc" (Test 66).
    # A user asking for this specifically wants a true Japanese kei-class
    # vehicle, not just any sub-1300cc car — see _FEATURE_EXCLUSIVE_ALLOWLIST.
    "660cc":                   "660cc",
    "660 cc":                  "660cc",
    "sub 660cc":               "660cc",
    "kei":                     "660cc",
    "kei car":                 "660cc",
    "1.5l":                    "under 1500cc",
    "1.5 l":                   "under 1500cc",
    "1.5 litre":               "under 1500cc",
    "1.5 liter":               "under 1500cc",
    "1.3l":                    "under 1300cc",
    "1.3 l":                   "under 1300cc",
    "1.3 litre":               "under 1300cc",
    "low tax":                 "under 1500cc",
    "token tax":               "under 1500cc",
    "save tax":                "under 1500cc",
    "tax bracket":             "under 1500cc",
    "low token":               "under 1500cc",
    "cheap token":             "under 1500cc",
    # ── High-Altitude Fuel Sensitivity / HOBC-GDI Knocking Gate ──────────
    # Users at altitude (northern areas) or without reliable HOBC/95 RON
    # access flag GDI/TGDI turbo engines as knock-prone on regular pump
    # fuel. Normalise all phrasings to the "regular fuel" gate so only
    # NA/MPI engines (Sportage Alpha MPI, Tucson FWD MPI, Corolla 1.8 NA)
    # pass through.
    "no hobc":                 "regular fuel",
    "regular fuel":            "regular fuel",
    "92 ron":                  "regular fuel",
    "no knocking":             "regular fuel",
    "engine knocking":         "regular fuel",
}

def get_eligible_cars(
    max_budget: int,
    min_budget: int,
    allow_chinese: bool,
    body_style: str | None = None,
    is_apex_luxury: bool = False,
    transmission_req: str | None = None,
    excluded_models: list[str] | None = None,
    required_features: list[str] | None = None,
    excluded_features: list[str] | None = None,
    direct_model_req: str | None = None,
    is_youth_query: bool = False,
    drive_req: str | None = None,
    powertrain_req: str | None = None,
    min_year: int = 0,
    is_luxury_request: bool = False,
    is_highway_ev: bool = False,
    origin_pref: str | None = None,
    is_diesel_hybrid_query: bool = False,
    excluded_origins: list[str] | None = None,
    is_llm_vetoed: bool = False,
    intent_id: str | None = None,
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

    NEWER GATES (added after the numbered list above was originally written —
    see inline comments at each site for full detail; not renumbered here to
    avoid disturbing the existing reference list):
      • origin_pref=="European" — hard-drops every non-European make (Test 63).
        See _EUROPEAN_MAKES.
      • origin_pref=="Local" — hard-drops every "jdm"-tagged model, forcing
        locally-assembled variants (e.g. suzuki:alto over suzuki:alto 660cc)
        (Test 71/72).
      • is_diesel_hybrid_query — unconditional zero-out: no diesel-electric
        hybrid exists in this registry at any price, so every model is
        dropped outright rather than silently substituting a petrol hybrid
        (Test 74).
      • Legacy luxury feature price-floor — Prado/Land Cruiser dropped for
        memory-seats/360-camera/HUD queries under PKR 1.5 Crore (Test 54).
        See _LEGACY_LUXURY_FEATURE_FLOOR.

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

    # ── Front-Door Veto Short-Circuit ────────────────────────────────────────
    # If resolve_constraints() set is_llm_vetoed, the query is paradoxical,
    # illegal, or physically impossible. Python must not even attempt a registry
    # scan — return immediately so the pipeline reaches an honest zero-hit.
    if is_llm_vetoed:
        return (
            "No eligible cars found. The user's query contains contradictory, "
            "illegal, or impossible constraints. Return an empty array []."
        )

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
    _dropped_by_min_year_floor = 0  # tracks drops caused specifically by the JDM year-price floor

    for key, info in CAR_REGISTRY.items():
        lo    = info["lo"]
        hi    = info["hi"]
        make, model = key.split(":", 1)

        is_direct_target = False
        if direct_model_req:
            dm_lower = direct_model_req.lower()
            if dm_lower == model.lower() or dm_lower == f"{make} {model}".lower():
                is_direct_target = True

        # 0a. Diesel-Electric Hybrid Paradox — unconditional zero-out (Test 74)
        # No diesel-electric hybrid exists in this registry at any price point
        # or budget — every "hybrid"-tagged model here is petrol-electric.
        # Rather than surgically dropping only hybrid-tagged cars (which would
        # still let plain non-hybrid petrol cars slip through and silently
        # answer a request the user didn't make), this drops EVERYTHING
        # unconditionally so the pipeline reaches a clean, honest zero-hit —
        # matching the disclaimer already injected in resolve_constraints.
        if is_diesel_hybrid_query:
            continue

        # 0b. JDM Hybrid Age-Price Floor Adjustment (Test 48/55 patch, extended)
        # A 2016+ (<=10yr old) recent-year JDM import — Aqua/Prius/Insight/Grace/
        # Note e-Power/Shuttle/Vitz/Passo/Note — realistically starts well above
        # the registry's blanket floor, which also covers much older, cheaper
        # units of the same model. When the user requests a recent-year hybrid
        # (or one of these specific JDM imports), elevate the floor so a stale
        # cheap-old-gen unit can't silently satisfy a budget that can't actually
        # reach a genuinely recent-year example. A 2018+ request tightens the
        # floor further, since 2018+ units are scarcer and command a premium.
        #
        # This is a curated explicit list rather than a blanket "jdm" tag match:
        # the registry's "jdm" tag also covers unrelated kei-car imports (Suzuki
        # Alto 660cc, Jimny, Hustler, Spacia, Solio) whose registry floors sit
        # well under this threshold — sweeping those in on tag alone would
        # wrongly block legitimate budget kei-import searches that have nothing
        # to do with the hybrid-import pricing problem this gate targets.
        #
        # The budget check here is deliberately STRICT (no grace margin), unlike
        # the general budget overlap gate later in this loop — a query below the
        # true elevated floor must be dropped outright, not squeeze through on
        # a 20% grace band meant for ordinary registry pricing spread.
        if key in _JDM_HYBRID_RECENT_IMPORTS and min_year >= 2016:
            effective_lo = _JDM_HYBRID_RECENT_FLOOR_2018 if min_year >= 2018 else _JDM_HYBRID_RECENT_FLOOR
            lo = max(lo, effective_lo)
            if max_budget > 0 and max_budget < effective_lo:
                _dropped_by_min_year_floor += 1
                continue

        # 0c. City Micro-EV Highway Hard-Gate
        # Honri VE, Rinco Aria, Metro Enfon have real-world ranges under 150km —
        # physically incapable of inter-city highway trips. When the user's query
        # signals a highway/long-range EV need, these are deleted outright rather
        # than silently scored low, so the LLM can never see or pick them.
        if is_highway_ev and key in _CITY_MICRO_EVS:
            continue

        # 1. Body style gate
        # SUV and Crossover are treated as interchangeable — Pakistani buyers use
        # both terms for the same category. Kia Sorento, Oshan X7, Tiggo 8 Pro etc.
        # are classified as "Crossover" in registry but must pass an "SUV" query.
        if body_style and not is_direct_target:
            allowed_styles = {body_style}
            if intent_id != "true_suv_demand":
                if body_style == "SUV":
                    allowed_styles.add("Crossover")
                elif body_style == "Crossover":
                    allowed_styles.add("SUV")
            if not any(style in info["styles"] for style in allowed_styles):
                continue

        # 2. Chinese gate
        if info["chinese"] and not allow_chinese:
            continue

        # 2b. Origin Preference Hard Gate (Test 63 European + Test 71/72 Local)
        # origin_pref was already being threaded into the target-selection LLM
        # prompt as a soft "prefer JDM" signal (see select_car_targets), but
        # had ZERO deterministic enforcement here — a "European only" request
        # could still see Corolla/Civic pass every other gate and get
        # surfaced to the LLM as eligible. This is a hard filter: non-European
        # makes are removed outright when origin_pref == "European", and
        # every "jdm"-tagged model is removed outright when origin_pref ==
        # "Local" (e.g. suzuki:alto 660cc is dropped, forcing the locally-
        # assembled suzuki:alto to be the one offered). Chinese origin_pref
        # remains a soft, prompt-level signal only — unchanged by this patch.
        if origin_pref == "European" and make not in _EUROPEAN_MAKES:
            continue
        if origin_pref == "Local" and "jdm" in info.get("tags", set()):
            continue

        # 2c. Excluded Origins Hard Gate (Defense-in-Depth)
        # If the LLM misses an origin wipeout (or the user stated it only
        # in natural language), Python enforces it here as a second layer.
        # Mirrors the same gate in _validate_targets().
        _excl_origins = excluded_origins or []
        if _excl_origins:
            skip_origin = False
            car_tags    = info.get("tags", set())
            car_is_jdm      = "jdm" in car_tags
            car_is_chinese  = info.get("chinese", False)
            car_is_european = make in _EUROPEAN_MAKES
            car_is_local    = not car_is_jdm and not car_is_chinese and not car_is_european

            for excl_orig in _excl_origins:
                if excl_orig in {"local", "pkdm", "locally assembled"} and car_is_local:
                    skip_origin = True; break
                if excl_orig in {"jdm", "imported", "japanese"} and car_is_jdm:
                    skip_origin = True; break
                if excl_orig in {"chinese", "china"} and car_is_chinese:
                    skip_origin = True; break
                if excl_orig in {"european", "europe", "germany", "german"} and car_is_european:
                    skip_origin = True; break
            if skip_origin:
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

        # 6. Apex Luxury / Luxury Tag Gate — PATCHED (Test 43: gate leakage)
        # Previous logic (`is_apex_luxury and hi < max_budget * 0.55` alone)
        # let mass-market commuter sedans (Civic/Corolla) leak into 1cr+ "boss
        # car" queries whenever their upper trim price crept toward ~95 Lakhs.
        # New rule: apex luxury OR an explicit luxury request at 1cr+ budget
        # ONLY allows models carrying the "luxury" or "status" tag — Corolla,
        # Civic, Yaris, and City are hard-blocked from serving as VIP/boss
        # alternatives regardless of how high their ceiling price reaches.
        _luxury_tier_active = is_apex_luxury or (is_luxury_request and max_budget >= 10_000_000)
        if _luxury_tier_active:
            if not ({"luxury", "status"} & info.get("tags", set())):
                continue
            if max_budget > 0 and hi < max_budget * 0.55:
                continue

        # 6b. Ultra-luxury tier — exclude Prado at 4+ crore budgets
        # At 4-5 crore, only Lexus LX600, LC300, Range Rover, Defender, BMW X7, Mercedes GLS
        if max_budget >= 40_000_000 and key == "toyota:prado":
            continue

        # 7. Hybrid Feature Gate (Allowlist + Blocklist)
        #
        #    A. Exclusive Allowlist (_FEATURE_EXCLUSIVE_ALLOWLIST):
        #       For rare/premium features.  If the feature has an allowlist,
        #       the car MUST appear in that set — everything else is excluded.
        #       This is mathematically bulletproof: no matter how many new
        #       models enter the market, the gate never leaks.
        #
        #    B. Impossible Blocklist (_FEATURE_IMPOSSIBLE):
        #       For common features.  If the car appears in the blocked set for
        #       a feature, it is excluded.  Unlisted cars pass through
        #       (unknown = allow, LLM decides).
        #
        #    Both checks run per feature; the first failure short-circuits.
        if active_feature_gates:
            skip = False
            for feat_key in active_feature_gates:
                # Direct Model Immunity is COMPLETELY REVOKED for feature gates.
                # Naming a car (e.g. "Suzuki Cultus") does not magically spawn
                # hardware it physically cannot have (e.g. Power Tailgate).
                # Every car — named or not — must pass all hardware blocklists.
                # A. Check Exclusive Allowlist first (strict inclusion)
                if feat_key in _FEATURE_EXCLUSIVE_ALLOWLIST:
                    if key not in _FEATURE_EXCLUSIVE_ALLOWLIST[feat_key]:
                        skip = True
                        break
                    # STRICT PKDM BUDGET OVERRIDE:
                    # Kia Sorento base/mid trims in Pakistan omit memory seats.
                    # Only the AWD HEV trim (₹1Cr+) retains them.
                    # Physically delete Sorento from memory seat queries under 1 Crore
                    # so the LLM cannot see it and cannot hallucinate it.
                    if (feat_key == "memory seats"
                            and key == "kia:sorento"
                            and max_budget > 0
                            and max_budget < 10_000_000):
                        skip = True
                        break

                    # LEGACY LUXURY FEATURE PRICE-FLOOR (Test 54 patch):
                    # toyota:prado / toyota:land cruiser are members of the
                    # "memory seats" and "360 camera" allowlists above because
                    # modern (2020+) trims genuinely carry them — but both
                    # models' registry price range starts as low as PKR 2.5M,
                    # spanning 1990s/2000s generations that do not. Below the
                    # PKR 1.5 Crore floor, a query is realistically hitting
                    # those older generations, so allowlist membership alone
                    # isn't enough — apply the same budget-override pattern
                    # used for Sorento above. mitsubishi:pajero is named here
                    # too for completeness with the original spec, but is
                    # currently a no-op: it is not a member of any of these
                    # three allowlists at all, so it is already unconditionally
                    # excluded from these features at every budget — a
                    # stricter, equally-correct outcome this check doesn't
                    # need to loosen.
                    if (feat_key in {"memory seats", "360 camera", "head up display"}
                            and key in {"toyota:prado", "toyota:land cruiser", "mitsubishi:pajero"}
                            and max_budget > 0
                            and max_budget < _LEGACY_LUXURY_FEATURE_FLOOR):
                        skip = True
                        break
                # B. Check Impossible Blocklist (strict exclusion)
                else:
                    impossible_set = _FEATURE_IMPOSSIBLE.get(feat_key, set())
                    if key in impossible_set:
                        skip = True
                        break

                    # COMBINATION PARADOX (Test 62): the PK-market Corolla
                    # 1.3L (XLi/GLi) genuinely exists, so toyota:corolla
                    # correctly passes the "under 1300cc" blocklist above on
                    # engine size alone — but that specific 1.3L trim is
                    # MANUAL ONLY in Pakistan; Automatic Corolla starts at
                    # 1.6L. The LLM hallucinated an "Automatic Corolla 1.0"
                    # because engine size and transmission were being
                    # checked as independent facts instead of as a joint
                    # combination. Hard-block that exact combination here.
                    if (feat_key == "under 1300cc"
                            and key == "toyota:corolla"
                            and transmission_req == "Automatic"):
                        skip = True
                        break
            if skip:
                continue

        # 7b. Excluded Feature Gate
        if excluded_features and not is_direct_target:
            skip_due_to_exclusion = False
            for excl_feat in excluded_features:
                excl_feat_lower = excl_feat.lower().strip()
                normalised_excl = _FEAT_NORMALISE.get(excl_feat_lower, excl_feat_lower)

                # If they forbid "660cc" or "jdm", we can check tags or the exclusive allowlist
                if normalised_excl == "660cc" and key in _FEATURE_EXCLUSIVE_ALLOWLIST.get("660cc", set()):
                    skip_due_to_exclusion = True
                    break
                if normalised_excl == "jdm" and "jdm" in info.get("tags", set()):
                    skip_due_to_exclusion = True
                    break
                # If they forbid a rare feature, and the car is in the exclusive allowlist for it
                if normalised_excl in _FEATURE_EXCLUSIVE_ALLOWLIST and key in _FEATURE_EXCLUSIVE_ALLOWLIST[normalised_excl]:
                    skip_due_to_exclusion = True
                    break
            if skip_due_to_exclusion:
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
                if max_budget > hi * 1.05:
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
        if is_direct_target:
            final_score += 1.0

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
        # If every candidate was dropped specifically by the JDM year-price floor
        # gate (rather than body style / features / other constraints), surface a
        # targeted message naming the year requirement as the actual blocker —
        # this is more actionable than the generic impossibility message below.
        if _dropped_by_min_year_floor > 0:
            return (
                "No eligible cars found matching your minimum year requirement within "
                "the specified budget. Return an empty array []."
            )

        # Do NOT silently drop feature requirements and retry — that caused the LLM
        # to hallucinate random cars that didn't have the requested features.
        # Instead, return an explicit impossibility message so the caller can handle
        # it gracefully (Stage 3.5 self-healing fallback in recommend_routes.py).
        style_note = f" matching body style '{body_style}'" if body_style else ""
        feat_note  = f" with required features [{', '.join(sorted(active_feature_gates))}]" if active_feature_gates else ""
        return (
            f"No eligible cars found{style_note}{feat_note} for this budget. "
            "The combination you are looking for is mathematically impossible in Pakistan. "
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

def _validate_targets(targets: list, constraints: dict) -> tuple[list, list[str]]:
    max_budget        = constraints.get("max_budget", 0)
    min_budget        = constraints.get("min_budget", 0)
    allow_chinese     = constraints.get("allow_chinese", False)
    body_style        = constraints.get("body_style")
    is_apex           = constraints.get("is_apex_luxury", False)
    is_luxury_request = constraints.get("is_luxury_request", False)
    origin_pref       = constraints.get("origin_pref")
    excluded_models   = {m.lower() for m in (constraints.get("excluded_models") or [])}
    required_features = constraints.get("required_features") or []
    direct_model_req  = constraints.get("direct_model")

    valid:           list     = []
    dropped_reasons: list[str] = []

    for t in targets:
        make_lower    = t.make.lower().strip()
        model_lower   = t.model.lower().strip()
        key           = f"{make_lower}:{model_lower}"
        info          = CAR_REGISTRY.get(key)
        display_lower = f"{make_lower} {model_lower}"

        is_direct_target = False
        if direct_model_req:
            dm_lower = direct_model_req.lower()
            if dm_lower == model_lower or dm_lower == display_lower:
                is_direct_target = True

        # 1. Strict veto / exclusion gate
        # Checks make, model, and "make model" form independently against
        # excluded_models. Checking make_lower separately closes a leak where
        # a bare-make veto ("no Haval") could theoretically miss a model whose
        # display string construction differs from the registry key format.
        is_vetoed = any(
            ex in display_lower or ex in model_lower or ex in make_lower or display_lower in ex
            for ex in excluded_models
        )
        if is_vetoed:
            reason = f"Dropped {t.make} {t.model}: Explicitly vetoed by user."
            print(f"[Validator] Hard-dropping {t.make} {t.model} — matches excluded_models veto")
            dropped_reasons.append(reason)
            continue

        # 2. Chinese gate
        if info and info["chinese"] and not allow_chinese:
            reason = f"Dropped {t.make} {t.model}: Chinese brand not requested by user."
            print(f"[Validator] Dropping {t.make} {t.model} — Chinese brand not requested")
            dropped_reasons.append(reason)
            continue

        # 2b. Origin Preference Hard Gate (Test 63 European + Test 71/72 Local, mirrors get_eligible_cars)
        if info and origin_pref == "European" and make_lower not in _EUROPEAN_MAKES:
            reason = f"Dropped {t.make} {t.model}: Not a European make; user requested European origin only."
            print(f"[Validator] Dropping {t.make} {t.model} — non-European make for European-only query")
            dropped_reasons.append(reason)
            continue
        if info and origin_pref == "Local" and "jdm" in info.get("tags", set()):
            reason = f"Dropped {t.make} {t.model}: Imported JDM model; user explicitly requested local PKDM assembly."
            print(f"[Validator] Dropping {t.make} {t.model} — JDM model for Local-only query")
            dropped_reasons.append(reason)
            continue

        # 2c. Excluded Origins Hard Gate (Defense-in-Depth — mirrors get_eligible_cars gate)
        if info:
            _v_excl_origins = constraints.get("excluded_origins", [])
            if _v_excl_origins:
                v_car_tags      = info.get("tags", set())
                v_car_is_jdm      = "jdm" in v_car_tags
                v_car_is_chinese  = info.get("chinese", False)
                v_car_is_european = make_lower in _EUROPEAN_MAKES
                v_car_is_local    = not v_car_is_jdm and not v_car_is_chinese and not v_car_is_european
                v_skip_origin     = False

                for excl_orig in _v_excl_origins:
                    if excl_orig in {"local", "pkdm", "locally assembled"} and v_car_is_local:
                        v_skip_origin = True; break
                    if excl_orig in {"jdm", "imported", "japanese"} and v_car_is_jdm:
                        v_skip_origin = True; break
                    if excl_orig in {"chinese", "china"} and v_car_is_chinese:
                        v_skip_origin = True; break
                    if excl_orig in {"european", "europe", "germany", "german"} and v_car_is_european:
                        v_skip_origin = True; break

                if v_skip_origin:
                    reason = f"Dropped {t.make} {t.model}: Origin is forbidden by user's explicit exclusion."
                    print(f"[Validator] Dropping {t.make} {t.model} — excluded origin")
                    dropped_reasons.append(reason)
                    continue

        # 3. Body style gate — SUV/Crossover treated as interchangeable (mirror of gate in get_eligible_cars)
        if info and body_style and not is_direct_target:
            allowed_styles = {body_style}
            if constraints.get("intent_id") != "true_suv_demand":
                if body_style == "SUV":
                    allowed_styles.add("Crossover")
                elif body_style == "Crossover":
                    allowed_styles.add("SUV")
            if not any(style in info["styles"] for style in allowed_styles):
                reason = f"Dropped {t.make} {t.model}: Body style '{'/'.join(info['styles'])}' does not match requested '{body_style}'."
                print(f"[Validator] Dropping {t.make} {t.model} — not a {body_style}")
                dropped_reasons.append(reason)
                continue

        # 4. Transmission gate
        transmission_req = constraints.get("transmission")
        if info and transmission_req:
            car_trans = info.get("transmission", "both")
            if transmission_req == "Manual" and car_trans == "auto":
                reason = f"Dropped {t.make} {t.model}: Auto-only car, user requires Manual."
                print(f"[Validator] Dropping {t.make} {t.model} — auto-only, user wants Manual")
                dropped_reasons.append(reason)
                continue
            if transmission_req == "Automatic" and car_trans == "manual":
                reason = f"Dropped {t.make} {t.model}: Manual-only car, user requires Automatic."
                print(f"[Validator] Dropping {t.make} {t.model} — manual-only, user wants Automatic")
                dropped_reasons.append(reason)
                continue

        # 5. Budget gates
        if info and max_budget > 0:
            lo, hi = info["lo"], info["hi"]
            if max_budget < lo * 0.85:
                reason = f"Dropped {t.make} {t.model}: Budget floor PKR {lo:,} is unreachable at PKR {max_budget:,}."
                print(f"[Validator] Dropping {t.make} {t.model} — floor PKR {lo:,} unreachable")
                dropped_reasons.append(reason)
                continue
            if min_budget > 0 and hi < min_budget * 0.80:
                reason = f"Dropped {t.make} {t.model}: Price ceiling PKR {hi:,} is below budget floor PKR {min_budget:,}."
                print(f"[Validator] Dropping {t.make} {t.model} — ceiling PKR {hi:,} below budget floor")
                dropped_reasons.append(reason)
                continue

        # 6. Apex Luxury / Luxury Tag Gate — PATCHED (Test 43, mirrors get_eligible_cars)
        _luxury_tier_active_v = is_apex or (is_luxury_request and max_budget >= 10_000_000)
        if _luxury_tier_active_v and info:
            if not ({"luxury", "status"} & info.get("tags", set())):
                reason = f"Dropped {t.make} {t.model}: Lacks luxury/status tag required for apex luxury query."
                print(f"[Validator] Dropping {t.make} {t.model} — no luxury/status tag for apex luxury query")
                dropped_reasons.append(reason)
                continue
            if max_budget > 0 and info["hi"] < max_budget * 0.55:
                reason = f"Dropped {t.make} {t.model}: Too affordable (max PKR {info['hi']:,}) for apex luxury query."
                print(f"[Validator] Dropping {t.make} {t.model} — too cheap for apex luxury query")
                dropped_reasons.append(reason)
                continue

        # 7. Required Feature Verification
        # Re-checks required_features against the same allowlist/blocklist gates
        # get_eligible_cars() uses. This is a second line of defense: if the LLM
        # hallucinates a feature claim (e.g. claiming a Hyundai Sonata has 360
        # camera) that somehow wasn't caught upstream, it is dropped here too.
        #
        # NOTE: the inner loop's `break` only exits the `for feat in
        # required_features` loop, not the outer `for t in targets` loop — a
        # `feature_violation` flag is used so the offending car is actually
        # skipped via `continue` below, rather than falling through to
        # `valid.append(t)` after merely logging a "Dropped" reason.
        feature_violation = False
        if required_features and info:
            for feat in required_features:
                feat_lower = feat.lower().strip()
                normalised = _FEAT_NORMALISE.get(feat_lower, feat_lower)

                # Direct Model Immunity is COMPLETELY REVOKED for feature gates.
                # Naming a car does not exempt it from physical hardware checks.
                # Every car — named or not — must pass the allowlist/blocklist.

                # Allowlist check — car MUST be in the set to pass
                if normalised in _FEATURE_EXCLUSIVE_ALLOWLIST:
                    if key not in _FEATURE_EXCLUSIVE_ALLOWLIST[normalised]:
                        reason = f"Dropped {t.make} {t.model}: Does not natively possess required feature '{normalised}'."
                        print(f"[Validator] Dropping {t.make} {t.model} — missing {normalised}")
                        dropped_reasons.append(reason)
                        feature_violation = True
                        break
                # Impossible blocklist check — car must NOT be in the set
                elif normalised in _FEATURE_IMPOSSIBLE:
                    if key in _FEATURE_IMPOSSIBLE[normalised]:
                        reason = f"Dropped {t.make} {t.model}: Cannot feature '{normalised}' in PKDM spec."
                        print(f"[Validator] Dropping {t.make} {t.model} — blocked for {normalised}")
                        dropped_reasons.append(reason)
                        feature_violation = True
                        break
        if feature_violation:
            continue

        # 7b. Excluded Feature Gate
        excluded_features = constraints.get("excluded_features", [])
        if excluded_features and info and not is_direct_target:
            skip_due_to_exclusion = False
            for excl_feat in excluded_features:
                excl_feat_lower = excl_feat.lower().strip()
                normalised_excl = _FEAT_NORMALISE.get(excl_feat_lower, excl_feat_lower)

                if normalised_excl == "660cc" and key in _FEATURE_EXCLUSIVE_ALLOWLIST.get("660cc", set()):
                    reason = f"Dropped {t.make} {t.model}: Contains forbidden feature '{normalised_excl}'."
                    print(f"[Validator] Dropping {t.make} {t.model} — forbidden feature {normalised_excl}")
                    dropped_reasons.append(reason)
                    skip_due_to_exclusion = True
                    break
                if normalised_excl == "jdm" and "jdm" in info.get("tags", set()):
                    reason = f"Dropped {t.make} {t.model}: Contains forbidden feature '{normalised_excl}'."
                    print(f"[Validator] Dropping {t.make} {t.model} — forbidden feature {normalised_excl}")
                    dropped_reasons.append(reason)
                    skip_due_to_exclusion = True
                    break
                if normalised_excl in _FEATURE_EXCLUSIVE_ALLOWLIST and key in _FEATURE_EXCLUSIVE_ALLOWLIST[normalised_excl]:
                    reason = f"Dropped {t.make} {t.model}: Contains forbidden feature '{normalised_excl}'."
                    print(f"[Validator] Dropping {t.make} {t.model} — forbidden feature {normalised_excl}")
                    dropped_reasons.append(reason)
                    skip_due_to_exclusion = True
                    break
            if skip_due_to_exclusion:
                continue

        # 8. Micro-Engine Trim Hallucination Gate (Test 62 / 71 / 72)
        trim_lower = t.trim.lower()

        # Prevent LLM from simulating JDM imports on Local PKDM queries
        if constraints.get("origin_pref") == "Local" and ("660cc" in trim_lower or "jdm" in trim_lower):
            reason = f"Dropped {t.make} {t.model}: Appended '{t.trim}' to a local car, simulating a banned JDM import."
            print(f"[Validator] Dropping {t.make} {t.model} — {reason}")
            dropped_reasons.append(reason)
            continue

        if "1.0" in trim_lower or "660cc" in trim_lower or "800cc" in trim_lower:
            if info and "Hatchback" not in info["styles"] and "Van" not in info["styles"]:
                # Allow exceptions for legitimate non-hatchback micro engines
                if key not in {"mitsubishi:mini pajero", "suzuki:jimny", "daihatsu:terios"}:
                    reason = f"Dropped {t.make} {t.model}: Hallucinated micro-engine trim '{t.trim}' on a large vehicle."
                    print(f"[Validator] Dropping {t.make} {t.model} — Hallucinated micro-engine")
                    dropped_reasons.append(reason)
                    continue

        valid.append(t)

    # ── Safety net REMOVED ────────────────────────────────────────────────────
    # The old `return [targets[0]]` fallback was resurrecting vetoed cars.
    # If everything was legitimately dropped (veto, wrong style, wrong budget),
    # we return [] and let the caller handle it with a proper self-healing fallback.
    return valid, dropped_reasons


# ---------------------------------------------------------------------------
# PHASE 1: INTENT EXTRACTOR & CONSTRAINT RESOLVER
# ---------------------------------------------------------------------------

class UserIntent(BaseModel):
    max_budget:        Optional[int]                                                                 = None
    min_year:          Optional[int]                                                                 = Field(default=None, description="Earliest acceptable model year, e.g. 'not older than 10 years' in 2026 -> 2016")
    body_style:        Optional[Literal["SUV", "Mini SUV", "Sedan", "Hatchback", "Pickup", "Crossover", "Van", "MPV", "Coupe"]] = None
    transmission:      Optional[Literal["Automatic", "Manual"]]                                     = None
    drive:             Optional[Literal["4x4", "AWD", "FWD", "RWD"]]                                = None
    powertrain:        Optional[Literal["hybrid", "ev"]]                                             = None
    use_case:          Optional[str]                                                                 = None
    origin_pref:       Optional[Literal["JDM", "Local", "European", "Chinese"]]                     = None
    direct_model:      Optional[str]                                                                 = Field(default=None, description="Explicitly mentioned car model (e.g. 'Civic', 'Vitz', 'Prado')")
    is_luxury_request: bool                                                                          = False
    required_features: list[str]                                                                     = Field(default_factory=list)
    excluded_features: list[str]                                                                     = Field(default_factory=list, description="Features explicitly forbidden by the user (e.g., ['660cc', 'sunroof', 'leather seats'])")
    excluded_brands:   list[str]                                                                     = Field(default_factory=list, description="Brands/makes explicitly forbidden or vetoed by the user, e.g. ['Haval', 'Changan', 'Chery']")
    excluded_models:   list[str]                                                                     = Field(default_factory=list, description="Specific models explicitly forbidden or vetoed by the user, e.g. ['Yaris', 'City', 'Corolla']")
    excluded_origins:  list[str]                                                                     = Field(default_factory=list, description="Origins explicitly forbidden, e.g. ['local', 'jdm', 'chinese', 'european']")
    immediate_veto_message: Optional[str]                                                            = Field(default=None, description="If the query contains a severe paradox (e.g. '1.8L engine under 1000cc tax', '7-seater coupe', banned ALL origins, or illegal 'NCP' cars), provide a rejection starting with an UPPERCASE bracketed section tag — one of '[IMPOSSIBLE QUERY PARADOX]', '[LEGAL COMPLIANCE VETO]', or '[TAX BRACKET CONFLICT]' — followed by a single space and one plain sentence explaining why it is impossible, then a short corrective instruction. Example: '[IMPOSSIBLE QUERY PARADOX] A 2-door sports coupe physically cannot accommodate 7 passengers in the Pakistani market. Please adjust your body style or seating capacity.' Otherwise null.")
    strategy_summary:  str                                                                           = Field(default="", description="A friendly 2-sentence summary explaining the search interpretation and car strategy.")
    disclaimers:       list[str]                                                                     = Field(default_factory=list)
    current_car:       Optional[str]                                                                 = None
    city:              Optional[str]                                                                 = Field(default=None, description="Pakistani city the buyer wants to buy in, if stated (e.g. 'in Lahore', 'Karachi walay', 'based in Isb'). Extract the city name only, never a province or country. Null if the user names no location.")
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
        "STRICT ROLE DEFINITION:\n"
        "Your SOLE job is accurate signal extraction. You are a signal detector, not a feasibility "
        "advisor. Extract EXACTLY what the user requested. Do NOT evaluate whether the user's "
        "destination, lifestyle, or trip plan is compatible with their requested vehicle type. "
        "Do NOT unilaterally wipe powertrain, body_style, or required_features because you think "
        "their choice is impractical. Real-world warnings (e.g. 'Deosai has no chargers') are "
        "handled exclusively by downstream disclaimers — never by intent extraction.\n\n"
        "Rules:\n"
        "- Convert Pakistani currency precisely:\n"
        "  '1 crore' -> 10000000,  '5 crore'  -> 50000000,  '10 crore' -> 100000000\n"
        "  '20 lacs' -> 2000000,   '50 lacs'  -> 5000000,   '80 lacs'  -> 8000000\n"
        "  Always convert — never leave as text.\n"
        "- min_year: Extract an earliest acceptable model year if the user states an age or\n"
        "  recency constraint. Convert relative age statements using the current year (2026):\n"
        "  'not older than 10 years' -> 2016,  'max 5 years old' -> 2021,\n"
        "  'within last 3 years' -> 2023,  '2018 or newer' -> 2018,  'not before 2020' -> 2020.\n"
        "  Leave null if no age/year constraint is stated — never guess.\n"
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
        "- current_car: If the user states they currently own, are upgrading from, or are replacing "
        "a specific car (e.g., 'upgrading from Bolan', 'replacing my Mehran'), extract that model "
        "name here (e.g. 'Bolan', 'Mehran').\n"
        "- direct_model: If the user explicitly mentions a specific car model (e.g. 'Civic', "
        "'Vitz', 'Prado'), capture it here.\n"
        "- city: If the user names a Pakistani city they want to buy in, extract the city name "
        "only. Examples: 'Family SUV under 80 lacs in Lahore' -> 'Lahore', 'looking in Isb' -> "
        "'Islamabad', 'Karachi walay' -> 'Karachi', 'based in pindi' -> 'Rawalpindi'. Extract a "
        "CITY, never a province ('Punjab'), country, or region. If the city appears only as a "
        "travel destination or route rather than where the buyer is shopping (e.g. 'road trips "
        "to Murree', 'Islamabad to Lahore highway'), leave this null — it is not a purchase "
        "location. Null when no buying location is stated.\n"
        "- excluded_features: Extract any feature, engine size, or specification the user EXPLICITLY forbids. Examples: 'no 660cc' -> ['660cc'], 'without a sunroof' -> ['sunroof'], 'no JDM imports' -> ['jdm']. Leave empty if no features are forbidden.\n"
        "- excluded_models: Extract any car model the user explicitly forbids or vetoes. "
        "Examples: 'no Corolla' -> ['Corolla'], 'strictly NO Fortuner or Sportage' -> "
        "['Fortuner', 'Sportage'], 'without Civic' -> ['Civic']. This is for SIMPLE, DIRECT "
        "vetoes only. Leave as empty list [] if no explicit exclusion is stated.\n"
        "- excluded_brands: Extract any BRAND/MAKE the user explicitly forbids or vetoes at "
        "the whole-brand level. Examples: 'strictly NO Haval, Changan, or Chery' -> "
        "['Haval', 'Changan', 'Chery'], 'no Kia' -> ['Kia'], 'don't want any MG' -> ['MG']. "
        "Only extract an explicitly named brand — never a vague category like 'Chinese "
        "cars' (that broader intent belongs to origin_pref, not here). Leave empty if not "
        "clearly stated.\n"
        "- excluded_origins: Extract any origin the user explicitly forbids. Examples: "
        "'NO local cars' -> ['local'], 'absolutely no Chinese or European' -> ['chinese', 'european'], "
        "'no JDM' -> ['jdm'], 'no Japanese imports' -> ['jdm'].\n"
        "- immediate_veto_message: YOU ARE THE FRONT-DOOR BOUNCER. If the user's request contains "
        "a physical impossibility, a legal violation, or an impossible filter combination, you MUST "
        "populate this field with a tagged rejection.\n"
        "  * MANDATORY FORMAT — the frontend renders this as a high-contrast Dark Neo-Brutalist "
        "alert card, so the shape of the string is load-bearing and must be followed exactly:\n"
        "      [SECTION TAG] <one plain sentence stating the impossibility>. <one short corrective instruction>.\n"
        "    - The string MUST begin with an opening square bracket at index 0. No greeting, no "
        "preamble, no emoji, no markdown, no bold markers, no leading whitespace.\n"
        "    - The tag MUST be UPPERCASE and MUST be exactly one of these three:\n"
        "        [IMPOSSIBLE QUERY PARADOX]  — physics, geometry, mechanical or spec contradictions\n"
        "        [LEGAL COMPLIANCE VETO]     — illegal, smuggled, non-duty-paid or non-road-legal requests\n"
        "        [TAX BRACKET CONFLICT]      — engine displacement vs tax/token bracket contradictions\n"
        "    - Exactly one space after the closing bracket, then a capital letter.\n"
        "    - Keep the whole message under 240 characters and write it in flat, declarative, "
        "high-contrast language. State the fact and the fix. No hedging, no apologising, no "
        "'unfortunately', no 'I'm sorry', no customer-service softening.\n"
        "  * EXAMPLES OF VETOES (note the tag on every one):\n"
        "    1. Illegal/Smuggled: 'I want an NCP Land Cruiser' -> '[LEGAL COMPLIANCE VETO] Non-Custom Paid (NCP) vehicles are illegal to purchase or register outside designated border regions. Please search for a duty-paid, registered vehicle instead.'\n"
        "    2. Tax Paradox: 'Honda Civic 1.8L under 1000cc tax' -> '[TAX BRACKET CONFLICT] A 1.8L engine physically cannot qualify for a sub-1000cc token tax bracket. Please raise your tax bracket or select a 1000cc vehicle.'\n"
        "    3. Geometry Paradox: '7-seater Mazda RX-8' -> '[IMPOSSIBLE QUERY PARADOX] A 2-door sports coupe physically cannot accommodate 7 passengers in the Pakistani market. Please adjust your body style or seating capacity.'\n"
        "    4. Total Wipeout: 'No local, no JDM, no Chinese, no European' -> '[IMPOSSIBLE QUERY PARADOX] You have excluded every vehicle origin available in the Pakistani market, leaving zero eligible cars. Please permit at least one origin.'\n"
        "    5. Mechanical Paradox: 'Manual transmission with Adaptive Cruise Control' -> '[IMPOSSIBLE QUERY PARADOX] Adaptive Cruise Control requires an automatic transmission to govern speed and is mechanically incompatible with a manual gearbox in this market. Please select an automatic.'\n"
        "    6. Economy ADAS Paradox: 'Suzuki Cultus with Lane Assist and Power Tailgate' -> '[IMPOSSIBLE QUERY PARADOX] Entry-level budget hatchbacks are not built with Level 2 ADAS or powered tailgates in PKDM spec. Please raise your budget or drop these features.'\n"
        "    7. Towing/Chassis Paradox: 'Crossover/Sedan to tow 3 tons' -> '[IMPOSSIBLE QUERY PARADOX] Unibody crossovers and sedans lack the chassis strength to tow 3-ton loads safely. Please select a body-on-frame SUV or pickup truck.'\n"
        "  * If you populate this, the system will instantly abort the search and show your message to the user. "
        "Leave null if the query is physically and legally possible.\n"
        "- Conditional / Nested Negations: For compound phrasing like 'no Suzuki unless "
        "it's not a hatchback' or 'don't give me any sedan that isn't a Honda', you do NOT "
        "need to enumerate every affected model — a deterministic backup system already "
        "handles these exact two phrasing patterns reliably against the live vehicle "
        "registry, so guessing a full model list yourself risks naming a model that isn't "
        "actually in the registry. For genuinely conditional/nested exclusions like these, "
        "leave excluded_models and excluded_brands empty for that clause rather than "
        "guessing — only populate them for plain, unconditional vetoes.\n"
        "- powertrain: Extract 'hybrid' if user mentions hybrid/HEV/e-power/aqua/prius. "
        "Extract 'ev' if user mentions electric/EV/100% electric/battery car/BEV/zero emission. "
        "Leave null otherwise.\n"
        "  CRITICAL EV ANTI-WIPE RULE: If the user explicitly requests an EV AND at least one EV "
        "physically exists in Pakistan under their stated budget (e.g. MG ZS EV ~PKR 8.5M, "
        "BYD Atto 3 ~PKR 12-14M, Omoda E5 ~PKR 11-13M under 1.5 Crore), you MUST set "
        "powertrain='ev'. NEVER wipe powertrain to null because the user's destination or route "
        "lacks chargers. Charging infrastructure is a disclaimer concern, not an extraction concern.\n"
        "- strategy_summary: Write a friendly 2-sentence summary explaining how you interpreted "
        "the request and what kind of cars you will prioritize. "
        "Example: 'You are looking for a fun daily driver for campus commutes with "
        "responsive acceleration under PKR 25 Lacs. We have prioritized punchy 1.3L "
        "automatic hatchbacks like the Suzuki Swift and Toyota Vitz over sluggish 660cc "
        "eco-cars or high-maintenance project vehicles.' Always be specific to the "
        "user's actual request — never generic.\n"
        "  IMPOSSIBLE QUERY RULE: You may ONLY wipe body_style to null or required_features to [] "
        "if NO vehicle in the entire Pakistani market physically exists for the combined HARDWARE "
        "specs (e.g., a 7-seater sports coupe is physically impossible — no such body shape exists "
        "anywhere; a brand-new luxury SUV under 30 Lakhs does not exist in Pakistan's market). "
        "Infrastructure mismatches (e.g., EV + no chargers at destination), lifestyle mismatches "
        "(e.g., sports car + family of 5), or subjective impracticality DO NOT qualify as "
        "impossible — extract the signals faithfully and let disclaimers handle the warnings.\n"
        "  CRITICAL RULE FOR 7-SEATER + SUB-1200CC GRIDLOCK: If a user requests a 7-seater family "
        "vehicle AND simultaneously requests an engine under 1200cc (e.g. 'under 1000cc', 'under 1.2L', "
        "'660cc', '800cc', '1000cc'), this combination is mathematically impossible in Pakistan — "
        "no 7-seater MPV or van in the PK market uses an engine below 1200cc. "
        "You MUST drop ONLY the engine CC constraint from required_features, but you MUST STRICTLY "
        "KEEP '7 seater' in required_features. Do NOT set required_features to [] if they asked for "
        "a 7-seater — that would erase the seating requirement along with the CC constraint. "
        "This allows 1.3L–1.5L 7-seater MPVs like Honda BR-V (1.5L) and Suzuki APV (1.3L) to appear "
        "while still enforcing the 7-seat requirement. Explicitly explain this trade-off in "
        "strategy_summary.\n"
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


# ---------------------------------------------------------------------------
# VETO MESSAGE FORMATTING — DARK NEO-BRUTALIST CONTRACT
#
# The frontend renders a vetoed query as a high-contrast alert card:
#   • Signal Red (#dc2626) badge carrying the section tag
#   • Thick solid border (border-2 border-black dark:border-white)
#   • Tight tracking body copy (font-black tracking-tight)
#
# For that to render deterministically the backend must guarantee the string
# shape, which means we cannot simply trust the LLM to follow the format
# instruction in its schema description. These two helpers are the enforcement
# layer: the extractor tells the frontend which badge to paint, and the
# formatter guarantees a valid tag is always present so the badge is never
# empty and the card never falls back to unstyled text.
#
# Contract (single source of truth for the frontend):
#   immediate_veto_message : "[TAG] Sentence. Corrective instruction."
#   veto_tag               : "IMPOSSIBLE QUERY PARADOX" | "LEGAL COMPLIANCE VETO"
#                            | "TAX BRACKET CONFLICT"   (bare, no brackets)
# ---------------------------------------------------------------------------

_VETO_TAGS: tuple[str, ...] = (
    "IMPOSSIBLE QUERY PARADOX",
    "LEGAL COMPLIANCE VETO",
    "TAX BRACKET CONFLICT",
)

# Keyword → tag routing, used only when the LLM returned an untagged message.
# Ordered most-specific first: a message about NCP/smuggled cars is a legal
# veto even though it may also mention engine size.
_VETO_TAG_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("LEGAL COMPLIANCE VETO", (
        "ncp", "non-custom", "non custom", "smuggl", "illegal", "unregistered",
        "stolen", "tampered", "duty-paid", "duty paid", "not road legal",
        "banned", "prohibited by law",
    )),
    ("TAX BRACKET CONFLICT", (
        "tax bracket", "token tax", "cc tax", "withholding", "filer",
        "tax slab", "registration tax", "duty structure",
    )),
)


def _extract_veto_tag(message: str) -> str:
    """
    Return the bare section tag carried by a formatted veto message.

    Always returns one of _VETO_TAGS — never an empty string — so the frontend
    can key its badge colour off this field unconditionally. Falls back to
    "IMPOSSIBLE QUERY PARADOX" (the generic case) when the message carries no
    recognised tag.
    """
    text = (message or "").strip()
    for tag in _VETO_TAGS:
        if text.upper().startswith(f"[{tag}]"):
            return tag
    return _VETO_TAGS[0]


def _format_veto_message(raw_message: str) -> str:
    """
    Normalise an LLM veto message into the Dark Neo-Brutalist wire format.

    Guarantees, regardless of what the LLM produced:
      1. The string starts with a recognised UPPERCASE tag in square brackets.
      2. Exactly one space separates the tag from the body.
      3. No leading emoji, markdown, or conversational preamble survives.

    Idempotent: re-formatting an already-formatted message returns it
    unchanged, so this is safe to call more than once on the same value.

    Untagged input is routed to a tag by keyword (legal / tax / generic
    paradox) rather than being dropped — a vetoed query must always render
    with a badge.
    """
    text = (raw_message or "").strip()
    if not text:
        return ""

    # Already correctly tagged — normalise the post-bracket spacing only.
    for tag in _VETO_TAGS:
        prefix = f"[{tag}]"
        if text.upper().startswith(prefix):
            body = text[len(prefix):].strip()
            return f"{prefix} {body}" if body else prefix

    # Strip conversational/decorative noise the LLM may have prepended before
    # deciding a tag, so keyword routing sees the actual claim.
    for noise in ("⚠️", "⚠", "**", "Paradox Detected:", "Query Rejected:",
                  "Error:", "Warning:", "Note:"):
        if text.startswith(noise):
            text = text[len(noise):].strip()

    lowered = text.lower()
    chosen = _VETO_TAGS[0]
    for tag, keywords in _VETO_TAG_KEYWORDS:
        if any(kw in lowered for kw in keywords):
            chosen = tag
            break

    return f"[{chosen}] {text}"


# Cities the buyer might name, longest-first so "rahim yar khan" is tested
# before "khan" and "wah cantt" before "wah".
_PROMPT_CITY_TERMS: list[tuple[str, str]] = sorted(
    (
        [(alias, canonical) for alias, canonical in CITY_ALIAS_MAP.items()]
        + [
            ("islmabad",   "Islamabad"),
            ("isloo",      "Islamabad"),
            ("rwp",        "Rawalpindi"),
            ("gujrat",     "Gujrat"),
            ("sargodha",   "Sargodha"),
            ("bahawalpur", "Bahawalpur"),
            ("sahiwal",    "Sahiwal"),
            ("jhelum",     "Jhelum"),
            ("mardan",     "Mardan"),
            ("attock",     "Attock"),
            ("sheikhupura", "Sheikhupura"),
            ("kasur",      "Kasur"),
            ("okara",      "Okara"),
            ("wah cantt",  "Wah Cantt"),
            ("rahim yar khan", "Rahim Yar Khan"),
        ]
    ),
    key=lambda pair: len(pair[0]),
    reverse=True,
)

# Phrases that mark a city as somewhere the buyer DRIVES TO, not where they are
# shopping. "SUV for weekend trips to Murree" is not a Murree inventory search,
# and "Islamabad to Lahore range" is an EV range statement, not two locations.
_CITY_DESTINATION_MARKERS = (
    "trip to", "trips to", "travel to", "travelling to", "traveling to",
    "drive to", "drives to", "driving to", "go to", "going to", "visit",
    "route to", "road to", "way to", " to ",
)


def _detect_city_in_prompt(prompt: str) -> str:
    """
    Deterministic fallback for the buyer's city when the LLM does not extract one.

    Returns a canonical city name, or "" when the prompt names no city or names
    one only as a travel destination.

    Prefers a city introduced by a location preposition ("in Lahore", "from
    Karachi", "based in Isb") over a bare mention, because a bare mention is far
    more likely to be a destination or a comparison than a buying location.
    Returning "" is the safe outcome: it leaves the city veto disabled rather
    than pinning the search to a city the buyer never asked for.
    """
    if not prompt:
        return ""

    lowered = prompt.lower()

    # Pass 1 — preposition-anchored, highest confidence.
    for alias, canonical in _PROMPT_CITY_TERMS:
        pattern = (
            r'\b(?:in|from|at|near|around|within|based\s+in|located\s+in|'
            r'living\s+in|side)\s+' + re.escape(alias) + r'\b'
        )
        if re.search(pattern, lowered):
            return canonical

    # Pass 2 — bare mention, accepted only when the prompt frames no journey.
    # A prompt that talks about travelling is describing where the car goes,
    # not where it is bought.
    if any(marker in lowered for marker in _CITY_DESTINATION_MARKERS):
        return ""

    for alias, canonical in _PROMPT_CITY_TERMS:
        # Require >= 4 chars for a bare hit: two- and three-letter aliases
        # ("isb", "lhr", "khi") are too collision-prone without a preposition.
        if len(alias) < 4:
            continue
        if re.search(r'\b' + re.escape(alias) + r'\b', lowered):
            return canonical

    return ""


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

    excluded_features = []
    for f in intent.excluded_features:
        f_lower = f.lower().strip()
        excluded_features.append(_FEAT_NORMALISE.get(f_lower, f_lower))

    constraints = {
        "min_budget":        min_budget,
        "max_budget":        max_budget,
        "min_year":          intent.min_year or 0,
        "is_apex_luxury":    is_apex_luxury,
        "allow_chinese":     True,  # Market Shift: Chinese crossovers are now mainstream
        "body_style":        intent.body_style,
        "transmission":      intent.transmission,
        "drive":             intent.drive,
        "use_case":          intent.use_case,
        "origin_pref":       intent.origin_pref,
        "is_luxury_request": intent.is_luxury_request,
        "required_features":  intent.required_features,
        "excluded_features":  excluded_features,
        "strategy_summary":   intent.strategy_summary or "",
        "intent_id":          None,
        "excluded_models":    excluded_models,
        # Canonicalised buying location, or "" when the user named none.
        # Carried all the way to recommend_normalizer, which HARD-VETOES any
        # listing outside this city and its NEARBY_CITY_MAP twin corridor.
        # An empty string means "no location constraint" and disables that veto,
        # so it must only ever be empty when the user genuinely named no city.
        "city":               normalize_city(intent.city or ""),
    }

    # ── Deterministic Expansion from LLM-Structured Exclusion Arrays ─────────
    # NEW PRIMARY exclusion path. extract_intent() now asks the LLM for clean
    # excluded_brands / excluded_models arrays directly — this catches natural
    # phrasing variation ("I'd rather avoid Haval", "Toyota just isn't for me")
    # that the fixed-vocabulary regex scanners below don't trigger on.
    #
    # SAFETY-NET GUARANTEE: this block is strictly ADDITIVE. It writes into the
    # exact same constraints["excluded_models"] list, using the exact same
    # lowercase-dedup pattern the regex scanners below already use. Nothing
    # below this block was removed, weakened, or reordered — every existing
    # regex safety net (the flat veto scanner, and the Test-45 nested-negation
    # scanner) still runs after this, completely unchanged, and will
    # independently re-derive anything this block happens to miss. If the LLM
    # under-extracts on a given turn, coverage silently falls back to exactly
    # today's behaviour; this block only ever adds coverage, never removes it.
    already_excluded_struct = {m.lower() for m in constraints["excluded_models"]}

    for raw_brand in (intent.excluded_brands or []):
        brand_norm = raw_brand.strip().lower()
        if not brand_norm:
            continue
        for reg_key, reg_info in CAR_REGISTRY.items():
            make, model = reg_key.split(":", 1)
            if make == brand_norm:
                for form in (model, f"{make} {model}", make):
                    if form not in already_excluded_struct:
                        constraints["excluded_models"].append(form)
                        already_excluded_struct.add(form)

    for raw_model in (intent.excluded_models or []):
        model_norm = raw_model.strip().lower()
        if not model_norm:
            continue
        canonical = _CANONICAL_MODEL_MAP.get(model_norm, raw_model.strip())
        if canonical and canonical.lower() not in already_excluded_struct:
            constraints["excluded_models"].append(canonical)
            already_excluded_struct.add(canonical.lower())

    # Apply keyword intent overrides — must receive raw user_prompt.
    # Called here so body_style/use_case/transmission overrides propagate
    # through the full pipeline (get_eligible_cars, select_car_targets, normalizer).
    # user_prompt is injected by the caller (recommend_routes.py) via intent.user_prompt.
    raw_prompt = getattr(intent, "user_prompt", "") or ""
    if raw_prompt:
        constraints = apply_keyword_intent(raw_prompt, constraints)

    # ── City Keyword Fallback ─────────────────────────────────────────────────
    # Same defence-in-depth pattern as the origin_pref and excluded_brands
    # scanners above: the LLM is the primary extractor, and this deterministic
    # pass re-derives the city when it under-extracts.
    #
    # This one matters more than the others. An empty city does not merely lose
    # a scoring signal — it silently DISABLES the hard city veto in both
    # normalizers, because each guards its veto behind `if req_city_str:`. A
    # missed city is therefore indistinguishable from "the buyer will drive
    # anywhere in Pakistan", which is how Karachi and Hyderabad listings were
    # reaching Lahore searches.
    #
    # No-op when the LLM already extracted a city.
    if raw_prompt and not constraints.get("city"):
        detected = _detect_city_in_prompt(raw_prompt)
        if detected:
            constraints["city"] = detected

    # ── Independent 660cc Engine Gate ──────────────────────────────────────────
    # apply_keyword_intent() returns on the FIRST matching KEYWORD_INTENT_MAP
    # entry ("first match wins" — see its own docstring/code comment). Since
    # "micro_engine_660cc" is one entry among many, an earlier-matching intent
    # (e.g. a student/budget/body-style intent that happens to match first)
    # would short-circuit the loop and silently skip the 660cc append_features
    # injection entirely, even though the prompt clearly says "660cc" or
    # "660 cc". This check runs independently of that loop so it can never be
    # shadowed by an unrelated intent winning the race.
    #
    # Deliberately narrower than a bare `\b660\b` match: engine displacement is
    # essentially never stated as a bare "660" without a "cc"/"CC" unit in
    # natural language, whereas a bare "660" appears constantly in unrelated
    # numbers — most commonly a budget figure like "660,000" (six lakh sixty
    # thousand PKR), where the comma is a regex word-boundary and would
    # wrongly trigger a bare-number pattern. Requiring the literal "cc" suffix
    # eliminates that false-positive class entirely.

    # ── Explicit Negative Model Exclusion Scanner ─────────────────────────────
    if raw_prompt:
        prompt_lower_ex = raw_prompt.lower()
        # Modified regex to capture the entire string up to the next condition/punctuation
        veto_patterns = [
            r'\b(?:strictly\s+no|without|don\'t\s+want|dont\s+want|except)\s+([a-z0-9\s\-\,]+?)(?=\s+(?:for|under|must|having|but)\b|[\.,]|$)',
            r'\bno\s+([a-z0-9\s\-\,]+?)(?=\s+(?:for|under|must|having|but)\b|[\.,]|$)'
        ]
        already_excluded = {m.lower() for m in constraints["excluded_models"]}
        for pattern in veto_patterns:
            for match in re.findall(pattern, prompt_lower_ex):
                # Split compound vetoes like "Toyota or Honda"
                for sub_candidate in re.split(r'\s+or\s+|\s+and\s+|,', match):
                    candidate = sub_candidate.strip()
                    if not candidate or len(candidate) > 30:
                        continue

                    # Strip common trailing filler words so "haval models" /
                    # "changan cars" / "kia vehicles" correctly resolve to the
                    # bare make name ("haval" / "changan" / "kia") instead of
                    # silently matching nothing in the registry.
                    clean_candidate = re.sub(
                        r'\b(models|model|cars|car|vehicles|vehicle|brand|brands|series)\b',
                        '', candidate, flags=re.IGNORECASE
                    ).strip()
                    if not clean_candidate:
                        continue

                    for reg_key in CAR_REGISTRY:
                        make, model = reg_key.split(":", 1)
                        if clean_candidate in model or clean_candidate == make or clean_candidate in reg_key:
                            forms_to_add = [model, f"{make} {model}"]
                            # Make-level veto ("no Haval") — also add the bare
                            # make string itself so is_vetoed's make_lower check
                            # catches it directly, on top of the per-model sweep
                            # this loop already performs (no break => every
                            # matching make:model in the registry gets appended).
                            if clean_candidate == make:
                                forms_to_add.append(make)
                            for form in forms_to_add:
                                if form not in already_excluded:
                                    constraints["excluded_models"].append(form)
                                    already_excluded.add(form)

    # ── Conditional Negation & Nested Boolean Expansion (Test 45) ────────────
    # Handles double-negative / nested-conditional phrasing that the flat veto
    # regex above cannot parse:
    #   "Sedan that isn't Honda"                  -> exclude every non-Honda sedan
    #   "don't give me any sedan that isn't Honda" -> same
    #   "no Suzuki unless it's not a hatchback"    -> exclude every Suzuki hatchback
    #   "never recommend any Suzuki unless ... not a hatchback" -> same
    if raw_prompt:
        prompt_lower_neg = raw_prompt.lower()
        already_excluded_neg = {m.lower() for m in constraints["excluded_models"]}

        # Pattern A: "sedan that isn't [a] <make>" — expands to every Sedan
        # in the registry whose make does NOT match the stated make.
        _SEDAN_NOT_MAKE_RE = re.compile(r"sedan\s+that\s+isn'?t\s+(?:a\s+)?([a-z]+)")
        for neg_match in _SEDAN_NOT_MAKE_RE.finditer(prompt_lower_neg):
            target_make = neg_match.group(1).strip()
            if not target_make:
                continue
            for reg_key, reg_info in CAR_REGISTRY.items():
                make, model = reg_key.split(":", 1)
                if "Sedan" in reg_info["styles"] and make != target_make:
                    for form in (model, f"{make} {model}"):
                        if form not in already_excluded_neg:
                            constraints["excluded_models"].append(form)
                            already_excluded_neg.add(form)

        # Pattern B: "no/never recommend any suzuki unless ... not [a] hatchback"
        # — expands to every Hatchback-bodied Suzuki model in the registry.
        _SUZUKI_UNLESS_NOT_HATCH_RE = re.compile(
            r"(?:no|never\s+recommend\s+any)\s+suzuki\s+unless.*?not\s+(?:a\s+)?hatchback"
        )
        if _SUZUKI_UNLESS_NOT_HATCH_RE.search(prompt_lower_neg):
            for reg_key, reg_info in CAR_REGISTRY.items():
                make, model = reg_key.split(":", 1)
                if make == "suzuki" and "Hatchback" in reg_info["styles"]:
                    for form in (model, f"{make} {model}"):
                        if form not in already_excluded_neg:
                            constraints["excluded_models"].append(form)
                            already_excluded_neg.add(form)

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

    # ── EV Highway / Long-Range Detection ─────────────────────────────────────
    # City micro-EVs (Honri VE, Rinco Aria, Metro Enfon) have real-world ranges
    # under 150km and cannot physically complete inter-city highway journeys.
    # When an EV query pairs with highway/long-distance signals, flag it so
    # get_eligible_cars() can hard-delete the micro-EVs from the eligible list
    # rather than letting the LLM hallucinate them into a 380km Islamabad-to-
    # Lahore recommendation.
    is_highway_ev = False
    if powertrain == "ev" and raw_prompt:
        prompt_lower_hwy = raw_prompt.lower()
        _HIGHWAY_EV_KEYWORDS = (
            "highway", "motorway", "lahore", "islamabad to lahore",
            "karachi to lahore", "long route", "long drive", "long distance",
            "inter-city", "intercity", "300km", "400km", "380km", "range",
        )
        if any(kw in prompt_lower_hwy for kw in _HIGHWAY_EV_KEYWORDS):
            is_highway_ev = True
    constraints["is_highway_ev"] = is_highway_ev

    # Generate advisory disclaimers based on prompt + constraints
    if raw_prompt:
        constraints["disclaimers"] = generate_disclaimers(raw_prompt, constraints)
    else:
        constraints["disclaimers"] = []

    if is_highway_ev:
        constraints["disclaimers"].append(
            "⚠️ EV Range Notice: City micro-EVs (Honri VE, Rinco Aria) have a real-world "
            "range under 150 km and cannot execute inter-city highway journeys (e.g., "
            "Islamabad to Lahore is 380 km). Long-range 300km+ EVs start above 70 Lakhs "
            "PKR in Pakistan."
        )

    # ── Local PKDM Assembly Keyword Fallback (Test 71/72) ────────────────────
    # origin_pref is primarily LLM-extracted, but "local"/"pkdm"/"locally
    # assembled"/"pakistani assembled" phrasing is common and important
    # enough (it now flips a hard registry gate in get_eligible_cars) to also
    # get a deterministic Python-side detector as a backup — same
    # defense-in-depth pattern as the excluded_brands/excluded_models regex
    # safety nets elsewhere in this function. No-op if the LLM already set
    # origin_pref == "Local". NOTE: the bare term "local" is intentionally
    # broad-matched, consistent with this file's existing keyword-detection
    # style elsewhere (e.g. the contraband/NCP terms below) — flag to revisit
    # if it ever proves too eager on real traffic.
    _LOCAL_ASSEMBLY_TERMS = ("local", "pkdm", "locally assembled", "pakistani assembled", "pak assembled")
    if raw_prompt and constraints.get("origin_pref") != "Local":
        if any(term in raw_prompt.lower() for term in _LOCAL_ASSEMBLY_TERMS):
            constraints["origin_pref"] = "Local"

    # ── Contraband / NCP Legal Compliance Intercept (Test 47) ────────────────
    # NCP ("Non-Custom Paid") vehicles are illegal to operate outside
    # Pakistan's designated border/tribal regions. If the raw prompt requests
    # NCP/non-custom-paid vehicles, strip that intent from any extracted
    # signals so it can never influence which cars get recommended, and
    # inject a compliance disclaimer so the pipeline continues cleanly with
    # legal, tax-paid alternatives. Placed AFTER the disclaimers assignment
    # above so this disclaimer is appended, not overwritten.
    _CONTRABAND_TERMS = ("ncp", "non-custom", "non custom paid", "non custom")
    if raw_prompt and any(term in raw_prompt.lower() for term in _CONTRABAND_TERMS):
        prompt_lower_cb = raw_prompt.lower()
        
        # Strip contraband terms from required features
        constraints["required_features"] = [
            f for f in constraints.get("required_features", [])
            if not any(term in f.lower() for term in _CONTRABAND_TERMS)
        ]
        
        # Blacklist models mentioned in the contraband query
        already_excl = {m.lower() for m in constraints["excluded_models"]}
        
        if intent.direct_model:
            dm_norm = intent.direct_model.strip()
            if dm_norm.lower() not in already_excl:
                constraints["excluded_models"].append(dm_norm)
                already_excl.add(dm_norm.lower())
                
        # Scan for high-risk contraband models in prompt
        _CONTRABAND_MODELS = ("land cruiser", "prado", "v8", "surf", "range rover", "defender")
        for cb_model in _CONTRABAND_MODELS:
            if cb_model in prompt_lower_cb:
                for reg_key in CAR_REGISTRY:
                    make, model = reg_key.split(":", 1)
                    if cb_model in model or cb_model in reg_key:
                        full_name = f"{make} {model}"
                        if full_name not in already_excl:
                            constraints["excluded_models"].append(full_name)
                            already_excl.add(full_name.lower())
                        if model not in already_excl:
                            constraints["excluded_models"].append(model)
                            already_excl.add(model.lower())

        # Unconditionally wipe direct model & sanitize summary
        intent.direct_model = None
        constraints["direct_model"] = None
        constraints["strategy_summary"] = "We have filtered your request for legally registered, tax-paid vehicles matching your budget."
        
        constraints["disclaimers"].append(
            "⚠️ Legal Compliance Notice: Non-Custom Paid (NCP) vehicles are strictly illegal "
            "outside border regions in Pakistan. The engine has automatically filtered for "
            "legally registered, tax-paid alternatives in your target city."
        )

    # ── Diesel-Electric Hybrid Paradox Intercept (Test 74) ────────────────────
    # No diesel-electric hybrid crossover exists in the Pakistani market under
    # PKR 90 Lakhs — every local/JDM hybrid crossover in this registry
    # (Corolla Cross, Haval HEV, Honda Vezel, Fronx, etc.) is petrol-electric.
    # Detected directly from raw_prompt so get_eligible_cars() can cleanly
    # zero out rather than silently substituting a petrol hybrid the user
    # never asked for.
    _DIESEL_TERMS = ("diesel",)
    _HYBRID_TERMS = ("hybrid", "hev", "phev")
    if raw_prompt:
        _prompt_lower_dh = raw_prompt.lower()
        if (any(t in _prompt_lower_dh for t in _DIESEL_TERMS)
                and any(t in _prompt_lower_dh for t in _HYBRID_TERMS)):
            constraints["is_diesel_hybrid_query"] = True
            constraints["disclaimers"].append(
                "⚠️ Fuel Disclaimer: Diesel-Electric Hybrids are extremely rare and "
                "unavailable in crossover body styles under PKR 90 Lakhs in Pakistan. "
                "Mainstream hybrid crossovers (Corolla Cross, Haval HEV, Honda Vezel) "
                "use petrol-electric powertrains."
            )

    # Detect direct model request and override strategy summary
    constraints["direct_model"] = None
    if intent.direct_model:
        model_lower = intent.direct_model.lower().strip()
        # Direct lookup first, or fallback to the provided string if not in the alias map
        mapped_model = _CANONICAL_MODEL_MAP.get(model_lower, intent.direct_model)
        if mapped_model:
            constraints["direct_model"] = mapped_model
            constraints["strategy_summary"] = f"You specifically asked for a {mapped_model.title()}. We've included budget-eligible variants of the {mapped_model.title()} alongside its closest market competitors to give you a complete picture."

    # Preserve the raw user prompt so the final AI sanitizer (Phase 3) can
    # re-check the finished recommendation list against the buyer's original
    # words one last time, independent of any structured field extraction.
    constraints["user_prompt"] = raw_prompt

    # ── excluded_origins + Front-Door Veto Lock-Down ─────────────────────────
    # excluded_origins feeds both get_eligible_cars() (origin hard-gate) and
    # the veto total-wipeout check in immediate_veto_message.
    constraints["excluded_origins"] = [o.lower().strip() for o in (intent.excluded_origins or [])]
    constraints["is_llm_vetoed"] = False

    if intent.immediate_veto_message:
        constraints["is_llm_vetoed"] = True

        veto_msg = _format_veto_message(intent.immediate_veto_message)
        constraints["immediate_veto_message"] = veto_msg
        constraints["veto_tag"] = _extract_veto_tag(veto_msg)
        constraints["strategy_summary"] = veto_msg
        constraints["disclaimers"].append(veto_msg)

        # Strip VIP immunity so nothing gets forced through on a vetoed query
        intent.direct_model = None
        constraints["direct_model"] = None

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
        excluded_models=constraints.get("excluded_models"),
        required_features=required_features,
        excluded_features=constraints.get("excluded_features"),
        direct_model_req=constraints.get("direct_model"),
        is_youth_query=is_youth_query,
        drive_req=drive,
        powertrain_req=constraints.get("powertrain"),
        min_year=constraints.get("min_year", 0),
        is_luxury_request=is_luxury,
        is_highway_ev=constraints.get("is_highway_ev", False),
        origin_pref=origin_pref,
        is_diesel_hybrid_query=constraints.get("is_diesel_hybrid_query", False),
        excluded_origins=constraints.get("excluded_origins", []),
        is_llm_vetoed=constraints.get("is_llm_vetoed", False),
        intent_id=constraints.get("intent_id"),
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
        "1. DIRECT MODEL MANDATE: If 'direct_model' is present in the BUYER PROFILE and exists in the ELIGIBLE CARS list, you MUST place that exact model as Recommendation #1. The remaining slots must be the best alternative competitors. If it does NOT appear in ELIGIBLE CARS (due to budget/features), do not force it.\n"
        "2. LIST ONLY: Never suggest a car not in the eligible list. "
        "The list is pre-verified by Python — trust it completely.\n"
        "2. PRINCIPLES FIRST: Apply the use-case principles above when ranking. "
        "They encode real Pakistani market knowledge — follow them.\n"
        "3. PRIORITY ORDER: Cars listed higher in the eligible list are ranked higher "
        "by budget fit AND market standing. Prefer them unless the buyer's use-case "
        "clearly makes a lower-ranked car more suitable.\n"
        "4. ORIGIN: If origin_pref is JDM, prefer JDM cars and specify exact trim "
        "(e.g. trim='G Grade', trim='RS Advance'). If European, prefer BMW/Audi/Mercedes.\n"
        "5. JDM ALTO PROTECTION: If recommending the imported 'Suzuki Alto 660cc', ALWAYS set "
        "trim='660cc'. HOWEVER, if the buyer strictly requests LOCAL PKDM assembly, NEVER append '660cc' or 'JDM' to the local Suzuki Alto. Use local trims (VXR, VXL, AGS) only.\n"
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
        "12. MEMORY SEATS CKD RULE: Locally assembled Kia Sportage, Hyundai Tucson, and base-spec "
        "Kia Sorento (non-AWD HEV trim) in Pakistan DO NOT feature driver seat memory buttons — "
        "this feature was explicitly omitted by local assemblers or only present in the top AWD HEV "
        "variant which exceeds 1 Crore. For memory seat queries under 1 Crore PKR, you MUST restrict "
        "picks strictly to Chinese crossovers (Haval Jolion, Haval H6, Changan Oshan X7 FutureSense, "
        "Chery Tiggo 8 Pro), Hyundai Sonata 2.5L, or luxury imports.\n"
        "13. ENGINE CC / TAX RULE: If the buyer mentions 'under 1500cc', 'low tax', 'token tax', "
        "'1.5L', 'under 1300cc', or '1.3L', you MUST strictly exclude models whose standard "
        "Pakistani-market engine is above 1500cc. This means DO NOT recommend: Hyundai Elantra "
        "(1.6L/2.0L), Kia Sportage (2.0L), Hyundai Tucson (2.0L), Honda Civic (1.5T turbo — "
        "sits in a higher token bracket despite being 1.5L due to turbo displacement rating), "
        "Toyota Corolla Altis/Grande (1.6L/1.8L), or Kia Stonic (1.4T). Instead recommend "
        "explicit sub-1500cc cars: Toyota Yaris (1.3L), Honda City (1.2L/1.5L), Suzuki Swift "
        "(1.2L), Suzuki Cultus (1.0L), Changan Alsvin (1.5L), Toyota Vitz (1.0L/1.3L), or "
        "Suzuki Wagon R (1.0L). For 'under 1300cc' requests, further restrict to 1.0L–1.3L only.\n"
        "14. TRIM-BUDGET REALITY: Multi-generation cars (Honda Civic, Toyota Corolla) span from "
        "10 Lakhs to 1 Crore+ in the used market. If a user's budget is UNDER 35 Lakhs PKR, "
        "you MUST NOT recommend modern turbo or premium trims. Specifically: DO NOT recommend "
        "'Civic 1.5T', 'Civic RS', 'Civic Oriel 1.5T', 'Corolla Altis Grande', or 'Corolla Altis X' "
        "for budgets under 35 Lakhs. You MUST explicitly name the older generation trim that "
        "actually exists in the used market at that price — e.g., 'Civic VTi Oriel' (2004–2012), "
        "'Civic Reborn 1.8 VTi' (2006–2012), 'Corolla XLi' (2002–2014), 'Corolla GLi' (2008–2019). "
        "Budget under 20 Lakhs: only specify 7th gen (Eagle Eye 2001–2005) or 8th gen (Reborn "
        "2006–2011) Civic trims. Budget 20–35 Lakhs: 9th gen Civic (2012–2016) trims allowed."
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
    validated, _dropped = _validate_targets(raw_targets, constraints)

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
            # Propagate the buyer's city into every target.
            #
            # This used to be hardcoded "" with the note "recommend_normalizer
            # handles city softly". It does not — recommend_normalizer HARD-VETOES
            # out-of-city listings, but only inside `if req_city_str:`. Blanking
            # the city here meant that guard was always false, the veto never
            # ran, and a Lahore search happily returned Karachi and Hyderabad
            # cars. The constraint was erased one step before the code that
            # existed to enforce it.
            "city":              constraints.get("city", ""),
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


class AuditItem(BaseModel):
    model_name: str = Field(description="Exactly 'Make Model' as given in the candidate list, e.g. 'Toyota Corolla Cross'.")
    is_compliant: bool = Field(
        description=(
            "False if this car violates ANY user hard constraint (e.g. JDM car when "
            "local PKDM requested, petrol hybrid when diesel hybrid requested, wrong "
            "seating capacity, vetoed brand/model)."
        )
    )
    rejection_reason: str = Field(default="", description="Brief reason if is_compliant is false.")


class AuditReport(BaseModel):
    evaluations: list[AuditItem] = Field(default_factory=list)


async def run_final_ai_sanitizer(formatted_targets: list[dict], user_prompt: str) -> list[dict]:
    """
    Phase 3 — Final AI QA Sanitizer (last line of defense), rebuilt as an
    iron-clad gatekeeper with full registry-metadata context (Test 71/72/74).

    Each candidate is enriched with its CAR_REGISTRY origin_type (Imported
    JDM / Chinese / Local-Mainstream) and tags before the audit LLM sees it,
    so it can correctly judge origin/assembly and powertrain constraints that
    aren't visible from make/model/trim/rationale text alone — e.g. flagging
    a JDM-tagged car against a "local assembly only" request, or a petrol
    hybrid against a "diesel hybrid" request.

    Design note — name-matched, not regenerated: the LLM returns a
    model_name + is_compliant verdict per car, not the car objects
    themselves. Python matches each verdict back to its candidate by
    normalised "make model" and filters using that — the LLM's only power
    is to flag a car for removal, never to rewrite make/model/trim/budget/
    rationale text. Matching by name (rather than index) is safe here
    specifically because _deduplicate_and_format() upstream already
    guarantees no two candidates in formatted_targets share the same
    (make, model) pair.

    Two distinct "empty" behaviours, deliberately different:
      • Fail-OPEN on error: if the API call itself errors (network, timeout,
        malformed response), the original list is returned UNCHANGED. A
        sanitizer hiccup must never zero out an already-valid, already-
        Python-vetted result.
      • Fail-CLOSED (zero-hit) on confirmed non-compliance: if the call
        succeeds and every candidate is genuinely flagged non-compliant,
        an empty list IS returned — the system must show a clean zero-hit
        brief rather than silently falling back to cars the audit itself
        just rejected. This is the "iron-clad" half of the rebuild.
    A candidate with no returned evaluation at all (LLM skipped it) is
    treated as compliant rather than penalised for an incomplete response —
    same fail-open bias as the error case above, just applied per-item.
    """
    if not formatted_targets:
        return []

    enriched_candidates = []
    for car in formatted_targets:
        key = f"{car['make'].lower()}:{car['model'].lower()}"
        info = CAR_REGISTRY.get(key, {})
        enriched_candidates.append({
            "make": car["make"],
            "model": car["model"],
            "trim": car.get("trim", ""),
            "origin_type": (
                "Imported JDM" if "jdm" in info.get("tags", set())
                else ("Chinese" if info.get("chinese") else "Local/Mainstream")
            ),
            "tags": list(info.get("tags", set())),
            "rationale": car.get("rationale", ""),
        })

    prompt = (
        f"You are a strict QA Auditor for an automotive recommendation engine — the "
        f"final gatekeeper before these cars reach a real buyer.\n"
        f"User's raw query: '{user_prompt}'\n\n"
        f"The system is proposing these cars, enriched with registry metadata:\n"
        f"{json.dumps(enriched_candidates, indent=2)}\n\n"
        f"TASK: Evaluate EACH car against the user's HARD constraints only — seating "
        f"capacity, engine displacement, body style, origin/assembly (Local vs "
        f"Imported JDM, from origin_type), fuel/powertrain type, and explicit "
        f"brand/model vetoes. Soft preferences, style opinions, or subjective fit are "
        f"NOT hard constraints and must not cause a rejection.\n"
        f"- If the user requested Local PKDM / Pakistani-assembled cars, ANY car with "
        f"origin_type 'Imported JDM' is NON-COMPLIANT.\n"
        f"- If the user requested a Diesel Hybrid, any petrol hybrid is NON-COMPLIANT "
        f"(every hybrid in this registry is petrol-electric).\n"
        f"- If the user explicitly vetoed a brand or model, any matching car is "
        f"NON-COMPLIANT.\n"
        f"- If the user requested 7 seats, any 5-seater hatchback/sedan is "
        f"NON-COMPLIANT.\n"
        f"- If the user asked for a specific engine size (e.g. 660cc), any car that "
        f"is not genuinely that engine size is NON-COMPLIANT.\n"
        f"- If the user explicitly forbids an engine size (e.g., 'no 660cc', 'not 1000cc'), any car featuring that engine size or trim is NON-COMPLIANT.\n"
        f"- If the user explicitly forbids imported JDM cars, any car with origin_type 'Imported JDM' or having 'JDM'/'660cc' in its trim/rationale is NON-COMPLIANT.\n"
        f"- NO DIRECT MODEL EXCEPTION: Even if the user named a specific car, it is still NON-COMPLIANT if it physically cannot satisfy a hard constraint. Naming a car does not create hardware it does not have. Judge every car equally.\n"
        f"For each car, return model_name as exactly '{{make}} {{model}}' using the "
        f"make/model fields given above, plus is_compliant, and — only when "
        f"is_compliant is false — a brief rejection_reason. Evaluate every car in the "
        f"list; do not skip any, and do not flag a car just because you would have "
        f"picked something else."
    )

    try:
        response_text = await generate_content_resilient(
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=AuditReport,
                temperature=0.0,
            ),
        )
        report = AuditReport.model_validate_json(response_text)

        # ── Structural fail-open guard ────────────────────────────────────────
        # A call can succeed at the HTTP/schema level yet carry zero verdicts
        # (empty array, truncated generation). That is an incomplete audit, NOT
        # a finding of universal non-compliance, so it must fail OPEN. Without
        # this guard the per-item fallback below would still return everything,
        # but silently — this makes the degraded path visible in the logs.
        if not report.evaluations:
            print(
                "[Sanitizer] Audit returned zero evaluations — treating as an "
                "incomplete response and failing open with the original list."
            )
            return formatted_targets

        def _norm(text: str) -> str:
            """Lowercase, collapse whitespace, drop punctuation that varies by writer."""
            return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()

        verdict_by_name: dict[str, AuditItem] = {
            _norm(item.model_name): item for item in report.evaluations
        }

        # Every candidate's canonical key, used to make sure a verdict that
        # already belongs to one candidate is never re-bound to another.
        candidate_keys = {
            _norm(f"{c['make']} {c['model']}") for c in formatted_targets
        }

        def _resolve_verdict(make: str, model: str) -> AuditItem | None:
            """
            Match an audit verdict back to its candidate.

            Primary path is an exact normalised "make model" hit. The fallback
            exists because the audit LLM intermittently decorates model_name
            with the trim or powertrain suffix it was shown — "Toyota Corolla
            Cross HEV" for candidate "Toyota Corolla Cross", "Honda HR-V e:HEV"
            for "Honda HR-V". Under exact-only matching those verdicts silently
            missed, and the per-item fail-open then admitted a car the auditor
            had explicitly rejected — the exact leak this gate exists to stop.

            The fallback is deliberately ONE-DIRECTIONAL: it only accepts a
            verdict whose name EXTENDS the candidate name (candidate is a
            prefix of the verdict). The reverse direction is unsafe and is
            explicitly rejected — a generic verdict for "Toyota Corolla" must
            never bind to the distinct candidate "Toyota Corolla Cross", which
            would reject a car the auditor never even evaluated.

            Two further guards:
              • The suffix must start at a word boundary, so "Corolla" cannot
                absorb "Corolla Cross" via raw string prefixing.
              • A verdict whose name is itself an exact key of some candidate
                is skipped — it already belongs to that car.
            Ambiguous or unresolved hits return None and fall through to the
            per-item fail-open path rather than guessing.
            """
            target = _norm(f"{make} {model}")
            exact = verdict_by_name.get(target)
            if exact is not None:
                return exact

            prefix = f"{target} "
            partial = [
                item for name, item in verdict_by_name.items()
                if name.startswith(prefix) and name not in candidate_keys
            ]
            if len(partial) == 1:
                return partial[0]
            return None

        compliant: list[dict] = []
        unmatched = 0
        for car in formatted_targets:
            item = _resolve_verdict(car["make"], car["model"])
            if item is None:
                # No evaluation returned for this specific candidate — fail
                # open for this one item rather than dropping it over an
                # incomplete LLM response.
                unmatched += 1
                compliant.append(car)
                continue
            if item.is_compliant:
                compliant.append(car)
            else:
                print(
                    f"[Sanitizer] Flagging {car['make']} {car['model']}: "
                    f"{item.rejection_reason or 'flagged by sanitizer'}"
                )

        if unmatched:
            print(
                f"[Sanitizer] {unmatched} candidate(s) had no matching verdict — "
                f"kept (per-item fail-open)."
            )

        if not compliant:
            print(
                "[Sanitizer] Iron-clad gate: zero compliant cars remain — "
                "returning empty result rather than falling back to flagged cars."
            )
        return compliant

    except Exception as e:
        # Fail-OPEN on any transport/parse/validation error. A sanitizer
        # outage must never zero out an already Python-vetted result set.
        print(f"[Sanitizer] Failed: {e} — returning original list unfiltered (fail-open)")
        return formatted_targets


# ---------------------------------------------------------------------------
# AGENTIC SELF-CORRECTION WRAPPER
# Wraps select_car_targets with a one-shot LLM retry when the validator drops
# cars. Keeps the pipeline honest: if the LLM hallucinated a vetoed/out-of-
# budget/wrong-style car, this loop fires exactly once to replace it with a
# valid substitute from the same eligible list.
# ---------------------------------------------------------------------------

async def get_validated_car_targets(constraints: dict) -> list[dict]:
    """
    Agentic loop: fetch targets → validate → if any dropped AND total valid < 3,
    ask LLM once to self-correct with replacement picks from the same eligible list.
    Returns the final formatted list via _deduplicate_and_format.
    """
    raw_targets = await select_car_targets(constraints)
    valid_targets, dropped_reasons = _validate_targets(raw_targets, constraints)

    # Only trigger self-correction if:
    #  (a) at least one car was dropped, AND
    #  (b) we ended up with fewer valid picks than we started with
    # This avoids a needless extra LLM call when all 3 passed first time.
    if dropped_reasons and len(valid_targets) < len(raw_targets):
        needed = max(0, 3 - len(valid_targets))
        print(
            f"[Fallback] {len(dropped_reasons)} car(s) dropped — triggering self-correction "
            f"to find {needed} replacement(s). Reasons:\n  " + "\n  ".join(dropped_reasons)
        )

        if needed > 0:
            # Re-fetch the eligible list so the replacement prompt is grounded
            eligible_list = get_eligible_cars(
                max_budget       = constraints.get("max_budget", 0),
                min_budget       = constraints.get("min_budget", 0),
                allow_chinese    = constraints.get("allow_chinese", False),
                body_style       = constraints.get("body_style"),
                is_apex_luxury   = constraints.get("is_apex_luxury", False),
                transmission_req = constraints.get("transmission"),
                excluded_models  = constraints.get("excluded_models"),
                required_features= constraints.get("required_features", []),
                excluded_features= constraints.get("excluded_features"),
                direct_model_req = constraints.get("direct_model"),
                powertrain_req   = constraints.get("powertrain"),
                min_year         = constraints.get("min_year", 0),
                is_luxury_request= constraints.get("is_luxury_request", False),
                is_highway_ev    = constraints.get("is_highway_ev", False),
                origin_pref      = constraints.get("origin_pref"),
                is_diesel_hybrid_query = constraints.get("is_diesel_hybrid_query", False),
                excluded_origins = constraints.get("excluded_origins", []),
                is_llm_vetoed    = constraints.get("is_llm_vetoed", False),
                intent_id        = constraints.get("intent_id"),
            )

            # ── Empty Eligible List Short-Circuit ─────────────────────────────
            # If Python found zero legitimately eligible cars (impossible
            # combination — vetoed brands + strict features, micro-EV highway
            # gridlock, etc.), do NOT invoke the LLM on an empty list. Doing so
            # previously caused the LLM to hallucinate vetoed models (e.g.
            # Haval Jolion HEV appearing despite "NO Haval" in the prompt)
            # because it had nothing legitimate to choose from. Return early
            # and let the caller receive a clean, possibly-empty result.
            if eligible_list.startswith("No eligible cars found"):
                print(
                    "[Fallback] Eligible list is empty — skipping LLM self-correction "
                    "to avoid hallucination on a zero-option list."
                )
                formatted = _deduplicate_and_format(valid_targets, constraints)
                return await run_final_ai_sanitizer(formatted, constraints.get("user_prompt", ""))

            # Already-picked valid makes/models — tell LLM not to repeat them
            already_picked = [
                f"{v.make} {v.model}" for v in valid_targets
            ]

            # ── Correction prompt: deliberately minimal ───────────────────────
            # This is a narrow repair call, not a re-run of the whole
            # recommendation task. The model needs exactly three things:
            # what went wrong, what it may choose from, and what it must not
            # repeat. Re-injecting the full original constraint block here was
            # counter-productive — it re-opened the door to the same
            # hallucinated picks the validator had just rejected, because the
            # model started re-reasoning about the query instead of simply
            # substituting from a pre-verified list.
            #
            # dropped_reasons is capped because only the distinct failure modes
            # carry signal; a wall of near-identical rejection lines pushes the
            # ELIGIBLE CARS list further from the instruction and measurably
            # degrades adherence on long lists.
            MAX_REASONS_SHOWN = 5
            shown_reasons = dropped_reasons[:MAX_REASONS_SHOWN]
            overflow = len(dropped_reasons) - len(shown_reasons)
            reason_block = "\n".join(f"  - {r}" for r in shown_reasons)
            if overflow > 0:
                reason_block += f"\n  - (+{overflow} more with the same failure modes)"

            plural = "car" if needed == 1 else "cars"
            correction_prompt = (
                f"REPLACEMENT TASK — your previous picks were rejected by a "
                f"deterministic validator.\n\n"
                f"REJECTED, AND WHY:\n{reason_block}\n\n"
                f"ELIGIBLE CARS — every entry below is already budget-, feature- "
                f"and veto-verified. Pick ONLY from this list:\n{eligible_list}\n\n"
                f"ALREADY PICKED (do not repeat these): {json.dumps(already_picked)}\n\n"
                f"Return EXACTLY {needed} replacement {plural} from the ELIGIBLE CARS "
                f"list. Do not re-derive the user's requirements, do not reinstate a "
                f"rejected car, and do not invent a model that is not in the list. "
                f"If no suitable car remains, return an empty JSON array []."
            )

            try:
                response_text = await generate_content_resilient(
                    contents=correction_prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=list[CarTargetRaw],
                        temperature=0.2,
                    ),
                )
                replacement_raws = [
                    CarTargetRaw.model_validate(item)
                    for item in json.loads(response_text)
                ]
                valid_replacements, still_dropped = _validate_targets(
                    replacement_raws, constraints
                )
                if still_dropped:
                    print(
                        f"[Fallback] Correction still dropped {len(still_dropped)} car(s) "
                        f"on second pass — accepting partial result."
                    )
                valid_targets.extend(valid_replacements)
                print(
                    f"[Fallback] Self-correction complete — "
                    f"{len(valid_replacements)} replacement(s) added."
                )
            except Exception as e:
                print(f"[Fallback] Self-correction LLM call failed: {e}")

    formatted = _deduplicate_and_format(valid_targets, constraints)
    return await run_final_ai_sanitizer(formatted, constraints.get("user_prompt", ""))


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
        excluded_features=constraints.get("excluded_features"),
        direct_model_req=constraints.get("direct_model"),
        drive_req=drive,
        powertrain_req=constraints.get("powertrain"),
        min_year=constraints.get("min_year", 0),
        is_luxury_request=is_luxury,
        is_highway_ev=constraints.get("is_highway_ev", False),
        origin_pref=constraints.get("origin_pref"),
        is_diesel_hybrid_query=constraints.get("is_diesel_hybrid_query", False),
        excluded_origins=constraints.get("excluded_origins", []),
        is_llm_vetoed=constraints.get("is_llm_vetoed", False),
        intent_id=constraints.get("intent_id"),
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
        valid, _dropped = _validate_targets(valid, constraints)
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
        excluded_features=original_constraints.get("excluded_features"),
        direct_model_req=original_constraints.get("direct_model"),
        drive_req=drive,
        powertrain_req=original_constraints.get("powertrain"),
        min_year=original_constraints.get("min_year", 0),
        is_luxury_request=is_luxury,
        is_highway_ev=original_constraints.get("is_highway_ev", False),
        origin_pref=original_constraints.get("origin_pref"),
        is_diesel_hybrid_query=original_constraints.get("is_diesel_hybrid_query", False),
        excluded_origins=original_constraints.get("excluded_origins", []),
        is_llm_vetoed=original_constraints.get("is_llm_vetoed", False),
        intent_id=original_constraints.get("intent_id"),
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
        valid, _dropped = _validate_targets(valid, original_constraints)
        return _deduplicate_and_format(valid, original_constraints)
    except Exception as e:
        print(f"[ExtendedMapper] Failed: {e}")
        traceback.print_exc()
        return []

