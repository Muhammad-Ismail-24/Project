import os
import asyncio
import functools
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """Central configuration management using Pydantic Settings.
    Automatically reads environment variables and provides safe fallbacks.
    """
    openrouter_api_key: str = ""
    gemini_api_key: str = ""
    database_url: str = "sqlite:///./gaariguru.db"
    
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

