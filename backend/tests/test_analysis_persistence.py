"""Workspace isolation tests for persisted deterministic analyses."""

import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select

from app.auth.dependencies import AuthenticatedPrincipal, get_current_principal
from app.main import app
from app.models import (
    AnalysisRecord,
    AuthorizedRepository,
    AuthSession,
    GeminiSpendReservation,
    GitHubAppInstallation,
    User,
    Workspace,
    WorkspaceMembership,
)
from app.config import get_settings
from app.services import analysis_service
from app.services.github_service import _resolve_clone_source


client = TestClient(app)


def test_another_users_analysis_and_findings_are_not_accessible(database_session):
    owner = database_session.scalar(select(User))
    owner_workspace = database_session.scalar(
        select(Workspace).where(Workspace.personal_owner_user_id == owner.id)
    )
    repository_id = 918273645
    database_session.add(
        GitHubAppInstallation(
            installation_id=918273645,
            workspace_id=owner_workspace.id,
            installed_by_user_id=owner.id,
            account_id=918273645,
            account_login="owner",
            account_type="User",
            repository_selection="selected",
            status="active",
        )
    )
    database_session.flush()
    database_session.add(
        AuthorizedRepository(
            github_repository_id=repository_id,
            installation_id=918273645,
            workspace_id=owner_workspace.id,
            owner_login="owner",
            name="private-repo",
            full_name="owner/private-repo",
            html_url="https://github.com/owner/private-repo",
            visibility="private",
            default_branch="main",
            is_active=True,
        )
    )
    analysis_id = uuid.uuid4()
    database_session.add(
        AnalysisRecord(
            id=analysis_id,
            workspace_id=owner_workspace.id,
            created_by_user_id=owner.id,
            github_repository_id=repository_id,
            base_commit="a" * 40,
            head_commit="b" * 40,
            status="succeeded",
            summary={},
        )
    )

    other_user = User(id=uuid.uuid4(), display_name="Other User", email=None)
    other_workspace = Workspace(
        id=uuid.uuid4(),
        name="Other User's workspace",
        workspace_type="personal",
        personal_owner_user_id=other_user.id,
    )
    database_session.add_all(
        [
            other_user,
            other_workspace,
            WorkspaceMembership(
                workspace_id=other_workspace.id,
                user_id=other_user.id,
                role="owner",
            ),
        ]
    )
    database_session.commit()
    other_principal = AuthenticatedPrincipal(
        user=other_user,
        session=AuthSession(
            id=uuid.uuid4(),
            user_id=other_user.id,
            token_hash="c" * 64,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        ),
    )
    app.dependency_overrides[get_current_principal] = lambda: other_principal
    try:
        detail = client.get(f"/api/analyses/{analysis_id}")
        assert detail.status_code == 404
        explanation = client.post(
            "/api/analyze/explanations",
            json={
                "analysis_id": str(analysis_id),
                "provider": "mock",
                "finding_ids": ["private-finding"],
            },
        )
        assert explanation.status_code == 404
    finally:
        app.dependency_overrides.pop(get_current_principal, None)


def test_analysis_creation_obeys_user_hour_limit(database_session, monkeypatch):
    user = database_session.scalar(select(User))
    workspace = database_session.scalar(
        select(Workspace).where(Workspace.personal_owner_user_id == user.id)
    )
    repository_id = 918273646
    database_session.add(
        GitHubAppInstallation(
            installation_id=918273646,
            workspace_id=workspace.id,
            installed_by_user_id=user.id,
            account_id=918273646,
            account_login="owner",
            account_type="User",
            repository_selection="selected",
            status="active",
        )
    )
    database_session.flush()
    database_session.add(
        AuthorizedRepository(
            github_repository_id=repository_id,
            installation_id=918273646,
            workspace_id=workspace.id,
            owner_login="owner",
            name="quota-repo",
            full_name="owner/quota-repo",
            html_url="https://github.com/owner/quota-repo",
            visibility="public",
            default_branch="main",
            is_active=True,
        )
    )
    database_session.commit()
    principal = AuthenticatedPrincipal(
        user=user,
        session=AuthSession(
            id=uuid.uuid4(),
            user_id=user.id,
            token_hash="d" * 64,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        ),
    )
    monkeypatch.setenv("ANALYSIS_PER_USER_HOUR_LIMIT", "1")
    get_settings.cache_clear()
    try:
        analysis_service.create_running_analysis(
            database_session, principal, repository_id, "a" * 40, "b" * 40
        )
        with pytest.raises(analysis_service.AnalysisQuotaExceededError):
            analysis_service.create_running_analysis(
                database_session, principal, repository_id, "c" * 40, "d" * 40
            )
    finally:
        get_settings.cache_clear()


def test_gemini_spend_reservation_fails_closed_at_user_budget(
    database_session, monkeypatch
):
    user = database_session.scalar(select(User))
    workspace = database_session.scalar(
        select(Workspace).where(Workspace.personal_owner_user_id == user.id)
    )
    repository_id = 918273647
    database_session.add(
        GitHubAppInstallation(
            installation_id=918273647,
            workspace_id=workspace.id,
            installed_by_user_id=user.id,
            account_id=918273647,
            account_login="owner",
            account_type="User",
            repository_selection="selected",
            status="active",
        )
    )
    database_session.flush()
    database_session.add(
        AuthorizedRepository(
            github_repository_id=repository_id,
            installation_id=918273647,
            workspace_id=workspace.id,
            owner_login="owner",
            name="budget-repo",
            full_name="owner/budget-repo",
            html_url="https://github.com/owner/budget-repo",
            visibility="private",
            default_branch="main",
            is_active=True,
        )
    )
    analysis = AnalysisRecord(
        workspace_id=workspace.id,
        created_by_user_id=user.id,
        github_repository_id=repository_id,
        base_commit="a" * 40,
        head_commit="b" * 40,
        status="succeeded",
        summary={},
    )
    database_session.add(analysis)
    database_session.commit()
    principal = AuthenticatedPrincipal(
        user=user,
        session=AuthSession(
            id=uuid.uuid4(),
            user_id=user.id,
            token_hash="e" * 64,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        ),
    )
    monkeypatch.setenv("GEMINI_DAILY_BUDGET_USD", "0.00001")
    monkeypatch.setenv("GEMINI_USER_DAILY_BUDGET_USD", "0.00001")
    monkeypatch.setenv("GEMINI_INPUT_USD_PER_MILLION_TOKENS", "1")
    monkeypatch.setenv("GEMINI_OUTPUT_USD_PER_MILLION_TOKENS", "1")
    get_settings.cache_clear()
    try:
        with pytest.raises(analysis_service.AnalysisQuotaExceededError):
            analysis_service.reserve_gemini_spend(
                database_session, principal, analysis, "gemini-test", "x"
            )
        assert database_session.query(GeminiSpendReservation).count() == 0
    finally:
        get_settings.cache_clear()


def test_demo_repository_interception_is_disabled_in_production(monkeypatch):
    repository_url = "https://github.com/docguard-demo/billing-api.git"
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "true")
    monkeypatch.setenv("FRONTEND_ORIGIN", "https://docguard.example")
    monkeypatch.setenv(
        "GITHUB_OAUTH_REDIRECT_URI",
        "https://api.docguard.example/api/auth/callback",
    )
    monkeypatch.setenv(
        "CELERY_BROKER_URL",
        "rediss://docguard:placeholder@redis.docguard.example:6380/0",
    )
    get_settings.cache_clear()
    try:
        assert _resolve_clone_source(repository_url) == repository_url
    finally:
        get_settings.cache_clear()
