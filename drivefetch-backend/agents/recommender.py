"""
agents/recommender.py
LLM logic for the AI Matchmaker — maps natural language intent to structured
car search targets using Gemini Flash Lite.
"""
import os
import json
import re
import traceback
from dotenv import load_dotenv
from google import genai
from google.genai import types
from typing import Optional, Literal
from pydantic import BaseModel, Field

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
client = genai.Client(api_key=GEMINI_API_KEY)

# ---------------------------------------------------------------------------
# PHASE 1: INTENT EXTRACTOR & CONSTRAINT RESOLVER
# ---------------------------------------------------------------------------
class UserIntent(BaseModel):
    max_budget: Optional[int] = None
    body_style: Optional[Literal["SUV", "Sedan", "Hatchback", "Pickup", "Crossover", "Van"]] = None
    transmission: Optional[Literal["Automatic", "Manual"]] = None
    use_case: Optional[str] = None
    origin_pref: Optional[Literal["JDM", "Local", "European", "Chinese"]] = None
    is_luxury_request: bool = False
    required_features: list[str] = Field(default_factory=list)

async def extract_intent(user_prompt: str) -> UserIntent:
    prompt = f"Extract the user's intent from this car search query: '{user_prompt}'\nNote: Convert terms like '5 crore' to 50000000, '50 lacs' to 5000000."
    response = await client.aio.models.generate_content(
        model="gemini-3.5-flash-lite",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=UserIntent,
            temperature=0.0
        ),
    )
    return UserIntent.model_validate_json(response.text)

def resolve_constraints(intent: UserIntent) -> dict:
    max_budget = intent.max_budget or 0
    min_budget = 0
    
    # 1. Dynamic 30% Budget Floor Math
    if max_budget > 0:
        min_budget = int(max_budget * 0.70)
        
    # 2. Elite Budget Apex Hierarchy
    if max_budget >= 30000000:
        allowed_tiers = ["Apex Luxury", "Luxury"]
    else:
        allowed_tiers = ["Economy", "Mid-Tier", "Luxury"]
        
    # 3. Budget Generation Logic
    if max_budget >= 5000000:
        min_year = 2018
    elif 0 < max_budget < 5000000:
        min_year = 2005
    else:
        min_year = 2020
        
    # 4. Tier Exclusions
    excluded_tiers = ["Tier-2-Chinese"]
    if intent.origin_pref == "Chinese":
        excluded_tiers.remove("Tier-2-Chinese")
        
    return {
        "min_budget": min_budget,
        "max_budget": max_budget,
        "min_year": min_year,
        "allowed_tiers": allowed_tiers,
        "excluded_tiers": excluded_tiers,
        "body_style": intent.body_style,
        "transmission": intent.transmission,
        "use_case": intent.use_case,
        "origin_pref": intent.origin_pref,
        "is_luxury_request": intent.is_luxury_request,
        "required_features": intent.required_features
    }

# ---------------------------------------------------------------------------
# PHASE 2: CAR SELECTOR & CANONICALIZER
# ---------------------------------------------------------------------------
class CarTargetRaw(BaseModel):
    make: str
    model: str
    trim: str
    rationale: str
    required_features: list[str] = Field(default_factory=list)

def _parse_llm_json(raw_text: str):
    """Strips meta-commentary and markdown fences to extract clean JSON."""
    raw = raw_text.strip()
    match = re.search(r'\[.*\]|\{.*\}', raw, re.DOTALL)
    if match:
        raw = match.group(0)
    return json.loads(raw)

async def select_car_targets(constraints: dict) -> list[CarTargetRaw]:
    prompt = f"""
    Based on the following constraints, recommend 1 to 3 car targets for the Pakistani market.
    Constraints: {json.dumps(constraints, indent=2)}
    
    Rules:
    - Output 1 to 3 targets maximum. Quality > Quantity.
    - Single-brand dominance IS permitted.
    - Hard-enforce allowed_tiers and body_style (if any) from the constraints dictionary.
    - If origin_pref == "JDM", specify explicit JDM trims (e.g., trim="G", trim="Turbo RS").
    - Hard-exclude closed-body SUVs for Pickup queries (open bed required).
    """
    response = await client.aio.models.generate_content(
        model="gemini-3.5-flash-lite",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=list[CarTargetRaw],
            temperature=0.25
        ),
    )
    raw_list = _parse_llm_json(response.text)
    return [CarTargetRaw.model_validate(item) for item in raw_list]

