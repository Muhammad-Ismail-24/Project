import os
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import create_db_and_tables
from api.calc_routes import router as calc_router
from api.chat_routes import router as chat_router
from api.search_routes import router as search_router

# Initialize the core FastAPI app
app = FastAPI(title="CarFinder API")

# Add CORS middleware to support local frontend React/Vite development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include core routers
app.include_router(calc_router)
app.include_router(chat_router)
app.include_router(search_router)

@app.on_event("startup")
def on_startup():
    """Trigger database and tables creation on application startup."""
    create_db_and_tables()

@app.get("/")
def read_root():
    """Simple API status health check endpoint."""
    return {"status": "API is running"}