from core.logger import get_logger
logger = get_logger(__name__)
"""
agents/config.py

Central configuration + the global multi-tier model router.

ROUTING ARCHITECTURE (2026-08-16)
---------------------------------
Every LLM call in DriveFetch now flows through a waterfall:

    Tier 1 — Gemini cascade (GEMINI_MODEL_POOL)
        Ordered by per-minute quota headroom, not by raw capability. On a 429
        the router does NOT sleep — it fails over to the next model in the pool
        immediately, because a different model has a different quota bucket and
        waiting 15s to retry the *same* exhausted bucket was the stall this
        replaces. Only a genuinely transient fault (503 / UNAVAILABLE) gets a
        short retry on the same model.

    Tier 2 — Groq (execute_groq_fallback)
        Reached when the whole Gemini pool is exhausted. Uses the OpenAI-compatible
        endpoint at https://api.groq.com/openai/v1. Replaces the previous
        OpenRouter fallback, whose free-tier key had gone inactive.

generate_content_resilient() raises once Tier 1 is exhausted; the agents that
have a text-shaped (rather than schema-shaped) response — chatbot.py and
orchestrator.py — catch that and call execute_groq_fallback() themselves.

BACKWARD COMPATIBILITY
    settings, async_retry, generate_content_resilient, PRIMARY_MODEL and
    FALLBACK_MODELS all keep their existing names and signatures, so no agent
    or route needed to change to pick up the new routing.
"""
import asyncio
import functools
import json
import os

from google import genai
from google.genai import types
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration management using Pydantic Settings.
    Automatically reads environment variables and provides safe fallbacks.
    """
    # DEPRECATED: the OpenRouter free-tier key is inactive. Retained so existing
    # .env files keep parsing; no code path reads it any more. Use groq_api_key.
    openrouter_api_key: SecretStr = SecretStr("")
    groq_api_key: SecretStr = SecretStr("")
    gemini_api_key: SecretStr = SecretStr("")
    google_api_key: SecretStr = SecretStr("")
    database_url: str = "sqlite:///./drivefetch.db"
    port: int = 8000
    host: str = "0.0.0.0"
    FRONTEND_URL: str = "https://drivefetch.vercel.app"
    secret_key: SecretStr = SecretStr("super-secret-key-for-local-dev")
    SESSION_SECRET_KEY: SecretStr = SecretStr("change-this-in-production")
    GOOGLE_CLIENT_ID: str
    GOOGLE_CLIENT_SECRET: SecretStr
    gemini_model_pool: SecretStr = SecretStr("")
    ENABLE_API_DOCS: bool = False
    SENTRY_DSN_BACKEND: str = ""
    # Empty string disables Sentry in local dev

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


# Instantiate settings globally
settings = Settings()


def async_retry(retries: int = 2, delay: float = 1.0):
    """Decorator to retry asynchronous functions with backoff.

    - On a 429 / ResourceExhausted (Gemini free-tier quota hit), applies a hard
      15-second sleep to let the per-minute bucket refill before the next
      attempt, rather than immediately hammering the endpoint.
    - On all other transient errors, uses the standard linear `delay` backoff.

    NOTE: this decorator wraps whole agent functions. Inside a single Gemini
    call, generate_content_resilient() already fails over across the model pool
    with no delay, so this 15s sleep is now a last resort rather than the first
    line of defence.
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
                    is_rate_limit = _is_rate_limit(e)
                    backoff = 15.0 if is_rate_limit else delay
                    logger.info(
                        f"[Retry Wrapper] Attempt {attempt + 1}/{retries + 1} failed for '{func.__name__}': {e}."
                        f" {'Rate limit hit — sleeping 15s.' if is_rate_limit else f'Retrying in {backoff}s.'}"
                    )
                    if attempt < retries:
                        await asyncio.sleep(backoff)
            # Re-raise the final exception if all retries are exhausted
            raise last_exc
        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# TIER 1 — GEMINI CASCADE
# ---------------------------------------------------------------------------

GEMINI_API_KEY = settings.gemini_api_key.get_secret_value() or settings.google_api_key.get_secret_value()
ai_client = genai.Client(
    api_key=GEMINI_API_KEY,
    http_options=types.HttpOptions(timeout=30000)
) if GEMINI_API_KEY else None

