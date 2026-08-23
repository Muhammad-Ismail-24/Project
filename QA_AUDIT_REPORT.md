# DriveFetch Overnight QA Audit Report

## Document A — Master Bug Report

| # | Severity | Section | File Path | Function/Line | Description | Recommended Fix |
|---|---|---|---|---|---|---|
| 1 | **Critical** | 2.5 Scraper Concurrency | `drivefetch-backend/scrapers/runner.py` | `execute_search_pipeline` | **Semaphore Scope Bug:** `asyncio.Semaphore(10)` is instantiated *inside* the route handler. This creates a new semaphore per request, bypassing global concurrency limits and allowing a DoS attack to exhaust sockets/RAM by opening thousands of concurrent scraper connections under load. | Move the `Semaphore` instantiation to the module level (global scope) so all concurrent requests share the same pool of 10 connections. |
| 2 | **Critical** | 2.6 Rate Limiter | `drivefetch-backend/main.py` & `api/rate_limiter.py` | `limiter = Limiter(key_func=get_remote_address)` | **Ineffective Rate Limiting:** The `slowapi` limiter uses an in-memory storage backend keyed by IP. In a multi-process deployment (e.g., Uvicorn workers), each process has its own limit. Furthermore, the chat (`/api/chat`) and calculator endpoints have no rate limiting at all, exposing the expensive LLM APIs to budget exhaustion. | Switch the limiter backend to Redis. Add `@limiter.limit` decorators to all state-changing and LLM-triggering routes (chat, calc). |
| 3 | **Critical** | 4.3 CORS Configuration | `drivefetch-backend/main.py` | `allow_methods=["*"]`, `allow_headers=["*"]` | **Excessive CORS Exposure:** Allowing all methods and headers alongside `allow_credentials=True` violates secure-by-default principles and enables cross-origin credentialed misuse if a sub-domain or related origin is compromised. | Restrict `allow_methods` to `["GET", "POST", "OPTIONS"]` and specify explicit allowed headers. |
| 4 | **Critical** | 4.1 Prompt Injection | `drivefetch-backend/agents/orchestrator.py` | `parse_user_query` | **Unbounded User Input:** Unlike the evaluator (which properly uses `<user_query>` XML boundaries and strict isolation instructions), the orchestrator injects `user_input` directly into the LLM chain without strong delimiters, allowing attackers to overwrite the system prompt and bypass constraints. | Wrap `user_input` in strict XML delimiters in the orchestrator's prompt and explicitly instruct the model to treat the content strictly as untrusted string data. |
| 5 | **High** | 2.3 OAuth Flow | `drivefetch-backend/auth/routes.py` | `auth_callback` | **Session Fixation Risk:** When the user completes the Google OAuth flow, their `user_id` is simply attached to the existing session via `request.session["user_id"] = user.id`. The underlying session ID is not explicitly regenerated, making it vulnerable to session fixation attacks. | Regenerate the session or clear and rebuild the session context fully upon successful login to assign a new secure session token. |
| 6 | **High** | 3.1 Unmounted Components | `drivefetch-frontend/src/components/CarResultCard.jsx` | `useEffect` (Cleanup) | **Dangling Async State Updates:** The component initializes an `AbortController`, but `evaluateSingleCar` from `utils/api.js` does not properly consume the Axios `signal`. When the component unmounts, the pending fetch continues and attempts to update React state (`setAiData`), causing memory leaks. | Update `evaluateSingleCar` to extract `options.signal` and pass it to the Axios configuration payload. |
| 7 | **High** | 4.5 Dependencies | `drivefetch-frontend/package.json` | N/A | **Vulnerable Packages:** `npm audit` reveals High severity vulnerabilities in `nanoid`, `postcss`, and `react-router-dom` (RSC Mode CSRF bypass). | Run `npm audit fix` and explicitly pin dependencies to patched versions (e.g., update `react-router` beyond 7.18.1). |
| 8 | **High** | 3.3 AI Chat Context | `drivefetch-frontend/src/pages/ChatPage.jsx` | `sendMessage` | **Unbounded Context Window:** The chat interface sends the full history back to the backend without limiting the message depth. A malicious or overly engaged user can exceed the Gemini token window, causing silent API failures and degraded performance. | Implement a sliding window strategy (e.g., last 20 messages + system prompt) or dynamically summarize old history. |
| 9 | **Medium** | 1.1 Secrets & Env | Repository Root | N/A | **Missing Dev Contract:** No `.env.example` file exists. Developers have to guess the required environment variables. Furthermore, the `requirements.txt` file uses unpinned dependencies (`fastapi`, `uvicorn`, `pydantic`), risking build drift. | Create a `.env.example` documenting all keys used in `agents/config.py`. Use `pip freeze` to explicitly pin dependency versions. |
| 10 | **Medium** | 2.2 Global Exception Guard | `drivefetch-backend/main.py` | N/A | **No Global Exception Handler:** While `RateLimitExceeded` is caught, unexpected errors (e.g., scraper crashes, DB timeouts) fall back to FastAPI's default 500 handler, which may leak raw stack traces to the client in certain environments. | Implement a generic `@app.exception_handler(Exception)` that logs the traceback internally and returns a sanitized JSON error to the user. |
| 11 | **Medium** | 5.4 Test Suite Rot | `drivefetch-backend/` | `test_*.py` | **Broken Test Suite:** 8 out of 8 existing test scripts in the backend fail to run due to broken import paths (`pydantic`, `curl_cffi`, `playwright`). This indicates the test suite has decayed and is completely ignored in the deployment lifecycle. | Delete vestigial tests (like `test_pw.py`) or repair the imports and run them via a GitHub Actions pipeline. |
| 12 | **Low** | 5.1 Dead Code & Smells | `drivefetch-backend/page.html` | N/A | **Vestigial Files & Print Statements:** `page.html` is a dead file containing TODO comments. Furthermore, production API routes (like `search_cars`) use raw `print()` statements instead of a structured Python logger, ruining log aggregators. | Remove `page.html`. Replace all `print()` calls with Python's standard `logging` library using a JSON formatter. |
| 13 | **Low** | 3.5 SPA SEO Limits | `drivefetch-frontend/` | N/A | **CSR Limitations for SEO:** The app is a pure React SPA. While dynamic JSON-LD injection exists, crawlers that don't execute JS (like social media link bots) will see an empty `index.html`. | Evaluate a lightweight pre-rendering service (e.g., Rendertron) or migrate heavy marketing pages to Next.js / Astro for native SSR. |
| 14 | **Low** | 5.5 Type Safety | `drivefetch-frontend/src/` | N/A | **No TypeScript in Frontend:** The entire frontend is written in plain `.jsx`, relying on implicit runtime assumptions and increasing the risk of undefined object properties (e.g., missing nested JSON fields from the AI orchestrator). | Progressively migrate the React frontend from `.jsx` to TypeScript (`.tsx`). |

