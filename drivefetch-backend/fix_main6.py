import os

with open('main.py', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace('settings.frontend_url.rstrip', 'settings.FRONTEND_URL.rstrip')

with open('main.py', 'w', encoding='utf-8') as f:
    f.write(content)
