with open('drivefetch-backend/agents/config.py', 'r', encoding='utf-8') as f:
    content = f.read()

import re

conflict_pattern = re.compile(r'<<<<<<< HEAD\n(.*?)\n=======\n(.*?)\n>>>>>>> [a-f0-9]+', re.DOTALL)

def replacer(match):
    # We construct the merged block manually to ensure everything is perfect.
    return (
        "    FRONTEND_URL: str = \"https://drivefetch.vercel.app\"\n"
        "    secret_key: SecretStr = SecretStr(\"super-secret-key-for-local-dev\")\n"
        "    SESSION_SECRET_KEY: SecretStr = SecretStr(\"change-this-in-production\")\n"
        "    GOOGLE_CLIENT_ID: str\n"
        "    GOOGLE_CLIENT_SECRET: SecretStr\n"
        "    gemini_model_pool: SecretStr = SecretStr(\"\")"
    )

content = conflict_pattern.sub(replacer, content)

# Also fix the settings.gemini_model_pool.strip()
content = content.replace(
    "_pool_override = settings.gemini_model_pool.strip()",
    "_pool_override = settings.gemini_model_pool.get_secret_value().strip()"
)

with open('drivefetch-backend/agents/config.py', 'w', encoding='utf-8') as f:
    f.write(content)