---

## Document B — Prioritized Remediation Roadmap

### **Sprint 1 (Do Today — Before Any Production Deployment)**
*The application must not handle real user traffic until these are closed.*
- **Fix the Scraper Concurrency Bug:** Move the `asyncio.Semaphore` out of the route handler into the global scope in `scrapers/runner.py` to prevent resource starvation.
- **Implement Robust Rate Limiting:** Apply `@limiter.limit` to `/api/chat` and `/api/calc`. Convert `slowapi` to use a Redis storage backend to support multi-process deployments.
- **Lock Down Prompt Boundaries:** Update `orchestrator.py` and `chatbot.py` to strictly encapsulate user queries in XML tags and apply rigid system prompts to prevent AI subversion.
- **Harden CORS Setup:** Remove wildcards from `allow_methods` and `allow_headers`.
- **Address npm Vulnerabilities:** Run `npm audit fix` immediately to patch the React Router CSRF flaw.

### **Sprint 2 (Do This Week)**
*Quality, stability, and fundamental security improvements.*
- **Secure the Auth Flow:** Explicitly regenerate session IDs upon successful Google OAuth callback to prevent session fixation.
- **Fix React Memory Leaks:** Ensure `axios` consumes the `AbortController` signal in `utils/api.js` to kill pending requests when components unmount.
- **Add Global Error Boundary (Backend):** Implement a global exception handler in FastAPI to prevent stack trace leaks.
- **Create Developer Contracts:** Add `.env.example` and lock `requirements.txt` dependencies.

