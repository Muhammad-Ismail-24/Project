"""
api/recommend_routes.py
Route: POST /api/recommend

Pipeline (v10.0):
  Stage 1   → Intent Extraction     (extract_intent → UserIntent)
  Stage 1   → Constraint Resolution (resolve_constraints → budget floor + Chinese gate only)
  Stage 2   → Budget Filter         (get_budget_eligible_cars → full price-overlap list)
  Stage 2   → Car Selection         (select_car_targets → LLM picks from eligible list)
  Stage 2   → Validation + Format   (_deduplicate_and_format_targets → 9-key dicts)
  Stage 3   → Parallel Scrape       (asyncio.gather across all targets)
  Stage 4   → Per-Model Normalise   (recommend_normalizer per target)
  Stage 4.5 → Validation & Fallback (smart failure classification → retry)
  Stage 5   → Emit Results          (SSE stream to frontend)

v10.0 changes:
  - Tier system completely removed (economy/mid/premium/apex_luxury gone)
  - _STYLE_TIER_ALLOWLIST catalog removed
  - resolve_constraints() now only computes budget floor + allow_chinese flag
  - get_budget_eligible_cars() replaces get_candidate_pool():
      pure budget overlap filter, no scoring, no style pre-filter
      full eligible list passed to LLM — LLM applies body style / use case
  - LLM prompt rewritten: receives budget-filtered list, applies all
      qualitative criteria (body style, use case, luxury, JDM, diversity)
  - gemini-3.5-flash-lite → gemini-2.0-flash-lite (valid model string fix)
  - UI BUG FIX: scraping status SSE now sends target_objects (with make/model keys)
    instead of target_names (strings) — fixes [undefined undefined] loading pills
  - Same target_objects fix applied in Stage 4.5 fallback status SSE

Preserved from v8.0:
  - Smart failure classification (SCRAPER_ZERO vs NORMALIZER_ZERO)
  - city="" passed to runner (soft city signal, recommend_normalizer enforces)
  - budget * 1.05 passed to runner (negotiate buffer pre-fetch)
  - trim stripped of generic powertrain tags before URL building
  - seen_urls dedup shared across initial + fallback pass
  - "targets" in results SSE includes fallback targets
  - _resolve_min_budget single write-through helper
"""

import asyncio
import json
from typing import AsyncGenerator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from agents.recommender import (
    extract_intent,
    resolve_constraints,
    select_car_targets,
    _deduplicate_and_format_targets,
    get_fallback_recommendations,
    get_extended_recommendations,
)
from scrapers.runner import execute_search_pipeline
from scrapers.recommend_normalizer import normalize_recommendation_target
from api.rate_limiter import limiter

router = APIRouter()

# ---------------------------------------------------------------------------
# Failure classification constants
# ---------------------------------------------------------------------------
_FAIL_SCRAPER_ZERO    = "scraper_zero"
_FAIL_NORMALIZER_ZERO = "normalizer_zero"

# If ALL failures are SCRAPER_ZERO and count exceeds this → assume infra issue,
# skip fallback. NORMALIZER_ZERO always triggers fallback regardless.
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
    make  = (rec.get("make")  or "").strip()
    model = (rec.get("model") or "").strip()
    trim  = (rec.get("trim")  or "").strip()

    # Prevent duplicate labels like "MG ZS EV [EV]"
    if trim and trim.lower() not in model.lower():
        trim_suffix = f" [{trim}]"
    else:
        trim_suffix = ""

    return f"{make} {model}".strip() + trim_suffix


def _resolve_min_budget(rec: dict, resolved_max_budget: int | None) -> int:
    """
    Returns the effective price floor in PKR for a recommendation dict.

    Priority:
      1. LLM-supplied min_budget (if > 0) — already set by resolve_constraints()
      2. 70% of max_budget as Python fallback
      3. 0 (no floor) when no max_budget exists

    Writes result back into rec["min_budget"] so _scrape_one and _normalise_one
    both see the same value without repeating the calculation.
    """
    explicit = rec.get("min_budget", 0) or 0
    if explicit > 0:
        return explicit

    if resolved_max_budget and resolved_max_budget > 0:
        floor = int(resolved_max_budget * 0.70)
        rec["min_budget"] = floor
        return floor

    return 0


