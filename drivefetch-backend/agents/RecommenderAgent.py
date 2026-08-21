from agents.recommender import (
    get_eligible_cars,
    select_car_targets,
    _validate_targets,
    _deduplicate_and_format,
    CarTargetRaw,
    CAR_REGISTRY,
    _CANONICAL_MODEL_MAP,
    _get_relevant_principles,
)
from agents.config import generate_content_resilient
from google.genai import types
import json

async def execute_recommendation(constraints: dict) -> list[dict]:
    """
    Runs the full recommendation pipeline:
    1. select_car_targets(constraints) -> raw LLM picks
    2. _validate_targets(raw, constraints) -> valid + dropped
    3. Self-correction loop if any dropped (one retry)
    4. _deduplicate_and_format(valid, constraints) -> formatted 9-key dicts
    Returns the formatted list of recommended cars.
    """
    raw_targets = await select_car_targets(constraints)
    valid_targets, dropped_reasons = _validate_targets(raw_targets, constraints)

    if dropped_reasons and len(valid_targets) < len(raw_targets):
        needed = max(0, 3 - len(valid_targets))
        print(
            f"[RecommenderAgent] {len(dropped_reasons)} car(s) dropped — triggering self-correction "
            f"to find {needed} replacement(s). Reasons:\n  " + "\n  ".join(dropped_reasons)
        )

        if needed > 0:
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
            )

            if eligible_list.startswith("No eligible cars found"):
                print(
                    "[RecommenderAgent] Eligible list is empty — skipping LLM self-correction "
                    "to avoid hallucination on a zero-option list."
                )
                return _deduplicate_and_format(valid_targets, constraints)

            already_picked = [
                f"{v.make} {v.model}" for v in valid_targets
            ]

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
                        f"[RecommenderAgent] Correction still dropped {len(still_dropped)} car(s) "
                        f"on second pass — accepting partial result."
                    )
                valid_targets.extend(valid_replacements)
                print(
                    f"[RecommenderAgent] Self-correction complete — "
                    f"{len(valid_replacements)} replacement(s) added."
                )
            except Exception as e:
                print(f"[RecommenderAgent] Self-correction LLM call failed: {e}")

    return _deduplicate_and_format(valid_targets, constraints)

async def execute_corrective_recommendation(
    constraints: dict,
    feedback: str,
    previous_cars: list[dict],
) -> list[dict]:
    """
    Called when the ReviewerAgent rejects the initial recommendation.
    Takes the reviewer's feedback string and uses it as a corrective instruction
    for a single retry.
    
    1. Gets the eligible car list
    2. Sends a focused correction prompt with the feedback
    3. Validates and formats the replacement picks
    """
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
    )

    if eligible_list.startswith("No eligible cars found"):
        print(
            "[RecommenderAgent] Eligible list is empty — skipping corrective recommendation "
            "to avoid hallucination on a zero-option list."
        )
        return []

    previous_car_names = [f"{car.get('make', '')} {car.get('model', '')}".strip() for car in previous_cars]

    correction_prompt = (
        f"CORRECTIVE TASK: Your previous picks were rejected by a reviewer.\n"
        f"REVIEWER FEEDBACK: {feedback}\n"
        f"ELIGIBLE CARS: {eligible_list}\n"
        f"ALREADY REJECTED (do not repeat): {json.dumps(previous_car_names)}\n"
        f"Return exactly 3 replacement cars from the ELIGIBLE CARS list."
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
        
        valid_targets, dropped = _validate_targets(replacement_raws, constraints)
        
        if dropped:
            print(f"[RecommenderAgent] Corrective pass dropped {len(dropped)} cars: {dropped}")
            
        return _deduplicate_and_format(valid_targets, constraints)
        
    except Exception as e:
        print(f"[RecommenderAgent] Corrective LLM call failed: {e}")
        return []
