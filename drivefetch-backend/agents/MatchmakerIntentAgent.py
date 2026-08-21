import re
from typing import Optional, Literal
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

from agents.config import generate_content_resilient, settings
from agents.recommender import (
    CAR_REGISTRY,
    _CANONICAL_MODEL_MAP,
    _FEAT_NORMALISE,
    _VETO_TAGS,
    _VETO_TAG_KEYWORDS,
    CITY_ALIAS_MAP
)
from scrapers.normalizer import normalize_city

_MODEL_BODY_STYLE_MAP = {
    'Crossover': ['Sportage', 'Tucson', 'CR-V', 'RAV4', 'HR-V', 'Vezel', 'CX-5', 'Stonic', 'Seltos'],
    'SUV': ['Fortuner', 'Prado', 'Land Cruiser', 'Pajero', 'Patrol', 'Wrangler', 'Defender'],
    'Sedan': ['Corolla', 'Civic', 'City', 'Elantra', 'Camry', 'Accord'],
    'Hatchback': ['Swift', 'Alto', 'Cultus', 'Vitz', 'Picanto', 'Fit'],
    'Pickup': ['Hilux', 'Revo', 'Ranger', 'D-Max']
}

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
        "- CATEGORY INFERENCE FROM REFERENCE MODEL: If the user asks for 'cars like [MODEL]', "
        "'alternatives to [MODEL]', or 'something similar to [MODEL]', you MUST:\n"
        "  1. Set direct_model to the mentioned model name (e.g. 'Sportage')\n"
        "  2. ALSO infer the body_style from the reference model's known category. Use this map:\n"
    ) + "".join(f"     {'/'.join(models)} -> {style}\n" for style, models in _MODEL_BODY_STYLE_MAP.items()) + (
        "  3. Do NOT leave body_style null when the reference model unambiguously belongs to a category.\n"
        "- TRUE SUV / PROPER SUV DETECTION: If the user says 'proper SUV', 'true SUV', "
        "'real SUV', 'ladder-frame', 'body-on-frame', or 'rugged 4x4', you MUST:\n"
        "  1. Set body_style to 'SUV' (NOT 'Crossover')\n"
        "  2. Set use_case to 'offroad'\n"
        "  This ensures crossovers like Sportage/Tucson are excluded in favor of true ladder-frame SUVs.\n"
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

