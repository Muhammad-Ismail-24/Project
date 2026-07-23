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

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
client = genai.Client(api_key=GEMINI_API_KEY)

# ---------------------------------------------------------------------------
# SEMANTIC MAPPER SYSTEM PROMPT — v5.0
# ---------------------------------------------------------------------------
#
# v3.0 changes over v2.0:
#   - Added "min_year" field to the JSON schema.
#     When the user gives NO budget, set min_year to the launch year of the
#     current generation of that model. This forces the scraper to surface
#     the newest units rather than flooding results with decade-old listings.
#     When the user gives a budget, set min_year = 0 (no year floor).
#   - Expanded GENERATION GROUND TRUTH section so the LLM knows exactly
#     which year = current gen for every major Pakistani market model.
#   - Expanded and rebalanced intent→car mappings for Chinese brands, EVs,
#     and the new 2022–2025 wave of models now common in the used market.
#   - Replaced the "stretch budget" diversity rule with a clearer instruction:
#     if no budget, prioritise newest shape over cheapest/most common variant.
#   - Added a 5th few-shot example specifically demonstrating the no-budget
#     newest-model behaviour.
# ---------------------------------------------------------------------------
SEMANTIC_MAPPER_PROMPT = """You are GaariGuru, an expert Pakistani used-car matchmaker. A user describes what they want in natural language, Roman Urdu, or Urdu script. Translate their intent into EXACTLY 5 car search targets for the Pakistani used-car market.

═══════════════════════════════════════════════════════
STEP 1 — THINK BEFORE YOU OUTPUT (internal reasoning, never printed)
═══════════════════════════════════════════════════════
Before generating any JSON, silently answer these five questions using your own
automotive knowledge of the Pakistani market. Do not print your answers.

  Q1. DRIVETRAIN: Does the user want AWD / 4x4 / off-road? 
      If yes: for each candidate model you consider, ask yourself:
        - "Is this model actually sold with AWD in Pakistan right now?"
        - "Does this model have BOTH FWD and AWD variants in Pakistan?" (if yes → trim="AWD")
        - "Is this model natively 4x4 by default?" (if yes → trim="")
        - "Is this model FWD-only in Pakistan?" (if yes → EXCLUDE it from an AWD query)
      Use your training knowledge. You know which models are FWD-only in Pakistan
      (e.g. MG HS, Honda HR-V, Chery Tiggo 4 Pro, Haval Jolion are all FWD-only locally).

  Q2. TRANSMISSION: Does the user want automatic/AGS/CVT?
      If yes: for each locally-assembled Suzuki you consider, ask yourself:
        - "Did this exact model and year range actually come with an automatic in Pakistan?"
        - You know that old-shape Cultus (pre-2018), old Alto (pre-2019), and old WagonR
          (pre-2020) were manual-only. If the budget forces you into that year range,
          pick a genuine automatic instead (Vitz, Mira, old City, Dayz, old Civic Prosmatec).

  Q3. BUDGET vs. GENERATION:
      - Budget given → min_year = 0. Let the budget filter naturally.
      - No budget given → min_year = first model year of the CURRENT generation of each car.
        Use your knowledge: Civic current gen = 2022, Sportage = 2022, Corolla = 2022, etc.

  Q4. TRIM flag:
      trim = "AWD"    → only when user wants AWD and the model has both FWD and AWD in Pakistan
      trim = "Hybrid" → only when user explicitly requests hybrid/HEV
      trim = "EV"     → only when user explicitly requests electric
      trim = "Manual" → only when user explicitly requests manual on a dual-transmission model
      trim = "Diesel" → only when user explicitly requests diesel on a dual-fuel model
      trim = ""       → ALL other cases, including sunroof, leather, turbo, panoramic roof.
                         For those, pick the MODEL that has them as standard.

  Q5. DIVERSITY: Do my 5 picks span at least 3 different makes?
      If not, swap one of the duplicates for an equally strong alternative.

═══════════════════════════════════════════════════════
STEP 2 — OUTPUT CONTRACT (non-negotiable)
═══════════════════════════════════════════════════════
Output ONLY a raw JSON array. Zero preamble. Zero explanation. Zero markdown.
The array must contain EXACTLY 5 objects, each with these EXACT 7 keys:

  "make"       → String. Brand name exactly as listed on PakWheels.
  "model"      → String. Model name exactly as listed on PakWheels.
  "trim"       → String. Set via Q4 reasoning above. Default is always "".
  "city"       → String. User’s city if mentioned, else "" (never null).
  "max_budget" → Integer. Budget in PKR. 0 if not mentioned (never null).
  "min_year"   → Integer. Set via Q3 reasoning above. 0 means no floor.
  "rationale"  → String. 1–2 punchy sentences: why this specific car for this user.

═══════════════════════════════════════════════════════
FEW-SHOT EXAMPLES
═══════════════════════════════════════════════════════
These show correct reasoning applied to real edge cases.

──────────────────────────────────────
USER: "AWD crossover with panoramic sunroof under 80 lacs in Lahore"
Q1: AWD wanted. Sportage → dual-variant → trim=AWD. Tucson → dual-variant → trim=AWD.
    Haval H6 → dual-variant → trim=AWD. MG HS → FWD-only → EXCLUDED.
    HR-V → FWD-only → EXCLUDED. Tiggo 4 Pro → FWD-only → EXCLUDED.
    Fortuner → native 4x4 → trim="". Sorento → dual → trim=AWD.
Q2: No transmission constraint.
Q3: Budget given → min_year=0. Q4: AWD → trim=AWD/blank per above. Q5: 4 makes ✓.
──────────────────────────────────────
[
  {"make":"Kia","model":"Sportage","trim":"AWD","city":"Lahore","max_budget":8000000,"min_year":0,"rationale":"5th gen NQ5 AWD comes with panoramic sunroof as standard — Pakistan’s top-selling 4x4 crossover with great resale."},
  {"make":"Hyundai","model":"Tucson","trim":"AWD","city":"Lahore","max_budget":8000000,"min_year":0,"rationale":"AWD Tucson pairs European ride quality with a panoramic roof and ADAS — polished family crossover at this budget."},
  {"make":"Haval","model":"H6","trim":"AWD","city":"Lahore","max_budget":8000000,"min_year":0,"rationale":"H6 2.0T is the only AWD Chinese crossover at this price with a massive panoramic roof and 9-speed DCT."},
  {"make":"Toyota","model":"Fortuner","trim":"","city":"Lahore","max_budget":8000000,"min_year":0,"rationale":"Body-on-frame 4x4 — every variant is 4WD; unmatched reliability and resale if off-road credentials matter."},
  {"make":"Kia","model":"Sorento","trim":"AWD","city":"Lahore","max_budget":8000000,"min_year":0,"rationale":"3-row AWD monocoque SUV — more cabin space than Sportage while meeting the 4x4 requirement."}
]

──────────────────────────────────────
USER: "cheap automatic for a student, budget 18 lacs"
Q1: No AWD. Q2: Automatic requested + budget < 20 lacs.
    Ask: "Did old Cultus/Alto come with auto at this price range?"
    Old Cultus (pre-2018) → manual-only. Old Alto (pre-2019) → manual-only.
    At 18 lacs these would all be the manual-only old shapes. EXCLUDE them.
    Genuine cheap autos: Vitz, Mira, old City auto, Dayz, old Civic Prosmatec.
Q3: Budget given → min_year=0. Q4: trim="" (auto is standard on all picks). Q5: 4 makes ✓.
──────────────────────────────────────
[
  {"make":"Toyota","model":"Vitz","trim":"","city":"","max_budget":1800000,"min_year":0,"rationale":"Japanese imported hatchback with a proven auto CVT — 2005–2010 units fit this budget and run indefinitely."},
  {"make":"Daihatsu","model":"Mira","trim":"","city":"","max_budget":1800000,"min_year":0,"rationale":"660cc Japanese automatic — ultra-light, excellent city fuel average, smooth CVT, easy to park."},
  {"make":"Honda","model":"City","trim":"","city":"","max_budget":1800000,"min_year":0,"rationale":"2004–2008 i-DSI Steermatic — spacious sedan with a genuine automatic, comfortable for daily commutes."},
  {"make":"Nissan","model":"Dayz","trim":"","city":"","max_budget":1800000,"min_year":0,"rationale":"Feature-rich 660cc Japanese auto with push-start and modern interior at a very accessible price."},
  {"make":"Honda","model":"Civic","trim":"","city":"","max_budget":1800000,"min_year":0,"rationale":"2004–2006 EXi Prosmatec — true automatic gearbox in a comfortable sedan; solid build, widely available."}
]

──────────────────────────────────────
USER: "automatic hatchback under 30 lacs, small car"
Q1: No AWD. Q2: Automatic requested. Budget 30 lacs → can reach new-shape Alto VXL (AGS 2019+)
    and new Cultus VXL (AGS 2018+). At 30 lacs, recent AGS units ARE in range. INCLUDE them.
Q3: Budget given → min_year=0. Q4: trim="" (all picks are auto). Q5: 3 makes ✓.
──────────────────────────────────────
[
  {"make":"Suzuki","model":"Alto","trim":"","city":"","max_budget":3000000,"min_year":2019,"rationale":"New-shape 660cc Alto VXL AGS — cheapest locally-assembled automatic in Pakistan with low running cost."},
  {"make":"Suzuki","model":"Cultus","trim":"","city":"","max_budget":3000000,"min_year":2018,"rationale":"New Celerio-shape Cultus VXL AGS — slightly roomier than Alto with the same automatic gearbox."},
  {"make":"Suzuki","model":"WagonR","trim":"","city":"","max_budget":3000000,"min_year":2020,"rationale":"New-shape WagonR VXL AGS — tallboy body with the most interior space of the Suzuki AGS trio."},
  {"make":"Toyota","model":"Vitz","trim":"","city":"","max_budget":3000000,"min_year":0,"rationale":"Japanese CVT automatic with a reliable reputation — 2010–2014 units comfortably within this range."},
  {"make":"Daihatsu","model":"Mira","trim":"","city":"","max_budget":3000000,"min_year":0,"rationale":"660cc Japanese CVT import — extremely fuel-efficient and easy to drive in city traffic."}
]

──────────────────────────────────────
USER: "hybrid gari chahiye, Islamabad mein"
Q1: No AWD. Q2: No transmission constraint (hybrid implies auto). Q3: No budget → min_year=current gen.
Q4: User said hybrid → trim="Hybrid". Q5: Spread across Toyota/Honda – add variety.
──────────────────────────────────────
[
  {"make":"Toyota","model":"Aqua","trim":"Hybrid","city":"Islamabad","max_budget":0,"min_year":2021,"rationale":"Most common hybrid in Pakistan — 25–28 km/l city average, parts everywhere, proven 2nd gen reliability."},
  {"make":"Toyota","model":"Prius","trim":"Hybrid","city":"Islamabad","max_budget":0,"min_year":2023,"rationale":"Roomier than Aqua with a smoother system — 20–24 km/l; ideal for families wanting hybrid comfort."},
  {"make":"Honda","model":"Vezel","trim":"Hybrid","city":"Islamabad","max_budget":0,"min_year":2022,"rationale":"3rd gen crossover hybrid — more ground clearance and cargo room than Aqua; great for Islamabad’s roads."},
  {"make":"Toyota","model":"Corolla Cross","trim":"Hybrid","city":"Islamabad","max_budget":0,"min_year":2022,"rationale":"Locally assembled hybrid SUV — Corolla reliability with crossover stance and factory economy."},
  {"make":"Toyota","model":"Fielder","trim":"Hybrid","city":"Islamabad","max_budget":0,"min_year":2015,"rationale":"Wagon-body hybrid with a massive boot — preferred by families needing practicality over SUV styling."}
]

──────────────────────────────────────
USER: "comfortable sedan chahiye, koi budget nahi"
Q1: No AWD. Q2: No transmission constraint. Q3: No budget → min_year=current gen per model.
Q4: trim="" (sedans don’t need trim filtering). Q5: 5 different makes ✓.
──────────────────────────────────────
[
  {"make":"Honda","model":"Civic","trim":"","city":"","max_budget":0,"min_year":2022,"rationale":"11th gen FE Civic — 1.5T turbo, Honda Sensing ADAS, sharpest-looking sedan on Pakistan’s roads right now."},
  {"make":"Toyota","model":"Corolla","trim":"","city":"","max_budget":0,"min_year":2022,"rationale":"12th gen on TNGA platform — better handling, refined cabin, and unbeatable Corolla resale value nationwide."},
  {"make":"Hyundai","model":"Elantra","trim":"","city":"","max_budget":0,"min_year":2021,"rationale":"7th gen CN7 — most striking exterior in class, turbocharged options, and genuinely premium interior feel."},
  {"make":"Changan","model":"Alsvin","trim":"","city":"","max_budget":0,"min_year":2021,"rationale":"Best-value Chinese sedan — turbo engine, touchscreen, competitive build quality at a price below Korean rivals."},
  {"make":"Kia","model":"Stonic","trim":"","city":"","max_budget":0,"min_year":2021,"rationale":"Locally assembled compact crossover-sedan — turbocharged with premium finishes usually above its price bracket."}
]
"""

