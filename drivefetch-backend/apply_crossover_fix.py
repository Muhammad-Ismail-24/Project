import re

with open('agents/recommender.py', 'r', encoding='utf-8') as f:
    content = f.read()

models_to_crossover = [
    "kia:sportage",
    "kia:sorento",
    "hyundai:tucson",
    "toyota:rush",
    "mg:hs",
    "mg:rx5",
    "changan:oshan x7",
    "changan:uni-t",
    "changan:deepal s07",
    "haval:jolion",
    "haval:h6",
    "haval:h6 hev",
    "chery:tiggo 8 pro",
    "proton:x70",
    "byd:atto 3",
    "nissan:x-trail",
    "mitsubishi:outlander",
    "subaru:forester",
    "mazda:cx-5",
    "bmw:x3",
    "bmw:x5",
    "bmw:ix",
    "mercedes-benz:glc",
    "mercedes-benz:gle",
    "audi:q5",
    "audi:e-tron"
]

def update_model_style(model):
    global content
    pattern = r'("' + re.escape(model) + r'":\s*\{.*?"styles":\s*)\{["\']SUV["\']\}'
    content = re.sub(pattern, r'\1{"Crossover"}', content)

for model in models_to_crossover:
    update_model_style(model)

with open('agents/recommender.py', 'w', encoding='utf-8') as f:
    f.write(content)
