with open("agents/recommender.py", "r", encoding="utf-8") as f:
    for i, line in enumerate(f):
        s = line.strip()
        for kw in ["_EXTENDED_MAPPER_PROMPT", "_FALLBACK_PROMPT", "Q-DOMINANCE", "Q-TIER"]:
            if kw in s:
                safe = s.replace("\u2192", "->").replace("\u2014", "--")[:120]
                print(f"{i+1}: {safe}")
                break
