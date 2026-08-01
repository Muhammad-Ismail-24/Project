import re

with open('agents/recommender.py', 'r', encoding='utf-8') as f:
    content = f.read()

models_to_change = [
    "kia:sportage", "kia:sorento", "hyundai:tucson", "toyota:rush",
    "mg:hs", "mg:rx5", "changan:oshan x7", "changan:uni-t",
    "changan:deepal s07", "haval:jolion", "haval:h6", "haval:h6 hev",
    "chery:tiggo 8 pro", "proton:x70", "byd:atto 3", "nissan:x-trail",
    "mitsubishi:outlander", "subaru:forester", "mazda:cx-5", "bmw:x3",
    "bmw:x5", "bmw:ix", "mercedes-benz:glc", "mercedes-benz:gle",
    "audi:q5", "audi:e-tron"
]

def replacer(match):
    make_model = match.group(1)
    rest = match.group(2)
    if make_model in models_to_change:
        # Replace "SUV" with "Crossover" in this line
        rest = re.sub(r'"styles":\s*\{"SUV"\}', '{"Crossover"}', rest)
        # Handle cases where it might not just replace properly using simple replace
        rest = rest.replace('"styles": {"SUV"}', '"styles": {"Crossover"}')
        rest = rest.replace("'styles': {'SUV'}", '"styles": {"Crossover"}')
    return f'"{make_model}":{rest}'

# We will just split the content by lines and replace in lines that start with the target models
lines = content.split('\n')
for i, line in enumerate(lines):
    for model in models_to_change:
        if line.strip().startswith(f'"{model}":'):
            lines[i] = re.sub(r'"styles":\s*\{"SUV"\}', '"styles": {"Crossover"}', line)

content = '\n'.join(lines)

with open('agents/recommender.py', 'w', encoding='utf-8') as f:
    f.write(content)
