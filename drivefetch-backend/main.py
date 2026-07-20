import os
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import create_db_and_tables

# Core Routers
from api.calc_routes import router as calc_router
from api.chat_routes import router as chat_router
from api.search_routes import router as search_router
from api.evaluate_routes import router as evaluate_router
from api.recommend_routes import router as recommend_router  # <--- NEW ROUTER
from api.user_routes import router as user_router
from auth.routes import router as auth_router

from starlette.middleware.sessions import SessionMiddleware
from auth.config import SECRET_KEY
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

# Initialize FastAPI App
app = FastAPI(title="CarFinder API")

# Render HTTPS Trust Headers
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")

# CORS Middleware (Updated with expose_headers for SSE streaming)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173", 
        "https://carfinderproject.vercel.app"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],  # <--- EXPOSE SSE HEADERS TO FRONTEND
)

# SessionMiddleware for OAuth2
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    same_site="none",
    https_only=True,
    max_age=14 * 24 * 60 * 60
)

# Register Routers
app.include_router(calc_router)
app.include_router(chat_router)
app.include_router(search_router)
app.include_router(evaluate_router)
app.include_router(recommend_router)  # <--- REGISTERED /api/recommend ROUTER
app.include_router(auth_router)
app.include_router(user_router, prefix="/user", tags=["user"])


@app.on_event("startup")
def on_startup():
    """Trigger database and tables creation on application startup."""
    create_db_and_tables()


@app.get("/")
def read_root():
    """Simple API status health check endpoint."""
    return {"status": "API is running"}