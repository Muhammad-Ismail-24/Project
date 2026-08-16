"""
test_model_routing.py

Tests the global multi-tier model router in agents/config.py.

  Tier 1 — Gemini cascade over GEMINI_MODEL_POOL, zero-delay failover on 429
  Tier 2 — Groq via the OpenAI-compatible endpoint

The Gemini cascade tests use a fake client, so they run offline and prove the
routing logic itself rather than the network. The Groq test makes a real call
and is SKIPPED (not failed) when GROQ_API_KEY is absent.

Run:  python test_model_routing.py
"""
import asyncio
import sys
import time

from google.genai import errors as genai_errors

import agents.config as config
from agents.config import (
    GEMINI_MODEL_POOL,
    GROQ_MODEL_POOL,
    execute_groq_fallback,
    generate_content_resilient,
    settings,
)

_passed = 0
_failed = 0
_skipped = 0


def check(label, condition, detail=""):
    global _passed, _failed
    if condition:
        _passed += 1
        print(f"  PASS  {label}{(' - ' + str(detail)) if detail else ''}")
    else:
        _failed += 1
        print(f"  FAIL  {label}{(' - ' + str(detail)) if detail else ''}")


def skip(label, reason):
    global _skipped
    _skipped += 1
    print(f"  SKIP  {label} - {reason}")


# ---------------------------------------------------------------------------
# Fake Gemini client
# ---------------------------------------------------------------------------

class _FakeResponse:
    def __init__(self, text):
        self.text = text


def _rate_limit_error(model: str) -> Exception:
    """A real google.genai 429, exactly as the SDK raises it."""
    return genai_errors.ClientError(
        429,
        {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED",
                   "message": f"Quota exceeded for model {model}"}},
    )


def _server_error() -> Exception:
    return genai_errors.ServerError(
        503,
        {"error": {"code": 503, "status": "UNAVAILABLE",
                   "message": "The model is overloaded"}},
    )


class _FakeModels:
    def __init__(self, behaviour):
        self.behaviour = behaviour
        self.calls = []

    async def generate_content(self, model, contents, config):
        self.calls.append(model)
        outcome = self.behaviour(model, len([c for c in self.calls if c == model]))
        if isinstance(outcome, Exception):
            raise outcome
        return _FakeResponse(outcome)


class _FakeAio:
    def __init__(self, models):
        self.models = models


class _FakeClient:
    """Stands in for genai.Client — only .aio.models.generate_content is used."""
    def __init__(self, behaviour):
        self._models = _FakeModels(behaviour)
        self.aio = _FakeAio(self._models)

    @property
    def calls(self):
        return self._models.calls


async def run_cascade(behaviour):
    client = _FakeClient(behaviour)
    try:
        text = await generate_content_resilient(
            contents="test prompt", config=None, client=client
        )
        return text, client.calls, None
    except Exception as e:
        return None, client.calls, e


