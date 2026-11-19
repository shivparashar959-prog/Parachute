"""
DocGuard Backend — Milestone 1: Project Foundation
Provides the core FastAPI application and health check endpoint.
"""

import logging
import os
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urlsplit

from dotenv import load_dotenv

load_dotenv(override=False)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware

from app.api.auth import router as auth_router
from app.api.analyses import router as analyses_router
from app.api.github_app import router as github_app_router
from app.api.ai_explanations import router as ai_explanations_router
from app.api.code_analysis import router as code_analysis_router
from app.api.documentation import router as documentation_router
from app.api.drift import router as drift_router
from app.api.repositories import router as repositories_router
from app.config import get_settings

logger = logging.getLogger("docguard")
SENSITIVE_QUERY_KEYS = {"code", "state", "access_token", "refresh_token"}


class SensitiveQueryRedactionMiddleware:
    """Redact one-time OAuth values before the ASGI server writes access logs."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        original_query = scope.get("query_string", b"")
        try:
            query_text = original_query.decode("ascii")
        except UnicodeDecodeError:
            query_text = ""
        sanitized_query = urlencode(
            [
                (key, "[REDACTED]" if key.lower() in SENSITIVE_QUERY_KEYS else value)
                for key, value in parse_qsl(query_text, keep_blank_values=True)
            ]
        ).encode("ascii")

        try:
            await self.app(scope, receive, send)
        finally:
            scope["query_string"] = sanitized_query

APP_NAME = "DocGuard"
APP_VERSION = "0.1.0"

DEFAULT_LOCAL_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
DEFAULT_ALLOWED_ORIGINS = list(DEFAULT_LOCAL_ORIGINS)


def get_allowed_cors_origins(
    cors_allowed_origins_env: Optional[str] = None,
    frontend_origin_env: Optional[str] = None,
    app_environment_env: Optional[str] = None,
) -> list[str]:
    """
    Use localhost origins only when no explicit origins are configured. Explicit
    settings replace those development defaults and accept only bare HTTP(S) origins.
    """
    raw_cors_list = (
        cors_allowed_origins_env
        if cors_allowed_origins_env is not None
        else os.getenv("CORS_ALLOWED_ORIGINS", "")
    )
    if not raw_cors_list.strip():
        raw_cors_list = os.getenv("ALLOWED_ORIGINS", "")
    raw_frontend = (
        frontend_origin_env
        if frontend_origin_env is not None
        else os.getenv("FRONTEND_ORIGIN", "")
    )
    app_environment = (
        app_environment_env
        if app_environment_env is not None
        else os.getenv("APP_ENV", "development")
    ).strip().lower()

    has_explicit_origins = bool(raw_cors_list.strip() or raw_frontend.strip())
    candidates: list[str] = (
        []
        if has_explicit_origins or app_environment != "development"
        else list(DEFAULT_LOCAL_ORIGINS)
    )
    if raw_frontend:
        candidates.extend(raw_frontend.split(","))
    if raw_cors_list:
        candidates.extend(raw_cors_list.split(","))

    allowed: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        cleaned = item.strip()
        if not cleaned:
            continue
        if (
            "*" in cleaned
            or "?" in cleaned
            or "#" in cleaned
            or any(char.isspace() for char in cleaned)
        ):
            logger.warning("Ignoring invalid CORS origin %r.", cleaned)
            continue

        try:
            parsed = urlsplit(cleaned)
            port = parsed.port
        except ValueError:
            logger.warning("Ignoring invalid CORS origin %r.", cleaned)
            continue

        scheme = parsed.scheme.lower()
        hostname = parsed.hostname
        if (
            scheme not in {"http", "https"}
            or not hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
            or parsed.netloc.endswith(":")
        ):
            logger.warning(
                "Ignoring invalid CORS origin %r; provide a bare HTTP(S) origin.",
                cleaned,
            )
            continue

        host = f"[{hostname.lower()}]" if ":" in hostname else hostname.lower()
        if port is not None and not (
            (scheme == "http" and port == 80)
            or (scheme == "https" and port == 443)
        ):
            host = f"{host}:{port}"
        normalized = f"{scheme}://{host}"
        if normalized not in seen:
            seen.add(normalized)
            allowed.append(normalized)

    return allowed


load_allowed_origins = get_allowed_cors_origins


class HealthResponse(BaseModel):
    """Schema for the health check endpoint response."""

    status: str
    application: str
    version: str


class RootResponse(BaseModel):
    """Schema for the root welcome endpoint response."""

    message: str
    docs_url: str
    health_url: str


app = FastAPI(
    title=APP_NAME,
    description="AI-powered documentation drift detection platform API",
    version=APP_VERSION,
)
app.add_middleware(SensitiveQueryRedactionMiddleware)

# Keep the OAuth protocol transaction separate from the persistent login session.
settings = get_settings()
if settings.github_oauth_state_secret:
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.github_oauth_state_secret,
        session_cookie="docguard_oauth_transaction",
        max_age=600,
        path="/api/auth",
        same_site="lax",
        https_only=settings.session_cookie_secure,
    )

# Configure CORS origins from environment variables (with development-only localhost defaults).
ALLOWED_ORIGINS = get_allowed_cors_origins()

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Accept", "Content-Type"],
)


@app.get("/", response_model=RootResponse, tags=["General"])
def read_root() -> RootResponse:
    """Root endpoint returning basic API metadata and helpful links."""
    return RootResponse(
        message="Welcome to the DocGuard API",
        docs_url="/docs",
        health_url="/api/health",
    )


@app.get("/api/health", response_model=HealthResponse, tags=["System"])
def health_check() -> HealthResponse:
    """Return the current health status of the DocGuard backend service."""
    return HealthResponse(
        status="ok",
        application=APP_NAME,
        version=APP_VERSION,
    )


app.include_router(auth_router)
app.include_router(analyses_router)
app.include_router(github_app_router)
app.include_router(repositories_router)
app.include_router(code_analysis_router)
app.include_router(documentation_router)
app.include_router(drift_router)
app.include_router(ai_explanations_router)
