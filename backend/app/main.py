"""
DocGuard Backend — Milestone 1: Project Foundation
Provides the core FastAPI application and health check endpoint.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

APP_NAME = "DocGuard"
APP_VERSION = "0.1.0"


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

# Allow the local Vite development server to communicate with the backend
ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

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