# ---------------------------------------------------------------------------
# FALLBACK PROMPT — used only by get_fallback_recommendations()
# ---------------------------------------------------------------------------
# Intentionally compact. The full CoT SEMANTIC_MAPPER_PROMPT is 170+ lines;
# the fallback is a repair call, not a fresh mapping. We give Gemini just
# enough context to pick intelligent alternatives without re-explaining all
# rules. The same JSON schema and sanitizer are shared with semantic_mapper.
# ---------------------------------------------------------------------------
_FALLBACK_PROMPT = """\
You are GaariGuru, a Pakistani used-car expert. Some car models returned zero \
available listings. Your job is to generate replacement search targets.

STRICT RULES:
1. Output ONLY a raw JSON array — no preamble, no markdown.
2. Return EXACTLY the requested number of replacement objects.
3. NEVER repeat any model in the excluded list.
4. Apply the same logic as the original search (same drivetrain, budget, city, intent).
5. Use the same 7-key schema: make, model, trim, city, max_budget, min_year, rationale.
6. "trim" rules: "" by default. Only "AWD"/"Hybrid"/"EV"/"Diesel"/"Manual" when 
   the user's original intent explicitly required it.
7. "min_year": 0 if budget given, current-gen first year if no budget.
8. "max_budget": 0 means no ceiling. Never null.
9. Pick models with GOOD inventory depth on PakWheels/OLX in Pakistan — avoid 
   ultra-rare imports that will also return 0 results.
"""


