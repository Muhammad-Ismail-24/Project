# Drive Fetch Backend - Project Context & Rules

This document serves as the master context for the Drive Fetch AI Matchmaker backend. When starting a new chat, refer to this file to understand the current architecture, established business rules, and recent fixes.

## 🏛️ System Architecture
- **Agents (`agents/recommender.py`):** Uses Gemini 3.5 Flash Lite to process user natural language queries and map them to strict JSON recommendation targets.
- **Routing (`api/recommend_routes.py`):** Orchestrates the pipeline. Intercepts LLM output, applies Python math fallbacks (e.g., 30% budget floor), and passes targets to scrapers.
- **Scrapers (`scrapers/runner.py`):** Translates targets into platform-specific URLs (PakWheels, OLX, WiseWheels) and fetches live inventory.
- **Normalizer (`scrapers/recommend_normalizer.py`):** Vetoes listings that breach strict budget windows, transmission requirements, or body style rules.

## 🛑 Established Business Rules & LLM Constraints
The `SEMANTIC_MAPPER_PROMPT` and `_EXTENDED_MAPPER_PROMPT` have been heavily tuned for the Pakistani market. The following strict rules are currently active:

### 1. Quality & Quantity
- **Top 3 Pure Quality Contract:** The initial pass MUST return EXACTLY 1 to 3 targets based on genuine market availability. We have abolished forced "brand diversity" fillers.
- **Extension Pipeline:** The "Show More Options" feature generates 0 to 3 Tier-2 alternatives. It strictly respects the original budget ceiling (no hallucinations of expensive cars for low-budget queries).

### 2. Budget Handling
- **Dynamic 30% Budget Floor:** If a user provides a `max_budget`, the system mathematically enforces a `min_budget` of 70% of the max (e.g., max 50 Lacs -> min 35 Lacs). This is backed by a bulletproof Python fallback in `api/recommend_routes.py`.
- **Elite Budget Apex Hierarchy (3 Crore+):** If the budget is >= 30,000,000 PKR, mid-tier SUVs (Fortuner, Sorento) are HARD-DEMOTED. Apex luxury vehicles (Land Cruiser 300, Range Rover, Porsche Cayenne) take priority.
- **"Aura" / Status Keywords:** Keywords like "aura", "boss", or "status" trigger a focus on commanding luxury vehicles and exclude utility commercial vehicles (like Hilux).

### 3. Body Style & Segment Strictness
- **Strict Body-Style Isolation:** If a user asks for a crossover, the system will never suggest a sedan (e.g., Elantra is forbidden for crossover queries). 
- **Pickup Bed Rule:** "Pickup truck" queries are strictly locked to open rear cargo bed vehicles (Hilux Revo, D-Max). Closed SUVs (Prado, Fortuner) are hard-excluded.
- **Cargo Van Categorization:** "7-seater cargo van" queries prioritize utility (Changan Karvaan, Suzuki Bolan) and hard-exclude passenger commuters (Toyota Hiace) and pickups (FAW Carrier).

### 4. Drivetrain, Trims, & Origin
- **JDM Disambiguation:** For JDM/Japanese import requests on dual-origin cars (like Suzuki Alto), the LLM must output JDM-exclusive trims (`trim="G"`, `trim="L"`, `trim="X"`) to prevent local Pak-Suzuki variants from leaking in.
- **Transmission Lock:** "Automatic" queries hard-exclude all manual trims.
- **Push-Start Constraints:** Prioritizes native push-start JDM cars for budget queries under 30 Lacs.
- **Chinese Entrants:** Hard-excluded from generic queries. Only recommended if the user explicitly requests Chinese brands.

## 🛠️ Data Contracts
The LLM must output a JSON array of objects with exactly these 9 keys:
`make`, `model`, `trim`, `city`, `min_budget`, `max_budget`, `min_year`, `required_features`, `rationale`.
