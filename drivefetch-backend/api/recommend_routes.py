"""
api/recommend_routes.py
Route: POST /api/recommend
"""

import asyncio
import json
from typing import AsyncGenerator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from agents.recommender import semantic_mapper
from scrapers.runner import execute_search_pipeline
from scrapers.normalizer import normalize_listings

router = APIRouter()

def _sse(event: str, data: dict) -> str:
    """Formats a server-sent event string."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"

async def run_recommend_pipeline(
    user_prompt: str,
    override_city: str | None = None,
    override_budget: int | None = None,
) -> AsyncGenerator[str, None]:
    
    # ── Stage 1: Semantic Mapping ──────────────────────────────────────────
    yield _sse("status", {"message": "🧠 Analysing your requirements...", "stage": "mapping"})

    recommendations = await semantic_mapper(user_prompt)

    if not recommendations:
        yield _sse("error", {"message": "Could not understand your requirements. Please rephrase."})
        return

    target_names = [f"{r.get('make','')} {r.get('model','')}".strip() for r in recommendations]
    yield _sse("status", {
        "message": f"🔍 Searching for: {', '.join(target_names)}",
        "stage": "scraping",
        "targets": target_names,
    })

    # ── Stage 2: Async Multi-Pipeline ─────────────────────────────────────
    async def _run_one(rec: dict) -> tuple[list, dict]:
        make   = rec.get("make") or ""
        model  = rec.get("model") or ""
        trim   = rec.get("trim") or ""
        city   = override_city or rec.get("city") or ""
        budget = override_budget or rec.get("max_budget")

        try:
            # We send the trim to the scraper normally
            listings, _ = await execute_search_pipeline(
                make=make, 
                model=model, 
                city=city, 
                max_budget=budget,
                color="", 
                trim=trim, 
                min_year=0, 
                max_year=0,
            )
            return listings, rec
        except Exception as e:
            print(f"[Recommender] Pipeline failed for {make} {model}: {e}")
            return [], rec

    # Run scrapers for all recommended cars in parallel
    results = await asyncio.gather(*[_run_one(rec) for rec in recommendations])

    # ── Stage 3: Aggregation (Per-Model Normalization) ─────────────────────
    yield _sse("status", {"message": "⚡ Ranking and deduplicating results...", "stage": "aggregating"})

    output = []
    seen_urls: set[str] = set()

    # Loop through the results for EACH recommended model individually
    for raw_listings, rec in results:
        if not raw_listings:
            continue

        rationale = rec.get("rationale", "")
        target_label = f"{rec.get('make','')} {rec.get('model','')}".strip()
        
        # Normalize specifically for this target car!
        # This gives the Normalizer the correct context (make, model, trim) to score accurately.
        clean_target_listings, _ = normalize_listings(
            raw_listings=raw_listings,
            requested_make=rec.get("make", ""),
            requested_model=rec.get("model", ""),
            requested_city=override_city or rec.get("city") or "",
            requested_budget=override_budget or rec.get("max_budget"),
            requested_color="",
            requested_trim=rec.get("trim", ""),
            min_year=0,
            max_year=0,
            debug=False,
        )

        # Slice the absolute top 5 mixed-platform cars for this specific model
        top_5_for_target = clean_target_listings[:5]

        for listing in top_5_for_target:
            url = listing.listing_url
            if url in seen_urls:
                continue
            seen_urls.add(url)

            listing_dict = listing.model_dump()
            listing_dict["ai_rationale"] = rationale
            listing_dict["matched_target"] = target_label
            listing_dict["image_url"] = listing_dict.get("image_url") or ""
            output.append(listing_dict)

    if not output:
        yield _sse("error", {"message": "No listings found matching your exact requirements. Try adjusting your budget."})
        return

    yield _sse("status", {"message": f"✅ Found {len(output)} matching listings", "stage": "complete"})
    yield _sse("results", {
        "listings": output,
        "targets": [{"make": r.get("make"), "model": r.get("model"), "trim": r.get("trim"), "rationale": r.get("rationale")} for r in recommendations],
        "total": len(output),
    })

@router.post("/api/recommend")
async def recommend_cars(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}

    user_prompt     = (body.get("prompt") or "").strip()
    city_override   = body.get("city") or None
    budget_override = body.get("max_budget") or None

    if not user_prompt:
        async def _err(): yield _sse("error", {"message": "Please enter what kind of car you are looking for."})
        return StreamingResponse(_err(), media_type="text/event-stream")

    return StreamingResponse(
        run_recommend_pipeline(user_prompt, city_override, budget_override),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )