import inspect
import traceback
from typing import Optional, Any

from agents.MatchmakerIntentAgent import extract_intent, resolve_constraints
from agents.RecommenderAgent import execute_recommendation, execute_corrective_recommendation
from agents.ReviewerAgent import review_recommendations


async def _maybe_await(obj: Any) -> Any:
    """Helper to await a function result only if it is a coroutine."""
    if inspect.isawaitable(obj):
        return await obj
    return obj


async def run_matchmaker_pipeline(
    user_prompt: str,
    override_city: Optional[str] = None,
    override_budget: Optional[int] = None,
) -> dict:
    pipeline_stages = []
    
    # Stage 1: Intent Extraction
    try:
        print("[MatchmakerController] Stage 1 - Intent Extraction")
        pipeline_stages.append("intent_extraction")
        
        intent = await _maybe_await(extract_intent(user_prompt))
        intent.user_prompt = user_prompt
        
        if override_budget is not None and override_budget > 0:
            intent.max_budget = override_budget
                
        constraints = resolve_constraints(intent)
        
        if override_city is not None:
            constraints["city"] = override_city
                
        # Check for early veto
        if constraints.get("is_llm_vetoed", False):
            print("[MatchmakerController] Intent vetoed — impossible/illegal query detected.")
            veto_msg = constraints.get("immediate_veto_message", constraints.get("strategy_summary", "Request vetoed."))
            return {
                "error": "Request vetoed",
                "veto_message": veto_msg,
                "strategy_summary": constraints.get("strategy_summary", ""),
                "disclaimers": constraints.get("disclaimers", []),
                "pipeline_stages": pipeline_stages,
                "constraints": constraints
            }
            
    except Exception as e:
        print("[MatchmakerController] Error in Stage 1 - Intent Extraction")
        traceback.print_exc()
        return {"error": "Failed during intent extraction", "details": str(e), "pipeline_stages": pipeline_stages}

    # Stage 2: Recommendation Execution
    try:
        print("[MatchmakerController] Stage 2 - Recommendation Execution")
        pipeline_stages.append("recommendation")
        
        proposed_cars = await _maybe_await(execute_recommendation(constraints))
        if not proposed_cars:
            print("[MatchmakerController] Error: Empty recommendation result.")
            return {"error": "No recommendations found", "pipeline_stages": pipeline_stages, "constraints": constraints}
            
    except Exception as e:
        print("[MatchmakerController] Error in Stage 2 - Recommendation Execution")
        traceback.print_exc()
        return {"error": "Failed during recommendation execution", "details": str(e), "pipeline_stages": pipeline_stages, "constraints": constraints}

    # Stage 3: Review
    try:
        print("[MatchmakerController] Stage 3 - Review")
        pipeline_stages.append("review")
        
        verdict = await _maybe_await(review_recommendations(user_prompt, constraints, proposed_cars))
        is_approved = getattr(verdict, "is_approved", True)
        feedback = getattr(verdict, "feedback", "")
    except Exception as e:
        print("[MatchmakerController] Error in Stage 3 - Review (failing open)")
        traceback.print_exc()
        is_approved = True
        feedback = "Fail-open due to review error."

    final_cars = proposed_cars

    # Stage 4: Corrective Retry
    if not is_approved:
        try:
            print("[MatchmakerController] Stage 4 - Corrective Retry")
            pipeline_stages.append("corrective_retry")
            
            final_cars = await _maybe_await(execute_corrective_recommendation(constraints, feedback, proposed_cars))
        except Exception as e:
            print("[MatchmakerController] Error in Stage 4 - Corrective Retry (failing open)")
            traceback.print_exc()
            final_cars = proposed_cars

    # Output
    print("[MatchmakerController] Pipeline completed successfully.")
    
    strategy_summary = constraints.get("strategy_summary", "")
    disclaimers = constraints.get("disclaimers", [])
    
    return {
        "recommendations": final_cars,
        "strategy_summary": strategy_summary,
        "disclaimers": disclaimers,
        "review_verdict": {
            "is_approved": is_approved,
            "feedback": feedback,
        },
        "pipeline_stages": pipeline_stages,
        "constraints": constraints,
    }