async def _scrape_one(
    rec: dict,
    override_city: str | None,
    override_budget: int | None,
) -> tuple[list, dict]:
    """
    Fires the scraper pipeline for one recommendation dict.
    Used by both the initial pass (Stage 3) and fallback pass (Stage 4.5).

    City passes as "" — runner's strict normalizer would hard-veto nearby-city
    listings. recommend_normalizer handles city as a soft signal.

    Budget is pre-expanded 5% so the runner doesn't drop listings that the
    recommend_normalizer's +5% negotiation buffer would have kept.

    min_budget is resolved once and written back into rec so _normalise_one
    reads the same value without recalculating.
    """
    make   = rec.get("make")  or ""
    model  = rec.get("model") or ""
    budget = _resolve_budget(override_budget, rec.get("max_budget", 0))

    min_budget = _resolve_min_budget(rec, budget)
    min_year   = _resolve_year(rec.get("min_year", 0))

   # Strip generic powertrain and instructional tags from trim
    GENERIC_POWERTRAIN_TAGS = {
        "ev", "electric", "hev", "phev", "hybrid",
        "petrol", "diesel", "cng", "awd", "fwd", "4x4", "4wd",
        "all trims", "any", "none" # <-- Intercepts LLM hallucinated instructions
    }
    trim_raw     = rec.get("trim") or ""
    trim_for_url = trim_raw if trim_raw.lower() not in GENERIC_POWERTRAIN_TAGS else ""

    scraper_budget = int(budget * 1.05) if budget else None

    try:
        listings, _ = await execute_search_pipeline(
            make=make,
            model=model,
            city=override_city or "",  # physical location query to platform
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
    make      = rec.get("make", "")
    model     = rec.get("model", "")
    rationale = rec.get("rationale", "")
    label     = _target_label(rec)
    budget    = _resolve_budget(override_budget, rec.get("max_budget", 0))
    min_budget = _resolve_min_budget(rec, budget)
    min_year   = _resolve_year(rec.get("min_year", 0))
    city       = override_city or rec.get("city") or ""
    year_suffix = f" (from {min_year})" if min_year else ""

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
        print(
            f"[Recommend] {label}{year_suffix}: NORMALIZER_ZERO — "
            f"{len(raw_listings)} raw listings all vetoed "
            f"(dry inventory or model mismatch)"
        )
        return _FAIL_NORMALIZER_ZERO

    print(
        f"[Recommend] {label}{year_suffix}: "
        f"{len(raw_listings)} raw → {len(clean_listings)} clean"
    )

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
    Determines whether Stage 4.5 fallback should fire.

    Decision logic:
      - No failures → don't fire (happy path)
      - Any NORMALIZER_ZERO → always fire
        (platform returned unrelated cars → dry inventory)
      - All SCRAPER_ZERO:
          ≤ threshold → treat as dry inventory, fire fallback
          > threshold → likely infra outage, skip fallback
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
        return True, (
            f"{len(normalizer_zeros)} normalizer-zero failure(s) — "
            f"scrapers returned data but normalizer vetoed all listings"
        )

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

    # ── Stage 1: Intent Extraction & Constraint Resolution ─────────────────
    yield _sse("status", {"message": "🧠 Analysing your requirements...", "stage": "mapping"})

    try:
        intent = await extract_intent(user_prompt)
        
        # Inject the raw prompt into the intent object so apply_keyword_intent 
        # can scan it for Python-level overrides.
        intent.user_prompt = user_prompt
        
        if override_budget is not None and override_budget > 0:
            intent.max_budget = override_budget
        constraints = resolve_constraints(intent)
        if override_city:
            constraints["city"] = override_city

        # ── Stage 2: Car Selection & Validation ───────────────────────────────
        raw_targets     = await select_car_targets(constraints)
        
    except Exception as e:
        print(f"[API Error] Google Gemini failed during mapping/selection: {e}")
        yield _sse("error", {
            "message": "The AI matchmaker is currently experiencing high demand and is overloaded. Please wait a few seconds and try again."
        })
        return

    recommendations = _deduplicate_and_format_targets(raw_targets, constraints)

    if not recommendations:
        # Emit strategy brief with disclaimers even on empty results —
        # gives user meaningful feedback instead of a dead-end error.
        disclaimers = constraints.get("disclaimers", [])
        summary = constraints.get("strategy_summary", "")
        if disclaimers or summary:
            yield _sse("strategy", {
                "summary":     summary,
                "disclaimers": disclaimers,
                "targets":     [],
            })
        yield _sse("error", {
            "message": "No cars matched your exact combination of features and budget. "
                       "Try removing a specific feature requirement or adjusting your budget range."
        })
        return

    target_names   = [_target_label(r) for r in recommendations]
    target_objects = [{"make": r.get("make"), "model": r.get("model")} for r in recommendations]

    # ── Stage 2.5: Stream Matchmaker Strategy Brief (BEFORE SCRAPING) ─────
    yield _sse("strategy", {
        "summary":     constraints.get("strategy_summary", ""),
        "disclaimers": constraints.get("disclaimers", []),
        "targets":     [
            {"make": r.get("make"), "model": r.get("model"), "trim": r.get("trim")}
            for r in recommendations
        ],
    })

    yield _sse("status", {
        "message": f"🔍 Searching for: {', '.join(target_names)}",
        "stage":   "scraping",
        "targets": target_objects,
    })

    # ── Stage 3: Parallel Scrape ──────────────────────────────────────────
    scrape_results = await asyncio.gather(
        *[_scrape_one(rec, override_city, override_budget) for rec in recommendations]
    )

    # ── Stage 4: Per-Model Normalisation ─────────────────────────────────
    yield _sse("status", {
        "message": "⚡ Ranking and deduplicating results...",
        "stage":   "aggregating",
    })

    output: list[dict]            = []
    seen_urls: set[str]           = set()
    failed_recs: list[dict]       = []
    failure_types: dict[str, str] = {}

    for raw_listings, rec in scrape_results:
        failure = _normalise_one(
            raw_listings, rec, override_city, override_budget, seen_urls, output
        )
        if failure:
            failed_recs.append(rec)
            failure_types[_target_label(rec)] = failure

    # ── Stage 4.5: Smart Validation & Self-Healing Fallback ───────────────
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

        print(f"[Recommend] Stage 4.5 FIRING: {fire_reason}")

        yield _sse("status", {
            "message": f"🔄 Finding alternatives for {len(failed_recs)} dry search(es)...",
            "stage":   "backfilling",
            "failed":  failed_labels,
        })

        try:
            fallback_recs = await get_fallback_recommendations(
                constraints=constraints,
                excluded_models=tried_models,
            )
        except Exception as e:
            print(f"[API Error] Google Gemini failed during fallback selection: {e}")
            fallback_recs = []

        if fallback_recs:
            fb_names   = [_target_label(r) for r in fallback_recs]
            fb_objects = [{"make": r.get("make"), "model": r.get("model")} for r in fallback_recs]
            yield _sse("status", {
                "message": f"🔍 Trying alternatives: {', '.join(fb_names)}",
                "stage":   "backfilling",
                "targets": fb_objects,
            })

            fb_scrape_results = await asyncio.gather(
                *[_scrape_one(rec, override_city, override_budget) for rec in fallback_recs]
            )

            for raw_listings, rec in fb_scrape_results:
                _normalise_one(
                    raw_listings, rec, override_city, override_budget, seen_urls, output
                )

            all_recommendations.extend(fallback_recs)

        else:
            print("[Recommend] Stage 4.5: fallback returned no replacements")

    elif failed_recs:
        _, skip_reason = _should_trigger_fallback(
            failed_recs, failure_types, len(recommendations)
        )
        print(f"[Recommend] Stage 4.5 SKIPPED: {skip_reason}")

    # ── Stage 5: Emit Results ─────────────────────────────────────────────
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
        "disclaimers": constraints.get("disclaimers", []),
        "total": len(output),
    })
    yield _sse("status", {
        "message": (
            f"✅ Found {len(output)} listings across "
            f"{len(all_recommendations)} model(s)"
        ),
        "stage": "complete",
    })


