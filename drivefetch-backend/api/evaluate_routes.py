from core.logger import get_logger
logger = get_logger(__name__)
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List
from agents.evaluator import evaluate_single_listing, DEFAULT_AI_ANALYSIS
from api.rate_limiter import limiter

router = APIRouter(prefix='/api', tags=['Evaluate'])


class SingleEvalRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    """Request body for evaluating a single car listing."""
    title: str
    price: int
    mileage: int
    year: int
    city: str
    platform: str
    user_query: str


@router.post("/evaluate-single")
@limiter.limit("10/minute")
async def evaluate_single(request: Request, body: SingleEvalRequest):
    """Evaluate a single car listing using Gemini AI appraisal."""
    try:
        listing_dict = {
            "title": body.title,
            "price": body.price,
            "mileage": body.mileage,
            "year": body.year,
            "city": body.city,
            "platform": body.platform,
        }
        result = await evaluate_single_listing(listing_dict, body.user_query)
        return result
    except Exception as e:
        logger.error(f"[EvaluateRoute] WARNING: evaluate_single failed: {e}", exc_info=True)
        return DEFAULT_AI_ANALYSIS
