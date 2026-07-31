"""
agents/recommender.py
LLM logic for the AI Matchmaker — maps natural language intent to structured
car search targets using Gemini Flash Lite.

Architecture: Sequential Multi-Agent Pipeline with Deterministic Guardrails
  Phase 1 — LLM:    extract_intent()                      → UserIntent (raw signals only)
  Phase 1 — Python: resolve_constraints()                 → fully resolved constraint dict
  Phase 2 — LLM:    select_car_targets()                  → CarTargetRaw list (car picks only)
  Phase 2 — Python: _validate_targets_against_market()    → drops budget-impossible picks
  Phase 2 — Python: _deduplicate_and_format_targets()     → final 9-key contract dicts
  Phase 3 — LLM:    get_fallback_recommendations()        → conditional replacement
  Phase 3 — LLM:    get_extended_recommendations()        → "show more" extension
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


# ---------------------------------------------------------------------------
# MARKET PRICE MAP — Pakistani used car market (PakWheels / OLX data)
# Format: "make:model" → (min_PKR, max_PKR)
# Used to:
#   1. Feed price context to the LLM so it knows what fits a given budget.
#   2. Post-validate LLM picks and silently drop impossible ones.
# Update this periodically as market prices shift.
# ---------------------------------------------------------------------------

PAKISTAN_MARKET_PRICES: dict[str, tuple[int, int]] = {
    # ── Suzuki ──────────────────────────────────────────────────────────────
    "suzuki:alto": (700000, 3600000),
    "suzuki:cultus": (1000000, 4500000),
    "suzuki:wagon r": (1500000, 3500000),
    "suzuki:swift": (1200000, 5200000),
    "suzuki:mehran": (300000, 1500000),
    "suzuki:every": (1000000, 3000000),
    "suzuki:bolan": (500000, 2000000),
    "suzuki:alto 660cc": (1500000, 3800000),
    "suzuki:hustler": (1800000, 4000000),
    "suzuki:spacia": (1800000, 4000000),
    "suzuki:wagon r jdm": (1500000, 3500000),
    "suzuki:solio": (2000000, 4500000),
    "suzuki:jimny": (2500000, 8500000),
    "suzuki:apv": (1500000, 3500000),

    # ── Toyota ──────────────────────────────────────────────────────────────
    "toyota:corolla": (2000000, 8500000),
    "toyota:yaris": (3500000, 6000000),
    "toyota:fortuner": (9000000, 21000000),
    "toyota:hilux": (8000000, 16000000),
    "toyota:vitz": (1500000, 4500000),
    "toyota:passo": (1500000, 4000000),
    "toyota:aqua": (2500000, 6500000),
    "toyota:yaris cross": (6000000, 9500000),
    "toyota:raize": (5000000, 7500000),
    "toyota:tank": (3000000, 4500000),
    "toyota:roomy": (3000000, 5000000),
    "toyota:prius": (2500000, 12000000),
    "toyota:crown": (4000000, 25000000),
    "toyota:mark x": (3000000, 7000000),
    "toyota:premio": (3500000, 9000000),
    "toyota:allion": (3000000, 8000000),
    "toyota:fielder": (2500000, 6000000),
    "toyota:probox": (2000000, 4500000),
    "toyota:sienta": (3000000, 6500000),
    "toyota:alphard": (6000000, 35000000),
    "toyota:vellfire": (6000000, 35000000),
    "toyota:camry": (7000000, 18000000),
    "toyota:c-hr": (4500000, 10000000),
    "toyota:rush": (5500000, 9000000),
    "toyota:prado": (18000000, 48000000),
    "toyota:land cruiser": (35000000, 90000000),
    "toyota:hiace": (3500000, 12000000),

    # ── Honda ───────────────────────────────────────────────────────────────
    "honda:city": (1500000, 6000000),
    "honda:civic": (2000000, 9500000),
    "honda:br-v": (3500000, 6500000),
    "honda:hr-v": (6000000, 8500000),
    "honda:n-box": (1800000, 4200000),
    "honda:n-wgn": (1500000, 3800000),
    "honda:fit": (2000000, 5500000),
    "honda:grace": (3500000, 6500000),
    "honda:vezel": (4000000, 11000000),
    "honda:insight": (2500000, 6500000),
    "honda:freed": (2500000, 6000000),
    "honda:shuttle": (3500000, 7000000),
    "honda:stepwgn": (3000000, 8000000),
    "honda:cr-v": (6000000, 14000000),
    "honda:accord": (4500000, 12000000),

    # ── Hyundai ─────────────────────────────────────────────────────────────
    "hyundai:elantra": (5000000, 7500000),
    "hyundai:sonata": (7500000, 11000000),
    "hyundai:tucson": (6000000, 9000000),
    "hyundai:porter": (2500000, 4000000),
    "hyundai:santro": (700000, 1800000),
    "hyundai:i10": (1200000, 3000000),
    "hyundai:palisade": (18000000, 35000000),

    # ── Kia ─────────────────────────────────────────────────────────────────
    "kia:picanto": (2500000, 3800000),
    "kia:stonic": (4500000, 6000000),
    "kia:sportage": (5500000, 10000000),
    "kia:sorento": (7500000, 11000000),
    "kia:carnival": (9000000, 18000000),

    # ── Daihatsu ────────────────────────────────────────────────────────────
    "daihatsu:mira": (1200000, 3800000),
    "daihatsu:move": (1200000, 3500000),
    "daihatsu:tanto": (1500000, 4000000),
    "daihatsu:cast": (2000000, 3500000),
    "daihatsu:hijet": (1000000, 2500000),
    "daihatsu:rocky": (5000000, 7500000),
    "daihatsu:cuore": (600000, 1600000),
    "daihatsu:terios": (2500000, 6000000),

    # ── Nissan ──────────────────────────────────────────────────────────────
    "nissan:dayz": (1500000, 3500000),
    "nissan:roox": (1500000, 3800000),
    "nissan:note": (3500000, 6500000),
    "nissan:juke": (3500000, 8000000),
    "nissan:x-trail": (5000000, 14000000),
    "nissan:patrol": (20000000, 55000000),

    # ── Mitsubishi ──────────────────────────────────────────────────────────
    "mitsubishi:mirage": (2000000, 4500000),
    "mitsubishi:asx": (3500000, 8000000),
    "mitsubishi:outlander": (5000000, 14000000),
    "mitsubishi:pajero": (5000000, 16000000),
    "mitsubishi:pajero sport": (8000000, 18000000),

    # ── Subaru ──────────────────────────────────────────────────────────────
    "subaru:xv": (4000000, 7500000),
    "subaru:forester": (4500000, 9000000),
    "subaru:impreza": (2500000, 6000000),
    "subaru:brz": (4500000, 10000000),

    # ── Mazda ───────────────────────────────────────────────────────────────
    "mazda:cx-3": (4000000, 7000000),
    "mazda:cx-5": (5500000, 9500000),
    "mazda:demio": (2500000, 4500000),
    "mazda:rx-8": (1500000, 4000000),
    "mazda:mazda3": (3000000, 7000000),

    # ── Chinese & New Entrants ──────────────────────────────────────────────
    "mg:hs": (6000000, 8500000),
    "mg:zs": (4500000, 6500000),
    "mg:zs ev": (7000000, 11000000),
    "mg:cyberster": (15000000, 25000000),
    "mg:rx5": (4500000, 9000000),
    "changan:alsvin": (3200000, 4800000),
    "changan:karvaan": (1500000, 3000000),
    "changan:oshan x7": (7000000, 9500000),
    "changan:uni-t": (8000000, 11000000),
    "changan:deepal s07": (13000000, 18000000),
    "changan:deepal l07": (13000000, 18000000),
    "haval:h6": (8900000, 10000000),
    "haval:h6 hev": (11400000, 14000000),
    "haval:jolion": (7000000, 9000000),
    "chery:tiggo 4 pro": (5500000, 7500000),
    "chery:tiggo 8 pro": (8000000, 10500000),
    "proton:saga": (2500000, 3800000),
    "proton:x70": (6000000, 8000000),
    "byd:atto 3": (11000000, 15000000),
    "byd:seal": (16000000, 22000000),
    "byd:dolphin": (9000000, 12000000),
    "gwm:tank 500": (35000000, 45000000),
    "gwm:ora 03": (8000000, 11000000),

    # ── European & Luxury ───────────────────────────────────────────────────
    "bmw:3 series": (6000000, 25000000),
    "bmw:5 series": (8000000, 35000000),
    "bmw:7 series": (15000000, 60000000),
    "bmw:x1": (7000000, 20000000),
    "bmw:x3": (9000000, 30000000),
    "bmw:x5": (12000000, 50000000),
    "bmw:x7": (40000000, 80000000),
    "bmw:i4": (25000000, 35000000),
    "bmw:i7": (60000000, 90000000),
    "bmw:ix": (35000000, 55000000),
    
    "mercedes-benz:c-class": (6000000, 30000000),
    "mercedes-benz:e-class": (8000000, 45000000),
    "mercedes-benz:s-class": (15000000, 80000000),
    "mercedes-benz:cla": (7000000, 18000000),
    "mercedes-benz:gla": (7500000, 20000000),
    "mercedes-benz:glc": (12000000, 35000000),
    "mercedes-benz:gle": (15000000, 50000000),
    "mercedes-benz:gls": (30000000, 75000000),
    
    "audi:a3": (5000000, 12000000),
    "audi:a4": (6500000, 20000000),
    "audi:a5": (8000000, 25000000),
    "audi:a6": (9000000, 35000000),
    "audi:a7": (15000000, 45000000),
    "audi:q2": (6500000, 11000000),
    "audi:q3": (7500000, 15000000),
    "audi:q5": (10000000, 25000000),
    "audi:q7": (15000000, 45000000),
    "audi:q8": (30000000, 60000000),
    "audi:e-tron": (18000000, 35000000),
    "audi:e-tron gt": (35000000, 60000000),
    
    "porsche:macan": (20000000, 45000000),
    "porsche:cayenne": (25000000, 70000000),
    "porsche:panamera": (25000000, 60000000),
    "porsche:taycan": (40000000, 85000000),
    
    "land rover:defender": (35000000, 85000000),
    "land rover:discovery": (15000000, 50000000),
    "land rover:range rover sport": (20000000, 75000000),
    "land rover:vogue": (25000000, 95000000),
    "land rover:range rover": (25000000, 95000000),
    "land rover:evoque": (9000000, 25000000),
    "land rover:velar": (20000000, 45000000),
    
    "lexus:ct200h": (4000000, 7500000),
    "lexus:is": (5000000, 15000000),
    "lexus:es": (8000000, 25000000),
    "lexus:rx": (10000000, 35000000),
    "lexus:nx": (12000000, 28000000),
    "lexus:lx570": (30000000, 75000000),
    "lexus:lx": (30000000, 75000000),
    "lexus:lx600": (90000000, 140000000),
}

# Chinese makes — only allowed when origin_pref == "Chinese"
_CHINESE_MAKES = {"mg", "changan", "chery", "haval", "proton", "baic", "geely"}


# ---------------------------------------------------------------------------
# MARKET PRICE HELPERS
# ---------------------------------------------------------------------------

# Canonical model name map — normalizes LLM output variants to scraper-safe names.
# Key: any variant the LLM might output (lowercased)
# Value: the canonical model name used in runner.py URL building
_CANONICAL_MODEL_MAP: dict[str, str] = {
    # Toyota
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
    
    # Honda
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
    
    # Suzuki
    "wagon r":                   "Wagon R",
    "wagonr":                    "Wagon R",
    "alto 660":                  "Alto 660cc",
    "wagon r jdm":               "Wagon R JDM",
    
    # Nissan
    "x-trail":                   "X-Trail",
    "xtrail":                    "X-Trail",
    "note e-power":              "Note e-Power",
    
    # Mazda
    "rx-8":                      "RX-8",
    "rx8":                       "RX-8",
    "cx-5":                      "CX-5",
    "cx5":                       "CX-5",
    "mazda2":                    "Demio",
    "demio/mazda2":              "Demio",
    
    # Chinese
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
    
    # European / Luxury
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

def get_market_price_context(max_budget: int) -> str:
    """
    Builds a filtered price reference block for the LLM prompt.
    Only includes models whose market range overlaps the user's budget window.
    Injected as a preamble to select_car_targets so the LLM has real price
    grounding instead of relying on potentially stale training data.
    """
    if max_budget <= 0:
        # No budget stated — return full list so LLM isn't flying blind
        lines = [
            f"  {key.replace(':', ' ').title()}: PKR {lo:,} – {hi:,}"
            for key, (lo, hi) in PAKISTAN_MARKET_PRICES.items()
        ]
    else:
        lines = []
        for key, (lo, hi) in PAKISTAN_MARKET_PRICES.items():
            # Include if there's meaningful overlap:
            #   floor is within 125% of budget (reachable), AND
            #   ceiling is at least 40% of budget (not laughably cheap)
            if lo <= max_budget * 1.25 and hi >= max_budget * 0.40:
                make, model = key.split(":", 1)
                lines.append(
                    f"  {make.title()} {model.title()}: PKR {lo:,} – {hi:,}"
                )

    if not lines:
        return ""

    return (
        "CURRENT PAKISTAN USED CAR MARKET PRICES (PakWheels/OLX data):\n"
        + "\n".join(lines)
        + "\n\nOnly recommend cars from this list whose price range overlaps the budget."
    )


def _validate_targets_against_market(
    targets: list,
    constraints: dict,
) -> list:
    """
    Python post-validation after LLM car selection.

    Drops targets that are provably wrong given the budget or origin preference:
      - Chinese brands when origin_pref != "Chinese"
      - Budget floor unreachable (market min > budget * 0.85)
      - Model too cheap (market ceiling < 80% of the 70%-floor — wastes scraper call)

    Unknown models (not in PAKISTAN_MARKET_PRICES) always pass through —
    we never silently drop a car the LLM picked if we have no price data for it.

    Safety net: if all targets get dropped (very rare), returns the first original
    so the pipeline never enters the scrape stage with zero targets.
    """
    max_budget  = constraints.get("max_budget", 0)
    origin_pref = constraints.get("origin_pref")
    allow_chinese = (origin_pref == "Chinese")

    valid = []
    for t in targets:
        make_lower  = t.make.lower().strip()
        model_lower = t.model.lower().strip()

        # ── Chinese brand gate ───────────────────────────────────────────────
        if make_lower in _CHINESE_MAKES and not allow_chinese:
            print(
                f"[Validator] Dropping {t.make} {t.model} — Chinese brand not requested "
                f"(origin_pref={origin_pref})"
            )
            continue

        # ── Budget feasibility gate ──────────────────────────────────────────
        if max_budget > 0:
            canonical_model = _CANONICAL_MODEL_MAP.get(model_lower, model_lower).lower()
            key = f"{make_lower}:{canonical_model}"
            if key in PAKISTAN_MARKET_PRICES:
                lo, hi = PAKISTAN_MARKET_PRICES[key]

                # Too expensive: budget can't reach 85% of market floor
                if max_budget < lo * 0.85:
                    print(
                        f"[Validator] Dropping {t.make} {t.model} — market floor "
                        f"PKR {lo:,} unreachable at budget PKR {max_budget:,}"
                    )
                    continue

                # Too cheap: market ceiling is way below the 70% budget floor
                min_budget = int(max_budget * 0.70)
                if hi < min_budget * 0.80:
                    print(
                        f"[Validator] Dropping {t.make} {t.model} — market ceiling "
                        f"PKR {hi:,} below budget floor PKR {min_budget:,}"
                    )
                    continue

        valid.append(t)

    if not valid and targets:
        # Safety net: never let the pipeline proceed with zero targets
        print("[Validator] All targets dropped — returning first original as safety fallback.")
        return [targets[0]]

    return valid


# ---------------------------------------------------------------------------
# PHASE 1: INTENT EXTRACTOR & CONSTRAINT RESOLVER
# ---------------------------------------------------------------------------

class UserIntent(BaseModel):
    """
    Raw signals extracted from the user's natural language query.
    LLM only extracts — it does NOT calculate or decide anything here.
    All budget math and rule application happens in resolve_constraints().
    """
    max_budget:        Optional[int]   = None
    body_style:        Optional[Literal["SUV", "Sedan", "Hatchback", "Pickup", "Crossover", "Van"]] = None
    transmission:      Optional[Literal["Automatic", "Manual"]] = None
    use_case:          Optional[str]   = None
    origin_pref:       Optional[Literal["JDM", "Local", "European", "Chinese"]] = None
    is_luxury_request: bool            = False
    required_features: list[str]       = Field(default_factory=list)


async def extract_intent(user_prompt: str) -> UserIntent:
    """
    Phase 1 LLM call — pure signal extraction, no decisions.
    Uses Gemini's native structured output (response_schema) so output
    is guaranteed to match UserIntent schema without manual parsing.
    Temperature 0.0 for deterministic extraction.
    """
    prompt = (
        f"Extract the user's car search intent from this query: '{user_prompt}'\n\n"
        "Rules:\n"
        "- Convert Pakistani currency precisely: '5 crore' → 50000000, "
        "'50 lacs/lakhs' → 5000000, '1 crore' → 10000000, '80 lacs' → 8000000.\n"
        "- use_case: brief phrase like 'family daily', 'offroad adventure', "
        "'city commute', 'sports driving', 'ride sharing'.\n"
        "- is_luxury_request: true ONLY if user says words like 'luxury', 'premium', "
        "'aura', 'VIP', 'boss car', 'status'.\n"
        "- required_features: only explicit features mentioned, e.g. 'sunroof', "
        "'push start', 'leather seats'. Do not invent features.\n"
        "- If a field is not mentioned, leave it null/empty — do not guess."
    )
    response = await client.aio.models.generate_content(
        model="gemini-3.5-flash-lite",
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
    Phase 1 Python gate — ALL rule logic lives here, zero LLM involvement.

    Applies:
      1. Budget floor (70% of max)
      2. Graduated min_year by budget tier (fixed gap from original 3-case logic)
      3. Tier classification for LLM guidance
      4. Chinese brand exclusion flag (enforced in Python, not LLM prompt)
      5. Body style (passed through for downstream Python validator)
      6. Luxury escalation flag
    """
    max_budget = intent.max_budget or 0
    min_budget = 0

    # ── 1. Budget floor ──────────────────────────────────────────────────────
    if max_budget > 0:
        min_budget = int(max_budget * 0.70)

    # ── 2. Year Floor ────────────────────────────────────────────────────────
    # Year constraints have been removed. The 30% budget floor handles all 
    # quality/tier filtering. 0 means the normalizer will accept any year.
    min_year = 0

    # ── 3. Tier classification ──────────────────────────────────────────────
    # Passed to the LLM as a clear signal — replaces the old allowed_tiers list
    # which the LLM frequently ignored when buried in a JSON dump.
    if max_budget >= 30_000_000 or intent.is_luxury_request:
        tier = "apex_luxury"          # LC300, Range Rover, Porsche, Patrol V8
    elif max_budget >= 10_000_000:
        tier = "premium"              # Fortuner, Prado, BMW 3, Sportage AWD
    elif max_budget >= 4_000_000:
        tier = "mid"                  # Civic, Corolla Grande, HR-V, BR-V
    else:
        tier = "economy"              # Alto, WagonR, Cultus, Vitz, City

    # ── 4. Chinese brand flag ───────────────────────────────────────────────
    allow_chinese = (intent.origin_pref == "Chinese")

    return {
        "min_budget":        min_budget,
        "max_budget":        max_budget,
        "min_year":          min_year,
        "tier":              tier,
        "allow_chinese":     allow_chinese,
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
    """
    Raw car target from the LLM selector.
    Trim can be empty — that's valid (lazy-seller listings won't have it).
    Rationale is 1 sentence max for UI display.
    """
    make:              str
    model:             str
    trim:              str
    rationale:         str
    required_features: list[str] = Field(default_factory=list)




async def select_car_targets(constraints: dict) -> list[CarTargetRaw]:
    """
    Phase 2 LLM call — car knowledge only.

    Receives fully resolved constraints from resolve_constraints() so the
    LLM doesn't need to do any math or rule evaluation.

    Key improvements over old version:
      - Market price context injected as a preamble (real price grounding)
      - Constraint summary is a clean focused dict, not a raw json.dumps of
        everything — prevents the LLM from getting confused by internal fields
        like allow_chinese, excluded_tiers, etc.
      - Rules are numbered and specific, not buried in a wall of text
      - response_schema guarantees valid JSON — no manual _parse_llm_json needed
    """
    max_budget     = constraints.get("max_budget", 0)
    market_context = get_market_price_context(max_budget)

    budget_str = (
        f"PKR {constraints['min_budget']:,} – {max_budget:,}"
        if max_budget > 0
        else "No stated budget ceiling"
    )

    # Clean summary — only fields the LLM needs for car selection
    constraint_summary = {
        "budget_window":     budget_str,
        "tier":              constraints.get("tier", "mid"),
        "min_year":          constraints.get("min_year", 0),
        "body_style":        constraints.get("body_style") or "Any",
        "transmission":      constraints.get("transmission") or "Any",
        "use_case":          constraints.get("use_case") or "General",
        "origin_pref":       constraints.get("origin_pref") or "Any (prefer Japanese/Korean)",
        "allow_chinese":     constraints.get("allow_chinese", False),
        "required_features": constraints.get("required_features", []),
    }

    prompt = (
        f"{market_context}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "TASK: Pick the best 1–3 used cars for a Pakistani buyer.\n\n"
        f"CONSTRAINTS:\n{json.dumps(constraint_summary, indent=2)}\n\n"
        "SELECTION RULES:\n"
        "1. Budget: Only recommend cars whose market price overlaps the budget_window. "
        "If the car's market floor exceeds the budget ceiling, do NOT recommend it.\n"
        "2. Tier: 'economy' → affordable hatchbacks/sedans. 'mid' → Civic/Corolla class. "
        "'premium' → Fortuner/Sportage/BMW class. 'apex_luxury' → Land Cruiser/Range Rover/Porsche only.\n"
        "3. Body style: If body_style is set, NEVER suggest a different body style. "
        "Pickup = open cargo bed only (Hilux, Revo). No closed SUVs for pickup queries.\n"
        "4. Transmission: If 'Automatic' is set, exclude manual-only models.\n"
        "5. JDM: If origin_pref is 'JDM', always specify exact trim (e.g. trim='G Grade', trim='Turbo RS').\n"
        "6. Chinese brands: Only recommend if allow_chinese is true.\n"
        "7. Quality > Quantity: Output 1 target if only 1 fits well. Never pad to reach 3.\n"
        "8. Trim: Leave trim empty if no specific trim is needed — do not invent trims.\n"
        "9. Rationale: 1 sentence, buyer-friendly, explain WHY this car fits their need.\n"
        "10. Single-brand dominance is fine — if Toyota has 3 perfect options, return all 3 Toyota."
    )

    response = await client.aio.models.generate_content(
        model="gemini-3.5-flash-lite",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=list[CarTargetRaw],
            temperature=0.2,
        ),
    )

    # response_schema guarantees valid JSON matching CarTargetRaw —
    # json.loads is sufficient; no manual fence-stripping needed.
    try:
        return [CarTargetRaw.model_validate(item) for item in json.loads(response.text)]
    except Exception as e:
        print(f"[Selector] Failed to parse LLM response: {e}\nRaw: {response.text[:300]}")
        return []


