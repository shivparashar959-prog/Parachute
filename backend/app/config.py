"""Environment-backed settings for database, OAuth, and browser security."""

import os
from dataclasses import dataclass
from functools import lru_cache
from urllib.parse import urlsplit


class ConfigurationError(RuntimeError):
    """Raised when a required or invalid application setting is encountered."""


def _read_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ConfigurationError(f"{name} must be a boolean value.")


def _read_int(name: str, default: int, minimum: int, maximum: int) -> int:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer.") from exc
    if parsed < minimum or parsed > maximum:
        raise ConfigurationError(
            f"{name} must be between {minimum} and {maximum}."
        )
    return parsed


def _read_nonnegative_float(name: str) -> float:
    value = os.getenv(name)
    if value is None or not value.strip():
        return 0.0
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be a number.") from exc
    if parsed < 0 or parsed == float("inf") or parsed != parsed:
        raise ConfigurationError(f"{name} must be a finite non-negative number.")
    return parsed


@dataclass(frozen=True)
class Settings:
    app_environment: str
    database_url: str
    github_oauth_client_id: str
    github_oauth_client_secret: str
    github_oauth_redirect_uri: str
    github_oauth_state_secret: str
    github_app_id: str
    github_app_slug: str
    github_app_client_id: str
    github_app_client_secret: str
    github_app_private_key: str
    github_app_webhook_secret: str
    github_app_setup_url: str
    github_app_user_callback_url: str
    frontend_origin: str
    session_cookie_name: str
    session_ttl_seconds: int
    session_cookie_secure: bool
    session_cookie_samesite: str
    analysis_per_user_hour_limit: int
    analysis_per_workspace_day_limit: int
    analysis_max_concurrent_per_workspace: int
    analysis_timeout_seconds: int
    gemini_daily_budget_usd: float
    gemini_user_daily_budget_usd: float
    gemini_input_usd_per_million_tokens: float
    gemini_output_usd_per_million_tokens: float
    gemini_provider_timeout_ms: int
    gemini_max_output_tokens: int
    celery_broker_url: str
    analysis_retry_max_attempts: int
    data_retention_days: int

    @property
    def github_oauth_configured(self) -> bool:
        return bool(
            self.github_oauth_client_id
            and self.github_oauth_client_secret
            and len(self.github_oauth_state_secret) >= 32
        )

    @property
    def github_app_configured(self) -> bool:
        return bool(
            self.github_app_id
            and self.github_app_slug
            and self.github_app_client_id
            and self.github_app_client_secret
            and self.github_app_private_key
            and len(self.github_app_webhook_secret) >= 32
        )

    @property
    def gemini_spend_controls_configured(self) -> bool:
        return all(
            value > 0
            for value in (
                self.gemini_daily_budget_usd,
                self.gemini_user_daily_budget_usd,
                self.gemini_input_usd_per_million_tokens,
                self.gemini_output_usd_per_million_tokens,
            )
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    environment = os.getenv("APP_ENV", "development").strip().lower()
    if environment not in {"development", "test", "production"}:
        raise ConfigurationError("APP_ENV must be development, test, or production.")
    secure_default = environment == "production"
    secure_cookie = _read_bool("SESSION_COOKIE_SECURE", secure_default)
    same_site = os.getenv("SESSION_COOKIE_SAMESITE", "lax").strip().lower()
    ttl_value = os.getenv("SESSION_TTL_SECONDS", "43200").strip()

    try:
        ttl_seconds = int(ttl_value)
    except ValueError as exc:
        raise ConfigurationError("SESSION_TTL_SECONDS must be an integer.") from exc

    if environment == "production" and not secure_cookie:
        raise ConfigurationError(
            "SESSION_COOKIE_SECURE must be enabled in production."
        )
    if same_site not in {"lax", "strict", "none"}:
        raise ConfigurationError(
            "SESSION_COOKIE_SAMESITE must be lax, strict, or none."
        )
    if same_site == "none" and not secure_cookie:
        raise ConfigurationError(
            "SESSION_COOKIE_SECURE must be enabled when SameSite is none."
        )
    analysis_per_user_hour_limit = _read_int(
        "ANALYSIS_PER_USER_HOUR_LIMIT", 10, 1, 1000
    )
    analysis_per_workspace_day_limit = _read_int(
        "ANALYSIS_PER_WORKSPACE_DAY_LIMIT", 100, 1, 10000
    )
    analysis_max_concurrent_per_workspace = _read_int(
        "ANALYSIS_MAX_CONCURRENT_PER_WORKSPACE", 2, 1, 100
    )
    analysis_timeout_seconds = _read_int("ANALYSIS_TIMEOUT_SECONDS", 180, 10, 900)
    gemini_provider_timeout_ms = _read_int(
        "GEMINI_PROVIDER_TIMEOUT_MS", 20000, 1000, 120000
    )
    gemini_max_output_tokens = _read_int(
        "GEMINI_MAX_OUTPUT_TOKENS", 512, 64, 4096
    )
    analysis_retry_max_attempts = _read_int(
        "ANALYSIS_RETRY_MAX_ATTEMPTS", 3, 1, 5
    )
    data_retention_days = _read_int(
        "DATA_RETENTION_DAYS", 90, 1, 3650
    )
    celery_broker_url = os.getenv(
        "CELERY_BROKER_URL", "redis://127.0.0.1:6379/0"
    ).strip()
    parsed_broker = urlsplit(celery_broker_url)
    if parsed_broker.scheme not in {"redis", "rediss"} or not parsed_broker.hostname:
        raise ConfigurationError("CELERY_BROKER_URL must be a Redis URL.")
    if environment == "production":
        if parsed_broker.scheme != "rediss":
            raise ConfigurationError("CELERY_BROKER_URL must use TLS in production.")
        if not parsed_broker.password:
            raise ConfigurationError(
                "CELERY_BROKER_URL must include Redis authentication in production."
            )
        if parsed_broker.hostname.lower() in {
            "localhost",
            "127.0.0.1",
            "::1",
        }:
            raise ConfigurationError(
                "CELERY_BROKER_URL must use the private managed Redis endpoint."
            )
    if ttl_seconds < 300 or ttl_seconds > 60 * 60 * 24 * 30:
        raise ConfigurationError(
            "SESSION_TTL_SECONDS must be between 300 and 2592000."
        )

    frontend_origin = os.getenv("FRONTEND_ORIGIN", "").strip().rstrip("/")
    if not frontend_origin and environment == "development":
        frontend_origin = "http://localhost:5173"
    parsed_frontend = urlsplit(frontend_origin)
    if (
        not frontend_origin
        or parsed_frontend.scheme not in {"http", "https"}
        or not parsed_frontend.hostname
        or parsed_frontend.path
        or parsed_frontend.query
        or parsed_frontend.fragment
        or parsed_frontend.username is not None
        or parsed_frontend.password is not None
    ):
        raise ConfigurationError("FRONTEND_ORIGIN must be a bare HTTP(S) origin.")
    if environment == "production" and parsed_frontend.scheme != "https":
        raise ConfigurationError("FRONTEND_ORIGIN must use HTTPS in production.")

    redirect_uri = os.getenv(
        "GITHUB_OAUTH_REDIRECT_URI",
        "http://localhost:8000/api/auth/callback",
    ).strip()
    parsed_redirect = urlsplit(redirect_uri)
    if (
        parsed_redirect.scheme not in {"http", "https"}
        or not parsed_redirect.hostname
        or parsed_redirect.path != "/api/auth/callback"
        or parsed_redirect.query
        or parsed_redirect.fragment
        or parsed_redirect.username is not None
        or parsed_redirect.password is not None
    ):
        raise ConfigurationError(
            "GITHUB_OAUTH_REDIRECT_URI must target /api/auth/callback."
        )
    if environment == "production" and parsed_redirect.scheme != "https":
        raise ConfigurationError(
            "GITHUB_OAUTH_REDIRECT_URI must use HTTPS in production."
        )

    github_app_id = os.getenv("GITHUB_APP_ID", "").strip()
    github_app_slug = os.getenv("GITHUB_APP_SLUG", "").strip()
    if github_app_id and not github_app_id.isdigit():
        raise ConfigurationError("GITHUB_APP_ID must contain only digits.")
    if github_app_slug and (
        not github_app_slug[0].isalnum()
        or any(
            not (char.islower() or char.isdigit() or char == "-")
            for char in github_app_slug
        )
    ):
        raise ConfigurationError("GITHUB_APP_SLUG must be a lowercase GitHub App slug.")

    setup_url = os.getenv(
        "GITHUB_APP_SETUP_URL",
        "http://localhost:8000/api/github/installations/callback",
    ).strip()
    app_user_callback_url = os.getenv(
        "GITHUB_APP_USER_CALLBACK_URL",
        "http://localhost:8000/api/github/user-callback",
    ).strip()
    for setting_name, callback_url, callback_path in (
        (
            "GITHUB_APP_SETUP_URL",
            setup_url,
            "/api/github/installations/callback",
        ),
        (
            "GITHUB_APP_USER_CALLBACK_URL",
            app_user_callback_url,
            "/api/github/user-callback",
        ),
    ):
        parsed_callback = urlsplit(callback_url)
        if (
            parsed_callback.scheme not in {"http", "https"}
            or not parsed_callback.hostname
            or parsed_callback.path != callback_path
            or parsed_callback.query
            or parsed_callback.fragment
            or parsed_callback.username is not None
            or parsed_callback.password is not None
        ):
            raise ConfigurationError(
                f"{setting_name} must be a bare URL ending in {callback_path}."
            )
        app_settings_present = any(
            (
                github_app_id,
                github_app_slug,
                os.getenv("GITHUB_APP_CLIENT_ID", "").strip(),
                os.getenv("GITHUB_APP_CLIENT_SECRET", "").strip(),
                os.getenv("GITHUB_APP_PRIVATE_KEY", "").strip(),
                os.getenv("GITHUB_APP_WEBHOOK_SECRET", "").strip(),
            )
        )
        if (
            environment == "production"
            and app_settings_present
            and parsed_callback.scheme != "https"
        ):
            raise ConfigurationError(f"{setting_name} must use HTTPS in production.")

    return Settings(
        app_environment=environment,
        database_url=os.getenv("DATABASE_URL", "").strip(),
        github_oauth_client_id=os.getenv("GITHUB_OAUTH_CLIENT_ID", "").strip(),
        github_oauth_client_secret=os.getenv(
            "GITHUB_OAUTH_CLIENT_SECRET", ""
        ).strip(),
        github_oauth_redirect_uri=redirect_uri,
        github_oauth_state_secret=os.getenv(
            "GITHUB_OAUTH_STATE_SECRET", ""
        ).strip(),
        github_app_id=github_app_id,
        github_app_slug=github_app_slug,
        github_app_client_id=os.getenv("GITHUB_APP_CLIENT_ID", "").strip(),
        github_app_client_secret=os.getenv(
            "GITHUB_APP_CLIENT_SECRET", ""
        ).strip(),
        github_app_private_key=os.getenv(
            "GITHUB_APP_PRIVATE_KEY", ""
        ).strip().replace("\\n", "\n"),
        github_app_webhook_secret=os.getenv(
            "GITHUB_APP_WEBHOOK_SECRET", ""
        ).strip(),
        github_app_setup_url=setup_url,
        github_app_user_callback_url=app_user_callback_url,
        frontend_origin=frontend_origin,
        session_cookie_name=os.getenv(
            "SESSION_COOKIE_NAME", "docguard_session"
        ).strip(),
        session_ttl_seconds=ttl_seconds,
        session_cookie_secure=secure_cookie,
        session_cookie_samesite=same_site,
        analysis_per_user_hour_limit=analysis_per_user_hour_limit,
        analysis_per_workspace_day_limit=analysis_per_workspace_day_limit,
        analysis_max_concurrent_per_workspace=analysis_max_concurrent_per_workspace,
        analysis_timeout_seconds=analysis_timeout_seconds,
        gemini_daily_budget_usd=_read_nonnegative_float(
            "GEMINI_DAILY_BUDGET_USD"
        ),
        gemini_user_daily_budget_usd=_read_nonnegative_float(
            "GEMINI_USER_DAILY_BUDGET_USD"
        ),
        gemini_input_usd_per_million_tokens=_read_nonnegative_float(
            "GEMINI_INPUT_USD_PER_MILLION_TOKENS"
        ),
        gemini_output_usd_per_million_tokens=_read_nonnegative_float(
            "GEMINI_OUTPUT_USD_PER_MILLION_TOKENS"
        ),
        gemini_provider_timeout_ms=gemini_provider_timeout_ms,
        gemini_max_output_tokens=gemini_max_output_tokens,
        celery_broker_url=celery_broker_url,
        analysis_retry_max_attempts=analysis_retry_max_attempts,
        data_retention_days=data_retention_days,
    )


def require_database_url() -> str:
    database_url = get_settings().database_url
    if not database_url:
        raise ConfigurationError("Database is not configured.")
    if not database_url.startswith(("postgresql+psycopg://", "sqlite://")):
        raise ConfigurationError(
            "DATABASE_URL must use postgresql+psycopg or sqlite."
        )
    if (
        get_settings().app_environment == "production"
        and not database_url.startswith("postgresql+psycopg://")
    ):
        raise ConfigurationError("Production requires PostgreSQL.")
    return database_url
