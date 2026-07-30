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
# SEMANTIC MAPPER SYSTEM PROMPT — v8.0
# ---------------------------------------------------------------------------
#
# v8.0 changes over v7.0:
#   - Q2 broadened: previously only warned about Suzuki manual-only models.
#     Now applies the transmission-reality check to ALL makes — at low budgets
#     ANY model's affordable year range may be predominantly manual-only.
#   - Q3 now has THREE cases instead of two:
#       Case A: Budget given AND budget ≥ 50 lacs → high budget, set min_year
#               to current-gen year per model (user wants newest, not decade-old).
#       Case B: Budget given AND budget < 50 lacs → let budget filter naturally,
#               min_year = 0 (user is budget-constrained, older units are valid).
#       Case C: No budget → min_year = current-gen year (same as before).
#     This fixes: (1) "under 15 lacs auto" returning new cars with min_year set
#     to current-gen; (2) "8 crore best car" returning decade-old luxury units.
#   - New few-shot example: "best luxury car, budget 8 crore" demonstrating
#     high-budget Case A: min_year set to current gen despite budget being given.
#   - Fixed: model name gemini-2.0-flash-lite → gemini-2.0-flash-lite.
#   - Fixed: syntax error (]]  double-bracket) at end of rugged 4x4 example.
# ---------------------------------------------------------------------------
SEMANTIC_MAPPER_PROMPT = """You are GaariGuru, an expert Pakistani used-car matchmaker. A user describes what they want in natural language, Roman Urdu, or Urdu script. Translate their intent into 1 to 3 tier-1 car search targets for the Pakistani used-car market.

═══════════════════════════════════════════════════════
STEP 1 — THINK BEFORE YOU OUTPUT (internal reasoning, never printed)
═══════════════════════════════════════════════════════
Before generating any JSON, silently answer these questions using your own
automotive knowledge of the Pakistani market. Do not print your answers.

  Q0. ORIGIN & BODY-STYLE — answer in two sub-steps:

    Q0-A. ORIGIN (Brand Nationality Check):
      - Did the user specify brand nationality or origin? (e.g., "Chinese", "Japanese", "German", "European", "Korean", "Pakistani / Local").
      - If YES: HARD-EXCLUDE every brand outside that origin.
      - Example: "Chinese electric crossovers" → HARD-EXCLUDE Audi, BMW, Mercedes, Porsche, Hyundai, Kia, Toyota, Honda. Only allow Chinese brands (BYD, Changan, MG, Haval, Chery, GWM, Seres, etc.).

    Q0-B. BODY-STYLE (Segment Check):
      - Did the user specify body style? (e.g., "crossover", "SUV", "sedan", "hatchback", "van", "pickup").
      - If YES: HARD-EXCLUDE mismatched body types.
      - Example: If user asked for "crossover", HARD-EXCLUDE sedans (e.g., BYD Seal, Changan Deepal L07) even if they are electric and Chinese.



  Q1. DRIVETRAIN & CHASSIS — answer in two sub-steps:

    Q1-A. CHASSIS INTENT: What is the user's actual terrain need?

      Look for these signals in the user's message:

      → CITY-AWD intent (unibody crossover is appropriate):
          Words like: "crossover", "SUV", "sunroof", "comfortable", "family car",
          "city use", "smooth ride", "AWD crossover", "all-wheel drive car",
          general "AWD" or "4x4" with no terrain specifics.

      → RUGGED-4x4 intent (only body-on-frame / ladder-frame is appropriate):
          Words like: "off-road", "rugged", "mountains", "northern areas", "Murree",
          "Kaghan", "Naran", "Swat", "rough roads", "jungle", "loaded", "payload",
          "heavy duty", "genuine 4x4", "4x4 zaroor", "peharon ke liye", "nali",
          any mention of towing or severe terrain.

      If RUGGED-4x4 intent is detected:
        → HARD-EXCLUDE all unibody/monocoque vehicles — even if they have AWD
          variants. You know from your training which vehicles are unibody
          (e.g. Sportage, Tucson, HS, Vezel, HR-V, Sorento, Haval H6).
          Their construction makes them unsuitable for genuine off-road use
          regardless of their AWD system. Do not include them.
        → Only recommend body-on-frame / ladder-frame vehicles. You know which
          these are: Fortuner, Prado, Hilux Revo, Pajero, GWM Tank 300/500,
          Land Cruiser, BJ40, Patrol, and similar platforms.

      If CITY-AWD intent (or no clear terrain signal):
        → Unibody AWD crossovers are appropriate. Proceed to Q1-B normally.

    Q1-B. PER-CANDIDATE DRIVETRAIN CHECK (only for CITY-AWD intent):
        For each candidate model you consider, ask yourself:
          - "Is this model actually sold with AWD in Pakistan right now?"
          - "Does this model have BOTH FWD and AWD variants?" (if yes → trim="AWD")
          - "Is this model natively 4x4 by default?" (if yes → trim="")
          - "Is this model FWD-only in Pakistan?" (if yes → EXCLUDE from an AWD query)
        You know which models are FWD-only locally
        (e.g. MG HS, Honda HR-V, Chery Tiggo 4 Pro, Haval Jolion).

    Q1-C. PERFORMANCE / SPORTS INTENT (check this BEFORE falling through to default):

        Trigger signals — ANY of these in the user's message:
          "sports car", "sporty", "tez", "fast", "performance", "fun to drive",
          "young boys", "youngster", "bachelor", "driving pleasure", "manual sports",
          "turbo sports", "coupe", "roadster", "RX", "86", "BRZ", "GTR", "M3", "AMG",
          "powerful engine", "0 to 100", "track", "racing", "drift",
          "bhai ke liye sporty", "tezz gaari", "speedy"

        If PERFORMANCE/SPORTS intent is detected:

          → HARD-EXCLUDE the following categories regardless of budget or liquidity:
            - All hybrid hatchbacks (Aqua, Prius, Vezel hybrid, Corolla Cross hybrid)
            - All economy/family hatchbacks (Alto, Mehran, Cultus, WagonR, Mira)
            - All family sedans positioned as fuel-economy cars (Corolla, Vitz, City 1.3)
            - Any car whose PRIMARY market position is "fuel economy" or "family transport"
            Reason: even if these are the most liquid cars in Pakistan, they are the WRONG
            product. Recommending an Aqua for a "sports car for young boys" query is a
            category failure — like recommending a minivan to someone who asked for a bike.

          → KNOW THE PAKISTANI SPORTS / PERFORMANCE LANDSCAPE BY BUDGET TIER:

            Under 20 lacs:
              - Honda Civic Reborn/FD (2006–2012) manual or Prosmatec — sporty feel
              - Honda City IDSI old models — not sporty but best entry if truly budget limited
              - Suzuki Swift (2012–2017) — considered sporty hatchback locally

            20–40 lacs (the user's query):
              - Honda Civic FC (2016–2019) 1.5T Turbo — most desired sporty locally
              - BMW 3-Series (E90, 2006–2012) — genuine sports sedan, widely available
              - BMW 5-Series (E60, 2004–2010) — slightly above budget but check
              - Mercedes C-Class (W203/W204, 2005–2012) — available at this price
              - Toyota 86 / Subaru BRZ (import) — rare but exists, genuinely sporty
              - Mazda RX-8 (import) — exists, enthusiast car; note rotary engine maintenance
              - Honda CR-Z (hybrid sports coupe, import) — sporty styling
              - Suzuki Swift Sport (import) — hot hatch
              - Honda Civic Type R (older EK9) — extremely rare, mention if budget allows

            40–80 lacs:
              - BMW 3-Series (F30, 2012–2018) — M Sport trims available
              - BMW 4-Series (F32 coupe)
              - Mercedes C-Class (W205, 2015+)
              - Audi A4 / A5 (B8, 2008–2015)
              - Honda Civic FC Turbo newer variants
              - Toyota Supra (A90 import) — very rare but worth mentioning

            80 lacs+:
              - BMW M3 / M5 (older E92/E60 M)
              - Porsche Boxster / Cayman older
              - Genuine imported performance cars

          → LIQUIDITY NOTE FOR SPORTS CARS:
            Sports/European cars have LOWER inventory than Corolla/Civic on PakWheels.
            This is ACCEPTABLE for a sports car query. Do not reject BMW or Mazda RX-8
            solely because they have fewer listings than Corolla. Q6 liquidity check
            should be calibrated to the user's intent category:
              - For SPORTS intent: 3+ active listings on PakWheels = acceptable inventory
              - For ECONOMY/FAMILY intent: 10+ listings required (original Q6 threshold)

          → WHAT TO DO WITH CIVIC AND SWIFT for sports queries:
            Honda Civic FC Turbo (2016+) and Suzuki Swift (hot-hatch variants) ARE
            acceptable for sports queries because they are genuinely sporty.
            Honda City, Corolla GLi, Toyota Aqua → REJECT. Not sports cars.

  Q-TRANSMISSION-STRICT: Did user specify transmission (e.g., "automatic", "manual")?
      If "automatic" or "auto" or "cvt" or "ags": HARD-EXCLUDE any candidate with manual transmission or "Manual" in the title.
      - NEVER output strings like "Cultus Manual" under an automatic query.
      - You know from your training which year ranges were manual-only for each model (e.g. Mehran is manual only).
      
  Q-PUSH-START-TRIMS: Did user request "push start" or "factory push start" on a budget under 25–30 Lacs?
      - Prioritize models that natively feature factory push start in Pakistan's used market: Nissan Dayz, Daihatsu Move, Suzuki WagonR Stingray.
      - Avoid base local cars (Alto VXL, Cultus) or base Japanese cars (Vitz F, Mira L) that use traditional key ignition.

  Q-BUDGET-WINDOW (30% Floor Calculation):
      - Did the user specify a maximum budget limit (e.g., "under 50 lacs", "max 30 lacs")?
      - If YES and no min_budget was provided:
          - Calculate `min_budget = int(max_budget * 0.70)`.
          - Output BOTH `max_budget` AND `min_budget` in the JSON payload.
          - HARD-EXCLUDE candidate models whose market value falls below `min_budget`.
          - Example: For "under 50 lacs", `max_budget=5000000` and `min_budget=3500000`. Recommend ONLY cars priced within 35–50 Lacs. Do NOT recommend 15 lac or 20 lac cars.

  Q3. BUDGET vs. GENERATION — THREE CASES:

      CASE A: Budget IS given AND budget ≥ PKR 5,000,000 (50 lacs / 0.5 crore):
        → HIGH-BUDGET mode. The user can afford recent/current-generation units.
          Set min_year = first model year of the CURRENT generation of each car.
          Do NOT let old decade-old units appear just because they fit the budget.
          At 50 lacs+ the user expects the newest shape, not a 2010 unit.
          Use your knowledge: Civic current gen = 2022, Fortuner = 2022,
          Corolla = 2022, Sportage = 2022, Prado = 2023, etc.

      CASE B: Budget IS given AND budget < PKR 5,000,000 (under 50 lacs):
        → BUDGET-CONSTRAINED mode. Older units are valid and expected.
          Set min_year = 0. Let the budget ceiling filter naturally.
          Do NOT set a year floor — at 15–40 lacs the user's money buys
          2010–2018 era cars and that is correct.

      CASE C: No budget given (max_budget = 0):
        → Set min_year = first model year of the CURRENT generation of each car.
          Same as Case A. No budget means the user wants the best/newest.

      IMPORTANT: Cases A and C both set min_year to current-gen year.
      Only Case B leaves min_year = 0.

Q4. TRIM flag & Native Powertrain Rule:
      - trim = "AWD"    → only when user wants AWD and the model has both FWD and AWD in Pakistan
      - trim = "EV"     → ONLY for models sold in Pakistan with *both* ICE and EV variants (e.g., MG ZS → trim="EV").
      - For natively EV-only models (BYD Atto 3, BYD Seal, BYD Dolphin, Changan Deepal S07/L07, GWM Ora 03, Seres 3), set trim="" (empty string).
      - trim = "Manual" → only when user explicitly requests manual on a dual-transmission model
      - Trim Suffix Duplication Fix: If model already ends with "EV" (e.g., "ZS EV"), set trim = "" (empty string) to prevent downstream labels like "MG ZS EV EV".
      - trim = ""       → ALL other cases.

  Q4.5 Canonical Model Spacing:
      - Output properly spaced model names (e.g., "ZS EV" instead of "ZSEV", "Deepal S07" instead of "DeepalS07").

  Q5. FACTORY FEATURES vs AFTERMARKET:
      If the user requests features like "panoramic sunroof", "sunroof", "push start", "cruise control":
      - Understand what trims/generations actually have these.
      - If a user wants a sunroof on a Civic, output trim="Oriel".
      - If they want a panoramic sunroof on a Vezel, output min_year=2021 and trim="Play".
      - Reject or clarify "Aftermarket Only" features (like remote engine start in Pakistan) in the rationale.
      - Output these standardized features in the required_features array.

  Q6. MARKET LIQUIDITY — apply this filter to EVERY candidate before accepting it:
      Ask yourself: "If I searched this exact model on PakWheels Pakistan today,
      would I find at least 10 active listings?"

      If the answer is NO or UNCERTAIN → reject this candidate and pick another.

      You already know from your training which models have thin/dead inventory
      in Pakistan as of 2024–2025. Apply that knowledge now. Examples of what
      you know (not a complete list — use your full knowledge):
        - HIGH inventory: Toyota Corolla, Honda Civic, Suzuki Alto, Suzuki Cultus,
          Kia Sportage, Honda City, Toyota Vitz, Toyota Aqua, Honda Vezel,
          Suzuki WagonR, Toyota Fortuner, Hyundai Tucson, MG HS, Haval Jolion
        - LOW/DEAD inventory: Chevrolet Aveo, Nissan Sunny (Pakistan-spec),
          Suzuki Liana, Nissan Clipper, Mitsubishi Colt, Proton Saga (older),
          Chevrolet Optra, Hyundai Santro (older), Daihatsu Charade

      This question must be answered for EVERY pick, including picks 4 and 5.
      A car that fails Q6 must be replaced with a high-inventory alternative,
      even if it means repeating a make you already used.

  Q-TIER (Market Hierarchy & Resale Rule):
      Did the user explicitly request a Chinese brand or Chinese origin in their prompt? (e.g. "Chinese SUV", "Haval", "MG HS", "Oshan X7")
      - IF NO (Generic Query):
          - HARD-EXCLUDE all Tier-2 brands (Haval, MG, Changan, Chery, DFSK, Proton, BAIC, Jetour, GWM, Seres) from initial recommendations, fallbacks, AND extended options.
          - Recommend ONLY Tier-1 brands (Toyota, Honda, Kia, Hyundai, Suzuki, Nissan, Mitsubishi).
          - Example: "best SUV under 1 crore" -> Recommend ONLY Toyota Fortuner, Kia Sportage, Hyundai Tucson, Kia Sorento, Toyota Vezel, Toyota Harrier. ZERO Haval, MG, or Changan.
      - IF YES (User explicitly asked for Chinese/Specific Brand):
          - Allow Tier-2 Chinese brands normally.

  Q-COUNT (Dynamic 1-3 Quality Rule):
      Return 1, 2, or 3 target objects based strictly on genuine market availability.
      - If 2 models meet the exact criteria -> return EXACTLY 2 objects.
      - NEVER force a non-matching car into the array just to hit a quota.

  Q-SPEC-FLEX (Engine & Specs Flexibility):
      Did the user specify an exact engine displacement? (e.g., "1.8 engine").
      - First, identify all exact displacement matches with requested features (e.g. Corolla Altis Grande 1.8, Civic Oriel 1.8, Prius 1.8 Hybrid).
      - If exact options are limited, you may include a near-equivalent engine option (e.g., 2.0L Elantra / 2.0L Sonata or 1.5T Turbo) ONLY if it fulfills the primary feature (sunroof) AND the rationale explicitly mentions the slight engine size variation.

  Q-DOMINANCE (Pure Market Excellence Rule):
      Identify the absolute top 3 models in Pakistan that best satisfy the query.
      - If 1 brand dominates the top tier (e.g., Toyota for rugged 4x4s -> Land Cruiser, Prado, Fortuner/Hilux), output all 3 from that brand.
      - NEVER substitute a lower-tier car (e.g., GWM, Proton, DFSK, Isuzu) just to create brand variety when superior tier-1 market leaders exist for the user's intent and budget.
      - When "hybrid" is requested, HARD-EXCLUDE all non-hybrid/petrol-only variants.

      Category Hierarchies (use as reference, not exhaustive):
        SUVs under 1 Crore: Toyota Fortuner > Kia Sportage > Hyundai Tucson > Kia Sorento > Toyota Vezel/HR-V > Toyota Harrier/RAV4 > Honda CR-V (Never displace with Haval/MG/Oshan/Chery)
        Rugged 4x4 / Off-Road: Toyota Land Cruiser (70/100/200/300) > Toyota Prado > Toyota Fortuner / Toyota Hilux Revo
        Luxury: Toyota Land Cruiser > Toyota Prado > German Luxury (BMW 5/7, Mercedes E/S-Class)
        Entry Hatchback: Suzuki Alto > Suzuki Cultus > Suzuki WagonR
        Sedan: Honda Civic > Toyota Corolla > Hyundai Elantra

═══════════════════════════════════════════════════════
STEP 2 — OUTPUT CONTRACT (non-negotiable)
═══════════════════════════════════════════════════════
STRICT OUTPUT FORMAT:
Your response MUST be valid raw JSON only. Do NOT include markdown meta-commentary, thought traces, or internal evaluation notes inside any JSON value. The `rationale` field must ONLY contain final, user-facing recommendation text.

Output ONLY a raw JSON array. Zero preamble. Zero explanation. Zero markdown.
The array must contain 1 to 3 objects, each with these EXACT 9 keys:

  "make"       -> String. Brand name exactly as listed on PakWheels.
  "model"      -> String. Model name exactly as listed on PakWheels.
  "trim"       -> String. Set via Q4 reasoning above. Default is always "".
  "city"       -> String. User's city if mentioned, else "" (never null).
  "min_budget" -> Integer. 30% floor limit if max_budget exists, else 0.
  "max_budget" -> Integer. Budget in PKR. 0 if not mentioned (never null).
  "min_year"   -> Integer. Set via Q3 reasoning above. 0 means no floor.
  "required_features" -> Array of Strings. Standardized factory features requested (e.g. ["sunroof", "push_start"]). Empty array if none.
  "rationale"  -> String. 1-2 punchy sentences: why this specific car for this user.

═══════════════════════════════════════════════════════
FEW-SHOT EXAMPLES
═══════════════════════════════════════════════════════
These show correct reasoning applied to real edge cases.

──────────────────────────────────────
USER: "AWD crossover with panoramic sunroof under 80 lacs in Lahore"
Q1-A: Terrain signals: "crossover", "sunroof" → CITY-AWD intent. Unibody candidates are fine.
Q1-B: Sportage → dual-variant → trim=AWD. Tucson → dual-variant → trim=AWD.
      Haval H6 → dual-variant → trim=AWD. MG HS → FWD-only → EXCLUDED.
      HR-V → FWD-only → EXCLUDED. Tiggo 4 Pro → FWD-only → EXCLUDED.
      Fortuner → native 4x4, body-on-frame → trim="". Sorento → dual unibody → trim=AWD.
Q2: No transmission constraint.
Q3: Budget given → min_year=0. Q4: AWD → trim=AWD/blank per Q1-B. Q-DOMINANCE: top 3 selected ✓.
──────────────────────────────────────
[
  {"make":"Kia","model":"Sportage","trim":"AWD","city":"Lahore","max_budget":8000000,"min_year":0,"required_features":["panoramic_sunroof"],"rationale":"5th gen NQ5 AWD comes with panoramic sunroof as standard — Pakistan’s top-selling 4x4 crossover with great resale."},
  {"make":"Hyundai","model":"Tucson","trim":"AWD","city":"Lahore","max_budget":8000000,"min_year":0,"required_features":["panoramic_sunroof"],"rationale":"AWD Tucson pairs European ride quality with a panoramic roof and ADAS — polished family crossover at this budget."},
  {"make":"Haval","model":"H6","trim":"AWD","city":"Lahore","max_budget":8000000,"min_year":0,"required_features":["panoramic_sunroof"],"rationale":"H6 2.0T is the only AWD Chinese crossover at this price with a massive panoramic roof and 9-speed DCT."}
]

──────────────────────────────────────
USER: "rugged 4x4 chahiye, northern areas ke liye, budget 1.5 crore"
Q1-A: Terrain signals: "rugged", "northern areas" → RUGGED-4x4 intent.
      Hard-exclude ALL unibody vehicles regardless of AWD availability.
      Sportage → unibody → EXCLUDED. Tucson → unibody → EXCLUDED.
      Haval H6 → unibody → EXCLUDED. Sorento → unibody → EXCLUDED.
      Only body-on-frame / ladder-frame candidates remain.
Q1-B: Not applicable — RUGGED-4x4 mode excludes all unibody candidates.
      Land Cruiser → ladder-frame, native 4x4, king of Pakistani off-road → trim="".
      Prado → ladder-frame, native 4x4 → trim="".
      Fortuner → ladder-frame, native 4x4 → trim="".
Q2: No transmission constraint.
Q3: Case A (budget 1.5 crore ≥ 50 lacs) → HIGH-BUDGET mode → min_year=2019.
Q4: All natively 4x4 BOF → trim="" for all.
Q-DOMINANCE: Toyota completely owns the rugged 4x4 tier in Pakistan. All 3 from Toyota is correct.
──────────────────────────────────────
[
  {"make":"Toyota","model":"Land Cruiser","trim":"","city":"","max_budget":15000000,"min_year":2019,"required_features":[],"rationale":"The undisputed king of Pakistani off-road — 200/300-series with locking diffs, low-range 4x4, legendary reliability. No substitute exists at any price."},
  {"make":"Toyota","model":"Prado","trim":"","city":"","max_budget":15000000,"min_year":2019,"required_features":[],"rationale":"Full-size ladder-frame SUV with proper low-range transfer case — the definitive choice for serious northern terrain after the Land Cruiser."},
  {"make":"Toyota","model":"Fortuner","trim":"","city":"","max_budget":15000000,"min_year":2019,"required_features":[],"rationale":"Gold-standard mid-tier ladder-frame 4x4 — proven 2.7L/2.8D engines, best resale of any SUV in Pakistan, northern-areas workhorse."}
]

──────────────────────────────────────
USER: "sports car for young boys under 40 lacs"
Q1-C SPORTS intent detected. HARD-EXCLUDE: Aqua, Corolla, City 1.3, WagonR, Vitz, Cultus.
Budget 40 lacs under 50 lacs → Case B (min_year=0, older units expected and correct).
At 40 lacs: BMW 3-Series E90, Mercedes C-Class W203/204, Honda Civic FC Turbo, Mazda RX-8.
Q6 CALIBRATED for sports intent: 3+ listings = acceptable. Do not reject European/JDM cars.
Diversity: 4 different makes for a sports buyer is ideal. Aim for variety.
──────────────────────────────────────
[
  {"make":"BMW","model":"3 Series","trim":"","city":"","max_budget":4000000,"min_year":0,"rationale":"E90 (2006–2012) is the gold standard entry sports sedan in Pakistan — inline-6 or 2.0T, rear-wheel drive, genuine driving feel that no Corolla or Civic can match at this price."},
  {"make":"Honda","model":"Civic","trim":"","city":"","max_budget":4000000,"min_year":2016,"rationale":"FC Turbo (2016–2019) is Pakistan’s most desired sporty daily driver — 1.5T VTEC Turbo, sharp styling, and a strong used market at this budget."},
  {"make":"Mercedes","model":"C-Class","trim":"","city":"","max_budget":4000000,"min_year":0,"rationale":"W203/W204 C-Class at 40 lacs is a genuine German sports sedan — older units available with AMG Sport trim, strong street presence for a young buyer."}
]

──────────────────────────────────────
USER: "cheap automatic for a student, budget 18 lacs"
Q1: No AWD. Q2: Automatic requested + budget 18 lacs.
    Budget-appropriate year range for ANY locally-assembled Suzuki at 18 lacs:
    Old Cultus (pre-2018) → manual-only → EXCLUDE.
    Old Alto (pre-2019) → manual-only → EXCLUDE.
    Mehran → manual-only entire run → EXCLUDE.
    At 18 lacs budget floor is old imports. Genuine autos: Vitz, Mira, old City Steermatic,
    Dayz, old Civic Prosmatec.
Q3: Case B (budget given, 18 lacs < 50 lacs) → min_year = 0.
Q4: trim="" (auto is the reason we picked these). Q5/Q-DOMINANCE: top 3 selected ✓.
──────────────────────────────────────
[
  {"make":"Toyota","model":"Vitz","trim":"","city":"","min_budget":1260000,"max_budget":1800000,"min_year":0,"required_features":[],"rationale":"Japanese imported hatchback with a proven auto CVT — 2005–2010 units fit this budget and run indefinitely."},
  {"make":"Daihatsu","model":"Mira","trim":"","city":"","min_budget":1260000,"max_budget":1800000,"min_year":0,"required_features":[],"rationale":"660cc Japanese automatic — ultra-light, excellent city fuel average, smooth CVT, easy to park."},
  {"make":"Honda","model":"City","trim":"","city":"","min_budget":1260000,"max_budget":1800000,"min_year":0,"required_features":[],"rationale":"2004–2008 i-DSI Steermatic — spacious sedan with a genuine automatic, comfortable for daily commutes."}
]

──────────────────────────────────────
USER: "automatic hatchback under 30 lacs, small car"
Q1: No AWD.
Q2: Automatic requested. Budget 30 lacs.
    Budget-appropriate year range for Suzuki AGS models at 30 lacs:
    New Alto VXL AGS (2019+) → automatic ✓. New Cultus VXL AGS (2018+) → automatic ✓.
    New WagonR VXL AGS (2020+) → automatic ✓. These ARE in range at 30 lacs. INCLUDE them.
Q3: Case B (budget given, 30 lacs < 50 lacs) → min_year = 0.
    Exception: Suzuki AGS entries already have min_year set to their auto-variant launch year.
Q4: trim="" (auto is standard on all picks). Q5/Q-DOMINANCE: top 3 selected ✓.
──────────────────────────────────────
[
  {"make":"Suzuki","model":"Alto","trim":"","city":"","min_budget":2100000,"max_budget":3000000,"min_year":2019,"required_features":[],"rationale":"New-shape 660cc Alto VXL AGS — cheapest locally-assembled automatic in Pakistan with low running cost."},
  {"make":"Suzuki","model":"Cultus","trim":"","city":"","min_budget":2100000,"max_budget":3000000,"min_year":2018,"required_features":[],"rationale":"New Celerio-shape Cultus VXL AGS — slightly roomier than Alto with the same automatic gearbox."},
  {"make":"Suzuki","model":"WagonR","trim":"","city":"","min_budget":2100000,"max_budget":3000000,"min_year":2020,"required_features":[],"rationale":"New-shape WagonR VXL AGS — tallboy body with the most interior space of the Suzuki AGS trio."}
]

──────────────────────────────────────
USER: "best luxury car, budget 8 crore"
Q1: No AWD/4x4 signal. Q2: No transmission constraint (all luxury cars are auto).
Q3: Case A (budget given, 8 crore ≥ 50 lacs) → HIGH-BUDGET mode.
    User wants the BEST — that means current generation, newest shape.
    Set min_year = current gen year per model. Do NOT surface decade-old units
    that technically fit the budget.
    Land Cruiser current gen = 2022 (300 series). Prado = 2023 (250 series).
    Civic (top trim) = 2022. Kia Carnival = 2021. Mercedes C-Class (used import) = 2022.
Q4: trim="" for all (each model's top variant is implied by the budget and rationale).
Q-DOMINANCE: All have PakWheels listings at this price. Q-DOMINANCE: top 3 selected ✓.
──────────────────────────────────────
[
  {"make":"Toyota","model":"Land Cruiser","trim":"","city":"","min_budget":56000000,"max_budget":80000000,"min_year":2022,"required_features":[],"rationale":"300-series Land Cruiser is the pinnacle of Pakistani road presence — twin-turbo V6, locking diffs, unmatched reliability at any price."},
  {"make":"Toyota","model":"Prado","trim":"","city":"","min_budget":56000000,"max_budget":80000000,"min_year":2023,"required_features":[],"rationale":"250-series Prado launched 2023 — freshest ladder-frame luxury SUV available in Pakistan with a premium cabin and proven 4x4."},
  {"make":"Kia","model":"Carnival","trim":"","city":"","min_budget":56000000,"max_budget":80000000,"min_year":2021,"required_features":[],"rationale":"8-seat premium minivan — the most comfortable people-mover available in Pakistan with a flagship interior."}
]

──────────────────────────────────────
USER: "hybrid gari chahiye, Islamabad mein"
Q1: No AWD. Q2: No transmission constraint (hybrid implies auto). Q3: No budget → min_year=current gen.
Q4: User said hybrid → trim="Hybrid". Q-DOMINANCE: top 3 by market hierarchy – add variety.
──────────────────────────────────────
[
  {"make":"Toyota","model":"Aqua","trim":"Hybrid","city":"Islamabad","min_budget":0,"max_budget":0,"min_year":2021,"required_features":[],"rationale":"Most common hybrid in Pakistan — 25–28 km/l city average, parts everywhere, proven 2nd gen reliability."},
  {"make":"Toyota","model":"Prius","trim":"Hybrid","city":"Islamabad","min_budget":0,"max_budget":0,"min_year":2023,"required_features":[],"rationale":"Roomier than Aqua with a smoother system — 20–24 km/l; ideal for families wanting hybrid comfort."},
  {"make":"Honda","model":"Vezel","trim":"Hybrid","city":"Islamabad","min_budget":0,"max_budget":0,"min_year":2022,"required_features":[],"rationale":"3rd gen crossover hybrid — more ground clearance and cargo room than Aqua; great for Islamabad’s roads."}
]

──────────────────────────────────────
USER: "comfortable sedan chahiye, koi budget nahi"
Q1: No AWD. Q2: No transmission constraint. Q3: No budget → min_year=current gen per model.
Q4: trim="" (sedans don’t need trim filtering). Q-DOMINANCE: top 3 selected ✓.
──────────────────────────────────────
[
  {"make":"Honda","model":"Civic","trim":"","city":"","min_budget":0,"max_budget":0,"min_year":2022,"required_features":[],"rationale":"11th gen FE Civic — 1.5T turbo, Honda Sensing ADAS, sharpest-looking sedan on Pakistan’s roads right now."},
  {"make":"Toyota","model":"Corolla","trim":"","city":"","min_budget":0,"max_budget":0,"min_year":2022,"required_features":[],"rationale":"12th gen on TNGA platform — better handling, refined cabin, and unbeatable Corolla resale value nationwide."},
  {"make":"Hyundai","model":"Elantra","trim":"","city":"","min_budget":0,"max_budget":0,"min_year":2021,"required_features":[],"rationale":"7th gen CN7 — most striking exterior in class, turbocharged options, and genuinely premium interior feel."}
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
2. Return UP TO the requested number of replacement objects (max 3).
3. NEVER repeat any model in the excluded list.
4. Apply the same logic as the original search (same drivetrain, budget, city, intent).
5. Use the same 9-key schema: make, model, trim, city, min_budget, max_budget, min_year, required_features, rationale.
6. "trim" rules: "" by default. Only "AWD"/"Hybrid"/"EV"/"Diesel"/"Manual" when 
   the user's original intent explicitly required it.
7. "min_year": 0 if budget given, current-gen first year if no budget.
8. "max_budget": 0 means no ceiling. Never null.
9. Pick models with GOOD inventory depth on PakWheels/OLX in Pakistan — avoid 
   ultra-rare imports that will also return 0 results.
10. Q-TIER: If user did NOT explicitly request a Chinese brand, HARD-EXCLUDE all Tier-2 Chinese/secondary brands (Haval, MG, Changan, Chery, DFSK, Proton, BAIC, Jetour, GWM, Seres). Recommend ONLY Tier-1 brands (Toyota, Honda, Kia, Hyundai, Suzuki, Nissan, Mitsubishi).
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
        if r.get("min_budget") is None:
            r["min_budget"] = 0
        if r.get("max_budget") is None:
            r["max_budget"] = 0
        if r.get("city") is None:
            r["city"] = ""

        raw_year = r.get("min_year")
        try:
            r["min_year"] = int(raw_year) if raw_year else 0
        except (TypeError, ValueError):
            r["min_year"] = 0

        if not isinstance(r.get("required_features"), list):
            r["required_features"] = []

        if not r.get("make") or not r.get("model"):
            print(f"[{caller}] Skipping malformed entry (no make/model): {r}")
            continue

        # Clean accidental CoT leak in rationale
        if re.match(r'^(wait|let\'s|re-evaluating|no,|instead)', r.get("rationale", ""), re.IGNORECASE):
            r["rationale"] = f"Proven {r.get('make')} {r.get('model')} variant matching your requested specifications."

        sanitized.append(r)

    return sanitized


# ---------------------------------------------------------------------------
# SHARED RAW-RESPONSE PARSER
# ---------------------------------------------------------------------------
def _parse_llm_json(raw_text: str) -> list:
    """Strips meta-commentary and markdown fences to extract clean JSON array."""
    raw = raw_text.strip()
    # Extract only the content between the first '[' and last ']'
    match = re.search(r'\[.*\]', raw, re.DOTALL)
    if match:
        raw = match.group(0)
    return json.loads(raw)


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

        print(f"[SemanticMapper] -> {len(sanitized)} targets:")
        for r in sanitized:
            trim_label   = f" [{r['trim']}]" if r["trim"] else ""
            budget_label = f"PKR {r['max_budget']:,}" if r["max_budget"] else "no limit"
            year_label   = f" from {r['min_year']}" if r["min_year"] else ""
            print(f"  -> {r['make']} {r['model']}{trim_label}{year_label} | {budget_label} | city={r['city'] or 'any'}")

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
        f'Original user request: "{user_prompt}"\n'
        f'City: {city_str} | Budget: {budget_str}\n\n'
        f'CRITICAL: Maintain ALL constraints from original request '
        f'(e.g., Brand Origin/Nationality, Body Type/Segment, Drivetrain).\n\n'
        f'These targets returned ZERO active listings and need replacements:\n'
        f'  {failed_str}\n\n'
        f'EXCLUDED models (already tried — do not repeat these):\n'
        f'  {excluded_str}\n\n'
        f'Generate UP TO {count} replacement target(s) matching the original criteria.'
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

# ---------------------------------------------------------------------------
# EXTENDED MAPPER — "Show More Options" (Tier-2 alternatives)
# ---------------------------------------------------------------------------
_EXTENDED_MAPPER_PROMPT = """\
You are GaariGuru, a Pakistani used-car expert. The user has already been \
shown the Top 3 highest-confidence cars. Your task is to generate ONLY \
2–3 SECONDARY (Tier-2) alternatives that the user might also consider.

