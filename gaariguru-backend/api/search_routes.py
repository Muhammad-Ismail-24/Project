from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select
from datetime import datetime, timezone, timedelta
from typing import List
import json

from database import get_session
from models.db_models import SearchQueryCache, CachedCarListing
from agents.orchestrator import parse_user_query
from scrapers.runner import execute_search_pipeline
from agents.evaluator import evaluate_scraped_listings
from scrapers.normalizer import normalize_make_model, normalize_city

router = APIRouter(prefix="/api/search", tags=["Search"])

class SearchRequest(BaseModel):
    query: str = Field(..., description="Natural language search query", json_schema_extra={"example": "Cheap civic in Lahore"})

@router.post("")
async def search_cars(request: SearchRequest, session: Session = Depends(get_session)):
    # ----------------------------------------------------
    # STEP 1: Orchestration FIRST (Takes ~0.5 seconds)
    # ----------------------------------------------------
    print(f"[Live Pipeline] Orchestrating query parsing: '{request.query}'")
    params = await parse_user_query(request.query)

    make = (params.get("make") or "").strip()
    model = (params.get("model") or "").strip()
    city = (params.get("city") or "").strip()
    max_budget = params.get("max_budget") or 0
    color = (params.get("color") or "").strip()
    min_year = int(params.get("min_year") or 0)
    max_year = int(params.get("max_year") or 0)

    # --- THE NEW FAILSAFE GUARD ---
    # If the AIs hit a rate limit and return empty variables, STOP THE PIPELINE!
    if not make and not model:
        print("[Live Pipeline] ⚠ CRITICAL: Orchestrator returned empty Make/Model. API Rate Limit likely hit.")
        raise HTTPException(
            status_code=503, 
            detail="Our AI servers are currently experiencing heavy traffic or rate limits. Please check your API keys or wait a moment and try again!"
        )

    # ----------------------------------------------------
    # ----------------------------------------------------
    # STEP 2: Smart Parameter Caching
    # ----------------------------------------------------
    corrected_make, corrected_model = normalize_make_model(
        params.get("make", ""), params.get("model", "")
    )
    corrected_city = normalize_city(params.get("city", ""))
    budget = params.get("max_budget")
    color = params.get("color")
    trim = params.get("trim")

    cities_list = sorted([c.strip() for c in corrected_city.split(",") if c.strip()])
    cache_key = (
        f"make:{corrected_make.lower()}|"
        f"model:{corrected_model.lower()}|"
        f"trim:{(trim or 'none').lower()}|"
        f"city:{','.join(cities_list).lower()}|"
        f"budget:{budget or 'none'}|"
        f"color:{(color or 'none').lower()}|"
        f"yr:{min_year}-{max_year}"
    )

    try:
        query_stmt = select(SearchQueryCache).where(SearchQueryCache.normalized_query == cache_key)
        cache_record = session.exec(query_stmt).first()

        if cache_record:
            # Verify cache age is under 2 hours
            now = datetime.now(timezone.utc)
            if now - cache_record.created_at.replace(tzinfo=timezone.utc) < timedelta(hours=2):
                print(f"[Smart Cache] Hit! Loading search results from database for key: '{cache_key}'")
                
                # Fetch related CachedCarListing records
                cached_cars = cache_record.listings
                reconstructed_listings = []
                for car in cached_cars:
                    reconstructed_listings.append({
                        "id": car.id,
                        "title": car.title,
                        "price": car.price,
                        "mileage": car.mileage,
                        "city": car.city,
                        "year": car.year,
                        "listing_url": car.listing_url,
                        "image_url": car.image_url,
                        "platform": car.platform,
                        "scraped_at": now.isoformat(),
                        "ai_analysis": {
                            "red_flags": json.loads(car.red_flags_json),
                            "liquidity_score": car.liquidity_score,
                            "justification": car.justification
                        }
                    })
                return reconstructed_listings
            else:
                # Cache expired, delete the old record and cascading listings
                print(f"[Smart Cache] Expired record deleted for key: '{cache_key}'")
                session.delete(cache_record)
                session.commit()
    except Exception as cache_err:
        # Log error but do not crash; fallback to live search pipeline
        print(f"[Smart Cache] Error checking database cache: {cache_err}")

    # ----------------------------------------------------
    # STEP 3: Scraping (ThreadPool Scraper Runner)
    # ----------------------------------------------------
    # Unpack parameters defensively: execute_search_pipeline expects positional string args
    make = params.get("make") or ""
    model = params.get("model") or ""
    city = params.get("city") or ""
    trim = (params.get("trim") or "").strip()
    
    print(f"[Live Pipeline] Executing scraper runner: Make={make}, Model={model}, City={city}, Budget={budget}, Color={color}, Trim={trim}, Year={min_year}-{max_year}")
    clean_listings, is_empty = await execute_search_pipeline(make, model, city, max_budget=budget, color=color, trim=trim, min_year=min_year, max_year=max_year)

    if is_empty or not clean_listings:
        print("[Live Pipeline] Result flagged as empty. Skipping Gemini appraisal and skipping database cache to avoid memorizing blank pages.")
        return []

    # ----------------------------------------------------
    # STEP 4: Evaluation (The "Top 5" AI Diet)
    # ----------------------------------------------------
    top_5_cars = clean_listings[:5]
    remaining_cars = clean_listings[5:]




    print(f"[AI Diet] Ingesting Top {len(top_5_cars)} listings to Gemini appraiser")
    # evaluated_top_5 = await evaluate_scraped_listings(top_5_cars, request.query)
    
    # Mock data to save API limits during testing
    mock_analysis = {
        "red_flags": [],
        "liquidity_score": "High",
        "justification": "Mock AI evaluation applied during testing to conserve API rate limits."
    }
    evaluated_top_5 = [
        {**car.model_dump(), "ai_analysis": mock_analysis}
        for car in top_5_cars
    ]

    standard_analysis = {
        "red_flags": [],
        "liquidity_score": "Standard",
        "justification": "Standard listing. Deep AI analysis is reserved for the Top 5 best matches for this search."
    }

    remaining_with_fallback = [
        {**car.model_dump(), "ai_analysis": standard_analysis}
        for car in remaining_cars
    ]

    evaluated_listings = evaluated_top_5 + remaining_with_fallback

    # ----------------------------------------------------
    # STEP 5: Save Results to Cache Database
    # ----------------------------------------------------
    try:
        # Create parent cache query record
        new_cache = SearchQueryCache(normalized_query=cache_key)
        session.add(new_cache)
        session.commit()
        session.refresh(new_cache)

        for item in evaluated_listings:
            analysis = item.get("ai_analysis", {})
            db_car = CachedCarListing(
                id=item.get("id"),
                search_id=new_cache.id,
                title=item.get("title", ""),
                price=int(item.get("price") or 0),
                mileage=int(item.get("mileage") or 0),
                city=item.get("city", ""),
                year=int(item.get("year") or 0),
                listing_url=item.get("listing_url", ""),
                image_url=item.get("image_url"),
                platform=item.get("platform", ""),
                red_flags_json=json.dumps(analysis.get("red_flags", [])),
                liquidity_score=analysis.get("liquidity_score", "Medium"),
                justification=analysis.get("justification", "")
            )
            session.add(db_car)
        session.commit()
        print(f"[Smart Cache] Saved {len(evaluated_listings)} listings for key: '{cache_key}'")
    except Exception as db_err:
        print(f"[Cache Error] Failed to save search results to database: {db_err}")
        session.rollback()

    return evaluated_listings

