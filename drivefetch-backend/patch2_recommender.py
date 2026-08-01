with open('agents/recommender.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Chunk 1: family principles
content = content.replace(
    '  - Prioritise: boot space, rear legroom, reliability, service network availability\n  - Rank higher: cars with 5+ years of parts availability in Pakistan\n  - Rank higher: cars known for resale value retention (Toyota > Honda > others generally)\n  - For budgets under PKR 50 lacs: Corolla, Civic, City are the benchmark — pick alternatives only if they offer clear advantage (more space, lower maintenance)\n  - For 7-seat needs: prefer dedicated 7-seat (BR-V, Rush, Sorento) over squeezing 3 adults into a rear bench\n  - Avoid: sports-tuned cars (RX-8, BRZ) — stiff ride and limited boot space for families\n  - Avoid: kei cars (N-Box, Mira) for families with children over 8 — too small',
    '  - PAKISTANI MARKET REALITY: Families heavily prefer SEDANS over hatchbacks due to boot space ("diggi") and status.\n  - If budget >= PKR 1,500_000 (15 Lacs), ALWAYS prioritize Sedans (Corolla, City, Civic, Liana, Baleno) over small hatchbacks (Passo, Wagon R, Vitz) unless the user explicitly requested a hatchback.\n  - Prioritise: boot space, rear legroom, air conditioning effectiveness, reliability.'
)

# Chunk 2: offroad principles
content = content.replace(
    'USE-CASE PRINCIPLES — Off-road / Rugged:\n  - HARD RULE: body-on-frame or proven AWD/4WD ONLY — Fortuner, Prado, Land Cruiser, Patrol, Hilux, Pajero\n  - Unibody crossovers (Vezel, Stonic, C-HR) are NOT suitable — do not recommend them for offroad use\n  - Rank higher: cars with locking differentials and proper 4L mode\n  - Ground clearance matters: minimum 200mm for serious offroad\n  - Budget reality: capable 4x4s start at PKR 80 lacs — if budget is under 60 lacs, be honest that options are limited and suggest Pajero or Jimny as entry-level capable options\n  - Avoid: road-tuned AWD (Subaru XV, Tucson) for genuine offroad — they are road-biased',
    'USE-CASE PRINCIPLES — SUV / Off-road / Northern Areas:\n  - HARD SEPARATION: True SUVs (Land Cruiser, Prado, Pajero, Patrol, Fortuner) have ladder-frame chassis or true 4x4 systems.\n  - Crossovers (Sportage, Tucson, Vezel, Rush) are unibody city cars — NEVER recommend crossovers when the user asks for a true SUV or rugged 4x4.\n  - Old Land Cruisers (LC80/LC100), Prados, and Pajeros from 1990-2005 are extremely popular in Pakistan for rough terrain and Northern trips. Recommend them if budget allows!'
)

# Chunk 3: get_eligible_cars signature
content = content.replace(
    '    excluded_models: list[str] | None = None,\n) -> str:',
    '    excluded_models: list[str] | None = None,\n    drive_req: str | None = None,\n) -> str:'
)

# Chunk 4: Drive-type filtering in get_eligible_cars
content = content.replace(
    '        # 3. Transmission gate — only filter if user explicitly wants Automatic\n        if transmission_req == "Automatic" and info["transmission"] == "manual":\n            continue\n\n        # 4. Budget overlap',
    '        # 3. Transmission gate — only filter if user explicitly wants Automatic\n        if transmission_req == "Automatic" and info["transmission"] == "manual":\n            continue\n\n        # Drive type filtering\n        if drive_req and info.get("drive") != drive_req:\n            # Allow 4x4 when AWD is requested, but do NOT allow FWD for 4x4 queries\n            if drive_req == "4x4" and info.get("drive") != "4x4":\n                continue\n            elif drive_req == "AWD" and info.get("drive") not in {"AWD", "4x4"}:\n                continue\n            elif drive_req == "FWD" and info.get("drive") != "FWD":\n                continue\n\n        # 4. Budget overlap'
)

# Chunk 5: UserIntent
content = content.replace(
    '    transmission:      Optional[Literal["Automatic", "Manual"]]                                     = None\n    use_case:          Optional[str]',
    '    transmission:      Optional[Literal["Automatic", "Manual"]]                                     = None\n    drive:             Optional[Literal["4x4", "AWD", "FWD", "RWD"]]                                = None\n    use_case:          Optional[str]'
)

# Chunk 6: resolve_constraints
content = content.replace(
    '        "transmission":      intent.transmission,\n        "use_case":          intent.use_case,',
    '        "transmission":      intent.transmission,\n        "drive":             intent.drive,\n        "use_case":          intent.use_case,'
)

# Chunk 7: select_car_targets constraints
content = content.replace(
    '    transmission    = constraints.get("transmission")\n    use_case        = constraints.get("use_case")',
    '    transmission    = constraints.get("transmission")\n    drive           = constraints.get("drive")\n    use_case        = constraints.get("use_case")'
)

# Chunk 7 part 2: select_car_targets passing drive_req
content = content.replace(
    '        transmission_req=transmission,\n        excluded_models=None,\n    )',
    '        transmission_req=transmission,\n        excluded_models=None,\n        drive_req=drive,\n    )'
)

# Chunk 8: QUANTITY rule
content = content.replace(
    '"5. QUANTITY: Return 1 if only 1 car truly fits well. Never pad to 3.\\n"',
    '"8. QUANTITY: Always return 3 distinct targets if 3 or more eligible options exist in the list. Only return fewer than 3 if the eligible candidate list physically contains fewer than 3 cars.\\n"'
)

with open('agents/recommender.py', 'w', encoding='utf-8') as f:
    f.write(content)