# ---------------------------------------------------------------------------
async def main():
    print("\n[1] Pool wiring")
    check("GEMINI_MODEL_POOL is non-empty", len(GEMINI_MODEL_POOL) > 0, GEMINI_MODEL_POOL)
    check("PRIMARY_MODEL is the head of the pool",
          config.PRIMARY_MODEL == GEMINI_MODEL_POOL[0], config.PRIMARY_MODEL)
    check("FALLBACK_MODELS is the tail of the pool",
          config.FALLBACK_MODELS == GEMINI_MODEL_POOL[1:])
    check("settings exposes groq_api_key", hasattr(settings, "groq_api_key"))
    check("GROQ_MODEL_POOL leads with llama-3.3-70b-versatile",
          GROQ_MODEL_POOL[0] == "llama-3.3-70b-versatile", GROQ_MODEL_POOL)

    # -----------------------------------------------------------------------
    print("\n[2] 429 on model 1 -> instant failover to model 2")
    first = GEMINI_MODEL_POOL[0]

    def one_bad(model, _n):
        return _rate_limit_error(model) if model == first else "OK-FROM-SECOND"

    started = time.perf_counter()
    text, calls, err = await run_cascade(one_bad)
    elapsed = time.perf_counter() - started

    check("request succeeded", text == "OK-FROM-SECOND", repr(text))
    check("no exception raised", err is None, err)
    check("tried model 1 then model 2 in pool order",
          calls == [GEMINI_MODEL_POOL[0], GEMINI_MODEL_POOL[1]], calls)
    check("did NOT retry the rate-limited model",
          calls.count(first) == 1, f"{calls.count(first)} call(s) to {first}")
    check("failover was zero-delay (< 1s)", elapsed < 1.0, f"{elapsed:.3f}s")

    # -----------------------------------------------------------------------
    print("\n[3] 429 cascades the whole pool")
    def all_429(model, _n):
        return _rate_limit_error(model)

    started = time.perf_counter()
    text, calls, err = await run_cascade(all_429)
    elapsed = time.perf_counter() - started

    check("every model in the pool was tried once",
          calls == list(GEMINI_MODEL_POOL), calls)
    check("raises only after the pool is exhausted",
          isinstance(err, RuntimeError), type(err).__name__)
    check("error names the exhaustion",
          err is not None and "exhausted" in str(err).lower(), str(err)[:70])
    check("whole cascade stayed fast (< 2s)", elapsed < 2.0, f"{elapsed:.3f}s")

    # -----------------------------------------------------------------------
    print("\n[4] Last model in the pool answers")
    last = GEMINI_MODEL_POOL[-1]

    def only_last_ok(model, _n):
        return "OK-FROM-LAST" if model == last else _rate_limit_error(model)

    text, calls, err = await run_cascade(only_last_ok)
    check("recovers on the final model", text == "OK-FROM-LAST", repr(text))
    check("walked the full pool to get there", calls == list(GEMINI_MODEL_POOL))

    # -----------------------------------------------------------------------
    print("\n[5] 503 gets one same-model retry, then fails over")
    def flaky_first(model, n):
        if model == first:
            return _server_error()
        return "OK-AFTER-503"

    text, calls, err = await run_cascade(flaky_first)
    check("succeeds on the next model", text == "OK-AFTER-503", repr(text))
    check("retried the 503 model once before moving on",
          calls.count(first) == 2, f"{calls.count(first)} call(s) to {first}")

    # A 503 that clears on retry must be served by the same model.
    def recovers_on_retry(model, n):
        if model == first and n == 1:
            return _server_error()
        return "OK-SAME-MODEL"

    text, calls, err = await run_cascade(recovers_on_retry)
    check("a recovered 503 is served by the original model",
          text == "OK-SAME-MODEL" and calls == [first, first], calls)

    # -----------------------------------------------------------------------
    print("\n[6] Unknown/retired model is skipped, not fatal")
    def missing_first(model, _n):
        if model == first:
            return genai_errors.ClientError(
                404, {"error": {"code": 404, "status": "NOT_FOUND",
                                "message": f"models/{model} is not found"}})
        return "OK-AFTER-404"

    text, calls, err = await run_cascade(missing_first)
    check("skips the unknown model and continues", text == "OK-AFTER-404", repr(text))
    check("did not retry the missing model", calls.count(first) == 1, calls)

    # -----------------------------------------------------------------------
    print("\n[7] Non-transient errors raise immediately (no pool burn)")
    def bad_key(model, _n):
        return genai_errors.ClientError(
            400, {"error": {"code": 400, "status": "INVALID_ARGUMENT",
                            "message": "API key not valid"}})

    text, calls, err = await run_cascade(bad_key)
    check("raises rather than cascading", err is not None, type(err).__name__)
    check("stopped after the first model",
          calls == [first], calls)
    check("propagates the original error (not a pool-exhausted RuntimeError)",
          not isinstance(err, RuntimeError), type(err).__name__)

    # -----------------------------------------------------------------------
    print("\n[8] Groq fallback (Tier 2)")
    if not settings.groq_api_key:
        skip("live Groq call", "GROQ_API_KEY not set in this environment")
        # Still prove the guard fires cleanly rather than hanging or 401-ing.
        try:
            await execute_groq_fallback([{"role": "user", "content": "hi"}])
            check("missing key raises a clear error", False, "no exception raised")
        except ValueError as e:
            check("missing key raises a clear ValueError",
                  "GROQ_API_KEY" in str(e), str(e))
        except Exception as e:
            check("missing key raises a clear ValueError", False,
                  f"{type(e).__name__}: {e}")
    else:
        try:
            reply = await execute_groq_fallback(
                [
                    {"role": "system", "content": "You are terse."},
                    {"role": "user", "content": "Name the capital of Pakistan in one word."},
                ],
                temperature=0.0,
                max_tokens=20,
            )
            check("Groq returned text", bool(reply and reply.strip()), repr(reply[:60]))
            check("Groq answer is on-topic", "islamabad" in (reply or "").lower(), repr(reply[:60]))
        except Exception as e:
            check("Groq text call succeeded", False, f"{type(e).__name__}: {e}")

        try:
            import json
            raw = await execute_groq_fallback(
                [
                    {"role": "system", "content": "Extract car search fields."},
                    {"role": "user", "content": "corolla 2020 in lahore under 40 lacs"},
                ],
                temperature=0.0,
                json_mode=True,
            )
            parsed = json.loads(raw)
            check("Groq json_mode returns parseable JSON", isinstance(parsed, dict),
                  str(parsed)[:90])
        except Exception as e:
            check("Groq json_mode call succeeded", False, f"{type(e).__name__}: {e}")

    # -----------------------------------------------------------------------
    # Offline coverage for the Groq tier, so its failover and request shaping
    # are proven even when no GROQ_API_KEY is available to hit the live API.
    print("\n[8b] Groq request shaping + failover (offline, faked client)")

    class _FakeChoice:
        def __init__(self, content):
            self.message = type("M", (), {"content": content})()

    class _FakeCompletion:
        def __init__(self, content):
            self.choices = [_FakeChoice(content)]

    class _FakeCompletions:
        def __init__(self, behaviour, log):
            self.behaviour = behaviour
            self.log = log

        async def create(self, model, **kwargs):
            self.log.append({"model": model, **kwargs})
            outcome = self.behaviour(model)
            if isinstance(outcome, Exception):
                raise outcome
            return _FakeCompletion(outcome)

    class _FakeGroq:
        def __init__(self, behaviour, log):
            self.chat = type("C", (), {})()
            self.chat.completions = _FakeCompletions(behaviour, log)

    def install_fake_groq(behaviour):
        log = []
        config._groq_client = lambda: _FakeGroq(behaviour, log)
        return log

    real_groq_client = config._groq_client
    try:
        # 429 on the 70b model must fail over to 8b-instant.
        class _RateLimited(Exception):
            pass

        log = install_fake_groq(
            lambda m: _RateLimited("429 rate_limit_exceeded")
            if m == GROQ_MODEL_POOL[0] else "OK-FROM-8B"
        )
        out = await execute_groq_fallback([{"role": "user", "content": "hi"}])
        check("Groq 429 fails over to the next Groq model", out == "OK-FROM-8B", repr(out))
        check("tried both Groq models in order",
              [c["model"] for c in log] == GROQ_MODEL_POOL, [c["model"] for c in log])

        # json_mode must set response_format and satisfy Groq's "json" rule.
        log = install_fake_groq(lambda m: '{"make":"Toyota"}')
        await execute_groq_fallback([{"role": "user", "content": "corolla"}], json_mode=True)
        check("json_mode sets response_format=json_object",
              log[0].get("response_format") == {"type": "json_object"}, log[0].get("response_format"))
        check("json_mode guarantees the word 'json' appears in the prompt",
              any("json" in str(m["content"]).lower() for m in log[0]["messages"]))

        # max_tokens / temperature pass through.
        log = install_fake_groq(lambda m: "text")
        await execute_groq_fallback([{"role": "user", "content": "hi"}],
                                    temperature=0.65, max_tokens=900)
        check("max_tokens passes through", log[0].get("max_tokens") == 900, log[0].get("max_tokens"))
        check("temperature passes through", log[0].get("temperature") == 0.65, log[0].get("temperature"))
        check("plain text mode sets no response_format",
              "response_format" not in log[0])

        # response_schema forces JSON and injects the schema.
        from pydantic import BaseModel

        class _Shape(BaseModel):
            make: str

        log = install_fake_groq(lambda m: '{"make":"Honda"}')
        await execute_groq_fallback([{"role": "system", "content": "Extract."},
                                     {"role": "user", "content": "civic"}],
                                    response_schema=_Shape)
        check("response_schema forces json_object",
              log[0].get("response_format") == {"type": "json_object"})
        check("response_schema is injected into the system message",
              "make" in str(log[0]["messages"][0]["content"]))

        # Non-transient errors must not burn the second model.
        class _BadKey(Exception):
            pass

        log = install_fake_groq(lambda m: _BadKey("401 invalid api key"))
        try:
            await execute_groq_fallback([{"role": "user", "content": "hi"}])
            check("Groq non-transient error raises", False, "no exception")
        except _BadKey:
            check("Groq non-transient error raises immediately", True)
            check("Groq did not try the second model after a 401",
                  len(log) == 1, [c["model"] for c in log])
        except Exception as e:
            check("Groq non-transient error raises immediately", False,
                  f"{type(e).__name__}: {e}")
    finally:
        config._groq_client = real_groq_client

    # -----------------------------------------------------------------------
    print("\n[9] Agent wiring")
    import agents.chatbot as chatbot
    import agents.orchestrator as orchestrator

    check("chatbot exposes _execute_groq_call", hasattr(chatbot, "_execute_groq_call"))
    check("chatbot dropped _execute_llama_call",
          not hasattr(chatbot, "_execute_llama_call"))
    check("orchestrator exposes _execute_groq_call",
          hasattr(orchestrator, "_execute_groq_call"))
    check("orchestrator dropped _execute_openrouter_call",
          not hasattr(orchestrator, "_execute_openrouter_call"))

    # Signatures the rest of the codebase depends on must be untouched.
    import inspect
    sig = inspect.signature(generate_content_resilient)
    check("generate_content_resilient signature unchanged",
          list(sig.parameters) == ["contents", "config", "client"], list(sig.parameters))
    retry_sig = inspect.signature(config.async_retry)
    check("async_retry signature unchanged",
          list(retry_sig.parameters) == ["retries", "delay"], list(retry_sig.parameters))

    print(f"\n{'=' * 62}")
    print(f"  {_passed} passed, {_failed} failed, {_skipped} skipped")
    print(f"{'=' * 62}\n")
    return 1 if _failed else 0


sys.exit(asyncio.run(main()))
