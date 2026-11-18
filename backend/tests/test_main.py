"""
Tests for DocGuard Milestone 1 Backend Endpoints.
Run with: pytest
"""

from fastapi.testclient import TestClient
from app.main import app

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