def _deduplicate_and_format_targets(raw_targets: list[CarTargetRaw], constraints: dict) -> list[dict]:
    canonical_map = {
        "land cruiser prado": "prado",
        "revo hilux": "hilux",
        "hilux revo": "hilux",
        "corolla altis": "corolla",
        "civic oriel": "civic"
    }
    
    seen = set()
    formatted = []
    
    for raw in raw_targets:
        make_lower = raw.make.lower().strip()
        model_raw = raw.model.strip()
        model_lower = model_raw.lower()
        
        canonical_model = canonical_map.get(model_lower, model_raw)
        
        # Deduplicate
        key = (make_lower, canonical_model.lower())
        if key in seen:
            continue
        seen.add(key)
        
        # Merge features
        merged_features = list(set(constraints.get("required_features", []) + raw.required_features))
        
        # Format to 9-key contract
        formatted.append({
            "make": raw.make.strip(),
            "model": canonical_model,
            "trim": raw.trim.strip(),
            "city": "", 
            "min_budget": constraints.get("min_budget", 0),
            "max_budget": constraints.get("max_budget", 0),
            "min_year": constraints.get("min_year", 0),
            "required_features": merged_features, 
            "rationale": raw.rationale.strip()
        })
        
    return formatted

# ---------------------------------------------------------------------------
# PHASE 3: FALLBACK & EXTENSION PIPELINES
# ---------------------------------------------------------------------------

async def get_fallback_recommendations(constraints: dict, excluded_models: list[str]) -> list[dict]:
    prompt = f"""
    Based on the following constraints, recommend EXACTLY 1 replacement car target for the Pakistani market.
    The previous recommendations returned zero listings.
    
    Constraints: {json.dumps(constraints, indent=2)}
    
    CRITICAL RULES:
    - DO NOT recommend any of these previously tried/failed models: {json.dumps(excluded_models)}
    - The replacement MUST perfectly match the body_style, max_budget, and transmission constraints.
    - If no valid replacements exist within the exact parameters, it's better to return an empty array than to suggest an invalid car.
    """
    
    try:
        response = await client.aio.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=list[CarTargetRaw],
                temperature=0.25
            ),
        )
        raw_list = _parse_llm_json(response.text)
        
        # Enforce exactly 1 replacement
        if len(raw_list) > 1:
            raw_list = [raw_list[0]]
            
        valid_targets = [CarTargetRaw.model_validate(item) for item in raw_list]
        return _deduplicate_and_format_targets(valid_targets, constraints)
    except Exception as e:
        print(f"[FallbackMapper] Failed: {e}")
        traceback.print_exc()
        return []

async def get_extended_recommendations(original_constraints: dict, excluded_models: list[str]) -> list[dict]:
    prompt = f"""
    Generate 1 to 3 "Tier-2" or alternative "Show More" options based on the original search constraints.
    
    Original Constraints: {json.dumps(original_constraints, indent=2)}
    
    CRITICAL RULES:
    - DO NOT recommend any of these models that were already shown: {json.dumps(excluded_models)}
    - BUDGET REALISM: Any extended option MUST have a typical market price <= max_budget.
    - LOW-BUDGET CAP (<= 700000 PKR): If max_budget is 7 Lacs or below, ONLY suggest legacy runabouts (Mehran, Cuore, Khyber, Charade, Santro). Never suggest modern cars.
    - ZERO BODY-STYLE LEAKS: Strictly adhere to the requested body_style. If Crossover was requested, sedans are forbidden.
    - GRACEFUL EMPTY STATE: If no valid Tier-2 or secondary options exist within budget, return an empty list []. Do not hallucinate cars that break the budget.
    """
    
    try:
        response = await client.aio.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=list[CarTargetRaw],
                temperature=0.3
            ),
        )
        raw_list = _parse_llm_json(response.text)
        valid_targets = [CarTargetRaw.model_validate(item) for item in raw_list]
        return _deduplicate_and_format_targets(valid_targets, original_constraints)
    except Exception as e:
        print(f"[ExtendedMapper] Failed: {e}")
        traceback.print_exc()
        return []

# ---------------------------------------------------------------------------
# (End of Phase 3 New Architecture)
# ---------------------------------------------------------------------------