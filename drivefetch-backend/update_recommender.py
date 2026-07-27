import re

with open('agents/recommender.py', 'r', encoding='utf-8') as f:
    content = f.read()

q4_addition = """
  Q5. FACTORY FEATURES vs AFTERMARKET:
      If the user requests features like "panoramic sunroof", "sunroof", "push start", "cruise control":
      - Understand what trims/generations actually have these.
      - If a user wants a sunroof on a Civic, output trim="Oriel".
      - If they want a panoramic sunroof on a Vezel, output min_year=2021 and trim="Play".
      - Reject or clarify "Aftermarket Only" features (like remote engine start in Pakistan) in the rationale.
      - Output these standardized features in the required_features array.

  Q6. MARKET LIQUIDITY — apply this filter to EVERY candidate before accepting it:"""

content = content.replace('  Q5. MARKET LIQUIDITY — apply this filter to EVERY candidate before accepting it:', q4_addition.lstrip('\n'))
content = content.replace('Q5 has filtered', 'Q6 has filtered')
content = content.replace('fails Q5 must', 'fails Q6 must')
content = content.replace('Q6. DIVERSITY', 'Q7. DIVERSITY')

output_contract = """  "min_year"   → Integer. Set via Q3 reasoning above. 0 means no floor.
  "required_features" → Array of Strings. Standardized factory features requested (e.g. ["sunroof", "push_start"]). Empty array if none.
  "rationale"  → String. 1–2 punchy sentences: why this specific car for this user."""

content = content.replace('  "min_year"   → Integer. Set via Q3 reasoning above. 0 means no floor.\n  "rationale"  → String. 1–2 punchy sentences: why this specific car for this user.', output_contract)

fb_prompt = '5. Use the same 8-key schema: make, model, trim, city, max_budget, min_year, required_features, rationale.'
content = content.replace('5. Use the same 7-key schema: make, model, trim, city, max_budget, min_year, rationale.', fb_prompt)

# Add required_features to all JSONs
def replacer(m):
    obj = m.group(0)
    return obj.replace('"rationale":', '"required_features":[],"rationale":')

content = re.sub(r'\{"make".*?\}', replacer, content)

# Special case for the panoramic sunroof example
content = content.replace('"required_features":[],"rationale":"5th gen NQ5 AWD comes with panoramic sunroof', '"required_features":["panoramic_sunroof"],"rationale":"5th gen NQ5 AWD comes with panoramic sunroof')
content = content.replace('"required_features":[],"rationale":"AWD Tucson pairs European ride quality with a panoramic roof', '"required_features":["panoramic_sunroof"],"rationale":"AWD Tucson pairs European ride quality with a panoramic roof')
content = content.replace('"required_features":[],"rationale":"H6 2.0T is the only AWD Chinese crossover at this price with a massive panoramic roof', '"required_features":["panoramic_sunroof"],"rationale":"H6 2.0T is the only AWD Chinese crossover at this price with a massive panoramic roof')
content = content.replace('7 keys:', '8 keys:')

sanitize_new = """        try:
            r["min_year"] = int(raw_year) if raw_year else 0
        except (TypeError, ValueError):
            r["min_year"] = 0

        if not isinstance(r.get("required_features"), list):
            r["required_features"] = []

        if not r.get("make") or not r.get("model"):
"""

content = content.replace('        try:\n            r["min_year"] = int(raw_year) if raw_year else 0\n        except (TypeError, ValueError):\n            r["min_year"] = 0\n\n        if not r.get("make") or not r.get("model"):\n', sanitize_new)

with open('agents/recommender.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("Updated recommender.py")
