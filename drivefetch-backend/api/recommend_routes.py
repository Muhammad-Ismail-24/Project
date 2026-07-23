"""
api/recommend_routes.py
Route: POST /api/recommend

Pipeline (v5.0):
  Stage 1  → Semantic Mapping      (Gemini: 5 targets)
  Stage 2  → Parallel Scrape       (asyncio.gather across all 5)
  Stage 3  → Per-Model Normalise   (recommend_normalizer per target)
  Stage 3.5→ Validation & Fallback (detect 0-result targets, retry 1–3 replacements)
  Stage 4  → Emit Results          (SSE stream to frontend)

v5.0 changes over v4.1:
  - Stage 3.5 Async Self-Healing Loop: any target that returns 0 clean listings
    triggers a single Gemini fallback call (get_fallback_recommendations) followed
    by a parallel scrape + normalise pass for the replacements only. Max one retry
    pass to bound total latency. Only fires when 1–3 targets fail; if ≥4 fail it
    is likely a scraper / network issue, not a dry inventory issue.
  - _run_one() extracted to module-level coroutine so it can be called identically
    for both the initial batch and the fallback batch.
  - seen_urls dedup set is shared across initial + fallback pass.
  - "targets" in the final results SSE event now includes replacement targets so
    the frontend can show the full picture of what was searched.
  - Model name fixed: gemini-3.1-flash-lite → gemini-2.0-flash-lite (in recommender.py).

Preserved from v4.1:
  - city="" passed to runner (soft city signal, hard-enforced by recommend_normalizer)
  - budget * 1.05 passed to runner (negotiate buffer pre-fetch)
  - trim forwarded to URL builder only, never to normalizer
"""

import asyncio
import json
from typing import AsyncGenerator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from agents.recommender import semantic_mapper, get_fallback_recommendations
from scrapers.runner import execute_search_pipeline
from scrapers.recommend_normalizer import normalize_recommendation_target

router = APIRouter()

# ---------------------------------------------------------------------------
# Maximum number of failed targets that triggers the fallback retry.
# If MORE than this many fail, it is most likely a scraper/network problem
# rather than dry inventory — a Gemini retry call would be wasteful.
# ---------------------------------------------------------------------------
_MAX_FALLBACK_TARGETS = 3


def _sse(event: str, data: dict) -> str:
    """Formats a server-sent event string."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _resolve_budget(override: int | None, rec_budget: int) -> int | None:
    """
    Effective budget ceiling in PKR.
      None  → no ceiling (scraper fetches all prices)
      int   → base target budget
    Priority: explicit override (>0) > rec budget (>0) > None
    """
    if override is not None and override > 0:
        return override
    if rec_budget and rec_budget > 0:
        return rec_budget
    return None


def _resolve_year(rec_min_year: int) -> int:
    """
    Effective minimum year floor.
      0   → no floor (all years)
      int → only listings from this year onward
    """
    try:
        year = int(rec_min_year)
        return year if year > 1990 else 0
    except (TypeError, ValueError):
        return 0


def _target_label(rec: dict) -> str:
    """Human-readable label for a recommendation dict, e.g. 'Kia Sportage [AWD]'."""
    trim = rec.get("trim") or ""
    trim_suffix = f" [{trim}]" if trim else ""
    return f"{rec.get('make', '')} {rec.get('model', '')}".strip() + trim_suffix


async def _scrape_one(
    rec: dict,
    override_city: str | None,
    override_budget: int | None,
) -> tuple[list, dict]:
    """
    Fires the scraper pipeline for a single recommendation dict.
    Shared between the initial pass (Stage 2) and the fallback pass (Stage 3.5).

    City is intentionally passed as "" to the runner — the runner's strict
    normalizer would hard-veto nearby-city listings. City enforcement is
    handled as a soft signal inside recommend_normalizer.py.

    Budget is expanded by 5% so the runner's normalizer doesn't drop listings
    that the +5% negotiation buffer in recommend_normalizer would have kept.
    """
    make     = rec.get("make") or ""
    model    = rec.get("model") or ""
    budget   = _resolve_budget(override_budget, rec.get("max_budget", 0))
    min_year = _resolve_year(rec.get("min_year", 0))
    trim_for_url = rec.get("trim") or ""

    scraper_budget = int(budget * 1.05) if budget else None

    try:
        listings, _ = await execute_search_pipeline(
            make=make,
            model=model,
            city="",               # Soft city — enforced by recommend_normalizer
            max_budget=scraper_budget,
            color="",
            trim=trim_for_url,
            min_year=min_year,
            max_year=0,
        )
        return listings, rec
    except Exception as e:
        print(f"[Recommend] Scraper failed for {make} {model}: {e}")
        return [], rec


def _normalise_one(
    raw_listings: list,
    rec: dict,
    override_city: str | None,
    override_budget: int | None,
    seen_urls: set[str],
    output: list[dict],
) -> bool:
    """
    Runs recommend_normalizer on raw_listings for one rec dict.
    Appends qualifying listings into `output`, updating `seen_urls`.

    Returns True if at least one clean listing was found, False otherwise.
    Side-effects: mutates output and seen_urls in-place.
    """
    make         = rec.get("make", "")
    model        = rec.get("model", "")
    rationale    = rec.get("rationale", "")
    label        = _target_label(rec)
    budget       = _resolve_budget(override_budget, rec.get("max_budget", 0))
    min_year     = _resolve_year(rec.get("min_year", 0))
    city         = override_city or rec.get("city") or ""
    year_suffix  = f" (from {min_year})" if min_year else ""

    if not raw_listings:
        print(f"[Recommend] {label}: 0 raw listings from scraper")
        return False

    clean_listings = normalize_recommendation_target(
        raw_listings=raw_listings,
        requested_make=make,
        requested_model=model,
        requested_city=city,
        requested_budget=budget,
        requested_color="",
        requested_trim=rec.get("trim") or "",  # soft trim — normalizer handles lazy sellers
        min_year=min_year,
        max_year=0,
        top_k=5,
        debug=False,
    )

    if not clean_listings:
        print(f"[Recommend] {label}{year_suffix}: {len(raw_listings)} raw → 0 after normalisation")
        return False

    print(f"[Recommend] {label}{year_suffix}: {len(raw_listings)} raw → {len(clean_listings)} clean")

    added = 0
    for listing in clean_listings[:5]:
        url = listing.listing_url
        if url in seen_urls:
            continue
        seen_urls.add(url)

        listing_dict                   = listing.model_dump()
        listing_dict["ai_rationale"]   = rationale
        listing_dict["matched_target"] = f"{make} {model}".strip()
        listing_dict["image_url"]      = listing_dict.get("image_url") or ""
        output.append(listing_dict)
        added += 1

    return added > 0


# ---------------------------------------------------------------------------
# MAIN PIPELINE
# ---------------------------------------------------------------------------

async def run_recommend_pipeline(
    user_prompt: str,
    override_city: str | None = None,
    override_budget: int | None = None,
) -> AsyncGenerator[str, None]:

    # ── Stage 1: Semantic Mapping ──────────────────────────────────────────
    yield _sse("status", {"message": "🧠 Analysing your requirements...", "stage": "mapping"})

    recommendations = await semantic_mapper(user_prompt)

    if not recommendations:
        yield _sse("error", {
            "message": "Could not understand your requirements. Please try rephrasing."
        })
        return

    target_names = [_target_label(r) for r in recommendations]
    yield _sse("status", {
        "message": f"🔍 Searching for: {', '.join(target_names)}",
        "stage":   "scraping",
        "targets": target_names,
    })

    # ── Stage 2: Parallel Scrape ───────────────────────────────────────────
    scrape_results = await asyncio.gather(
        *[_scrape_one(rec, override_city, override_budget) for rec in recommendations]
    )

    # ── Stage 3: Per-Model Normalisation ──────────────────────────────────
    yield _sse("status", {"message": "⚡ Ranking and deduplicating results...", "stage": "aggregating"})

    output: list[dict]    = []
    seen_urls: set[str]   = set()
    failed_recs: list[dict] = []   # recs that produced 0 clean listings

    for raw_listings, rec in scrape_results:
        found = _normalise_one(raw_listings, rec, override_city, override_budget, seen_urls, output)
        if not found:
            failed_recs.append(rec)

    # ── Stage 3.5: Validation & Self-Healing Fallback ─────────────────────
    # Conditions for triggering a retry:
    #   - At least 1 target failed (otherwise nothing to retry)
    #   - At most _MAX_FALLBACK_TARGETS failed (more likely scraper/network issue)
    all_recommendations = list(recommendations)  # grows if fallback succeeds

    if 1 <= len(failed_recs) <= _MAX_FALLBACK_TARGETS:
        failed_labels = [_target_label(r) for r in failed_recs]
        tried_models  = [
            f"{r.get('make', '')} {r.get('model', '')}".strip()
            for r in recommendations
        ]

        # Effective city and budget for the fallback context message
        eff_city   = override_city or (recommendations[0].get("city") or "") if recommendations else ""
        eff_budget = _resolve_budget(override_budget, recommendations[0].get("max_budget", 0) if recommendations else 0)

        yield _sse("status", {
            "message": f"🔄 Finding alternatives for {len(failed_recs)} dry search(es)...",
            "stage":   "backfilling",
            "failed":  failed_labels,
        })

        print(f"[Recommend] Stage 3.5: {len(failed_recs)} target(s) failed → requesting fallback")

        fallback_recs = await get_fallback_recommendations(
            user_prompt=user_prompt,
            failed_targets=failed_labels,
            tried_models=tried_models,
            city=eff_city,
            budget=eff_budget,
            count=len(failed_recs),   # replace exactly as many as failed
        )

        if fallback_recs:
            fb_names = [_target_label(r) for r in fallback_recs]
            yield _sse("status", {
                "message": f"🔍 Trying alternatives: {', '.join(fb_names)}",
                "stage":   "backfilling",
                "targets": fb_names,
            })

            # Parallel scrape for replacements only
            fb_scrape_results = await asyncio.gather(
                *[_scrape_one(rec, override_city, override_budget) for rec in fallback_recs]
            )

            for raw_listings, rec in fb_scrape_results:
                _normalise_one(raw_listings, rec, override_city, override_budget, seen_urls, output)

            # Track fallback recs for the final targets manifest
            all_recommendations.extend(fallback_recs)

        else:
            print("[Recommend] Stage 3.5: fallback returned no replacements — proceeding with partial results")

    elif len(failed_recs) > _MAX_FALLBACK_TARGETS:
        print(
            f"[Recommend] Stage 3.5: {len(failed_recs)}/{len(recommendations)} targets failed — "
            f"likely a scraper/network issue, skipping fallback to avoid LLM waste"
        )

    # ── Stage 4: Emit Results ─────────────────────────────────────────────
    if not output:
        yield _sse("error", {
            "message": (
                "No listings found for any of the recommended cars. "
                "Try widening your budget or searching a larger city."
            )
        })
        return

    yield _sse("results", {
        "listings": output,
        "targets": [
            {
                "make":      r.get("make"),
                "model":     r.get("model"),
                "trim":      r.get("trim"),
                "rationale": r.get("rationale"),
            }
            for r in all_recommendations  # includes fallback targets
        ],
        "total": len(output),
    })
    yield _sse("status", {
        "message": (
            f"✅ Found {len(output)} listings across "
            f"{len(all_recommendations)} model(s)"
        ),
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