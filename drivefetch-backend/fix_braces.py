import re

with open('agents/recommender.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix the missing brace
content = re.sub(r'("tags":\s*\{[^}]*?)(,\s*"chinese":\s*(?:True|False)\})', r'\1}\2', content)

with open('agents/recommender.py', 'w', encoding='utf-8') as f:
    f.write(content)