def _deduplicate_and_format_targets(
    raw_targets: list[CarTargetRaw],
    constraints: dict,
) -> list[dict]:
    """
    Phase 2 Python gate — validation, canonicalization, deduplication, formatting.

    Order of operations:
      1. Python market validation (_validate_targets_against_market)
      2. Model name canonicalization via _CANONICAL_MODEL_MAP
      3. Deduplication on (make, canonical_model) key
      4. Feature merging and 9-key contract formatting
    """
    # Validate against market prices and origin preference
    validated = _validate_targets_against_market(raw_targets, constraints)

    seen:      set[tuple[str, str]] = set()
    formatted: list[dict]           = []

    for raw in validated:
        make_lower  = raw.make.lower().strip()
        model_raw   = raw.model.strip()
        model_lower = model_raw.lower()

        # Canonicalize model name
        canonical_model = _CANONICAL_MODEL_MAP.get(model_lower, model_raw)

        # Deduplicate on (make, canonical_model)
        dedup_key = (make_lower, canonical_model.lower())
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        # Merge features — constraint features + LLM-suggested features
        merged_features = list(
            set(constraints.get("required_features", []) + raw.required_features)
        )

        formatted.append({
            "make":              raw.make.strip(),
            "model":             canonical_model,
            "trim":              raw.trim.strip(),
            "city":              "",    # always empty — recommend_normalizer handles city softly
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
    Phase 3 LLM call — fires only when a target returns NORMALIZER_ZERO.
    Returns exactly 1 replacement target (not more).

    Passes market price context so the replacement is budget-realistic.
    Validates output through the same Python gates as the main selector.
    """
    max_budget     = constraints.get("max_budget", 0)
    market_context = get_market_price_context(max_budget)

    budget_str = (
        f"PKR {constraints.get('min_budget', 0):,} – {max_budget:,}"
        if max_budget > 0
        else "No stated budget ceiling"
    )

    prompt = (
        f"{market_context}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "TASK: Suggest exactly 1 replacement car. Previous recommendations had zero listings.\n\n"
        f"ORIGINAL CONSTRAINTS:\n"
        f"  Budget: {budget_str}\n"
        f"  Body style: {constraints.get('body_style') or 'Any'}\n"
        f"  Transmission: {constraints.get('transmission') or 'Any'}\n"
        f"  Use case: {constraints.get('use_case') or 'General'}\n"
        f"  Tier: {constraints.get('tier', 'mid')}\n\n"
        f"ALREADY TRIED (DO NOT REPEAT): {json.dumps(excluded_models)}\n\n"
        "RULES:\n"
        "- Return exactly 1 target in the array. Never return more than 1.\n"
        "- Must match budget_window, body_style, and transmission exactly.\n"
        "- Must NOT be in the already-tried list.\n"
        "- If no valid replacement exists, return an empty array [] — never hallucinate."
    )

    try:
        response = await client.aio.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=list[CarTargetRaw],
                temperature=0.25,
            ),
        )
        raw_list = json.loads(response.text)

        # Enforce max 1
        if len(raw_list) > 1:
            raw_list = [raw_list[0]]

        valid_targets = [CarTargetRaw.model_validate(item) for item in raw_list]

        # Python validation — same gates as main pipeline
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
    Returns 1–3 Tier-2 or alternative picks, validated through Python gates.
    """
    max_budget     = original_constraints.get("max_budget", 0)
    market_context = get_market_price_context(max_budget)

    budget_str = (
        f"PKR {original_constraints.get('min_budget', 0):,} – {max_budget:,}"
        if max_budget > 0
        else "No stated budget ceiling"
    )

    # Low-budget floor: prevent modern car hallucination for sub-12-lac searches
    legacy_only_note = ""
    if 0 < max_budget <= 1_200_000:
        legacy_only_note = (
            "\nLOW-BUDGET RULE: Budget is ≤ PKR 1,200,000. "
            "ONLY suggest legacy cars: Mehran, Cuore, Khyber, Charade, Santro. "
            "Never suggest any modern car.\n"
        )

    prompt = (
        f"{market_context}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"TASK: Generate 1–3 alternative 'Show More' car options.{legacy_only_note}\n\n"
        f"ORIGINAL CONSTRAINTS:\n"
        f"  Budget: {budget_str}\n"
        f"  Body style: {original_constraints.get('body_style') or 'Any'}\n"
        f"  Transmission: {original_constraints.get('transmission') or 'Any'}\n"
        f"  Use case: {original_constraints.get('use_case') or 'General'}\n"
        f"  Tier: {original_constraints.get('tier', 'mid')}\n\n"
        f"ALREADY SHOWN (DO NOT REPEAT): {json.dumps(excluded_models)}\n\n"
        "RULES:\n"
        "- Budget realism: every option MUST have a market price within budget_window.\n"
        "- Zero body style leaks: if Crossover was requested, sedans are forbidden.\n"
        "- These should be genuine alternatives — different model from already-shown.\n"
        "- Quality > Quantity: return 1 if only 1 good option exists.\n"
        "- If no valid alternatives exist within budget, return empty array []."
    )

    try:
        response = await client.aio.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=list[CarTargetRaw],
                temperature=0.3,
            ),
        )
        raw_list = json.loads(response.text)
        valid_targets = [CarTargetRaw.model_validate(item) for item in raw_list]

        # Python validation — same gates as main pipeline
        valid_targets = _validate_targets_against_market(valid_targets, original_constraints)

        return _deduplicate_and_format_targets(valid_targets, original_constraints)

    except Exception as e:
        print(f"[ExtendedMapper] Failed: {e}")
        traceback.print_exc()
        return []