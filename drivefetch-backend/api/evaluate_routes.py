from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List
from agents.evaluator import evaluate_single_listing, DEFAULT_AI_ANALYSIS

router = APIRouter(prefix='/api', tags=['Evaluate'])


class SingleEvalRequest(BaseModel):
    """Request body for evaluating a single car listing."""
    title: str
    price: int
    mileage: int
    year: int
    city: str
    platform: str
    user_query: str


@router.post("/evaluate-single")
async def evaluate_single(body: SingleEvalRequest):
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
        print(f"[EvaluateRoute] WARNING: evaluate_single failed: {e}")
        return DEFAULT_AI_ANALYSIS
