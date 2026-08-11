import os
import asyncio
import functools
from pydantic_settings import BaseSettings, SettingsConfigDict
from google import genai
from google.genai import types

class Settings(BaseSettings):
    """Central configuration management using Pydantic Settings.
    Automatically reads environment variables and provides safe fallbacks.
    """
    openrouter_api_key: str = ""
    gemini_api_key: str = ""
    google_api_key: str = ""
    database_url: str = "sqlite:///./drivefetch.db"
    port: int = 8000
    host: str = "0.0.0.0"
    frontend_url: str = "http://localhost:5173"
    secret_key: str = "super-secret-key-for-local-dev"
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

# Instantiate settings globally
settings = Settings()

def async_retry(retries: int = 2, delay: float = 1.0):
    """Decorator to retry asynchronous functions with backoff.
    
    - On a 429 / ResourceExhausted (Gemini free-tier 5 RPM quota hit),
      applies a hard 15-second sleep to let the per-minute bucket refill
      before the next attempt, rather than immediately hammering the endpoint.
    - On all other transient errors, uses the standard linear `delay` backoff.
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(retries + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exc = e
                    err_str = str(e).lower()
                    # Detect Gemini 429 / quota exceeded
                    is_rate_limit = (
                        '429' in err_str
                        or 'quota' in err_str
                        or 'resource_exhausted' in err_str
                        or 'rate limit' in err_str
                    )
                    backoff = 15.0 if is_rate_limit else delay
                    print(
                        f"[Retry Wrapper] Attempt {attempt + 1}/{retries + 1} failed for '{func.__name__}': {e}."
                        f" {'Rate limit hit — sleeping 15s.' if is_rate_limit else f'Retrying in {backoff}s.'}"
                    )
                    if attempt < retries:
                        await asyncio.sleep(backoff)
            # Re-raise the final exception if all retries are exhausted
            raise last_exc
        return wrapper
    return decorator


# Centralized Model Config
GEMINI_API_KEY = settings.gemini_api_key or settings.google_api_key
ai_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

PRIMARY_MODEL = "gemini-3.5-flash-lite"
FALLBACK_MODELS = ["gemini-3.1-flash-lite"]

async def generate_content_resilient(
    contents,
    config: types.GenerateContentConfig,
    client: genai.Client = None
) -> str:
    """
    Centralized execution wrapper for all Gemini API calls across DriveFetch agents.
    Handles 503 UNAVAILABLE, 429 Rate Limits, and high demand spikes via 
    exponential backoff and fallback model failover.
    """
    if client is None:
        client = ai_client
        
    models_to_try = [PRIMARY_MODEL] + FALLBACK_MODELS
    
    for model_name in models_to_try:
        max_retries = 2
        for attempt in range(max_retries):
            try:
                response = await client.aio.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=config,
                )
                return response.text
            except Exception as e:
                err_str = str(e)
                is_transient = any(
                    phrase in err_str 
                    for phrase in ["503", "429", "UNAVAILABLE", "high demand", "Quota", "RESOURCE_EXHAUSTED"]
                )
                
                if is_transient and attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 2.0
                    print(f"[Gemini Retry] {model_name} busy/rate-limited. Retrying in {wait_time}s (Attempt {attempt + 1}/{max_retries})...")
                    await asyncio.sleep(wait_time)
                elif is_transient:
                    print(f"[Gemini Fallback] {model_name} failed after retries. Failing over to next model...")
                    break
                else:
                    # Non-transient error (e.g. invalid key or malformed prompt)
                    raise e

    raise RuntimeError("CRITICAL: All Gemini AI models (Primary + Fallbacks) are currently unavailable due to high Google API demand.")
