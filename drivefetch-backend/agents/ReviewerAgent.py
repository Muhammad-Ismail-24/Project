from core.logger import get_logger
logger = get_logger(__name__)
import json
import re
from pydantic import BaseModel, Field
from google.genai import types

from agents.config import generate_content_resilient
from agents.recommender import CAR_REGISTRY

class ReviewVerdict(BaseModel):
    is_approved: bool
    feedback: str  # "Approved" or a strict, 1-sentence corrective prompt

async def review_recommendations(
    user_raw_query: str,
    user_intent_constraints: dict,
    proposed_cars: list[dict],
) -> ReviewVerdict:
    """
    Agent 3 of the AI Matchmaker pipeline (Gatekeeper).
    Deliberately simple to prevent hallucinations.
    Evaluates whether the proposed cars violate the user's hard constraints.
    Returns a binary verdict with corrective feedback if any car fails.
    """
    if not proposed_cars:
        return ReviewVerdict(is_approved=True, feedback="Approved")

    # Enrich each proposed car with registry metadata
    enriched_candidates = []
    for car in proposed_cars:
        make = car.get("make", "")
        model = car.get("model", "")
        key = f"{make.lower()}:{model.lower()}"
        info = CAR_REGISTRY.get(key, {})
        enriched_candidates.append({
            "make": make,
            "model": model,
            "trim": car.get("trim", ""),
            "origin_type": (
                "Imported JDM" if "jdm" in info.get("tags", set())
                else ("Chinese" if info.get("chinese") else "Local/Mainstream")
            ),
            "tags": list(info.get("tags", set())),
            "rationale": car.get("rationale", ""),
        })

    prompt = (
        "You are a strict QA Auditor for an automotive recommendation engine — the final gatekeeper.\n"
        f"User's raw query: '{user_raw_query}'\n"
        f"Resolved user intent constraints: {json.dumps(user_intent_constraints, indent=2)}\n\n"
        f"The system is proposing these cars, enriched with registry metadata:\n"
        f"{json.dumps(enriched_candidates, indent=2)}\n\n"
        "TASK: Evaluate whether the proposed cars violate any of the user's hard constraints:\n"
        "- Body style mismatch (e.g., user asked for Crossover but got Sedan)\n"
        "- Budget violation\n"
        "- Origin violation (e.g., user said 'no Chinese' but got a Chinese car, or requested 'local' and got 'JDM')\n"
        "- Explicit brand/model vetoes\n"
        "- Transmission mismatch\n"
        "- Powertrain mismatch (e.g., user asked for hybrid but got petrol)\n- DIRECT MODEL ALIGNMENT: If the user explicitly requested a specific model (direct_model) and it is eligible, it MUST be the primary recommendation. This is not a violation.\n\n"
        "If ALL cars pass these hard constraints: return is_approved=True and feedback='Approved'.\n"
        "If ANY car fails: return is_approved=False and feedback containing a strict, 1-sentence corrective prompt. "
        "For example: 'The user asked for a Crossover like Sportage, but you provided a Sedan. Replace the Sedan with a Crossover.'"
    )

    try:
        response_text = await generate_content_resilient(
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=ReviewVerdict,
                temperature=0.0,
            ),
        )
        verdict = ReviewVerdict.model_validate_json(response_text)
        return verdict
    except Exception as e:
        logger.info(f"[ReviewerAgent] Failed: {e} — failing OPEN (Approved)")
        return ReviewVerdict(is_approved=True, feedback="Approved")

