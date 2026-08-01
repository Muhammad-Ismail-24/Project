import re

with open('agents/recommender.py', 'r', encoding='utf-8') as f:
    content = f.read()

# ---------------------------------------------------------
# TASK 1: Add drive field and Legacy budget cars
# ---------------------------------------------------------
def replacer(match):
    make_model = match.group(1).lower()
    ws = match.group(2)
    lo = match.group(3)
    hi = match.group(4)
    styles = match.group(5)
    rest = match.group(6)
    
    drive = '"FWD"'
    if 'offroad' in rest or 'awd' in rest or '4x4' in rest:
        if any(x in make_model for x in ['fortuner', 'hilux', 'prado', 'land cruiser', 'jimny', 'pajero', 'patrol', 'defender', 'wrangler']):
            drive = '"4x4"'
        else:
            drive = '"AWD"'
    elif any(x in make_model for x in ['bolan', 'hiace', 'rx-8', 'mark x', 'crown']):
        drive = '"RWD"'
        
    return f'"{make_model}":{ws}{{"lo": {lo}, "hi": {hi}, "styles": {styles}, "drive": {drive}, {rest}'

pattern = re.compile(r'"([^"]+)":(\s*)\{\s*"lo":\s*([\d_]+)\s*,\s*"hi":\s*([\d_]+)\s*,\s*"styles":\s*(\{.*?\})\s*,\s*(.*?)\}', re.DOTALL)
content = pattern.sub(replacer, content)

legacy_cars = """
    "suzuki:fx":               {"lo": 150_000,    "hi": 600_000,    "styles": {"Hatchback"}, "drive": "FWD", "transmission": "manual", "tags": {"economy","city"}, "chinese": False},
    "suzuki:khyber":           {"lo": 300_000,    "hi": 1_200_000,  "styles": {"Hatchback"}, "drive": "FWD", "transmission": "manual", "tags": {"economy","city"}, "chinese": False},
    "suzuki:margalla":         {"lo": 400_000,    "hi": 1_500_000,  "styles": {"Sedan"},     "drive": "FWD", "transmission": "manual", "tags": {"economy","family"}, "chinese": False},
    "daihatsu:charade":        {"lo": 250_000,    "hi": 1_000_000,  "styles": {"Hatchback"}, "drive": "FWD", "transmission": "both",   "tags": {"economy","city"}, "chinese": False},
    "nissan:sunny":            {"lo": 500_000,    "hi": 1_800_000,  "styles": {"Sedan"},     "drive": "FWD", "transmission": "both",   "tags": {"economy","family"}, "chinese": False},
"""

content = content.replace('"suzuki:mehran":', legacy_cars.strip() + '\n    "suzuki:mehran":')

# Lower SUV Price Floors
content = re.sub(r'("toyota:land cruiser":\s*\{"lo":\s*)35_000_000', r'\g<1>2_500_000', content)
content = re.sub(r'("toyota:prado":\s*\{"lo":\s*)18_000_000', r'\g<1>2_500_000', content)
content = re.sub(r'("mitsubishi:pajero":\s*\{"lo":\s*)5_000_000', r'\g<1>1_800_000', content)

with open('agents/recommender.py', 'w', encoding='utf-8') as f:
    f.write(content)
