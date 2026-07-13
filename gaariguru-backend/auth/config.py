import os
from authlib.integrations.starlette_client import OAuth
from starlette.config import Config

# Fallback secret key for local development. In production, this should be set in the environment.
SECRET_KEY = os.getenv("SECRET_KEY", "super-secret-key-for-local-dev")

# Initialize Authlib config utilizing environment variables
config = Config(environ=os.environ)

# Initialize the OAuth registry
oauth = OAuth(config)

# Register the Google OAuth2 client
oauth.register(
    name="google",
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={
        "scope": "openid email profile"
    }
)
