with open('main.py', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace('exc_info=True\n    # Return a sanitized', 'exc_info=True\n    )\n    # Return a sanitized')

with open('main.py', 'w', encoding='utf-8') as f:
    f.write(content)