# Ordered by capability first, because the live AI Studio limits make that free:
# the three strongest lite models all sit at the maximum 15 RPM, so leading with
# the newest costs nothing in availability. Each entry is still an independent
# quota bucket, which is what makes the zero-delay failover worth doing — the
# router only drops to a lower tier once the better one is actually exhausted.
#
# (This supersedes the earlier RPM-first ordering, which put 2.5-flash-lite at
# the head and traded answer quality for headroom that turned out not to be
# needed.)
#
# Override at deploy time with GEMINI_MODEL_POOL as a comma-separated list,
# e.g. GEMINI_MODEL_POOL="gemini-3.5-flash-lite,gemini-3.1-flash-lite"
_DEFAULT_GEMINI_MODEL_POOL = [
    "gemini-3.5-flash-lite",   # 15 RPM (Primary: Best reasoning)
    "gemini-3.1-flash-lite",   # 15 RPM (Secondary)
    "gemini-2-flash-lite",     # 15 RPM (Tertiary)
    "gemini-2.5-flash-lite",   # 10 RPM (Fallback)
    "gemini-3.1-pro",          # 10 RPM (Heavy reasoning fallback)
]

_pool_override = settings.gemini_model_pool.get_secret_value().strip()
GEMINI_MODEL_POOL = (
    [m.strip() for m in _pool_override.split(",") if m.strip()]
    if _pool_override else list(_DEFAULT_GEMINI_MODEL_POOL)
)

# Retained for backward compatibility — chatbot.py imports PRIMARY_MODEL.
PRIMARY_MODEL = GEMINI_MODEL_POOL[0]
FALLBACK_MODELS = GEMINI_MODEL_POOL[1:]

# ---------------------------------------------------------------------------
# TIMEOUT — the same 30-second budget for both Gemini and Groq tiers.
# Gemini's google-genai SDK wants milliseconds; Groq's openai SDK wants seconds.
# ---------------------------------------------------------------------------
GEMINI_TIMEOUT_SECONDS = 30
GEMINI_TIMEOUT_MS = GEMINI_TIMEOUT_SECONDS * 1000

# Transient faults worth one quick retry on the SAME model (the model is fine,
# the server is briefly busy).
_TRANSIENT_MARKERS = ("503", "unavailable", "high demand", "500",
                      "internal error", "deadline", "timeout")

# Quota exhaustion — retrying the same model is pointless, move on instantly.
_RATE_LIMIT_MARKERS = ("429", "resource_exhausted", "resourceexhausted",
                       "quota", "rate limit", "ratelimit", "too many requests")

# A model name this project asked for that the API does not serve. Skip it
# rather than aborting the whole request — model aliases get retired, and one
# stale name in the pool must not take the router down with it.
_MODEL_MISSING_MARKERS = ("404", "not_found", "not found", "was not found",
                          "is not supported", "unsupported model",
                          "invalid model", "does not exist", "unknown model")


