"""
DocGuard Backend — Milestone 1: Project Foundation
Provides the core FastAPI application and health check endpoint.
"""

import logging
import os
from typing import Optional
from urllib.parse import urlsplit

from dotenv import load_dotenv

load_dotenv(override=False)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.api.ai_explanations import router as ai_explanations_router
from app.api.code_analysis import router as code_analysis_router
from app.api.documentation import router as documentation_router
from app.api.drift import router as drift_router
from app.api.repositories import router as repositories_router

logger = logging.getLogger("docguard")

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

    has_explicit_origins = bool(raw_cors_list.strip() or raw_frontend.strip())
    candidates: list[str] = (
        [] if has_explicit_origins else list(DEFAULT_LOCAL_ORIGINS)
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

# Configure CORS origins from environment variables (with localhost dev defaults)
ALLOWED_ORIGINS = get_allowed_cors_origins()

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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


app.include_router(repositories_router)
app.include_router(code_analysis_router)
app.include_router(documentation_router)
app.include_router(drift_router)
app.include_router(ai_explanations_router)
