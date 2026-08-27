with open('.env.example', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace(
    "GOOGLE_API_KEY=your-google-api-key-here",
    "GOOGLE_API_KEY=your-google-api-key-here\nGOOGLE_CLIENT_ID=your-google-client-id.apps.googleusercontent.com\nGOOGLE_CLIENT_SECRET=your-google-client-secret-here"
)

with open('.env.example', 'w', encoding='utf-8') as f:
    f.write(content)
