"""Authentication, session, and workspace boundary tests."""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api import auth as auth_api
from app.auth.dependencies import get_current_principal
from app.config import ConfigurationError, get_settings
from app.db.session import _session_factory
from app.main import app
from app.models import (
    AuthSession,
    OAuthLoginState,
    User,
    UserIdentity,
    Workspace,
    WorkspaceMembership,
)

SESSION_COOKIE = "docguard_session"
def _persist_user_session(
    db,
    display_name: str,
    subject: str,
    token: str,
    expires_at: datetime | None = None,
):
    user = User(display_name=display_name, email=None)
    db.add(user)
    db.flush()
    db.add(
        UserIdentity(
            user_id=user.id,
            issuer=auth_api.GITHUB_ISSUER,
            subject=subject,
        )
    )
    workspace = Workspace(
        name=f"{display_name}'s workspace",
        workspace_type="personal",
        personal_owner_user_id=user.id,
    )
    db.add(workspace)
    db.flush()
    db.add(
        WorkspaceMembership(
            workspace_id=workspace.id,
            user_id=user.id,
            role="owner",
        )
    )
    session = AuthSession(
        user_id=user.id,
        token_hash=hashlib.sha256(token.encode()).hexdigest(),
        expires_at=expires_at or datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db.add(session)
    db.commit()
    return user, workspace, session


def _set_session_cookie(client, token: str) -> None:
    client.cookies.set(
        SESSION_COOKIE,
        token,
        domain="testserver.local",
        path="/",
    )


@pytest.fixture
def real_auth_client(unauthenticated_client):
    return unauthenticated_client


def test_auth_status_never_exposes_oauth_secrets(real_auth_client):
    response = real_auth_client.get("/api/auth/status")

    assert response.status_code == 200
    assert response.json() == {"sign_in_enabled": True}
    assert "test-only-github-oauth-secret" not in response.text
    assert "test-only-state-signing-secret" not in response.text


def test_missing_github_oauth_configuration_fails_closed(
    real_auth_client, monkeypatch
):
    monkeypatch.setenv("GITHUB_OAUTH_CLIENT_ID", "")
    monkeypatch.setenv("GITHUB_OAUTH_CLIENT_SECRET", "")
    monkeypatch.setenv("GITHUB_OAUTH_STATE_SECRET", "")
    get_settings.cache_clear()
    try:
        status_response = real_auth_client.get("/api/auth/status")
        login_response = real_auth_client.get(
            "/api/auth/login", follow_redirects=False
        )
    finally:
        get_settings.cache_clear()

    assert status_response.json() == {"sign_in_enabled": False}
    assert login_response.status_code == 503
    assert "secret" not in login_response.text.lower()


def test_production_rejects_insecure_cookie_and_requires_https_origins(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")
    monkeypatch.setenv("FRONTEND_ORIGIN", "https://app.example.test")
    monkeypatch.setenv(
        "GITHUB_OAUTH_REDIRECT_URI",
        "https://api.example.test/api/auth/callback",
    )
    monkeypatch.setenv(
        "CELERY_BROKER_URL",
        "rediss://docguard:placeholder@redis.example.test:6380/0",
    )
    get_settings.cache_clear()
    try:
        with pytest.raises(ConfigurationError):
            get_settings()

        monkeypatch.setenv("SESSION_COOKIE_SECURE", "true")
        get_settings.cache_clear()
        settings = get_settings()
        assert settings.session_cookie_secure is True

        monkeypatch.setenv("FRONTEND_ORIGIN", "http://app.example.test")
        get_settings.cache_clear()
        with pytest.raises(ConfigurationError):
            get_settings()
    finally:
        get_settings.cache_clear()


def test_login_redirect_uses_state_and_pkce_and_persists_only_state_hash(
    real_auth_client, database_session
):
    response = real_auth_client.get("/api/auth/login", follow_redirects=False)

    assert response.status_code == 302
    query = parse_qs(urlsplit(response.headers["location"]).query)
    state = query["state"][0]
    assert query["code_challenge_method"] == ["S256"]
    assert query["code_challenge"]
    saved = database_session.get(
        OAuthLoginState,
        hashlib.sha256(state.encode()).hexdigest(),
    )
    assert saved is not None
    assert state not in saved.state_hash
    transaction_cookie = response.headers.get("set-cookie", "")
    assert "docguard_oauth_transaction=" in transaction_cookie
    assert "httponly" in transaction_cookie.lower()


def test_callback_rejects_missing_expired_and_replayed_state(
    real_auth_client, database_session, monkeypatch
):
    called = False

    def forbidden_client():
        nonlocal called
        called = True
        raise AssertionError("OAuth client must not run for invalid state")

    monkeypatch.setattr(auth_api, "get_github_oauth_client", forbidden_client)
    invalid = real_auth_client.get(
        "/api/auth/callback", params={"state": "not-issued"}
    )
    assert invalid.status_code == 400
    assert not called

    expired_state = "expired-state"
    database_session.add(
        OAuthLoginState(
            state_hash=hashlib.sha256(expired_state.encode()).hexdigest(),
            expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        )
    )
    database_session.commit()
    expired = real_auth_client.get(
        "/api/auth/callback", params={"state": expired_state}
    )
    assert expired.status_code == 400
    assert not called


def test_callback_rejects_state_without_authlib_transaction_cookie(
    real_auth_client
):
    start = real_auth_client.get("/api/auth/login", follow_redirects=False)
    state = parse_qs(urlsplit(start.headers["location"]).query)["state"][0]
    real_auth_client.cookies.clear()

    callback = real_auth_client.get(
        "/api/auth/callback",
        params={"state": state, "code": "not-a-real-code"},
    )

    assert callback.status_code == 400
    assert "code" not in callback.text


def test_callback_creates_account_personal_workspace_and_hashed_session(
    real_auth_client, database_session, monkeypatch, caplog
):
    _previous_user, _previous_workspace, previous_session = _persist_user_session(
        database_session, "Previous User", "previous", "previous-session"
    )
    _set_session_cookie(real_auth_client, "previous-session")
    login_response = real_auth_client.get(
        "/api/auth/login", follow_redirects=False
    )
    state = parse_qs(urlsplit(login_response.headers["location"]).query)["state"][0]
    provider_token = "test-only-provider-access-token"

    class FakeResponse:
        def __init__(self, value):
            self.value = value

        def raise_for_status(self):
            return None

        def json(self):
            return self.value

    class FakeGitHubOAuth:
        async def authorize_access_token(self, _request):
            return {"access_token": provider_token}

        async def get(self, endpoint, token):
            assert token["access_token"] == provider_token
            if endpoint == "user":
                return FakeResponse(
                    {
                        "id": 123456,
                        "login": "docguard-user",
                        "name": "DocGuard User",
                        "email": "unverified@example.invalid",
                    }
                )
            assert endpoint == "user/emails"
            return FakeResponse(
                [
                    {
                        "email": "verified@example.invalid",
                        "primary": True,
                        "verified": True,
                    }
                ]
            )

    monkeypatch.setattr(
        auth_api, "get_github_oauth_client", lambda: FakeGitHubOAuth()
    )
    callback = real_auth_client.get(
        "/api/auth/callback",
        params={"state": state, "code": "fake-code"},
        follow_redirects=False,
    )

    assert callback.status_code == 303
    assert callback.headers["location"] == "http://localhost:5173/"
    cookie_headers = callback.headers.get_list("set-cookie")
    session_cookie = next(
        value for value in cookie_headers if value.startswith(f"{SESSION_COOKIE}=")
    )
    assert "httponly" in session_cookie.lower()
    assert "samesite=lax" in session_cookie.lower()
    assert "secure" not in session_cookie.lower()

    raw_session_token = real_auth_client.cookies.get(
        SESSION_COOKIE, domain="testserver.local", path="/"
    )
    assert raw_session_token
    database_session.refresh(previous_session)
    assert previous_session.revoked_at is not None
    persisted = database_session.scalar(
        select(AuthSession).where(
            AuthSession.token_hash
            == hashlib.sha256(raw_session_token.encode()).hexdigest()
        )
    )
    assert persisted is not None
    assert persisted.token_hash != raw_session_token
    assert raw_session_token not in callback.text
    assert provider_token not in callback.text
    assert raw_session_token not in caplog.text
    assert provider_token not in caplog.text
    assert provider_token not in repr(persisted)

    identity = database_session.scalar(
        select(UserIdentity).where(UserIdentity.subject == "123456")
    )
    assert identity is not None
    user = database_session.get(User, identity.user_id)
    assert user is not None
    assert user.email == "verified@example.invalid"
    workspace = database_session.scalar(
        select(Workspace).where(Workspace.personal_owner_user_id == user.id)
    )
    assert workspace is not None
    membership = database_session.get(
        WorkspaceMembership,
        {"workspace_id": workspace.id, "user_id": user.id},
    )
    assert membership is not None
    assert membership.role == "owner"
    database_session.expire_all()
    session_count = database_session.query(AuthSession).count()
    replay = real_auth_client.get(
        "/api/auth/callback",
        params={"state": state, "code": "fake-code"},
        follow_redirects=False,
    )
    assert replay.status_code == 400
    assert database_session.query(AuthSession).count() == session_count


def test_me_is_bound_to_session_and_ignores_forged_identity_ids(
    real_auth_client, database_session
):
    user_a, workspace_a, _ = _persist_user_session(
        database_session, "User A", "github-a", "opaque-session-a"
    )
    _persist_user_session(
        database_session, "User B", "github-b", "opaque-session-b"
    )
    _set_session_cookie(real_auth_client, "opaque-session-a")

    response = real_auth_client.get(
        "/api/auth/me?user_id=forged&workspace_id=forged",
        headers={"X-User-Id": "forged"},
    )

    assert response.status_code == 200
    assert response.json()["user"]["id"] == str(user_a.id)
    assert response.json()["workspace"]["id"] == str(workspace_a.id)
    assert "session" not in response.json()
    assert "token" not in response.json()
    assert "opaque-session-a" not in response.text
    assert "opaque-session-b" not in response.text


def test_expired_session_is_rejected(real_auth_client, database_session):
    _persist_user_session(
        database_session,
        "Expired User",
        "expired",
        "expired-session",
        datetime.now(timezone.utc) - timedelta(seconds=1),
    )
    _set_session_cookie(real_auth_client, "expired-session")

    response = real_auth_client.get("/api/auth/me")

    assert response.status_code == 401


def test_logout_requires_trusted_origin_revokes_and_clears_session(
    real_auth_client, database_session
):
    _user, _workspace, auth_session = _persist_user_session(
        database_session, "Logout User", "logout", "logout-session"
    )
    _set_session_cookie(real_auth_client, "logout-session")

    rejected = real_auth_client.post(
        "/api/auth/logout",
        headers={"Origin": "https://attacker.example", "Sec-Fetch-Site": "cross-site"},
    )
    assert rejected.status_code == 403
    assert auth_session.revoked_at is None

    missing_origin = real_auth_client.post("/api/auth/logout")
    assert missing_origin.status_code == 403
    assert auth_session.revoked_at is None

    logged_out = real_auth_client.post(
        "/api/auth/logout",
        headers={"Origin": "http://localhost:5173", "Sec-Fetch-Site": "same-origin"},
    )
    assert logged_out.status_code == 204
    database_session.refresh(auth_session)
    assert auth_session.revoked_at is not None
    clear_cookie = next(
        header
        for header in logged_out.headers.get_list("set-cookie")
        if header.startswith(f"{SESSION_COOKIE}=")
    )
    assert "max-age=0" in clear_cookie.lower()
    assert real_auth_client.get("/api/auth/me").status_code == 401


@pytest.mark.parametrize(
    "method,path,payload",
    [
        ("post", "/api/repositories/inspect", {"github_repository_id": 1113855450}),
        (
            "post",
            "/api/repositories/compare",
            {
                "github_repository_id": 1113855450,
                "base_commit": "a" * 40,
                "head_commit": "b" * 40,
            },
        ),
        (
            "post",
            "/api/analyze/code",
            {
                "github_repository_id": 1113855450,
                "base_commit": "a" * 40,
                "head_commit": "b" * 40,
            },
        ),
        (
            "post",
            "/api/analyze/documentation",
            {
                "github_repository_id": 1113855450,
                "head_commit": "b" * 40,
            },
        ),
        ("get", "/api/analyze/explanations/providers", None),
        (
            "post",
            "/api/analyze/drift",
            {
                "github_repository_id": 1113855450,
                "base_commit": "a" * 40,
                "head_commit": "b" * 40,
            },
        ),
        (
            "post",
            "/api/analyses",
            {
                "github_repository_id": 1113855450,
                "base_commit": "a" * 40,
                "head_commit": "b" * 40,
            },
        ),
        (
            "post",
            "/api/analyze/explanations",
            {
                "analysis_id": "11111111-1111-4111-8111-111111111111",
                "finding_ids": ["finding-1"],
            },
        ),
        (
            "get",
            "/api/analyses",
            None,
        ),
        (
            "get",
            "/api/analyses/11111111-1111-4111-8111-111111111111",
            None,
        ),
        (
            "get",
            "/api/analyses/11111111-1111-4111-8111-111111111111/status",
            None,
        ),
        (
            "post",
            "/api/analyses/11111111-1111-4111-8111-111111111111/cancel",
            None,
        ),
        (
            "post",
            "/api/analyses/11111111-1111-4111-8111-111111111111/retry",
            None,
        ),
        (
            "delete",
            "/api/analyses/11111111-1111-4111-8111-111111111111",
            None,
        ),
    ],
)
def test_analysis_routes_require_authentication(
    unauthenticated_client, method, path, payload
):
    request = getattr(unauthenticated_client, method)
    response = (
        request(path, json=payload)
        if payload is not None
        else request(path)
    )

    assert response.status_code == 401


def test_login_start_is_rate_limited(unauthenticated_client):
    responses = [
        unauthenticated_client.get("/api/auth/login", follow_redirects=False)
        for _ in range(auth_api.LOGIN_RATE_LIMIT + 1)
    ]

    assert all(response.status_code == 302 for response in responses[:-1])
    assert responses[-1].status_code == 429
