from core.logger import get_logger
logger = get_logger(__name__)
import os
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import create_db_and_tables
from agents.config import settings

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
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from api.rate_limiter import limiter

# Initialize FastAPI App
app = FastAPI(title="CarFinder API")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import HTTPException

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(
        f"Unhandled exception on {request.method} {request.url.path}",
        exc_info=True
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": "An unexpected error occurred. Our team has been notified.",
            "request_id": str(request.headers.get("x-request-id", "unknown"))
        }
    )

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail}
    )


# Trust proxy headers from Render's load balancer.
# Safe on Render because their infrastructure strips client-supplied
# X-Forwarded-For headers before they reach this service.
# IMPORTANT: If migrating off Render, audit this setting first.
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=["*"])

# CORS Middleware (Updated with expose_headers for SSE streaming)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL, "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Requested-With"],
)

# SessionMiddleware for OAuth2
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    same_site="lax",
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


@app.get("/health", tags=["Health"])
async def health_check():
    """
    Dedicated health check endpoint for Render's health monitor.
    Returns 200 if the application is running correctly.
    """
    return {
        "status": "healthy",
        "service": "drivefetch-backend",
    }


@app.get("/")
def read_root():
    """Simple API status health check endpoint."""
    return {"status": "API is running"}