from fastapi.responses import StreamingResponse

@router.post("/stream")
async def search_cars_stream(request: SearchRequest, session: Session = Depends(get_session)):
    async def event_generator():
        yield f"data: {json.dumps({'status': 'AI analyzing your request...'})}\n\n"
        
        print(f"[Live Pipeline] Orchestrating query parsing: '{request.query}'")
        params = await parse_user_query(request.query)

        make = (params.get("make") or "").strip()
        model = (params.get("model") or "").strip()
        city = (params.get("city") or "").strip()
        max_budget = params.get("max_budget") or 0
        color = (params.get("color") or "").strip()
        min_year = int(params.get("min_year") or 0)
        max_year = int(params.get("max_year") or 0)

        if not make and not model:
            print("[Live Pipeline] ⚠ CRITICAL: Orchestrator returned empty Make/Model. API Rate Limit likely hit.")
            yield f"data: {json.dumps({'error': 'Our AIs are currently experiencing heavy traffic. Please try again!'})}\n\n"
            return

        target_car = model or make or "your car"
        yield f"data: {json.dumps({'status': f'Searching platforms for {target_car}...'})}\n\n"

        corrected_make, corrected_model = normalize_make_model(params.get("make", ""), params.get("model", ""))
        corrected_city = normalize_city(params.get("city", ""))
        budget = params.get("max_budget")
        trim = params.get("trim")

        cities_list = sorted([c.strip() for c in corrected_city.split(",") if c.strip()])
        cache_key = (
            f"make:{corrected_make.lower()}|"
            f"model:{corrected_model.lower()}|"
            f"trim:{(trim or 'none').lower()}|"
            f"city:{','.join(cities_list).lower()}|"
            f"budget:{budget or 'none'}|"
            f"color:{(color or 'none').lower()}|"
            f"yr:{min_year}-{max_year}"
        )

        try:
            query_stmt = select(SearchQueryCache).where(SearchQueryCache.normalized_query == cache_key)
            cache_record = session.exec(query_stmt).first()
            if cache_record:
                now = datetime.now(timezone.utc)
                if now - cache_record.created_at.replace(tzinfo=timezone.utc) < timedelta(hours=2):
                    print(f"[Smart Cache] Hit! Loading search results from database for key: '{cache_key}'")
                    cached_cars = cache_record.listings
                    reconstructed_listings = []
                    for car in cached_cars:
                        reconstructed_listings.append({
                            "id": car.id,
                            "title": car.title,
                            "price": car.price,
                            "mileage": car.mileage,
                            "city": car.city,
                            "year": car.year,
                            "listing_url": car.listing_url,
                            "image_url": car.image_url,
                            "platform": car.platform,
                            "scraped_at": now.isoformat(),
                            "ai_analysis": {
                                "red_flags": json.loads(car.red_flags_json),
                                "liquidity_score": car.liquidity_score,
                                "justification": car.justification
                            }
                        })
                    yield f"data: {json.dumps({'status': 'done', 'results': reconstructed_listings})}\n\n"
                    return
                else:
                    print(f"[Smart Cache] Expired record deleted for key: '{cache_key}'")
                    session.delete(cache_record)
                    session.commit()
        except Exception as cache_err:
            print(f"[Smart Cache] Error checking database cache: {cache_err}")

        make = params.get("make") or ""
        model = params.get("model") or ""
        city = params.get("city") or ""
        trim = (params.get("trim") or "").strip()
        
        clean_listings, is_empty = await execute_search_pipeline(make, model, city, max_budget=budget, color=color, trim=trim, min_year=min_year, max_year=max_year)

        if is_empty or not clean_listings:
            yield f"data: {json.dumps({'status': 'done', 'results': []})}\n\n"
            return

        yield f"data: {json.dumps({'status': f'Found {len(clean_listings)} cars. Scoring top matches...'})}\n\n"

        top_5_cars = clean_listings[:5]
        remaining_cars = clean_listings[5:]

        yield f"data: {json.dumps({'status': f'Top {min(5, len(clean_listings))} cars selected! Passing to AI Appraiser...'})}\n\n"
        evaluated_top_5 = await evaluate_scraped_listings(top_5_cars, request.query)

        standard_analysis = {
            "red_flags": [],
            "liquidity_score": "Standard",
            "justification": "Standard listing. Deep AI analysis is reserved for the Top 5 best matches for this search."
        }

        remaining_with_fallback = [
            {**car.model_dump(), "ai_analysis": standard_analysis}
            for car in remaining_cars
        ]

        evaluated_listings = evaluated_top_5 + remaining_with_fallback

        try:
            new_cache = SearchQueryCache(normalized_query=cache_key)
            session.add(new_cache)
            session.commit()
            session.refresh(new_cache)

            for item in evaluated_listings:
                analysis = item.get("ai_analysis", {})
                db_car = CachedCarListing(
                    id=item.get("id"),
                    search_id=new_cache.id,
                    title=item.get("title", ""),
                    price=int(item.get("price") or 0),
                    mileage=int(item.get("mileage") or 0),
                    city=item.get("city", ""),
                    year=int(item.get("year") or 0),
                    listing_url=item.get("listing_url", ""),
                    image_url=item.get("image_url"),
                    platform=item.get("platform", ""),
                    red_flags_json=json.dumps(analysis.get("red_flags", [])),
                    liquidity_score=analysis.get("liquidity_score", "Medium"),
                    justification=analysis.get("justification", "")
                )
                session.add(db_car)
            session.commit()
            print(f"[Smart Cache] Saved {len(evaluated_listings)} listings for key: '{cache_key}'")
        except Exception as db_err:
            print(f"[Cache Error] Failed to save search results to database: {db_err}")
            session.rollback()

        yield f"data: {json.dumps({'status': 'done', 'results': evaluated_listings})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")