# ---------------------------------------------------------------------------
# ROUTE: POST /api/recommend
# ---------------------------------------------------------------------------

@router.post("/api/recommend")
@limiter.limit("5/minute")
async def recommend_cars(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}

    user_prompt   = (body.get("prompt") or "").strip()
    city_override = (body.get("city")   or "").strip() or None

    raw_budget = body.get("max_budget")
    try:
        budget_override = int(raw_budget) if raw_budget is not None else None
        if budget_override is not None and budget_override <= 0:
            budget_override = None
    except (ValueError, TypeError):
        budget_override = None

    if not user_prompt:
        async def _err():
            yield _sse("error", {
                "message": "Please describe what kind of car you are looking for."
            })
        return StreamingResponse(_err(), media_type="text/event-stream")

    return StreamingResponse(
        run_recommend_pipeline(user_prompt, city_override, budget_override),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# ROUTE: POST /api/recommend/extend  ("Show More Options")
# ---------------------------------------------------------------------------

@router.post("/api/recommend/extend")
@limiter.limit("5/minute")
async def recommend_extend(request: Request):
    """
    Generates 1–3 alternative recommendations for the 'Show More Options'
    button. Receives the original prompt plus models already shown.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}

    user_prompt    = (body.get("prompt")         or "").strip()
    exclude_models = body.get("exclude_models")  or []
    city           = (body.get("city")           or "").strip() or None

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
            "stage":   "extending",
        })

        try:
            # Re-extract intent + constraints (same as main pipeline)
            intent = await extract_intent(user_prompt)
            intent.user_prompt = user_prompt  # Inject raw prompt for the Python Keyword Mapper
            
            if budget is not None and budget > 0:
                intent.max_budget = budget
            constraints = resolve_constraints(intent)
            if city:
                constraints["city"] = city

            extended_targets = await get_extended_recommendations(
                original_constraints=constraints,
                excluded_models=exclude_models,
            )
        except Exception as e:
            print(f"[API Error] Google Gemini failed during extension: {e}")
            yield _sse("error", {
                "message": "The AI matchmaker is currently experiencing high demand. Please try again in a few moments."
            })
            return

        if not extended_targets:
            yield _sse("extension_results", {
                "targets":  [],
                "listings": [],
                "total":    0,
            })
            yield _sse("status", {
                "message": "No additional options found.",
                "stage":   "complete",
            })
            return

        target_names   = [_target_label(r) for r in extended_targets]
        target_objects = [{"make": r.get("make"), "model": r.get("model")} for r in extended_targets]
        yield _sse("status", {
            "message": f"Searching for: {', '.join(target_names)}",
            "stage":   "extending",
            "targets": target_objects,
        })

        # Parallel scrape
        scrape_results = await asyncio.gather(
            *[_scrape_one(rec, city, budget) for rec in extended_targets]
        )

        # Normalize
        output:    list[dict] = []
        seen_urls: set[str]   = set()

        for raw_listings, rec in scrape_results:
            _normalise_one(raw_listings, rec, city, budget, seen_urls, output)

        # Stream extension results
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
            "total":    len(output),
        })
        yield _sse("status", {
            "message": f"Found {len(output)} more listing(s)",
            "stage":   "complete",
        })

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )