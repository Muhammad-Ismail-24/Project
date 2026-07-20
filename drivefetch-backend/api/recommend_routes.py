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
            # Unpack the tuple returned by execute_search_pipeline
            listings, _ = await execute_search_pipeline(
                make=make, 
                model=model, 
                city=city, 
                max_budget=budget,
                color="", 
                trim=trim or "", 
                min_year=0, 
                max_year=0,
            )
            return listings, rec
        except Exception as e:
            print(f"[Recommender] Pipeline failed for {make} {model}: {e}")
            return [], rec

    results = await asyncio.gather(*[_run_one(rec) for rec in recommendations])

    # ── Stage 3: Aggregation ───────────────────────────────────────────────
    yield _sse("status", {"message": "⚡ Ranking and deduplicating results...", "stage": "aggregating"})

    rationale_map: dict[str, str] = {}
    target_label_map: dict[str, str] = {}
    all_raw: list = []

    for listings, rec in results:
        rationale = rec.get("rationale", "")
        target_label = f"{rec.get('make','')} {rec.get('model','')}".strip()

        for listing in listings:
            url = listing.listing_url
            if url not in rationale_map:
                rationale_map[url] = rationale
                target_label_map[url] = target_label
            all_raw.append(listing)

    if not all_raw:
        yield _sse("error", {"message": "No listings found matching your requirements. Try adjusting your budget or location."})
        return

    first_rec = recommendations[0]
    city_for_norm = override_city or first_rec.get("city") or ""
    budget_for_norm = override_budget or first_rec.get("max_budget")

    clean_listings, is_empty = normalize_listings(
        raw_listings=all_raw, 
        requested_make="", 
        requested_model="",
        requested_city=city_for_norm, 
        requested_budget=budget_for_norm,
        requested_color="", 
        requested_trim="", 
        min_year=0, 
        max_year=0, 
        debug=False,
    )

    if not clean_listings:
        yield _sse("error", {"message": "Listings were found but failed quality/age checks. Try a broader search."})
        return

    output = []
    seen_urls: set[str] = set()

    for listing in clean_listings:
        url = listing.listing_url
        if url in seen_urls: continue
        seen_urls.add(url)

        listing_dict = listing.model_dump()
        listing_dict["ai_rationale"] = rationale_map.get(url, "")
        listing_dict["matched_target"] = target_label_map.get(url, "")
        listing_dict["image_url"] = listing_dict.get("image_url") or ""
        output.append(listing_dict)

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