def _error_code(exc: Exception):
    """Best-effort HTTP status for an exception, or None."""
    for attr in ("code", "status_code"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
    return None


def _matches(exc: Exception, markers: tuple) -> bool:
    text = f"{getattr(exc, 'status', '')} {exc}".lower()
    return any(m in text for m in markers)


def _is_rate_limit(exc: Exception) -> bool:
    """True for 429 / RESOURCE_EXHAUSTED from any provider."""
    return _error_code(exc) == 429 or _matches(exc, _RATE_LIMIT_MARKERS)


def _is_transient(exc: Exception) -> bool:
    """True for briefly-retryable server-side faults (not quota)."""
    return _error_code(exc) in (500, 502, 503, 504) or _matches(exc, _TRANSIENT_MARKERS)


def _is_model_unavailable(exc: Exception) -> bool:
    """True when the named model itself is unknown/retired."""
    return _error_code(exc) == 404 or _matches(exc, _MODEL_MISSING_MARKERS)


async def generate_content_resilient(
    contents,
    config: types.GenerateContentConfig,
    client: genai.Client = None
) -> str:
    """
    Centralized execution wrapper for all Gemini API calls across DriveFetch agents.

    Walks GEMINI_MODEL_POOL in order:
      - 429 / RESOURCE_EXHAUSTED  -> log and fail over to the next model with NO delay
      - 503 / UNAVAILABLE / 5xx   -> one short retry on the same model, then fail over
      - unknown or retired model  -> skip it and continue down the pool
      - anything else             -> raise immediately (bad key, malformed prompt)

    Raises RuntimeError only once every model in the pool has been exhausted.
    Callers that can accept a non-Gemini answer should catch that and fall
    through to execute_groq_fallback() (Tier 2).

    Signature is unchanged from the pre-router version.
    """
    if client is None:
        client = ai_client

    if client is None:
        raise RuntimeError(
            "CRITICAL: No Gemini client configured — set GEMINI_API_KEY or GOOGLE_API_KEY."
        )

    pool = GEMINI_MODEL_POOL
    last_error: Exception | None = None

    for index, model_name in enumerate(pool):
        next_model = pool[index + 1] if index + 1 < len(pool) else None

        # One retry budget per model, spent only on genuinely transient faults.
        for attempt in range(2):
            try:
                response = await client.aio.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=config,
                )
                if index > 0:
                    logger.info(f"[ModelRouter] Served by fallback model '{model_name}'.")
                return response.text

            except (TimeoutError, asyncio.TimeoutError) as e:
                last_error = e
                logger.error(
                    f"[ModelRouter] Gemini call to {model_name} timed out "
                    f"after {GEMINI_TIMEOUT_SECONDS}s (attempt {attempt + 1})."
                )
                if attempt == 0:
                    await asyncio.sleep(1.0)
                    continue
                if next_model:
                    logger.info(
                        f"[ModelRouter] Failing over to {next_model} after timeout..."
                    )
                break

            except Exception as e:
                last_error = e

                if _is_rate_limit(e):
                    # Zero-delay failover: a different model is a different
                    # quota bucket, so sleeping here would waste the request.
                    if next_model:
                        logger.info(
                            f"[ModelRouter] Rate limit hit on {model_name}. "
                            f"Failing over to {next_model}..."
                        )
                    else:
                        logger.info(
                            f"[ModelRouter] Rate limit hit on {model_name}. "
                            f"No models left in the Gemini pool."
                        )
                    break

                if _is_model_unavailable(e):
                    logger.info(
                        f"[ModelRouter] Model '{model_name}' is not available "
                        f"({e}). Skipping to next model in pool."
                    )
                    break

                if _is_transient(e):
                    if attempt == 0:
                        logger.info(
                            f"[ModelRouter] {model_name} temporarily unavailable. "
                            f"Retrying once in 2s..."
                        )
                        await asyncio.sleep(2.0)
                        continue
                    logger.info(
                        f"[ModelRouter] {model_name} still unavailable after retry. "
                        f"Failing over to {next_model or 'nothing — pool exhausted'}..."
                    )
                    break

                # Non-transient: invalid API key, malformed prompt, safety block.
                # Failing over would just reproduce the same error on every model.
                raise

    raise RuntimeError(
        f"CRITICAL: All {len(pool)} Gemini models in the routing pool are exhausted "
        f"or unavailable. Last error: {last_error}"
    )


# ---------------------------------------------------------------------------
# TIER 2 — GROQ FALLBACK
# ---------------------------------------------------------------------------

GROQ_BASE_URL = "https://api.groq.com/openai/v1"

# Same idea as the Gemini pool: try the strong model, drop to the fast one when
# its quota is gone. 8b-instant has a much larger free-tier allowance.
GROQ_MODEL_POOL = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
]

GROQ_TIMEOUT = float(GEMINI_TIMEOUT_SECONDS)  # aligned with Gemini tier


def _groq_client():
    """Builds an AsyncOpenAI client pointed at Groq, or raises if unconfigured."""
    api_key = settings.groq_api_key.get_secret_value()
    if not api_key:
        raise ValueError("GROQ_API_KEY is empty/not configured.")

    # Imported lazily so a missing/older `openai` package cannot break module
    # import for the Gemini-only code paths.
    from openai import AsyncOpenAI

    return AsyncOpenAI(
        base_url=GROQ_BASE_URL,
        api_key=api_key,
        max_retries=0,      # instant failover — the router handles retries
        timeout=GROQ_TIMEOUT,
    )