# ---------------------------------------------------------------------------
# SHARED SANITIZER
# ---------------------------------------------------------------------------
def _sanitize_recommendations(raw_list: list, caller: str = "Recommender") -> list[dict]:
    """
    Validates and normalises a list of recommendation dicts from the LLM.
    Shared between semantic_mapper() and get_fallback_recommendations()
    to guarantee identical downstream contracts.

    Guarantees:
      - trim     → always str  (None → "")
      - max_budget → always int  (None → 0,  0 = no ceiling)
      - city     → always str  (None → "")
      - min_year → always int  (None → 0,  0 = no floor)
      - make + model → both non-empty (malformed entries are dropped with a log)
    """
    sanitized = []
    for r in raw_list:
        if r.get("trim") is None:
            r["trim"] = ""
        if r.get("max_budget") is None:
            r["max_budget"] = 0
        if r.get("city") is None:
            r["city"] = ""

        raw_year = r.get("min_year")
        try:
            r["min_year"] = int(raw_year) if raw_year else 0
        except (TypeError, ValueError):
            r["min_year"] = 0

        if not r.get("make") or not r.get("model"):
            print(f"[{caller}] Skipping malformed entry (no make/model): {r}")
            continue

        sanitized.append(r)

    return sanitized


# ---------------------------------------------------------------------------
# SHARED RAW-RESPONSE PARSER
# ---------------------------------------------------------------------------
def _parse_llm_json(raw_text: str) -> list:
    """Strips markdown fences and parses the LLM's JSON array response."""
    raw = raw_text.strip()
    raw = re.sub(r'^```(?:json)?\s*', '', raw, flags=re.MULTILINE)
    raw = re.sub(r'\s*```$', '', raw, flags=re.MULTILINE)
    return json.loads(raw.strip())


