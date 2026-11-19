"""
Tests for DocGuard Milestone 1 Backend Endpoints.
Run with: pytest
"""

from fastapi.testclient import TestClient
from fastapi.middleware.cors import CORSMiddleware

from app.main import ALLOWED_ORIGINS, app, get_allowed_cors_origins

client = TestClient(app)


def test_read_root():
    """Verify the root endpoint returns a 200 status and basic navigation links."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Welcome to the DocGuard API"
    assert data["health_url"] == "/api/health"


def test_health_check():
    """Verify GET /api/health returns the exact expected Milestone 1 JSON payload."""
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "application": "DocGuard",
        "version": "0.1.0",
    }


def test_cors_allowed_origins_configuration():
    """
    Explicit deployment origins replace development defaults and are normalized;
    unsafe or non-origin URL values are rejected.
    """
    origins = get_allowed_cors_origins(
        cors_allowed_origins_env=(
            "*, https://docguard.example.com/, https://staging.docguard.example.com, "
            "ftp://bad.example, https://user:pass@example.com, "
            "https://example.com/path, https://*.example.com, "
            "https://example.com?, https://example.com:invalid"
        ),
        frontend_origin_env="https://app.docguard.example.com:443/",
    )
    assert "https://app.docguard.example.com" in origins
    assert "https://docguard.example.com" in origins
    assert "https://staging.docguard.example.com" in origins
    assert len(origins) == 3


def test_cors_origins_default_to_local_vite_only(monkeypatch):
    """Without custom environment variables, the local Vite origins are allowed."""
    from app.main import DEFAULT_ALLOWED_ORIGINS, load_allowed_origins

    monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    monkeypatch.delenv("FRONTEND_ORIGIN", raising=False)
    assert load_allowed_origins() == DEFAULT_ALLOWED_ORIGINS


def test_cors_legacy_environment_and_invalid_only_configuration(monkeypatch):
    """The legacy allowlist is supported and invalid explicit values never restore defaults."""
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "")
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://legacy.example.com")
    monkeypatch.setenv("FRONTEND_ORIGIN", "")
    assert get_allowed_cors_origins() == ["https://legacy.example.com"]

    assert get_allowed_cors_origins(
        cors_allowed_origins_env="https://example.com/path",
        frontend_origin_env="",
    ) == []


def test_cors_middleware_applies_configured_allowlist():
    """The FastAPI middleware allows a configured origin and rejects an unlisted one."""
    origin = ALLOWED_ORIGINS[0]
    allowed = client.options(
        "/api/health",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
        },
    )
    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == origin

    rejected = client.options(
        "/api/health",
        headers={
            "Origin": "https://not-allowed.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert "access-control-allow-origin" not in rejected.headers
