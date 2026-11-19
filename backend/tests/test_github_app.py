"""Workspace authorization and GitHub App lifecycle tests."""

import hashlib
import hmac
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api import github_app as github_app_api
from app.auth import github_app
from app.auth.dependencies import AuthenticatedPrincipal, get_current_principal
from app.auth.github_app import InstallationAccessToken
from app.main import app
from app.models import (
    AuthSession,
    AuthorizedRepository,
    GitHubAppInstallation,
    GitHubAppState,
    PullRequestAutomationResult,
    User,
    UserIdentity,
    Workspace,
    WorkspaceMembership,
)
from app.services import github_app_service


def _create_principal(db, display_name: str, github_id: str):
    user = User(display_name=display_name, email=None)
    db.add(user)
    db.flush()
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
    db.add(
        UserIdentity(
            user_id=user.id,
            issuer=github_app_service.GITHUB_ISSUER,
            subject=github_id,
        )
    )
    db.commit()
    principal = AuthenticatedPrincipal(
        user=user,
        session=AuthSession(
            id=uuid.uuid4(),
            user_id=user.id,
            token_hash="a" * 64,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        ),
    )
    return principal, workspace


def _create_installation_and_repository(
    db,
    principal: AuthenticatedPrincipal,
    workspace: Workspace,
    *,
    installation_id: int,
    repository_id: int,
):
    installation = GitHubAppInstallation(
        installation_id=installation_id,
        workspace_id=workspace.id,
        installed_by_user_id=principal.user.id,
        account_id=installation_id + 100,
        account_login=f"owner-{installation_id}",
        account_type="User",
        repository_selection="selected",
        status="active",
    )
    repository = AuthorizedRepository(
        github_repository_id=repository_id,
        installation_id=installation_id,
        workspace_id=workspace.id,
        owner_login=installation.account_login,
        name="private-project",
        full_name=f"{installation.account_login}/private-project",
        html_url=f"https://github.com/{installation.account_login}/private-project",
        visibility="private",
        default_branch="main",
    )
    db.add_all([installation, repository])
    db.commit()
    return installation, repository


def test_installation_state_is_user_bound_and_single_use(database_session):
    principal_a, workspace_a = _create_principal(
        database_session, "User A", "github-user-a"
    )
    principal_b, _workspace_b = _create_principal(
        database_session, "User B", "github-user-b"
    )
    raw_state = github_app_service._insert_state(
        database_session,
        principal=principal_a,
        workspace=workspace_a,
        purpose="install",
    )

    with pytest.raises(github_app_service.GitHubAppStateError):
        github_app_service.consume_state(
            database_session,
            raw_state,
            principal=principal_b,
            purpose="install",
        )

    saved_state = database_session.get(
        GitHubAppState, github_app_service._hash_state(raw_state)
    )
    assert saved_state is not None
    assert raw_state not in saved_state.state_hash
    github_app_service.consume_state(
        database_session,
        raw_state,
        principal=principal_a,
        purpose="install",
    )
    with pytest.raises(github_app_service.GitHubAppStateError):
        github_app_service.consume_state(
            database_session,
            raw_state,
            principal=principal_a,
            purpose="install",
        )