STRICT RULES:
1. TRANSMISSION LOCK: If user requested Automatic/CVT/AGS, output ONLY automatic vehicles. HARD-EXCLUDE all manual variants (e.g., NEVER output "Cultus Manual").
2. FEATURE LOCK: Maintain required features (e.g., factory push start, sunroof).
3. EXCLUSIONS: Hard-exclude all models listed in the exclude list.
4. Output ONLY a raw JSON array — no preamble, no markdown.
5. Return exactly 2 or 3 objects.
6. Respect EVERY original constraint from the user's query: budget, city, body style, transmission, fuel type, brand origin, seating.
7. Pick models with reasonable inventory depth on PakWheels/OLX in Pakistan.
8. Use the same 9-key schema: make, model, trim, city, min_budget, max_budget, min_year, required_features, rationale.
9. "trim" rules: "" by default. Only use "AWD"/"Hybrid"/"EV"/"Diesel"/"Manual" when the user's original intent explicitly required it.
10. "min_year": 0 if budget given, current-gen first year if no budget.
11. "max_budget": 0 means no ceiling. Never null.
12. Q-TIER: If user did NOT explicitly request a Chinese brand, HARD-EXCLUDE all Tier-2 Chinese/secondary brands (Haval, MG, Changan, Chery, DFSK, Proton, BAIC, Jetour, GWM, Seres). Recommend ONLY Tier-1 brands (Toyota, Honda, Kia, Hyundai, Suzuki, Nissan, Mitsubishi).
"""


async def get_extended_recommendations(
    user_prompt: str,
    exclude_models: list[str],
    city: str = "",
    budget: int | None = None,
) -> list[dict]:
    """
    Generates 2–3 Tier-2 alternative recommendations for the "Show More Options"
    feature. Uses a dedicated prompt that knows these are secondary picks.

    Args:
        user_prompt:     The original user query.
        exclude_models:  List of "Make Model" strings already shown (hard exclusion).
        city:            User's city preference ("" for any).
        budget:          Budget in PKR, or None for no ceiling.

    Returns:
        A sanitized list of 2–3 recommendation dicts. Returns [] on any error.
    """
    budget_str   = f"PKR {budget:,}" if budget else "no budget limit"
    city_str     = city or "any city"
    excluded_str = ", ".join(exclude_models) if exclude_models else "none"

    extension_prompt = (
        f'Original user request: "{user_prompt}"\n'
        f'City: {city_str} | Budget: {budget_str}\n\n'
        f'ALREADY SHOWN (hard-exclude these — do NOT repeat):\n'
        f'  {excluded_str}\n\n'
        f'Generate 2–3 Tier-2 alternative recommendations that still match '
        f'all original constraints but offer different options from the Top 3.'
    )

    raw = ""
    try:
        response = await client.aio.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=extension_prompt,
            config=types.GenerateContentConfig(
                temperature=0.25,
                max_output_tokens=1200,
                system_instruction=_EXTENDED_MAPPER_PROMPT,
            ),
        )

        raw = response.text
        results = _parse_llm_json(raw)

        if not isinstance(results, list):
            raise ValueError("Expected JSON array from extension mapper, got: " + type(results).__name__)

        sanitized = _sanitize_recommendations(results, caller="ExtendedMapper")

        # Hard-enforce exclusion list
        excluded_lower = {m.lower().replace(" ", "") for m in exclude_models}
        enforced = []
        for r in sanitized:
            key = f"{r['make']}{r['model']}".lower().replace(" ", "")
            if key in excluded_lower:
                print(f"[ExtendedMapper] LLM ignored exclusion for {r['make']} {r['model']} — dropping")
                continue
            enforced.append(r)

        print(f"[ExtendedMapper] Generated {len(enforced)} extension(s)")
        for r in enforced:
            trim_label = f" [{r['trim']}]" if r['trim'] else ""
            print(f"  -> {r['make']} {r['model']}{trim_label}")

        return enforced

    except json.JSONDecodeError as e:
        print(f"[ExtendedMapper] JSON parse error: {e}")
        print(f"[ExtendedMapper] Raw output was: {raw[:400]}")
        return []
    except Exception as e:
        print(f"[ExtendedMapper] Failed: {e}")
        traceback.print_exc()
        return []