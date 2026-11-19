from sqlalchemy import select

from app.models import PasswordCredential


def test_local_registration_and_login_work_without_github_oauth(
    real_auth_client, database_session, monkeypatch
):
    monkeypatch.setenv("GITHUB_OAUTH_CLIENT_ID", "")
    monkeypatch.setenv("GITHUB_OAUTH_CLIENT_SECRET", "")
    monkeypatch.setenv("GITHUB_OAUTH_STATE_SECRET", "")
    from app.config import get_settings

    get_settings.cache_clear()
    headers = {"Origin": "http://localhost:5173"}
    try:
        status = real_auth_client.get("/api/auth/status")
        assert status.json() == {
            "sign_in_enabled": True,
            "github_oauth_enabled": False,
        }

        created = real_auth_client.post(
            "/api/auth/register",
            headers=headers,
            json={
                "name": "Local User",
                "email": "local@example.com",
                "password": "a-very-strong-password",
            },
        )
        assert created.status_code == 200
        assert real_auth_client.get("/api/auth/me").status_code == 200
        credential = database_session.scalar(select(PasswordCredential))
        assert credential is not None
        assert credential.password_hash != "a-very-strong-password"

        real_auth_client.post("/api/auth/logout", headers=headers)
        login = real_auth_client.post(
            "/api/auth/login",
            headers=headers,
            json={
                "email": "local@example.com",
                "password": "a-very-strong-password",
            },
        )
        assert login.status_code == 200
        assert real_auth_client.get("/api/auth/me").status_code == 200
    finally:
        get_settings.cache_clear()


def test_local_auth_rejects_duplicate_registration_and_invalid_password(
    real_auth_client,
):
    headers = {"Origin": "http://localhost:5173"}
    account = {
        "name": "Local User",
        "email": "local@example.com",
        "password": "a-very-strong-password",
    }
    assert (
        real_auth_client.post(
            "/api/auth/register", headers=headers, json=account
        ).status_code
        == 200
    )
    duplicate = real_auth_client.post(
        "/api/auth/register", headers=headers, json=account
    )
    assert duplicate.status_code == 409

    real_auth_client.post("/api/auth/logout", headers=headers)
    invalid = real_auth_client.post(
        "/api/auth/login",
        headers=headers,
        json={"email": account["email"], "password": "wrong-password"},
    )
    assert invalid.status_code == 401
