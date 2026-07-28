"""
update_top3_architecture.py
Transitions the Semantic Mapper from UP TO 5 to EXACTLY 3 targets,
abolishes forced diversity, establishes market dominance hierarchy,
and trims all few-shot examples to 3 objects each.
"""
import re

# ============================================================================
# STEP 1 & 2: Update agents/recommender.py
# ============================================================================
rec_file = "agents/recommender.py"

with open(rec_file, "r", encoding="utf-8") as f:
    content = f.read()

# ── 1a. System instruction header: UP TO 5 → EXACTLY 3 ────────────────────
content = content.replace(
    "Translate their intent into 1 to 5 car search targets (UP TO 5) for the Pakistani used-car market.",
    "Translate their intent into EXACTLY 3 tier-1 car search targets for the Pakistani used-car market."
)

# ── 1b. Question count: "six questions" → "these questions" (flexible) ──────
content = content.replace(
    "silently answer these six questions",
    "silently answer these questions"
)

# ── 1c. Remove Q-QUOTA entirely (replaced by Q-DOMINANCE below) ───────────
content = re.sub(
    r'  Q-QUOTA \(Quality > Quantity Rule\):.*?When "hybrid" is requested, HARD-EXCLUDE all non-hybrid/petrol-only variants\.\n',
    '',
    content,
    flags=re.DOTALL
)

# ── 1d. Replace Q7 DIVERSITY with Q-DOMINANCE ─────────────────────────────
old_diversity = re.compile(
    r'  Q7\. DIVERSITY.*?alternative from another brand genuinely exists\.\n',
    re.DOTALL
)
new_dominance = """  Q-DOMINANCE (Pure Market Excellence Rule):
      Identify the absolute top 3 models in Pakistan that best satisfy the query.
      - If 1 brand dominates the top tier (e.g., Toyota for rugged 4x4s -> Land Cruiser, Prado, Fortuner/Hilux), output all 3 from that brand.
      - NEVER substitute a lower-tier car (e.g., GWM, Proton, DFSK, Isuzu) just to create brand variety when superior tier-1 market leaders exist for the user's intent and budget.
      - When "hybrid" is requested, HARD-EXCLUDE all non-hybrid/petrol-only variants.

      Category Hierarchies (use as reference, not exhaustive):
        Rugged 4x4 / Off-Road: Toyota Land Cruiser (70/100/200/300) > Toyota Prado > Toyota Fortuner / Toyota Hilux Revo
        Luxury: Toyota Land Cruiser > Toyota Prado > German Luxury (BMW 5/7, Mercedes E/S-Class)
        Entry Hatchback: Suzuki Alto > Suzuki Cultus > Suzuki WagonR
        Sedan: Honda Civic > Toyota Corolla > Hyundai Elantra
"""

content = old_diversity.sub(new_dominance, content)

# ── 1e. Update Output Contract: UP TO 5 → EXACTLY 3 ──────────────────────
content = content.replace(
    "The array must contain UP TO 5 objects (1 to 5), each with these EXACT 8 keys:",
    "The array must contain EXACTLY 3 objects, each with these EXACT 8 keys:"
)

# ── 1f. Trim ALL few-shot examples from 5 to 3 objects ────────────────────
# Strategy: find each JSON array block in the few-shot section and keep only the first 3 objects.
# We'll do this by finding array blocks between [ and ] that contain 5 objects.

def trim_array_to_3(match):
    """Takes a JSON array string with 5 objects and returns one with 3."""
    full = match.group(0)
    # Split by the object boundary pattern: "},\n  {"
    # We need to find individual objects
    objects = re.split(r'\},\s*\n\s*\{', full)
    if len(objects) <= 3:
        return full  # already 3 or fewer
    # Reconstruct first 3
    # First object starts with [{ and last ends with }]
    # Middle objects are just the content
    trimmed = objects[:3]
    # Rejoin
    result = '},\n  {'.join(trimmed)
    # Ensure the last object ends with }] not },
    if not result.rstrip().endswith(']'):
        result = result.rstrip()
        if result.endswith('}'):
            result += '\n]'
        elif result.endswith('},'):
            result = result[:-1] + '\n]'
    return result

# More reliable approach: use line-based trimming
lines = content.split('\n')
new_lines = []
in_array = False
obj_count = 0
skip_until_close = False

for i, line in enumerate(lines):
    stripped = line.strip()
    
    if skip_until_close:
        if stripped == ']':
            skip_until_close = False
            new_lines.append(line)
            in_array = False
            obj_count = 0
        continue
    
    if stripped == '[':
        in_array = True
        obj_count = 0
        new_lines.append(line)
        continue
    
    if in_array:
        if stripped.startswith('{"make"'):
            obj_count += 1
            if obj_count <= 3:
                # For the 3rd object, remove trailing comma if present
                if obj_count == 3:
                    clean_line = line.rstrip()
                    if clean_line.endswith('},'):
                        clean_line = clean_line[:-1]  # remove trailing comma
                    new_lines.append(clean_line)
                else:
                    new_lines.append(line)
            elif obj_count == 4:
                # Start skipping - we already emitted 3
                skip_until_close = True
            continue
        
        if stripped == ']':
            in_array = False
            obj_count = 0
            new_lines.append(line)
            continue
        
        # Empty lines or other content inside array region
        new_lines.append(line)
        continue
    
    new_lines.append(line)

