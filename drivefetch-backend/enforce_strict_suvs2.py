import re

with open('agents/recommender.py', 'r', encoding='utf-8') as f:
    text = f.read()

strict_suv_list = [
    'toyota:fortuner', 'toyota:prado', 'toyota:land cruiser', 'mitsubishi:pajero',
    'mitsubishi:pajero sport', 'nissan:patrol', 'gwm:tank 500', 'land rover:defender',
    'land rover:discovery', 'land rover:range rover', 'land rover:vogue',
    'land rover:range rover sport', 'lexus:lx570', 'lexus:lx', 'lexus:lx600',
    'bmw:x7', 'mercedes-benz:gls'
]

# We need to find every model in CAR_REGISTRY and if it has "SUV", and is NOT in strict_suv_list, change "SUV" to "Crossover"
# CAR_REGISTRY entries look like: "make:model": {"lo": ..., "hi": ..., "styles": {"SUV", ...}, ...}

def replacer(match):
    make_model = match.group(1)
    before_styles = match.group(2)
    styles_str = match.group(3)
    
    if make_model not in strict_suv_list:
        if '"SUV"' in styles_str or "'SUV'" in styles_str:
            new_styles = styles_str.replace('"SUV"', '"Crossover"').replace("'SUV'", "'Crossover'")
            # clean up duplicate "Crossover"
            items = set(re.findall(r'["\']([^"\']+)["\']', new_styles))
            cleaned = "{" + ", ".join(f'"{x}"' for x in items) + "}"
            return f'"{make_model}":{before_styles}"styles": {cleaned}'
    return match.group(0)

# Use re.DOTALL so .*? can match across lines, since some entries have "styles" on a different line, but actually they are mostly on the same line.
text = re.sub(r'"([^"]+)":(\s*\{.*?(?:(?<=\,)|(?<=\{))\s*)"styles":\s*(\{.*?\})', replacer, text, flags=re.DOTALL)

with open('agents/recommender.py', 'w', encoding='utf-8') as f:
    f.write(text)
