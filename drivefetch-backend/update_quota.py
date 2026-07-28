import re

rec_file = "agents/recommender.py"

with open(rec_file, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Update EXACTLY 5 to UP TO 5 in the main instructions
content = content.replace(
    "Translate their intent into EXACTLY 5 car search targets",
    "Translate their intent into 1 to 5 car search targets (UP TO 5)"
)

# 2. Add Q-QUOTA and Powertrain Hard-Exclusion
quota_rule = """
  Q-QUOTA (Quality > Quantity Rule):
      - Output ONLY cars that strictly meet ALL of the user's primary category constraints (powertrain, body style, origin, budget).
      - If 5 distinct, high-quality models match the criteria → return 5 objects.
      - If only 2 or 3 models genuinely exist in Pakistan matching the request (e.g. Japanese hybrid hatchbacks under 35 lacs) → return ONLY those 2 or 3 objects.
      - STRICTLY FORBIDDEN: Never add non-matching or category-adjacent cars (e.g., adding petrol Vitz/Passo to a Hybrid query) simply to pad the list to 5 items.
      - When "hybrid" is requested, HARD-EXCLUDE all non-hybrid/petrol-only variants.
"""

# Insert right after Q0
content = re.sub(
    r'(Q0-B\. BODY-STYLE \(Segment Check\):.*?)\n  Q1\. DRIVETRAIN & CHASSIS',
    r'\1\n' + quota_rule + '\n  Q1. DRIVETRAIN & CHASSIS',
    content,
    flags=re.DOTALL
)

# 3. Update Output Contract from EXACTLY 5 to UP TO 5
content = content.replace(
    "The array must contain EXACTLY 5 objects",
    "The array must contain UP TO 5 objects (1 to 5)"
)

# 4. Update Fallback Prompt & _FALLBACK_PROMPT
content = content.replace(
    "Return EXACTLY the requested number",
    "Return UP TO the requested number"
)
content = content.replace(
    "Generate EXACTLY {count} replacement",
    "Generate UP TO {count} replacement"
)
content = content.replace(
    "Return EXACTLY {count} replacement",
    "Return UP TO {count} replacement"
)

# Also ensure Q6 or Q7 DIVERSITY mentions UP TO 5 rather than filtering "your 5 candidates".
# Let's see how diversity is phrased.
content = content.replace(
    "filtered your 5 candidates",
    "filtered your candidates"
)
content = content.replace(
    "If no (all 5 are the same brand)",
    "If no (all are the same brand and you have 5 picks)"
)

with open(rec_file, "w", encoding="utf-8") as f:
    f.write(content)

print("Updated recommender.py for 1-5 dynamic quota.")