async def semantic_mapper(user_prompt: str) -> list[dict]:
    """
    Calls Gemini Flash Lite to translate a natural language requirement into
    exactly 5 structured car search targets.

    Returns an empty list on any failure — the route handles the fallback.
    """
    raw = ""
    try:
        response = await client.aio.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=user_prompt,
            config=types.GenerateContentConfig(
                temperature=0.25,        # Low temp → tight, consistent JSON
                max_output_tokens=1600,  # 5 objects × ~320 tokens each
                system_instruction=SEMANTIC_MAPPER_PROMPT,
            ),
        )

        raw = response.text
        recommendations = _parse_llm_json(raw)

        if not isinstance(recommendations, list):
            raise ValueError("Expected JSON array, got: " + type(recommendations).__name__)

        sanitized = _sanitize_recommendations(recommendations, caller="SemanticMapper")

        if not sanitized:
            raise ValueError("All recommendations were malformed after sanitization")

        print(f"[SemanticMapper] → {len(sanitized)} targets:")
        for r in sanitized:
            trim_label   = f" [{r['trim']}]" if r["trim"] else ""
            budget_label = f"PKR {r['max_budget']:,}" if r["max_budget"] else "no limit"
            year_label   = f" from {r['min_year']}" if r["min_year"] else ""
            print(f"  → {r['make']} {r['model']}{trim_label}{year_label} | {budget_label} | city={r['city'] or 'any'}")

        return sanitized

    except json.JSONDecodeError as e:
        print(f"[SemanticMapper] JSON parse error: {e}")
        print(f"[SemanticMapper] Raw output was: {raw[:500]}")
        return []
    except Exception as e:
        print(f"[SemanticMapper] Failed: {e}")
        traceback.print_exc()
        return []


