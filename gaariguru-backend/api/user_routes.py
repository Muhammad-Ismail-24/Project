from fastapi import APIRouter, Depends, Request, HTTPException
from sqlmodel import Session, select
from database import get_session
from models.db_models import User, SavedListing
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
    listings = db.exec(statement).all()
    
    return [
        {
            "listing_id": item.listing_id,
            "platform": item.platform,
            "title": item.title,
            "saved_at": item.saved_at.isoformat()
        } for item in listings
    ]

# REMINDER: Add this to main.py:
# from api.user_routes import router as user_router
# app.include_router(user_router, prefix="/user", tags=["user"])
