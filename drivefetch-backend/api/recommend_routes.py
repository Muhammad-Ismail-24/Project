"""
api/recommend_routes.py

The AI Matchmaker — Feature-Based Car Recommender
===================================================
Route: POST /api/recommend

Pipeline:
  Stage 1 — Semantic Mapper (Gemini via google-genai)
  Stage 2 — Async Multi-Pipeline
  Stage 3 — Aggregation
"""

import asyncio
import json
import re
import traceback
from typing import AsyncGenerator

from google import genai
from google.genai import types
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from agents.config import GEMINI_API_KEY
from scrapers.runner import run_pipeline
from scrapers.normalizer import normalize_listings

router = APIRouter()

# Initialize the modern google-genai client
client = genai.Client(api_key=GEMINI_API_KEY)

# ─────────────────────────────────────────────────────────────────────────────
# Stage 1: Semantic Mapper
# ─────────────────────────────────────────────────────────────────────────────

SEMANTIC_MAPPER_PROMPT = """
You are an expert Pakistani automotive advisor with deep knowledge of the
used car market. A user will describe what they want in natural language,
Roman Urdu, or Urdu script. Your job is to translate their requirement
into a list of specific car models they should search for.

STRICT RULES:
1. Return ONLY a valid JSON array. No preamble, no explanation, no markdown.
2. Return 2-5 car models maximum. More is worse — focus on the best matches.
3. Use exact make/model names as they appear on PakWheels Pakistan.
4. If the user mentions a budget, split it across trim levels where relevant.
5. If no city is mentioned, set city to null.
6. Always prefer locally assembled (locally popular) cars over obscure imports.
7. For budget under 20 lacs: Suzuki Alto, Suzuki Cultus, Toyota Vitz, Honda City (old)
8. For 20-40 lacs: Honda Civic (FC/FD), Toyota Corolla (various), Suzuki Swift
9. For 40-80 lacs: Honda Civic (latest), Toyota Fortuner, Kia Sportage, MG HS, Hyundai Tucson
10. For 80+ lacs: Toyota Fortuner (latest), Kia Stinger, Chery Tiggo 8 Pro, MG Gloster

PAKISTANI MARKET KNOWLEDGE:
- "AWD" or "4x4" → Kia Sportage AWD, Hyundai Tucson AWD, Toyota Fortuner 4x4
- "Sunroof" → MG HS, Kia Sportage, Hyundai Tucson, Chery Tiggo 8 Pro
- "7 seater" / "family SUV" → KIA Sorento, Toyota Fortuner, MG Gloster, Chery Tiggo 8 Pro
- "Economical" / "fuel efficient" → Suzuki Alto, Daihatsu Mira, Toyota Vitz
- "Automatic" budget car → Suzuki Alto AGS, Suzuki Cultus AGS
- "Hybrid" → Toyota Prius, Toyota Aqua, Honda Vezel
- "New driver" / "first car" → Suzuki Alto, Suzuki Cultus, Toyota Vitz
- "Performance" / "sports" → Honda Civic (Turbo FC)
- "CNG" → Only if user explicitly wants it.
- Prices in Pakistan are in PKR. "Lacs" = 100,000 PKR. "Crore" = 10,000,000 PKR.

OUTPUT FORMAT (strict JSON array):
[
  {
    "make": "Honda",
    "model": "Civic",
    "trim": "Turbo",
    "city": "Lahore",
    "max_budget": 4000000,
    "rationale": "Best performance car in this budget with factory turbo engine"
  },
  {
    "make": "Toyota",
    "model": "Corolla",
    "trim": "Altis",
    "city": "Lahore",
    "max_budget": 4000000,
    "rationale": "Most reliable option with excellent resale value in Pakistan"
  }
]

If trim is not relevant or specified, set trim to null.
If budget is not mentioned, set max_budget to null.
"""


