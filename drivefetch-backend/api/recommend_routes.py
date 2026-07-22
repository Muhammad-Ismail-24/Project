"""
api/recommend_routes.py
Route: POST /api/recommend

Pipeline: Semantic Mapper → Parallel Scrapers → Per-Model Recommendation Normalization → SSE stream

v4.1 changes:
  - Scraper pipeline call now receives city="" and budget*1.05 to prevent runner's
    strict normalizer from prematurely hard-vetoing listings before recommend_normalizer.py
    can apply soft city scoring and the +5% negotiation ceiling.
"""

import asyncio
import json
from typing import AsyncGenerator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from agents.recommender import semantic_mapper
from scrapers.runner import execute_search_pipeline
from scrapers.recommend_normalizer import normalize_recommendation_target

router = APIRouter()


def _sse(event: str, data: dict) -> str:
    """Formats a server-sent event string."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _resolve_budget(override: int | None, rec_budget: int) -> int | None:
    """
    Resolves the effective budget ceiling in PKR.
      Returns None  → no ceiling (scraper fetches all prices)
      Returns int   → base target budget in PKR
    Priority: explicit override (>0) > rec budget (>0) > None
    """
    if override is not None and override > 0:
        return override
    if rec_budget and rec_budget > 0:
        return rec_budget
    return None


def _resolve_year(rec_min_year: int) -> int:
    """
    Resolves the effective minimum year floor for the scraper and normalizer.
      Returns 0    → no year floor (all model years accepted)
      Returns int  → only listings from this year onward are returned
    """
    try:
        year = int(rec_min_year)
        return year if year > 1990 else 0
    except (TypeError, ValueError):
        return 0


async def run_recommend_pipeline(
    user_prompt: str,
    override_city: str | None = None,
    override_budget: int | None = None,
) -> AsyncGenerator[str, None]:

    # ── Stage 1: Semantic Mapping ──────────────────────────────────────────
    yield _sse("status", {"message": "🧠 Analysing your requirements...", "stage": "mapping"})

    recommendations = await semantic_mapper(user_prompt)

    if not recommendations:
        yield _sse("error", {"message": "Could not understand your requirements. Please try rephrasing."})
        return

    target_names = [
        f"{r.get('make', '')} {r.get('model', '')}".strip()
        for r in recommendations
    ]
    yield _sse("status", {
        "message": f"🔍 Searching for: {', '.join(target_names)}",
        "stage": "scraping",
        "targets": target_names,
    })

    # ── Stage 2: Parallel Scraper Pipeline ────────────────────────────────
    async def _run_one(rec: dict) -> tuple[list, dict]:
        make     = rec.get("make") or ""
        model    = rec.get("model") or ""
        city     = override_city or rec.get("city") or ""
        budget   = _resolve_budget(override_budget, rec.get("max_budget", 0))
        min_year = _resolve_year(rec.get("min_year", 0))

        trim_for_url = rec.get("trim") or ""

        # Allow +5% budget headroom for raw scraper fetch so runner's normalizer doesn't veto negotiation candidates
        scraper_budget = int(budget * 1.05) if budget else None

        try:
            # Pass city="" to runner so runner's strict normalizer doesn't hard-veto out-of-city options
            listings, _ = await execute_search_pipeline(
                make=make,
                model=model,
                city="",                     # Handled as soft signal by recommend_normalizer
                max_budget=scraper_budget,   # Handled with +5% headroom
                color="",
                trim=trim_for_url,
                min_year=min_year,
                max_year=0,
            )
            return listings, rec
        except Exception as e:
            print(f"[Recommend] Scraper failed for {make} {model}: {e}")
            return [], rec

    results = await asyncio.gather(*[_run_one(rec) for rec in recommendations])

    # ── Stage 3: Per-Model Normalization ──────────────────────────────────
    yield _sse("status", {"message": "⚡ Ranking and deduplicating results...", "stage": "aggregating"})

    output: list[dict] = []
    seen_urls: set[str] = set()

    for raw_listings, rec in results:
        make         = rec.get("make", "")
        model        = rec.get("model", "")
        rationale    = rec.get("rationale", "")
        target_label = f"{make} {model}".strip()
        budget       = _resolve_budget(override_budget, rec.get("max_budget", 0))
        min_year     = _resolve_year(rec.get("min_year", 0))
        city         = override_city or rec.get("city") or ""

        if not raw_listings:
            print(f"[Recommend] {target_label}: 0 raw listings from scrapers")
            continue

        # Use the AI-specific normalizer which applies soft city scoring,
        # +5% negotiation buffer, and smart trim logic
        clean_listings = normalize_recommendation_target(
            raw_listings=raw_listings,
            requested_make=make,
            requested_model=model,
            requested_city=city,
            requested_budget=budget,
            requested_color="",
            requested_trim=rec.get("trim") or "",
            min_year=min_year,
            max_year=0,
            top_k=5,
            debug=False,
        )

        year_label = f" (from {min_year})" if min_year else ""
        if not clean_listings:
            print(f"[Recommend] {target_label}{year_label}: {len(raw_listings)} raw → 0 after normalization")
            continue

        print(f"[Recommend] {target_label}{year_label}: {len(raw_listings)} raw → {len(clean_listings)} clean")

        # Take top 5 for this specific model — already globally sorted by score
        for listing in clean_listings[:5]:
            url = listing.listing_url
            if url in seen_urls:
                continue
            seen_urls.add(url)

            listing_dict = listing.model_dump()
            listing_dict["ai_rationale"]   = rationale
            listing_dict["matched_target"] = target_label
            listing_dict["image_url"]      = listing_dict.get("image_url") or ""
            output.append(listing_dict)

    # ── Stage 4: Emit Results ─────────────────────────────────────────────
    if not output:
        yield _sse("error", {
            "message": (
                "No listings found for any of the recommended cars. "
                "Try widening your budget or searching a larger city."
            )
        })
        return

    # Results first, then completion signal
    yield _sse("results", {
        "listings": output,
        "targets": [
            {
                "make":      r.get("make"),
                "model":     r.get("model"),
                "trim":      r.get("trim"),
                "rationale": r.get("rationale"),
            }
            for r in recommendations
        ],
        "total": len(output),
    })
    yield _sse("status", {
        "message": f"✅ Found {len(output)} matching listings across {len(target_names)} models",
        "stage": "complete",
    })


@router.post("/api/recommend")
async def recommend_cars(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}

    user_prompt     = (body.get("prompt") or "").strip()
    city_override   = (body.get("city") or "").strip() or None
    raw_budget      = body.get("max_budget")
    budget_override = int(raw_budget) if raw_budget and int(raw_budget) > 0 else None

    if not user_prompt:
        async def _err():
            yield _sse("error", {"message": "Please describe what kind of car you are looking for."})
        return StreamingResponse(_err(), media_type="text/event-stream")

    return StreamingResponse(
        run_recommend_pipeline(user_prompt, city_override, budget_override),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )