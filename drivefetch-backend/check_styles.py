import re
with open('agents/recommender.py', 'r', encoding='utf-8') as f:
    text = f.read()

models = [
    'kia:sportage', 'kia:sorento', 'hyundai:tucson', 'toyota:rush',
    'mg:hs', 'changan:oshan x7', 'haval:h6', 'nissan:x-trail',
    'bmw:x5', 'audi:e-tron', 'toyota:fortuner', 'toyota:prado'
]

for m in models:
    match = re.search(f'"{m}":\s*.*?styles":\s*(\{{.*?\}})', text)
    if match:
        print(f'{m}: {match.group(1)}')
    else:
        print(f'{m}: NOT FOUND')
