with open('drivefetch-frontend/public/sitemap.xml', 'r', encoding='utf-8') as f:
    content = f.read()

import re

conflict_pattern = re.compile(r'<<<<<<< HEAD\n\s*<lastmod>2026-08-26</lastmod>\n=======\n\s*<lastmod>2026-08-21</lastmod>\n>>>>>>> [a-f0-9]+', re.DOTALL)

def replacer(match):
    return "    <lastmod>2026-08-26</lastmod>"

content = conflict_pattern.sub(replacer, content)

with open('drivefetch-frontend/public/sitemap.xml', 'w', encoding='utf-8') as f:
    f.write(content)