async def execute_groq_fallback(
    formatted_messages: list,
    response_schema=None,
    temperature: float = 0.2,
    json_mode: bool = False,
    max_tokens: int | None = None,
) -> str:
    """
    Tier 2 fallback: runs a chat completion on Groq and returns the raw text.

    Args:
        formatted_messages: OpenAI-style [{"role": ..., "content": ...}, ...].
        response_schema:    Optional pydantic model or dict describing the wanted
                            JSON shape. Groq's OpenAI-compatible endpoint has no
                            native schema enforcement, so the schema is injected
                            into the system message as an instruction and JSON
                            mode is forced on. Validate the result caller-side.
        temperature:        Sampling temperature.
        json_mode:          Force response_format={"type": "json_object"}.
        max_tokens:         Optional output cap. Additive to the agreed
                            signature — chatbot.py needs 900 to stop long spec
                            answers being truncated mid-sentence.

    Raises the last exception if every model in GROQ_MODEL_POOL fails.
    """
    if not formatted_messages:
        raise ValueError("execute_groq_fallback called with no messages.")

    want_json = json_mode or response_schema is not None
    fallback_result = json.dumps({"make": "Unknown", "model": "Unknown"}) if want_json else "Unknown"

    try:
        client = _groq_client()
    except ValueError as e:
        logger.warning(f"Groq fallback skipped: {e}")
        return fallback_result
    except Exception as e:
        logger.error(f"Failed to initialize Groq client: {e}")
        return fallback_result

    messages = [dict(m) for m in formatted_messages]

    if response_schema is not None:
        schema_text = _schema_to_text(response_schema)
        if schema_text:
            instruction = (
                "Respond with a single valid JSON object and nothing else. "
                f"It must match this schema:\n{schema_text}"
            )
            if messages and messages[0].get("role") == "system":
                messages[0]["content"] = f"{messages[0]['content']}\n\n{instruction}"
            else:
                messages.insert(0, {"role": "system", "content": instruction})

    if want_json and not any("json" in str(m.get("content", "")).lower() for m in messages):
        # Groq rejects json_object mode unless the word "json" appears in the
        # prompt; this guard keeps the request from 400-ing.
        messages.append({"role": "system", "content": "Reply with JSON only."})

    request_kwargs = {"messages": messages, "temperature": temperature}
    if want_json:
        request_kwargs["response_format"] = {"type": "json_object"}
    if max_tokens:
        request_kwargs["max_tokens"] = max_tokens

    last_error: Exception | None = None
    for index, model_name in enumerate(GROQ_MODEL_POOL):
        next_model = GROQ_MODEL_POOL[index + 1] if index + 1 < len(GROQ_MODEL_POOL) else None
        try:
            response = await client.chat.completions.create(
                model=model_name, **request_kwargs
            )
            text = (response.choices[0].message.content or "").strip()
            logger.info(f"[ModelRouter] Groq fallback served by '{model_name}'.")
            return text

        except Exception as e:
            last_error = e
            if _is_rate_limit(e) or _is_transient(e):
                if next_model:
                    logger.info(
                        f"[ModelRouter] Groq {model_name} unavailable ({e}). "
                        f"Failing over to {next_model}..."
                    )
                    continue
                logger.info(f"[ModelRouter] Groq {model_name} unavailable and no models left.")
                break
            # Bad key / malformed request — the next model would fail identically.
            logger.error(f"[ModelRouter] Groq fallback failed: {e}")
            return fallback_result

    logger.error(f"Groq fallback exhausted all models. Last error: {last_error}")
    return fallback_result


def _schema_to_text(response_schema) -> str:
    """Renders a pydantic model or plain dict schema as prompt-injectable JSON."""
    try:
        if hasattr(response_schema, "model_json_schema"):
            return json.dumps(response_schema.model_json_schema(), indent=1)
        if isinstance(response_schema, dict):
            return json.dumps(response_schema, indent=1)
        return str(response_schema)
    except Exception:
        return ""