def test_installation_verification_syncs_public_and_private_repositories(
    database_session, monkeypatch
):
    principal, workspace = _create_principal(
        database_session, "Install User", "4242"
    )
    raw_state = github_app_service._insert_state(
        database_session,
        principal=principal,
        workspace=workspace,
        purpose="verify",
        installation_id=8901,
    )
    token_value = "ephemeral-installation-token"
    monkeypatch.setattr(
        github_app_service,
        "get_settings",
        lambda: SimpleNamespace(
            github_app_id="123",
            github_app_client_id="client-id",
            github_app_user_callback_url=(
                "https://api.example.test/api/github/user-callback"
            ),
        ),
    )
    monkeypatch.setattr(
        github_app_service.github_app,
        "exchange_user_authorization_code",
        lambda _code: "ephemeral-user-token",
    )
    monkeypatch.setattr(
        github_app_service.github_app,
        "get_authenticated_github_user",
        lambda _token: {"id": 4242},
    )
    monkeypatch.setattr(
        github_app_service.github_app,
        "list_user_installations",
        lambda _token: [
            {
                "id": 8901,
                "app_id": 123,
                "account": {"id": 5678},
            }
        ],
    )
    monkeypatch.setattr(
        github_app_service.github_app,
        "verify_installation",
        lambda _installation_id: {
            "installation_id": 8901,
            "app_id": 123,
            "account_id": 5678,
            "account_login": "authorized-owner",
            "account_type": "Organization",
            "repository_selection": "selected",
            "suspended": False,
        },
    )
    monkeypatch.setattr(
        github_app_service.github_app,
        "create_installation_access_token",
        lambda _installation_id: InstallationAccessToken(
            value=token_value,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        ),
    )
    monkeypatch.setattr(
        github_app_service.github_app,
        "list_installation_repositories",
        lambda token: (
            [
                {
                    "id": 9001,
                    "owner": {"login": "authorized-owner"},
                    "name": "public-project",
                    "visibility": "public",
                },
                {
                    "id": 9002,
                    "owner": {"login": "authorized-owner"},
                    "name": "private-project",
                    "visibility": "private",
                },
            ]
            if token == token_value
            else pytest.fail("unexpected installation token")
        ),
    )

    installation = github_app_service.complete_installation_verification(
        database_session,
        principal=principal,
        raw_state=raw_state,
        code="one-time-code",
    )
    repositories = database_session.query(AuthorizedRepository).all()

    assert installation.installation_id == 8901
    assert {item.github_repository_id for item in repositories} == {9001, 9002}
    assert {item.visibility for item in repositories} == {"public", "private"}
    assert token_value not in repr(installation)
    assert token_value not in repr(repositories)
    assert "ephemeral-user-token" not in repr(installation)


def test_installation_verification_rejects_a_different_github_identity(
    database_session, monkeypatch
):
    principal, workspace = _create_principal(
        database_session, "Install User", "4242"
    )
    raw_state = github_app_service._insert_state(
        database_session,
        principal=principal,
        workspace=workspace,
        purpose="verify",
        installation_id=8901,
    )
    monkeypatch.setattr(
        github_app_service,
        "get_settings",
        lambda: SimpleNamespace(github_app_id="123"),
    )
    monkeypatch.setattr(
        github_app_service.github_app,
        "exchange_user_authorization_code",
        lambda _code: "ephemeral-user-token",
    )
    monkeypatch.setattr(
        github_app_service.github_app,
        "get_authenticated_github_user",
        lambda _token: {"id": 9999},
    )

    with pytest.raises(github_app_service.GitHubAppStateError):
        github_app_service.complete_installation_verification(
            database_session,
            principal=principal,
            raw_state=raw_state,
            code="one-time-code",
        )

    assert database_session.query(GitHubAppInstallation).count() == 0


def test_repository_catalog_and_pull_request_access_are_workspace_scoped(
    database_session, monkeypatch
):
    principal_a, workspace_a = _create_principal(
        database_session, "User A", "github-user-a"
    )
    principal_b, workspace_b = _create_principal(
        database_session, "User B", "github-user-b"
    )
    _installation_a, repository_a = _create_installation_and_repository(
        database_session,
        principal_a,
        workspace_a,
        installation_id=8101,
        repository_id=9101,
    )
    _create_installation_and_repository(
        database_session,
        principal_b,
        workspace_b,
        installation_id=8102,
        repository_id=9102,
    )
    monkeypatch.setattr(
        github_app_service.github_app,
        "create_installation_access_token",
        lambda _installation_id: SimpleNamespace(value="secret-token"),
    )
    monkeypatch.setattr(github_app_service, "_sync_repository_catalog", lambda *_: None)
    app.dependency_overrides[get_current_principal] = lambda: principal_a

    with TestClient(app) as client:
        response = client.get("/api/github/repositories")

    assert response.status_code == 200
    assert [
        item["github_repository_id"] for item in response.json()["repositories"]
    ] == [repository_a.github_repository_id]
    assert "secret-token" not in response.text

    with pytest.raises(github_app_service.GitHubAppRepositoryDeniedError):
        github_app_service.resolve_repository_access(
            database_session,
            principal_b,
            repository_a.github_repository_id,
        )


