from fastapi import APIRouter, Depends, Request, HTTPException
from sqlmodel import Session, select
from database import get_session
from models.db_models import User, SavedListing, CachedCarListing
from pydantic import BaseModel
import urllib.parse

router = APIRouter(tags=["user"])

class SaveListingRequest(BaseModel):
    listing_id: str
    platform: str
    title: str

@router.post("/saved-listings")
def save_listing(payload: SaveListingRequest, request: Request, db: Session = Depends(get_session)):
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
        
    statement = select(SavedListing).where(
        SavedListing.user_id == user.id,
        SavedListing.listing_id == payload.listing_id
    )
    existing = db.exec(statement).first()
    
    if existing:
        return {"status": "already_saved"}
        
    new_save = SavedListing(
        listing_id=payload.listing_id,
        platform=payload.platform,
        title=payload.title,
        user_id=user.id
    )
    db.add(new_save)
    db.commit()
    
    return {"status": "saved"}

@router.delete("/saved-listings/{listing_id:path}")
def remove_saved_listing(listing_id: str, request: Request, db: Session = Depends(get_session)):
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
        
    # The path param might be decoded by FastAPI but could still need decoding depending on frontend
    decoded_id = urllib.parse.unquote(listing_id)
        
    statement = select(SavedListing).where(
        SavedListing.user_id == user_id,
        (SavedListing.listing_id == listing_id) | (SavedListing.listing_id == decoded_id)
    )
    existing = db.exec(statement).first()
    
    if not existing:
        raise HTTPException(status_code=404, detail="Saved listing not found")
        
    db.delete(existing)
    db.commit()
    
    return {"status": "removed"}

@router.get("/saved-listings")
def get_saved_listings(request: Request, db: Session = Depends(get_session)):
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
        
    statement = select(SavedListing).where(SavedListing.user_id == user_id).order_by(SavedListing.saved_at.desc())
    saved_items = db.exec(statement).all()
    
    if not saved_items:
        return []
        
    # Get the car details for these listings
    listing_ids = [item.listing_id for item in saved_items]
    statement_cars = select(CachedCarListing).where(CachedCarListing.id.in_(listing_ids))
    cars_data = db.exec(statement_cars).all()
    
    # Map them back to preserve the sort order
    car_map = {car.id: car for car in cars_data}
    
    result = []
    for item in saved_items:
        car = car_map.get(item.listing_id)
        if car:
            car_dict = car.model_dump()
            car_dict["saved_at"] = item.saved_at.isoformat()
            result.append(car_dict)
            
    return result

# REMINDER: Add this to main.py:
# from api.user_routes import router as user_router
# app.include_router(user_router, prefix="/user", tags=["user"])
