from authlib.integrations.starlette_client import OAuth
from starlette.config import Config
from agents.config import settings

# Fallback secret key for local development. In production, this should be set in the environment.
SECRET_KEY = settings.secret_key.get_secret_value()

# Define the frontend URL for redirects, using the dynamic environment variable
FRONTEND_URL = settings.FRONTEND_URL

# Initialize the OAuth registry
oauth = OAuth()

# Register the Google OAuth2 client
oauth.register(
    name="google",
    client_id=settings.GOOGLE_CLIENT_ID,
    client_secret=settings.GOOGLE_CLIENT_SECRET.get_secret_value(),
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={
        "scope": "openid email profile"
    }
)
