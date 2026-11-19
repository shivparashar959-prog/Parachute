"""GitHub OAuth client registration and configuration checks."""

from authlib.integrations.starlette_client import OAuth

from app.config import ConfigurationError, get_settings

oauth = OAuth()


def get_github_oauth_client():
    settings = get_settings()
    if not settings.github_oauth_configured:
        raise ConfigurationError("GitHub sign-in is not configured.")

    client = oauth.create_client("github")
    if client is None:
        oauth.register(
            name="github",
            client_id=settings.github_oauth_client_id,
            client_secret=settings.github_oauth_client_secret,
            authorize_url="https://github.com/login/oauth/authorize",
            access_token_url="https://github.com/login/oauth/access_token",
            api_base_url="https://api.github.com/",
            token_endpoint_auth_method="client_secret_post",
            client_kwargs={
                "scope": "read:user user:email",
                "code_challenge_method": "S256",
            },
        )
    return oauth.create_client("github")