content = '\n'.join(new_lines)

# ── 1g. Update few-shot reasoning comments to reference 3 instead of 5 ────
content = content.replace('Q5: 4 makes', 'Q-DOMINANCE: top 3 selected')
content = content.replace('Q5: All have solid PakWheels', 'Q-DOMINANCE: All have solid PakWheels')
content = content.replace('Q5: All have PakWheels', 'Q-DOMINANCE: All have PakWheels')
content = content.replace('Q6: 4 makes', 'Q-DOMINANCE: top 3 selected')
content = content.replace('Q6: 5 different makes', 'Q-DOMINANCE: top 3 selected')
content = content.replace('Q6: 3 makes', 'Q-DOMINANCE: top 3 selected')
content = content.replace('Q5/Q6: 4 makes', 'Q-DOMINANCE: top 3 selected')
content = content.replace('Q5/Q6: 3 makes', 'Q-DOMINANCE: top 3 selected')
content = content.replace('Q5: Spread across Toyota/Honda', 'Q-DOMINANCE: top 3 by market hierarchy')
content = content.replace('Q5: 5 different makes', 'Q-DOMINANCE: top 3 selected')
content = content.replace("Q5: 4 makes", "Q-DOMINANCE: top 3 selected")

# ── 1h. Update _FALLBACK_PROMPT for 1-3 replacements ─────────────────────
content = content.replace(
    "Return UP TO the requested number of replacement objects.",
    "Return UP TO the requested number of replacement objects (max 3)."
)

with open(rec_file, "w", encoding="utf-8") as f:
    f.write(content)

print("[1/2] Updated agents/recommender.py")

# ============================================================================
# STEP 3: Update api/recommend_routes.py
# ============================================================================
routes_file = "api/recommend_routes.py"

with open(routes_file, "r", encoding="utf-8") as f:
    routes = f.read()

# ── 3a. Add the extension endpoint before the closing of the file ─────────
extension_endpoint = '''

# ---------------------------------------------------------------------------
# ON-DEMAND EXTENSION: "Show More Options" (targets 4-6)
# ---------------------------------------------------------------------------
@router.post("/api/recommend/more")
async def recommend_more_cars(request: Request):
    """
    Fetches additional recommendations (targets 4-6) for a query where the
    initial 3 targets have already been displayed. The frontend sends the
    original prompt plus the list of models already shown.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}

    user_prompt  = (body.get("prompt") or "").strip()
    tried_models = body.get("tried_models") or []
    city         = (body.get("city") or "").strip() or None

    raw_budget = body.get("max_budget")
    try:
        budget = int(raw_budget) if raw_budget is not None else None
        if budget is not None and budget <= 0:
            budget = None
    except (ValueError, TypeError):
        budget = None

    if not user_prompt:
        async def _err():
            yield _sse("error", {"message": "Missing original prompt for extension."})
        return StreamingResponse(_err(), media_type="text/event-stream")

    async def _stream():
        yield _sse("status", {"message": "Finding more options...", "stage": "extending"})

        tried_labels = [m if isinstance(m, str) else f"{m.get('make','')} {m.get('model','')}".strip() for m in tried_models]

        extra_recs = await get_fallback_recommendations(
            user_prompt=user_prompt,
            failed_targets=[],
            tried_models=tried_labels,
            city=city or "",
            budget=budget,
            count=3,
        )

        if not extra_recs:
            yield _sse("status", {"message": "No additional options found.", "stage": "complete"})
            return

        scrape_results = await asyncio.gather(
            *[_scrape_one(rec, city, budget) for rec in extra_recs]
        )

        output: list[dict] = []
        seen_urls: set[str] = set()

        for raw_listings, rec in scrape_results:
            _normalise_one(raw_listings, rec, city, budget, seen_urls, output)

        if not output:
            yield _sse("status", {"message": "No additional listings found.", "stage": "complete"})
            return

        yield _sse("results", {
            "listings": output,
            "targets": [
                {"make": r.get("make"), "model": r.get("model"),
                 "trim": r.get("trim"), "rationale": r.get("rationale")}
                for r in extra_recs
            ],
            "total": len(output),
            "is_extension": True,
        })
        yield _sse("status", {"message": f"Found {len(output)} more listing(s)", "stage": "complete"})

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
'''

# Append the extension endpoint
routes += extension_endpoint

with open(routes_file, "w", encoding="utf-8") as f:
    f.write(routes)

print("[2/2] Updated api/recommend_routes.py")
print("\nAll updates applied successfully.")
