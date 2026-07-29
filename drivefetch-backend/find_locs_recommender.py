with open("agents/recommender.py", "r", encoding="utf-8") as f:
    for i, line in enumerate(f):
        if "STEP 2 " in line or "def _parse_llm_json" in line or "def _sanitize_recommendations" in line or "Q-DOMINANCE" in line:
            print(f"{i+1}: {line.strip()[:50]}")
