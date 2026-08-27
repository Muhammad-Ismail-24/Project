with open('drivefetch-backend/agents/config.py', 'r', encoding='utf-8') as f:
    content = f.read()

insert = "    GOOGLE_CLIENT_ID: str\n    GOOGLE_CLIENT_SECRET: SecretStr\n"
target = "    SESSION_SECRET_KEY: SecretStr = SecretStr(\"change-this-in-production\")\n"
content = content.replace(target, target + insert)

with open('drivefetch-backend/agents/config.py', 'w', encoding='utf-8') as f:
    f.write(content)
