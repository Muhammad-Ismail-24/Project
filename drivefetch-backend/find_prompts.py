with open("agents/recommender.py", "r", encoding="utf-8") as f:
    for i, line in enumerate(f):
        if "_FALLBACK_PROMPT =" in line or "_EXTENDED_MAPPER_PROMPT =" in line or "Q0. ORIGIN & BODY-STYLE" in line:
            print(f"{i+1}: {line.strip()[:50]}")
