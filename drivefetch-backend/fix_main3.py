with open('main.py', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace('        }', '        }\n    )')
content = content.replace('exc_info=True\n    )\n    )', 'exc_info=True\n    )') # just in case

with open('main.py', 'w', encoding='utf-8') as f:
    f.write(content)
