from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select
from auth.config import oauth, SECRET_KEY
from database import get_session
from models.db_models import User
import os
import jwt
from datetime import datetime, timedelta, timezone

router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.get("/login")
async def login(request: Request):
    """Redirect to Google for OAuth authentication."""
    # Construct the callback URL
    redirect_uri = request.url_for("auth_callback")
    
    # Render requires secure cookies (https). Make sure redirect_uri is https if not local
    if "onrender.com" in str(redirect_uri) or os.getenv("RENDER"):
        redirect_uri = str(redirect_uri).replace("http://", "https://")

    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/google/callback", name="auth_callback")
async def auth_callback(request: Request, db: Session = Depends(get_session)):
    """Callback route for Google OAuth2."""
    try:
        # Fetch the token using the authorization code
        token = await oauth.google.authorize_access_token(request)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Authentication failed: {str(e)}")

    user_info = token.get("userinfo")
    if not user_info:
        raise HTTPException(status_code=400, detail="Could not retrieve user info from Google")

    email = user_info.get("email")
    name = user_info.get("name")
    picture = user_info.get("picture")

    if not email:
        raise HTTPException(status_code=400, detail="No email provided by Google")

    # Check if user exists in the DB
    statement = select(User).where(User.email == email)
    user = db.exec(statement).first()

    if not user:
        # Create a new user record
        user = User(email=email, name=name, picture=picture)
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        # Update name and picture if they changed
        changed = False
        if name and user.name != name:
            user.name = name
            changed = True
        if picture and user.picture != picture:
            user.picture = picture
            changed = True
        
        if changed:
            db.add(user)
            db.commit()
            db.refresh(user)

    # Store the user ID in the session
    request.session["user_id"] = user.id

    # Redirect to the frontend dashboard
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173")
    return RedirectResponse(url=f"{frontend_url}/")

@router.get("/me")
async def get_current_user(request: Request, db: Session = Depends(get_session)):
    """Retrieve the current logged-in user from the session."""
    user_id = request.session.get("user_id")
    
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # Fetch the latest profile from the database
    user = db.get(User, user_id)
    if not user:
        # If user was deleted but session exists, clear the session
        request.session.pop("user_id", None)
        raise HTTPException(status_code=401, detail="User not found")
        
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "picture": user.picture
    }