async def get_fallback_recommendations(
    user_prompt: str,
    failed_targets: list[str],
    tried_models: list[str],
    city: str,
    budget: int | None,
    count: int,
) -> list[dict]:
    """
    Asks Gemini Flash Lite to generate `count` replacement search targets for
    models that returned zero listings.

    Args:
        user_prompt:    The original user query (for intent context).
        failed_targets: Human-readable labels of failed targets, e.g.
                        ["Haval H6 [AWD]", "Kia Sorento [AWD]"].
        tried_models:   All make+model strings already tried (initial + any
                        prior fallbacks), used as a hard exclusion list.
        city:           Effective city from the search (may be "" for any city).
        budget:         Effective budget in PKR, or None for no ceiling.
        count:          How many replacement targets to generate (1–3).

    Returns:
        A sanitized list of recommendation dicts (may be shorter than `count`
        if the LLM returns malformed entries). Returns [] on any error.
    """
    if count < 1:
        return []

    budget_str   = f"PKR {budget:,}" if budget else "no budget limit"
    city_str     = city or "any city"
    excluded_str = ", ".join(tried_models) if tried_models else "none"
    failed_str   = ", ".join(failed_targets)

    fallback_prompt = (
        f"Original user request: \"{user_prompt}\"\n"
        f"City: {city_str} | Budget: {budget_str}\n\n"
        f"These targets returned ZERO active listings and need replacements:\n"
        f"  {failed_str}\n\n"
        f"EXCLUDED models (already tried — do not repeat these):\n"
        f"  {excluded_str}\n\n"
        f"Generate EXACTLY {count} replacement target(s) that:\n"
        f"  - Match the same user intent as the original request\n"
        f"  - Have good inventory depth on PakWheels/OLX in Pakistan\n"
        f"  - Are NOT any model in the excluded list above\n"
        f"Output a raw JSON array of EXACTLY {count} object(s). No preamble."
    )

    raw = ""
    try:
        response = await client.aio.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=fallback_prompt,
            config=types.GenerateContentConfig(
                temperature=0.20,                    # Tighter than mapper — follow exclusions strictly
                max_output_tokens=count * 350,       # ~350 tokens per replacement object
                system_instruction=_FALLBACK_PROMPT,
            ),
        )

        raw = response.text
        replacements = _parse_llm_json(raw)

        if not isinstance(replacements, list):
            raise ValueError("Expected JSON array from fallback, got: " + type(replacements).__name__)

        sanitized = _sanitize_recommendations(replacements, caller="FallbackMapper")

        # Hard-enforce exclusion list — the LLM sometimes ignores it
        tried_lower = {m.lower().replace(" ", "") for m in tried_models}
        enforced = []
        for r in sanitized:
            key = f"{r['make']}{r['model']}".lower().replace(" ", "")
            if key in tried_lower:
                print(f"[FallbackMapper] LLM ignored exclusion for {r['make']} {r['model']} — dropping")
                continue
            enforced.append(r)

        print(f"[FallbackMapper] Generated {len(enforced)} replacement(s) for: {failed_str}")
        for r in enforced:
            trim_label = f" [{r['trim']}]" if r["trim"] else ""
            print(f"  ↳ {r['make']} {r['model']}{trim_label}")

        return enforced

    except json.JSONDecodeError as e:
        print(f"[FallbackMapper] JSON parse error: {e}")
        print(f"[FallbackMapper] Raw output was: {raw[:400]}")
        return []
    except Exception as e:
        print(f"[FallbackMapper] Failed: {e}")
        traceback.print_exc()
        return []