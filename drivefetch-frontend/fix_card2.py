with open('src/components/CarResultCard.tsx', 'r', encoding='utf-8') as f:
    content = f.read()

import re
content = re.sub(r'// const liquidityBadge = \{[\s\S]*?\};', '', content)

with open('src/components/CarResultCard.tsx', 'w', encoding='utf-8') as f:
    f.write(content)