def test_uninstall_webhook_revokes_repository_access(database_session, monkeypatch):
    principal, workspace = _create_principal(
        database_session, "Install User", "4242"
    )
    installation, repository = _create_installation_and_repository(
        database_session,
        principal,
        workspace,
        installation_id=8201,
        repository_id=9201,
    )
    monkeypatch.setattr(
        github_app_service,
        "get_settings",
        lambda: SimpleNamespace(github_app_id="123"),
    )

    accepted = github_app_service.process_webhook(
        database_session,
        delivery_id="delivery-uninstall",
        event_name="installation",
        payload={
            "action": "deleted",
            "installation": {"id": installation.installation_id, "app_id": 123},
        },
    )

    database_session.refresh(installation)
    database_session.refresh(repository)
    assert accepted is True
    assert installation.status == "uninstalled"
    assert repository.is_active is False
    with pytest.raises(github_app_service.GitHubAppRepositoryDeniedError):
        github_app_service.resolve_repository_access(
            database_session,
            principal,
            repository.github_repository_id,
        )


def test_rate_limit_is_returned_without_upstream_details(
    database_session, monkeypatch
):
    principal, _workspace = _create_principal(
        database_session, "Rate Limited User", "7777"
    )
    app.dependency_overrides[get_current_principal] = lambda: principal

    def rate_limited(*_args, **_kwargs):
        from app.auth.github_app import GitHubAppRateLimitError

        raise GitHubAppRateLimitError(30)

    monkeypatch.setattr(
        github_app_service,
        "list_workspace_repositories",
        rate_limited,
    )
    with TestClient(app) as client:
        response = client.get("/api/github/repositories")

    assert response.status_code == 429
    assert response.headers["retry-after"] == "30"
    assert "token" not in response.text.lower()


def test_webhook_signature_is_required_and_delivery_is_idempotent(
    database_session, monkeypatch
):
    webhook_secret = "test-webhook-secret-with-sufficient-length"
    monkeypatch.setattr(
        github_app_api,
        "get_settings",
        lambda: SimpleNamespace(
            github_app_configured=True,
            github_app_webhook_secret=webhook_secret,
        ),
    )
    monkeypatch.setattr(
        github_app_service,
        "get_settings",
        lambda: SimpleNamespace(github_app_id="123"),
    )
    body = b'{"action":"created"}'
    signature = "sha256=" + hmac.new(
        webhook_secret.encode("utf-8"), body, hashlib.sha256
    ).hexdigest()

    with TestClient(app) as client:
        rejected = client.post(
            "/api/github/webhook",
            content=body,
            headers={
                "X-GitHub-Event": "ping",
                "X-GitHub-Delivery": "delivery-invalid",
                "X-Hub-Signature-256": "sha256=invalid",
            },
        )
        accepted = client.post(
            "/api/github/webhook",
            content=body,
            headers={
                "X-GitHub-Event": "ping",
                "X-GitHub-Delivery": "delivery-valid",
                "X-Hub-Signature-256": signature,
            },
        )
        replay = client.post(
            "/api/github/webhook",
            content=body,
            headers={
                "X-GitHub-Event": "ping",
                "X-GitHub-Delivery": "delivery-valid",
                "X-Hub-Signature-256": signature,
            },
        )

    assert rejected.status_code == 401
    assert accepted.status_code == 200
    assert accepted.json() == {"accepted": True, "duplicate": False}
    assert replay.status_code == 200
    assert replay.json() == {"accepted": True, "duplicate": True}


def test_expired_installation_token_is_rejected_without_exposing_token(
    monkeypatch,
):
    token_value = "expired-installation-secret"
    monkeypatch.setattr(
        github_app,
        "_require_configured",
        lambda: None,
    )
    monkeypatch.setattr(
        github_app,
        "_api_request",
        lambda *_args, **_kwargs: {
            "token": token_value,
            "expires_at": "2000-01-01T00:00:00Z",
        },
    )

    with pytest.raises(github_app.GitHubAppUpstreamError) as error:
        github_app.create_installation_access_token(123)

    assert token_value not in str(error.value)


