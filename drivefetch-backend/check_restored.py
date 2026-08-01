import re

with open('agents/recommender.py', 'r', encoding='utf-8') as f:
    text = f.read()

models = ['lexus:rx', 'honda:cr-v', 'toyota:fortuner', 'hyundai:santa fe', 'mitsubishi:mini pajero']
for m in models:
    match = re.search(f'"{m}":\s*.*?styles":\s*(\{{.*?\}})', text)
    if match:
        print(f'{m}: {match.group(1)}')
    else:
        print(f'{m}: NOT FOUND')
