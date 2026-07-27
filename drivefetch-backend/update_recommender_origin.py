import re

file_path = "agents/recommender.py"

with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Add Q-ORIGIN & Q-BODYSTYLE
origin_bodystyle = """
  Q0. ORIGIN & BODY-STYLE — answer in two sub-steps:

    Q0-A. ORIGIN (Brand Nationality Check):
      - Did the user specify brand nationality or origin? (e.g., "Chinese", "Japanese", "German", "European", "Korean", "Pakistani / Local").
      - If YES: HARD-EXCLUDE every brand outside that origin.
      - Example: "Chinese electric crossovers" → HARD-EXCLUDE Audi, BMW, Mercedes, Porsche, Hyundai, Kia, Toyota, Honda. Only allow Chinese brands (BYD, Changan, MG, Haval, Chery, GWM, Seres, etc.).

    Q0-B. BODY-STYLE (Segment Check):
      - Did the user specify body style? (e.g., "crossover", "SUV", "sedan", "hatchback", "van", "pickup").
      - If YES: HARD-EXCLUDE mismatched body types.
      - Example: If user asked for "crossover", HARD-EXCLUDE sedans (e.g., BYD Seal, Changan Deepal L07) even if they are electric and Chinese.

  Q1. DRIVETRAIN & CHASSIS — answer in two sub-steps:"""

content = content.replace("  Q1. DRIVETRAIN & CHASSIS — answer in two sub-steps:", origin_bodystyle.lstrip('\n'))

# 2. Add Trim Suffix Duplication Fix
trim_suffix_fix = """      - Trim Suffix Duplication Fix: If model already ends with "EV" (e.g., "ZS EV"), set trim = "" (empty string) to prevent downstream labels like "MG ZS EV EV".
      - trim = ""       → ALL other cases."""

content = content.replace('      - trim = ""       → ALL other cases.', trim_suffix_fix)

# 3. Update fallback prompt
fallback_original = """    fallback_prompt = (
        f"Original user request: \\"{user_prompt}\\"\\n"
        f"City: {city_str} | Budget: {budget_str}\\n\\n"
        f"These 5 targets returned ZERO active listings and need replacements:\\n"
        f"  {failed_str}\\n\\n"
        f"EXCLUDED models (already tried — do not repeat these):\\n"
        f"  {excluded_str}\\n\\n"
        f"Generate EXACTLY {count} replacement target(s) matching the original criteria.\\n"
        f"Ensure they are different from the excluded ones."
    )"""

# Fallback might look a bit different. Let's do regex replacement for the fallback prompt variable.
new_fallback = """    fallback_prompt = (
        f"Original user request: \\"{user_prompt}\\"\\n"
        f"City: {city_str} | Budget: {budget_str}\\n\\n"
        f"CRITICAL: Maintain ALL constraints from original request "
        f"(e.g., Brand Origin/Nationality, Body Type/Segment, Drivetrain).\\n\\n"
        f"These targets returned ZERO active listings and need replacements:\\n"
        f"  {failed_str}\\n\\n"
        f"EXCLUDED models (already tried — do not repeat these):\\n"
        f"  {excluded_str}\\n\\n"
        f"Generate EXACTLY {count} replacement target(s) matching the original criteria."
    )"""

content = re.sub(r'    fallback_prompt = \(\n        f"Original user request:.*?    \)', new_fallback, content, flags=re.DOTALL)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)

print("Updated recommender.py successfully.")
