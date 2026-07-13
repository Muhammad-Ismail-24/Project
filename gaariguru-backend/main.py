import os
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import create_db_and_tables
from api.calc_routes import router as calc_router
from api.chat_routes import router as chat_router
from api.search_routes import router as search_router
from starlette.middleware.sessions import SessionMiddleware
from auth.routes import router as auth_router
from auth.config import SECRET_KEY

# Initialize the core FastAPI app
app = FastAPI(title="CarFinder API")[cite: 1]

# Add CORS middleware to support local frontend and Vercel production
# FIX 1: When allow_credentials=True, allow_origins cannot be ["*"]. 
# You must explicitly define your frontend domains.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173", 
        "https://carfinderproject.vercel.app"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add SessionMiddleware for OAuth2 state management
# FIX 2: Added same_site="none" and https_only=True to allow cookies 
# to travel between Render and your frontend (Vercel/Localhost).
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    same_site="none",
    https_only=True,
)

# Include core routers
app.include_router(calc_router)[cite: 1]
app.include_router(chat_router)[cite: 1]
app.include_router(search_router)[cite: 1]
app.include_router(auth_router)[cite: 1]

@app.on_event("startup")[cite: 1]
def on_startup():[cite: 1]
    """Trigger database and tables creation on application startup."""[cite: 1]
    create_db_and_tables()[cite: 1]

@app.get("/")[cite: 1]
def read_root():[cite: 1]
    """Simple API status health check endpoint."""[cite: 1]
    return {"status": "API is running"}[cite: 1]