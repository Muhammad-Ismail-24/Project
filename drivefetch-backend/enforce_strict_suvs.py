import re
import json

with open('agents/recommender.py', 'r', encoding='utf-8') as f:
    text = f.read()

strict_suv_list = [
    'toyota:fortuner', 'toyota:prado', 'toyota:land cruiser', 'mitsubishi:pajero',
    'mitsubishi:pajero sport', 'nissan:patrol', 'gwm:tank 500', 'land rover:defender',
    'land rover:discovery', 'land rover:range rover', 'land rover:vogue',
    'land rover:range rover sport', 'lexus:lx570', 'lexus:lx', 'lexus:lx600',
    'bmw:x7', 'mercedes-benz:gls'
]

# Specifically update lexus:rx and honda:cr-v
text = re.sub(r'("lexus:rx":\s*\{.*?"styles":\s*)\{[^}]*\}', r'\1{"Crossover"}', text)
text = re.sub(r'("honda:cr-v":\s*\{.*?"styles":\s*)\{[^}]*\}', r'\1{"Crossover"}', text)

# Now iterate over all entries with "SUV" in styles and if they are not in the strict list, replace "SUV" with "Crossover"
# Wait, some might have multiple styles like {"Mini SUV", "SUV"}. If we remove SUV, maybe we just replace the whole styles with Crossover?
# The prompt says: "Ensure ONLY these vehicles retain "styles": {"SUV"} in CAR_REGISTRY"
# I will find all lines starting with "make:model": and check styles.

def replacer(match):
    make_model = match.group(1)
    styles_str = match.group(2)
    
    if make_model not in strict_suv_list:
        if '"SUV"' in styles_str or "'SUV'" in styles_str:
            # Replace "SUV" with "Crossover"
            new_styles = styles_str.replace('"SUV"', '"Crossover"').replace("'SUV'", "'Crossover'")
            
            # Since a set can't have duplicate "Crossover", if there are two "Crossover" we can let it be, but let's clean it up
            # just replacing is fine, Python set parsing in the backend logic will handle it (Wait, it's python source code. {"Crossover", "Crossover"} is valid syntax but redundant).
            # Let's clean it.
            items = re.findall(r'["\']([^"\']+)["\']', new_styles)
            items = list(set(items))
            cleaned = "{" + ", ".join(f'"{x}"' for x in items) + "}"
            return f'"{make_model}": {match.group(3)}"styles": {cleaned}'
    
    return match.group(0)

# "make:model": ... "styles": { ... }
text = re.sub(r'"([^"]+)":(\s*\{.*?(?:(?<=\,)|(?<=\{))\s*)"styles":\s*(\{[^}]*\})', replacer, text)


with open('agents/recommender.py', 'w', encoding='utf-8') as f:
    f.write(text)
