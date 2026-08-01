import re

with open('agents/recommender.py', 'r', encoding='utf-8') as f:
    text = f.read()

suv_models = []
matches = re.finditer(r'"([^"]+)":\s*\{.*?"styles":\s*\{[^}]*?"SUV"[^}]*?\}', text)
for m in matches:
    suv_models.append(m.group(1))

print('Current SUVs:')
for sm in suv_models:
    print(sm)