def test_pull_request_automation_is_opt_in_and_workspace_scoped(database_session):
    principal, workspace = _create_principal(
        database_session, "PR Owner", "pr-owner"
    )
    _installation, repository = _create_installation_and_repository(
        database_session,
        principal,
        workspace,
        installation_id=8301,
        repository_id=9301,
    )
    assert repository.pr_automation_enabled is False

    repository = github_app_service.set_pull_request_automation(
        database_session,
        principal,
        repository.github_repository_id,
        True,
    )
    database_session.refresh(repository)
    assert repository.pr_automation_enabled is True

    other_principal, _other_workspace = _create_principal(
        database_session, "Other User", "pr-other"
    )
    with pytest.raises(github_app_service.GitHubAppRepositoryDeniedError):
        github_app_service.set_pull_request_automation(
            database_session,
            other_principal,
            repository.github_repository_id,
            False,
        )


def test_pull_request_webhook_fetches_current_metadata_and_deduplicates_head(
    database_session,
    monkeypatch,
):
    principal, workspace = _create_principal(
        database_session, "Webhook Owner", "webhook-owner"
    )
    installation, repository = _create_installation_and_repository(
        database_session,
        principal,
        workspace,
        installation_id=8302,
        repository_id=9302,
    )
    repository.pr_automation_enabled = True
    database_session.commit()

    base_sha = "a" * 40
    head_sha = "b" * 40
    current_pr = {
        "state": "open",
        "draft": False,
        "number": 17,
        "base": {"sha": base_sha},
        "head": {"sha": head_sha},
    }
    monkeypatch.setattr(
        github_app_service,
        "get_settings",
        lambda: SimpleNamespace(github_app_id="123"),
    )
    monkeypatch.setattr(
        github_app,
        "create_installation_access_token",
        lambda *_args, **_kwargs: InstallationAccessToken(
            value="installation-token",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        ),
    )
    monkeypatch.setattr(
        github_app,
        "get_pull_request",
        lambda *_args, **_kwargs: current_pr,
    )
    dispatched = []
    monkeypatch.setattr(
        __import__("app.tasks.analysis_jobs", fromlist=["dispatch_analysis_job"]),
        "dispatch_analysis_job",
        lambda analysis_id: dispatched.append(analysis_id),
    )
    payload = {
        "action": "synchronize",
        "installation": {"id": installation.installation_id, "app_id": 123},
        "repository": {"id": repository.github_repository_id},
        "pull_request": {"number": 17},
    }

    first = github_app_service.process_webhook(
        database_session,
        delivery_id="pr-delivery-1",
        event_name="pull_request",
        payload=payload,
    )
    second = github_app_service.process_webhook(
        database_session,
        delivery_id="pr-delivery-1",
        event_name="pull_request",
        payload=payload,
    )
    assert first is True
    assert second is False
    assert len(dispatched) == 1
    assert database_session.query(PullRequestAutomationResult).count() == 1

    current_pr["base"] = {"sha": "c" * 40}
    third = github_app_service.process_webhook(
        database_session,
        delivery_id="pr-delivery-2",
        event_name="pull_request",
        payload=payload,
    )
    assert third is True
    assert len(dispatched) == 2
    assert database_session.query(PullRequestAutomationResult).count() == 2


def test_check_run_updates_idempotently_and_bounds_summary(monkeypatch):
    calls = []

    def fake_request(method, path, **kwargs):
        calls.append((method, path, kwargs["json_body"]))
        return {"id": 456}

    monkeypatch.setattr(github_app, "_api_request", fake_request)
    result = github_app.create_or_update_check_run(
        "owner",
        "repo",
        access_token="test-token",
        head_sha="a" * 40,
        conclusion="success",
        title="DocGuard review complete",
        summary="x" * 5000,
        check_run_id=456,
    )

    assert result["id"] == 456
    assert calls[0][0] == "PATCH"
    assert calls[0][1].endswith("/check-runs/456")
    assert len(calls[0][2]["output"]["summary"]) == 4000