async def semantic_mapper(user_prompt: str) -> list[dict]:
    """
    Calls Gemini using the modern google-genai SDK to translate a natural 
    language requirement into a list of structured car search queries.
    """
    try:
        # Use the native async client (client.aio)
        response = await client.aio.models.generate_content(
            model='gemini-1.5-flash',
            contents=user_prompt,
            config=types.GenerateContentConfig(
                temperature=0.3,
                max_output_tokens=1000,
                system_instruction=SEMANTIC_MAPPER_PROMPT,
            ),
        )
        
        raw = response.text.strip()

        # Strip markdown code fences if present
        raw = re.sub(r'^```(?:json)?\s*', '', raw, flags=re.MULTILINE)
        raw = re.sub(r'\s*```$', '', raw, flags=re.MULTILINE)

        recommendations = json.loads(raw)

        if not isinstance(recommendations, list):
            raise ValueError("Expected JSON array")

        print(f"[Recommender] Semantic Mapper returned {len(recommendations)} targets:")
        for r in recommendations:
            print(f"  → {r.get('make')} {r.get('model')} {r.get('trim','')} | Budget: {r.get('max_budget')}")

        return recommendations

    except Exception as e:
        print(f"[Recommender] Semantic Mapper failed: {e}")
        traceback.print_exc()
        return []


def _sse(event: str, data: dict) -> str:
    """Formats a server-sent event string."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


# ─────────────────────────────────────────────────────────────────────────────
# Stage 2 + 3: Pipeline Orchestrator + Aggregator
# ─────────────────────────────────────────────────────────────────────────────

async def run_recommend_pipeline(
    user_prompt: str,
    override_city: str | None = None,
    override_budget: int | None = None,
) -> AsyncGenerator[str, None]:
    """
    Full 3-stage recommend pipeline yielding SSE events.
    """

    # ── Stage 1: Semantic Mapping ──────────────────────────────────────────
    yield _sse("status", {"message": "🧠 Analysing your requirements...", "stage": "mapping"})

    recommendations = await semantic_mapper(user_prompt)

    if not recommendations:
        yield _sse("error", {"message": "Could not understand your requirements. Please rephrase."})
        return

    target_names = [
        f"{r.get('make','')} {r.get('model','')}".strip()
        for r in recommendations
    ]
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
            listings = await run_pipeline(
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

    # Safe output packaging via dict serialization
    output = []
    seen_urls: set[str] = set()

    for listing in clean_listings:
        url = listing.listing_url
        if url in seen_urls:
            continue
        seen_urls.add(url)

        listing_dict = listing.model_dump()
        listing_dict["ai_rationale"] = rationale_map.get(url, "")
        listing_dict["matched_target"] = target_label_map.get(url, "")
        listing_dict["image_url"] = listing_dict.get("image_url") or ""
        output.append(listing_dict)

    print(f"[Recommender] Outputting {len(output)} clean recommendations.")

    yield _sse("status", {"message": f"✅ Found {len(output)} matching listings", "stage": "complete"})
    yield _sse("results", {
        "listings": output,
        "targets": [
            {
                "make": r.get("make"),
                "model": r.get("model"),
                "trim": r.get("trim"),
                "rationale": r.get("rationale"),
            }
            for r in recommendations
        ],
        "total": len(output),
    })


# ─────────────────────────────────────────────────────────────────────────────
# FastAPI Endpoint Route
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/api/recommend")
async def recommend_cars(request: Request):
    """
    Feature-based AI car recommender endpoint.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}

    user_prompt     = (body.get("prompt") or "").strip()
    city_override   = body.get("city") or None
    budget_override = body.get("max_budget") or None

    if not user_prompt:
        async def _err():
            yield _sse("error", {"message": "Please enter what kind of car you are looking for."})
        return StreamingResponse(_err(), media_type="text/event-stream")

    print(f"[Recommender] Prompt: '{user_prompt}' | city={city_override} | budget={budget_override}")

    return StreamingResponse(
        run_recommend_pipeline(user_prompt, city_override, budget_override),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )