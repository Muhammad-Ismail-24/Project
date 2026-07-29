"""
api/recommend_routes.py
Route: POST /api/recommend

Pipeline (v6.0):
  Stage 1  → Semantic Mapping      (Gemini: 5 targets)
  Stage 2  → Parallel Scrape       (asyncio.gather across all 5)
  Stage 3  → Per-Model Normalise   (recommend_normalizer per target)
  Stage 3.5→ Validation & Fallback (smart failure classification → retry)
  Stage 4  → Emit Results          (SSE stream to frontend)

v6.0 changes over v5.0:
  ─────────────────────────────────────────────────────────────────────────────
  FIX 1 — Smart Fallback Triggering (the "EV zero result" bug):
    Old logic: if failed_count > _MAX_FALLBACK_TARGETS (3) → assume network issue → skip fallback.
    Problem: When all 5 targets are a niche category (EVs, rare imports, etc.),
             ALL 5 can fail due to dry inventory, not a scraper outage.
             WiseWheels returns 40 listings for any query (its API ignores unknown
             models and returns popular cars) — so raw_count > 0 but normalizer
             vetos everything. Old code saw 5 failures and assumed "network issue".

    New logic: classify each failure as one of two types:
      - SCRAPER_ZERO:     platform returned 0 raw listings (possible infra issue)
      - NORMALIZER_ZERO:  platform returned raw listings but normalizer vetoed all

    Fallback fires if:
      a) Any NORMALIZER_ZERO failures exist (always inventory issue, not infra), OR
      b) SCRAPER_ZERO count ≤ _MAX_SCRAPER_ZERO_THRESHOLD (3) (few pure zeros = probably ok)

    This means niche EV searches now correctly trigger the fallback and get
    reasonable alternatives (Prius, Vezel, etc.) instead of a dead-end error.

  FIX 2 — Budget override parsing hardened (GAP-5 from test battery):
    Old:  int(raw_budget) called twice — crashes on "80 lacs" string input.
    New:  wrapped in try/except, called once, graceful fallback to None.

  FIX 3 — Log clarity: _normalise_one now returns a FailureType enum-like string
    so Render logs show exactly WHY each target failed.

  Preserved from v5.0:
    - city="" passed to runner (soft city signal, enforced by recommend_normalizer)
    - budget * 1.05 passed to runner (negotiate buffer pre-fetch)
    - trim forwarded to URL builder only, never to normalizer
    - seen_urls dedup shared across initial + fallback pass
    - "targets" in results SSE includes fallback targets
"""

import asyncio
import json
from typing import AsyncGenerator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from agents.recommender import semantic_mapper, get_fallback_recommendations, get_extended_recommendations
from scrapers.runner import execute_search_pipeline
from scrapers.recommend_normalizer import normalize_recommendation_target

router = APIRouter()

# ---------------------------------------------------------------------------
# Failure classification constants
# ---------------------------------------------------------------------------
# SCRAPER_ZERO     = platform returned no raw listings at all (possible outage)
# NORMALIZER_ZERO  = platform returned listings but normalizer vetoed everything
#                    (inventory dry for this exact model, or model unrecognised)
_FAIL_SCRAPER_ZERO    = "scraper_zero"
_FAIL_NORMALIZER_ZERO = "normalizer_zero"

# How many pure scraper-zero failures before we assume it's an infra issue.
# If ALL failures are scraper_zero AND count > this → skip fallback.
# Normalizer-zero failures ALWAYS trigger fallback regardless of count.
_MAX_SCRAPER_ZERO_THRESHOLD = 3


def _sse(event: str, data: dict) -> str:
    """Formats a server-sent event string."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _resolve_budget(override: int | None, rec_budget: int) -> int | None:
    """
    Effective budget ceiling in PKR.
      None  → no ceiling (scraper fetches all prices)
      int   → base target budget in PKR
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
      0   → no floor (all model years accepted)
      int → only listings from this year onward
    """
    try:
        year = int(rec_min_year)
        return year if year > 1990 else 0
    except (TypeError, ValueError):
        return 0


def _target_label(rec: dict) -> str:
    """Human-readable label, e.g. 'Kia Sportage [AWD]'."""
    make = (rec.get("make") or "").strip()
    model = (rec.get("model") or "").strip()
    trim = (rec.get("trim") or "").strip()
    
    # Prevent duplicate labels like "MG ZS EV [EV]" or "ZS EV EV"
    if trim and trim.lower() not in model.lower():
        trim_suffix = f" [{trim}]"
    else:
        trim_suffix = ""
        
    return f"{make} {model}".strip() + trim_suffix


async def _scrape_one(
    rec: dict,
    override_city: str | None,
    override_budget: int | None,
) -> tuple[list, dict]:
    """
    Fires the scraper pipeline for one recommendation dict.
    Used by both the initial pass (Stage 2) and the fallback pass (Stage 3.5).

    City passes as "" — the runner's strict normalizer would hard-veto
    nearby-city listings. The recommend_normalizer handles city as a soft signal.

    Budget is pre-expanded 5% so the runner's normalizer doesn't drop listings
    that the recommend_normalizer's +5% negotiation buffer would have kept.
    """
    make         = rec.get("make") or ""
    model        = rec.get("model") or ""
    budget       = _resolve_budget(override_budget, rec.get("max_budget", 0))
    min_budget   = rec.get("min_budget", 0)
    min_year     = _resolve_year(rec.get("min_year", 0))
    GENERIC_POWERTRAIN_TAGS = {
        "ev", "electric", "hev", "phev", "hybrid", 
        "petrol", "diesel", "cng", "awd", "fwd", "4x4", "4wd"
    }
    trim_raw = rec.get("trim") or ""
    trim_for_url = trim_raw if trim_raw.lower() not in GENERIC_POWERTRAIN_TAGS else ""

    scraper_budget = int(budget * 1.05) if budget else None

    try:
        listings, _ = await execute_search_pipeline(
            make=make,
            model=model,
            city="",                  # soft city — enforced by recommend_normalizer
            max_budget=scraper_budget,
            min_budget=min_budget,
            color="",
            trim=trim_for_url,
            min_year=min_year,
            max_year=0,
        )
        return listings, rec
    except Exception as e:
        print(f"[Recommend] Scraper exception for {make} {model}: {e}")
        return [], rec


def _normalise_one(
    raw_listings: list,
    rec: dict,
    override_city: str | None,
    override_budget: int | None,
    seen_urls: set[str],
    output: list[dict],
) -> str | None:
    """
    Runs recommend_normalizer on raw_listings for one rec dict.
    Appends qualifying listings to `output`, updating `seen_urls`.

    Returns:
      None                  — at least one listing found (success)
      _FAIL_SCRAPER_ZERO    — scraper returned 0 raw listings
      _FAIL_NORMALIZER_ZERO — scraper returned listings but all were vetoed
    """
    make        = rec.get("make", "")
    model       = rec.get("model", "")
    rationale   = rec.get("rationale", "")
    label       = _target_label(rec)
    budget      = _resolve_budget(override_budget, rec.get("max_budget", 0))
    min_budget  = rec.get("min_budget", 0)
    min_year    = _resolve_year(rec.get("min_year", 0))
    city        = override_city or rec.get("city") or ""
    year_suffix = f" (from {min_year})" if min_year else ""

    # ── Classify scraper-zero immediately ────────────────────────────────────
    if not raw_listings:
        print(f"[Recommend] {label}: SCRAPER_ZERO — 0 raw listings from any platform")
        return _FAIL_SCRAPER_ZERO

    clean_listings = normalize_recommendation_target(
        raw_listings=raw_listings,
        requested_make=make,
        requested_model=model,
        requested_city=city,
        requested_budget=budget,
        requested_color="",
        requested_trim=rec.get("trim") or "",
        required_features=rec.get("required_features") or [],
        min_budget=min_budget,
        min_year=min_year,
        max_year=0,
        top_k=5,
        debug=False,
    )

    if not clean_listings:
        # Scraper found something but normalizer vetoed it all → inventory issue
        print(
            f"[Recommend] {label}{year_suffix}: NORMALIZER_ZERO — "
            f"{len(raw_listings)} raw listings all vetoed (dry inventory or model mismatch)"
        )
        return _FAIL_NORMALIZER_ZERO

    print(f"[Recommend] {label}{year_suffix}: {len(raw_listings)} raw → {len(clean_listings)} clean")

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

    return None   # success


def _should_trigger_fallback(
    failed_recs: list[dict],
    failure_types: dict[str, str],
    total_targets: int,
) -> tuple[bool, str]:
    """
    Determines whether Stage 3.5 fallback should fire and why.

    Args:
        failed_recs:    list of rec dicts that produced 0 clean listings
        failure_types:  {target_label: failure_type} for all failed recs
        total_targets:  total number of initial recommendations

    Returns:
        (should_fire: bool, reason: str)

    Decision logic:
      - If no failures → don't fire (happy path)
      - If any failure is NORMALIZER_ZERO → always fire
        (WiseWheels/OLX returned unrelated cars for niche query → inventory issue)
      - If all failures are SCRAPER_ZERO:
          ≤ threshold → probably dry inventory, fire fallback
          > threshold → probably infra outage, skip fallback
    """
    if not failed_recs:
        return False, "no failures"

    normalizer_zeros = [
        label for label, ft in failure_types.items()
        if ft == _FAIL_NORMALIZER_ZERO
    ]
    scraper_zeros = [
        label for label, ft in failure_types.items()
        if ft == _FAIL_SCRAPER_ZERO
    ]

    if normalizer_zeros:
        # Listings were fetched but vetoed → definitely inventory/category issue
        return True, (
            f"{len(normalizer_zeros)} normalizer-zero failure(s) "
            f"(scrapers returned data but normalizer vetoed all listings — "
            f"dry inventory or model not indexed on platforms)"
        )

    # All failures are scraper-zero (no raw listings at all)
    if len(scraper_zeros) <= _MAX_SCRAPER_ZERO_THRESHOLD:
        return True, (
            f"{len(scraper_zeros)} scraper-zero failure(s) "
            f"(≤ threshold {_MAX_SCRAPER_ZERO_THRESHOLD} → treating as dry inventory)"
        )

    return False, (
        f"{len(scraper_zeros)} scraper-zero failures exceed threshold "
        f"{_MAX_SCRAPER_ZERO_THRESHOLD}/{total_targets} — likely scraper/network issue"
    )


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

    output: list[dict]         = []
    seen_urls: set[str]        = set()
    failed_recs: list[dict]    = []
    failure_types: dict[str, str] = {}   # label → failure type

    for raw_listings, rec in scrape_results:
        failure = _normalise_one(
            raw_listings, rec, override_city, override_budget, seen_urls, output
        )
        if failure:
            failed_recs.append(rec)
            failure_types[_target_label(rec)] = failure

    # ── Stage 3.5: Smart Validation & Self-Healing Fallback ───────────────
    all_recommendations = list(recommendations)

    should_fire, fire_reason = _should_trigger_fallback(
        failed_recs, failure_types, len(recommendations)
    )

    if should_fire:
        failed_labels = [_target_label(r) for r in failed_recs]
        tried_models  = [
            f"{r.get('make', '')} {r.get('model', '')}".strip()
            for r in recommendations
        ]
        eff_city   = override_city or (recommendations[0].get("city") or "") if recommendations else ""
        eff_budget = _resolve_budget(
            override_budget,
            recommendations[0].get("max_budget", 0) if recommendations else 0
        )

        print(f"[Recommend] Stage 3.5 FIRING: {fire_reason}")

        yield _sse("status", {
            "message": f"🔄 Finding alternatives for {len(failed_recs)} dry search(es)...",
            "stage":   "backfilling",
            "failed":  failed_labels,
        })

        fallback_recs = await get_fallback_recommendations(
            user_prompt=user_prompt,
            failed_targets=failed_labels,
            tried_models=tried_models,
            city=eff_city,
            budget=eff_budget,
            count=len(failed_recs),
        )

        if fallback_recs:
            fb_names = [_target_label(r) for r in fallback_recs]
            yield _sse("status", {
                "message": f"🔍 Trying alternatives: {', '.join(fb_names)}",
                "stage":   "backfilling",
                "targets": fb_names,
            })

            fb_scrape_results = await asyncio.gather(
                *[_scrape_one(rec, override_city, override_budget) for rec in fallback_recs]
            )

            for raw_listings, rec in fb_scrape_results:
                _normalise_one(raw_listings, rec, override_city, override_budget, seen_urls, output)

            all_recommendations.extend(fallback_recs)

        else:
            print("[Recommend] Stage 3.5: fallback returned no replacements")

    elif failed_recs:
        # Not firing — log the reason clearly
        _, skip_reason = _should_trigger_fallback(
            failed_recs, failure_types, len(recommendations)
        )
        print(f"[Recommend] Stage 3.5 SKIPPED: {skip_reason}")

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
            for r in all_recommendations
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

    user_prompt   = (body.get("prompt") or "").strip()
    city_override = (body.get("city") or "").strip() or None

    # FIX 2: Hardened budget parsing — wraps int() in try/except so strings
    # like "80 lacs" don't crash the route before SSE starts (GAP-5).
    raw_budget = body.get("max_budget")
    try:
        budget_override = int(raw_budget) if raw_budget is not None else None
        if budget_override is not None and budget_override <= 0:
            budget_override = None
    except (ValueError, TypeError):
        budget_override = None

    if not user_prompt:
        async def _err():
            yield _sse("error", {"message": "Please describe what kind of car you are looking for."})
        return StreamingResponse(_err(), media_type="text/event-stream")

    return StreamingResponse(
        run_recommend_pipeline(user_prompt, city_override, budget_override),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

# ---------------------------------------------------------------------------
# ON-DEMAND EXTENSION: "Show More Options" (targets 4-6)
# ---------------------------------------------------------------------------
@router.post("/api/recommend/extend")
async def recommend_extend(request: Request):
    """
    Generates 2–3 Tier-2 alternative recommendations for the "Show More Options"
    button. Receives the original prompt plus models already shown.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}

    user_prompt    = (body.get("prompt") or "").strip()
    exclude_models = body.get("exclude_models") or []
    city           = (body.get("city") or "").strip() or None

    raw_budget = body.get("max_budget")
    try:
        budget = int(raw_budget) if raw_budget is not None else None
        if budget is not None and budget <= 0:
            budget = None
    except (ValueError, TypeError):
        budget = None

    if not user_prompt:
        async def _err():
            yield _sse("error", {"message": "Missing original prompt for extension."})
        return StreamingResponse(_err(), media_type="text/event-stream")

    async def _stream():
        yield _sse("status", {
            "message": "Finding more options...",
            "stage": "extending",
        })

        # ── Step 1: Get extended recommendations from Gemini ──────────
        extended_targets = await get_extended_recommendations(
            user_prompt=user_prompt,
            exclude_models=exclude_models,
            city=city or "",
            budget=budget,
        )

        if not extended_targets:
            yield _sse("extension_results", {
                "targets": [],
                "listings": [],
                "total": 0,
            })
            yield _sse("status", {
                "message": "No additional options found.",
                "stage": "complete",
            })
            return

        target_names = [_target_label(r) for r in extended_targets]
        yield _sse("status", {
            "message": f"Searching for: {', '.join(target_names)}",
            "stage": "extending",
            "targets": target_names,
        })

        # ── Step 2: Parallel scrape ───────────────────────────────────
        scrape_results = await asyncio.gather(
            *[_scrape_one(rec, city, budget) for rec in extended_targets]
        )

        # ── Step 3: Normalize ─────────────────────────────────────────
        output: list[dict] = []
        seen_urls: set[str] = set()

        for raw_listings, rec in scrape_results:
            _normalise_one(raw_listings, rec, city, budget, seen_urls, output)

        # ── Step 4: Stream extension results ──────────────────────────
        yield _sse("extension_results", {
            "targets": [
                {
                    "make":      r.get("make"),
                    "model":     r.get("model"),
                    "trim":      r.get("trim"),
                    "rationale": r.get("rationale"),
                }
                for r in extended_targets
            ],
            "listings": output,
            "total": len(output),
        })
        yield _sse("status", {
            "message": f"Found {len(output)} more listing(s)",
            "stage": "complete",
        })

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