### **Sprint 3 (Backlog)**
*Refactoring, maintainability, and long-term scaling.*
- **Implement Chat Context Limiting:** Enforce a sliding window mechanism for chat token tracking.
- **Revamp Logging & Observability:** Rip out `print()` statements and replace them with a structured logger (`structlog` or `logging`).
- **Test Suite Resurrection:** Fix or delete the broken `test_*.py` files and integrate `pytest` into `.github/workflows`.
- **Frontend TS Migration:** Begin migrating the `.jsx` frontend to TypeScript to catch runtime property errors statically.
- **SEO Pre-Rendering:** Evaluate integrating a pre-rendering hook in Vercel for crawler bots.

---

## Document C — Security Sign-Off Checklist

| Control / Check | Status | Associated Finding |
|---|---|---|
| 1. `.env` files are excluded from version control | **Yes** | — |
| 2. Development secrets are documented in `.env.example` | **No** | *Bug #9 (Sprint 2)* |
| 3. Dependency versions are pinned (Python & Node) | **No** | *Bug #9 (Sprint 2)* |
| 4. Third-party dependencies are free of critical/high CVEs | **No** | *Bug #7 (Sprint 1)* |
| 5. System secrets are strongly typed (Pydantic `SecretStr`) | **No** | Missing from `config.py` |
| 6. HTTP methods mapped semantically (GET for read, POST for write) | **Yes** | — |
| 7. User input validated via strict schemas before processing | **Yes** | Handled natively by Pydantic / FastAPI |
| 8. Application prevents brute force & DDoS (Global Rate Limiting) | **No** | *Bug #2 (Sprint 1)* |
| 9. CORS is restricted to explicit origins, methods, and headers | **No** | *Bug #3 (Sprint 1)* |
| 10. Database queries parameterised to prevent SQL Injection | **Yes** | Handled by SQLModel |
| 11. OAuth State parameter generated & validated (CSRF prevention) | **Yes** | Handled by `authlib` |
| 12. Session IDs regenerated upon authentication | **No** | *Bug #5 (Sprint 2)* |
| 13. Authentication cookies utilize `HttpOnly`, `Secure`, `SameSite` | **Yes** | Configured in `auth/routes.py` |
| 14. Prompt injection explicitly mitigated (delimiters + directives) | **No** | *Bug #4 (Sprint 1)* |
| 15. Cross-Site Scripting (XSS) mitigated on frontend output | **Yes** | React defaults; no unsafe `dangerouslySetInnerHTML` |
| 16. Sensitive PII / API keys excluded from application logs | **No** | *Bug #12 (Sprint 3)* - Unstructured `print()` usage |
| 17. Unhandled exceptions do not leak stack traces to the client | **No** | *Bug #10 (Sprint 2)* |
| 18. Automated CI pipeline tests pull requests before merging | **No** | *Bug #11 (Sprint 3)* |
| 19. Concurrent outbound connections bounded (Semaphore/Pool) | **No** | *Bug #1 (Sprint 1)* |
| 20. Application runs as non-root user (Docker `USER` directive) | **N/A** | No Dockerfile present |

**Audit Status:** `REJECTED — DO NOT DEPLOY.`
Critical remediations required from Sprint 1 before production launch.