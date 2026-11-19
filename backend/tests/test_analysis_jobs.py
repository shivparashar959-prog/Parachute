"""Durable job lifecycle, authorization, idempotency, and retry tests."""

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi.testclient import TestClient
import pytest
from kombu.exceptions import OperationalError
from sqlalchemy import select

from app.api import analyses as analyses_api
from app.auth.dependencies import AuthenticatedPrincipal, get_current_principal
from app.config import ConfigurationError, get_settings
from app.db.session import _session_factory
from app.main import app
from app.models import (
    AnalysisFinding,
    AnalysisRecord,
    AuthorizedRepository,
    AuthSession,
    GeminiSpendReservation,
    GitHubAppInstallation,
    User,
    Workspace,
    WorkspaceMembership,
)
from app.services import analysis_service
from app.services.github_app_service import RepositoryAccess
from app.services.github_service import RepositoryNetworkError
from app.services.github_app_service import GitHubAppRepositoryDeniedError
from app.tasks import analysis_jobs

client = TestClient(app)
TRUSTED_ORIGIN = {"Origin": "http://localhost:5173"}


def _authorized_repository(db, principal, repository_id: int) -> None:
    workspace = db.scalar(
        select(Workspace).where(
            Workspace.personal_owner_user_id == principal.user.id
        )
    )
    db.add(
        GitHubAppInstallation(
            installation_id=repository_id,
            workspace_id=workspace.id,
            installed_by_user_id=principal.user.id,
            account_id=repository_id,
            account_login="job-owner",
            account_type="User",
            repository_selection="selected",
            status="active",
        )
    )
    db.flush()
    db.add(
        AuthorizedRepository(
            github_repository_id=repository_id,
            installation_id=repository_id,
            workspace_id=workspace.id,
            owner_login="job-owner",
            name="job-repo",
            full_name="job-owner/job-repo",
            html_url="https://github.com/job-owner/job-repo",
            visibility="private",
            default_branch="main",
            is_active=True,
        )
    )
    db.commit()


def _repository_access(repository_id: int) -> RepositoryAccess:
    return RepositoryAccess(
        github_repository_id=repository_id,
        installation_id=repository_id,
        owner_login="job-owner",
        name="job-repo",
        full_name="job-owner/job-repo",
        html_url="https://github.com/job-owner/job-repo",
        visibility="private",
        default_branch="main",
        installation_token="test-only-token",
    )


def _principal():
    return app.dependency_overrides[get_current_principal]()


def _queued_record(db, principal, repository_id: int) -> AnalysisRecord:
    _authorized_repository(db, principal, repository_id)
    record, created = analysis_service.create_queued_analysis(
        db, principal, repository_id, "a" * 40, "b" * 40
    )
    assert created is True
    return record


def test_analysis_create_is_202_idempotent_and_dispatches_only_id(
    database_session, monkeypatch
):
    principal = _principal()
    repository_id = 765432101
    _authorized_repository(database_session, principal, repository_id)
    dispatched = []
    monkeypatch.setattr(
        analyses_api,
        "resolve_repository_access",
        lambda _db, _principal, repo_id: _repository_access(repo_id),
    )
    monkeypatch.setattr(
        analyses_api,
        "dispatch_analysis_job",
        lambda analysis_id: dispatched.append(str(analysis_id)) or True,
    )
    payload = {
        "github_repository_id": repository_id,
        "base_commit": "a" * 40,
        "head_commit": "b" * 40,
    }
    headers = {
        **TRUSTED_ORIGIN,
        "Idempotency-Key": "analysis-create-test-key-01",
    }

    first = client.post("/api/analyses", json=payload, headers=headers)
    second = client.post("/api/analyses", json=payload, headers=headers)

    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["analysis_id"] == second.json()["analysis_id"]
    assert first.json()["status"] == "queued"
    assert dispatched == [first.json()["analysis_id"]] * 2
    workspace = database_session.scalar(
        select(Workspace).where(
            Workspace.personal_owner_user_id == principal.user.id
        )
    )
    assert (
        database_session.query(AnalysisRecord)
        .filter_by(workspace_id=workspace.id)
        .count()
        == 1
    )

    changed = {**payload, "head_commit": "c" * 40}
    conflict = client.post("/api/analyses", json=changed, headers=headers)
    assert conflict.status_code == 409


def test_job_status_cancel_and_workspace_idor_denial(database_session):
    principal = _principal()
    record = _queued_record(database_session, principal, 765432102)

    status_response = client.get(
        f"/api/analyses/{record.id}/status"
    )
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "queued"

    cancelled = client.post(
        f"/api/analyses/{record.id}/cancel",
        headers=TRUSTED_ORIGIN,
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert analysis_service.claim_queued_analysis(
        database_session, record.id
    ) is None

    other_user = User(id=uuid.uuid4(), display_name="Other", email=None)
    other_workspace = Workspace(
        id=uuid.uuid4(),
        name="Other workspace",
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
            token_hash="e" * 64,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        ),
    )
    app.dependency_overrides[get_current_principal] = lambda: other_principal
    try:
        denied = client.get(f"/api/analyses/{record.id}/status")
        assert denied.status_code == 404
    finally:
        app.dependency_overrides[get_current_principal] = lambda: principal


def test_duplicate_delivery_claims_analysis_once(database_session):
    principal = _principal()
    record = _queued_record(database_session, principal, 765432103)

    first_claim = analysis_service.claim_queued_analysis(database_session, record.id)
    second_claim = analysis_service.claim_queued_analysis(database_session, record.id)

    assert first_claim is not None
    assert first_claim.status == "running"
    assert first_claim.attempt_count == 1
    assert second_claim is None


def test_retry_is_bounded_and_uses_exponential_backoff(
    database_session, monkeypatch, tmp_path
):
    principal = _principal()
    record = _queued_record(database_session, principal, 765432104)
    monkeypatch.setenv("ANALYSIS_RETRY_MAX_ATTEMPTS", "2")
    get_settings.cache_clear()
    monkeypatch.setattr(
        analysis_jobs,
        "resolve_repository_access_for_analysis",
        lambda _db, **kwargs: _repository_access(kwargs["github_repository_id"]),
    )

    def fail_with_network_error(**_kwargs):
        raise RepositoryNetworkError("test network failure")

    monkeypatch.setattr(
        analysis_jobs, "analyze_repository_drift", fail_with_network_error
    )
    monkeypatch.setenv("DOCGUARD_SCRATCH_ROOT", str(tmp_path / "scratch"))
    try:
        first = analysis_jobs._execute_analysis_job(record.id)
        database_session.refresh(record)
        assert first == ("queued", True, 5)
        assert record.status == "queued"
        assert record.error_category == "repository_unavailable"
        assert record.scratch_cleanup_status == "complete"

        second = analysis_jobs._execute_analysis_job(record.id)
        database_session.refresh(record)
        assert second == ("failed", False, 0)
        assert record.status == "failed"
        assert record.attempt_count == 2
        assert record.error_category == "repository_unavailable"
    finally:
        get_settings.cache_clear()


def test_stale_worker_is_requeued_or_failed_after_attempt_limit(
    database_session, monkeypatch
):
    principal = _principal()
    record = _queued_record(database_session, principal, 765432105)
    record.status = "running"
    record.attempt_count = 1
    record.started_at = datetime.now(timezone.utc) - timedelta(hours=1)
    record.last_heartbeat_at = record.started_at
    database_session.commit()

    monkeypatch.setenv("ANALYSIS_RETRY_MAX_ATTEMPTS", "2")
    get_settings.cache_clear()
    try:
        recovered = analysis_service.recover_stale_analyses(database_session)
        database_session.refresh(record)
        assert recovered == [record.id]
        assert record.status == "queued"
        assert record.error_category == "worker_lost"

        record.status = "running"
        record.attempt_count = 2
        record.last_heartbeat_at = datetime.now(timezone.utc) - timedelta(hours=1)
        database_session.commit()
        assert analysis_service.recover_stale_analyses(database_session) == []
        database_session.refresh(record)
        assert record.status == "failed"
        assert record.error_category == "worker_lost"
    finally:
        get_settings.cache_clear()


def test_running_worker_observes_cancel_request_and_cleans_scratch(
    database_session, monkeypatch, tmp_path
):
    principal = _principal()
    record = _queued_record(database_session, principal, 765432107)
    monkeypatch.setenv("DOCGUARD_SCRATCH_ROOT", str(tmp_path / "scratch"))
    monkeypatch.setattr(
        analysis_jobs,
        "resolve_repository_access_for_analysis",
        lambda _db, **kwargs: _repository_access(kwargs["github_repository_id"]),
    )

    def request_cancel_then_check(**kwargs):
        response = client.post(
            f"/api/analyses/{record.id}/cancel",
            headers=TRUSTED_ORIGIN,
        )
        assert response.status_code == 200
        assert response.json()["cancellation_requested"] is True
        kwargs["cancellation_check"]()

    monkeypatch.setattr(
        analysis_jobs,
        "analyze_repository_drift",
        request_cancel_then_check,
    )

    result = analysis_jobs._execute_analysis_job(record.id)
    database_session.refresh(record)

    assert result == ("cancelled", False, 0)
    assert record.status == "cancelled"
    assert record.scratch_cleanup_status == "complete"


def test_worker_rechecks_repository_permission_before_analysis(
    database_session, monkeypatch, tmp_path
):
    principal = _principal()
    record = _queued_record(database_session, principal, 765432108)
    monkeypatch.setenv("DOCGUARD_SCRATCH_ROOT", str(tmp_path / "scratch"))
    monkeypatch.setattr(
        analysis_jobs,
        "resolve_repository_access_for_analysis",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            GitHubAppRepositoryDeniedError("revoked")
        ),
    )
    ran_pipeline = False

    def unexpected_pipeline(**_kwargs):
        nonlocal ran_pipeline
        ran_pipeline = True

    monkeypatch.setattr(
        analysis_jobs, "analyze_repository_drift", unexpected_pipeline
    )

    result = analysis_jobs._execute_analysis_job(record.id)
    database_session.refresh(record)

    assert result == ("failed", False, 0)
    assert record.status == "failed"
    assert record.error_category == "repository_access_revoked"
    assert ran_pipeline is False
    assert record.scratch_cleanup_status == "complete"


def test_worker_restart_recovery_cleans_orphan_and_redispatches(
    database_session, monkeypatch, tmp_path
):
    principal = _principal()
    record = _queued_record(database_session, principal, 765432109)
    record.status = "running"
    record.attempt_count = 1
    record.started_at = datetime.now(timezone.utc) - timedelta(hours=1)
    record.last_heartbeat_at = record.started_at
    database_session.commit()
    scratch_root = tmp_path / "scratch"
    orphan = scratch_root / f"analysis-{record.id.hex}-attempt-1"
    orphan.mkdir(parents=True)
    (orphan / "partial-clone").write_text("interrupted", encoding="utf-8")
    monkeypatch.setenv("DOCGUARD_SCRATCH_ROOT", str(scratch_root))
    dispatched = []
    monkeypatch.setattr(
        analysis_jobs.celery_app,
        "send_task",
        lambda name, *, args: dispatched.append((name, args)),
    )

    result = analysis_jobs.maintain_analysis_jobs.run()
    database_session.refresh(record)

    assert result["recovered"] == 1
    assert result["dispatched"] == 1
    assert record.status == "queued"
    assert record.error_category == "worker_lost"
    assert record.scratch_cleanup_status == "complete"
    assert not orphan.exists()
    assert dispatched == [(analysis_jobs.TASK_NAME, [str(record.id)])]


def test_celery_task_timeouts_are_bounded_by_analysis_deadline():
    settings = get_settings()
    assert (
        analysis_jobs.celery_app.conf.task_soft_time_limit
        == settings.analysis_timeout_seconds + 30
    )
    assert (
        analysis_jobs.celery_app.conf.task_time_limit
        == settings.analysis_timeout_seconds + 60
    )


def test_production_requires_authenticated_tls_redis(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "true")
    monkeypatch.setenv("FRONTEND_ORIGIN", "https://app.docguard.example")
    monkeypatch.setenv(
        "GITHUB_OAUTH_REDIRECT_URI",
        "https://api.docguard.example/api/auth/callback",
    )
    monkeypatch.setenv("CELERY_BROKER_URL", "rediss://redis.example:6380/0")
    get_settings.cache_clear()
    try:
        with pytest.raises(ConfigurationError, match="authentication"):
            get_settings()

        monkeypatch.setenv(
            "CELERY_BROKER_URL", "rediss://docguard:placeholder@redis.example:6380/0"
        )
        get_settings.cache_clear()
        assert get_settings().celery_broker_url.startswith("rediss://")
    finally:
        get_settings.cache_clear()


def test_dispatch_payload_contains_only_analysis_id(database_session, monkeypatch):
    principal = _principal()
    record = _queued_record(database_session, principal, 765432106)
    sent = []
    monkeypatch.setattr(
        analysis_jobs.celery_app,
        "send_task",
        lambda name, *, args: sent.append((name, args)),
    )

    assert analysis_jobs.dispatch_analysis_job(record.id) is True
    assert sent == [
        (analysis_jobs.TASK_NAME, [str(record.id)])
    ]


def test_broker_failure_leaves_durable_queued_job_with_safe_category(
    database_session, monkeypatch
):
    principal = _principal()
    record = _queued_record(database_session, principal, 765432110)

    def broker_unavailable(*_args, **_kwargs):
        raise OperationalError("private broker details")

    monkeypatch.setattr(analysis_jobs.celery_app, "send_task", broker_unavailable)

    assert analysis_jobs.dispatch_analysis_job(record.id) is False
    database_session.refresh(record)
    assert record.status == "queued"
    assert record.error_category == "queue_unavailable"
    assert record.last_dispatched_at is not None


def test_history_is_paginated_workspace_scoped_and_hides_revoked_repository(
    database_session, monkeypatch
):
    principal = _principal()
    repository_id = 765432111
    _authorized_repository(database_session, principal, repository_id)
    older, _ = analysis_service.create_queued_analysis(
        database_session, principal, repository_id, "a" * 40, "b" * 40
    )
    newer, _ = analysis_service.create_queued_analysis(
        database_session, principal, repository_id, "c" * 40, "d" * 40
    )
    newer.status = "succeeded"
    newer.created_at = datetime.now(timezone.utc) + timedelta(seconds=1)
    database_session.add(
        AnalysisFinding(
            analysis_id=newer.id,
            finding_id="stored-finding",
            status="CONFIRMED_DRIFT",
            severity="HIGH",
            confidence=0.95,
            evidence={"finding_id": "stored-finding"},
        )
    )
    database_session.commit()
    accesses = []
    monkeypatch.setattr(
        analyses_api,
        "resolve_repository_access",
        lambda _db, _principal, repo_id: (
            accesses.append(repo_id) or _repository_access(repo_id)
        ),
    )

    first_page = client.get("/api/analyses?limit=1&offset=0")
    second_page = client.get("/api/analyses?limit=1&offset=1")

    assert first_page.status_code == 200
    first_data = first_page.json()
    assert first_data["total_count"] == 2
    assert first_data["items"][0]["analysis_id"] == str(newer.id)
    assert first_data["items"][0]["finding_count"] == 1
    assert first_data["items"][0]["repository_accessible"] is True
    assert second_page.json()["items"][0]["analysis_id"] == str(older.id)
    assert accesses == [repository_id, repository_id]

    monkeypatch.setattr(
        analyses_api,
        "resolve_repository_access",
        lambda *_args: (_ for _ in ()).throw(GitHubAppRepositoryDeniedError("revoked")),
    )
    revoked_page = client.get("/api/analyses?limit=1&offset=0").json()
    revoked = revoked_page["items"][0]
    assert revoked["repository_accessible"] is False
    assert revoked["github_repository_id"] is None
    assert revoked["repository_full_name"] is None
    assert revoked["base_commit"] is None
    assert revoked["head_commit"] is None
    assert revoked["finding_count"] == 0


def test_history_does_not_expose_another_workspace_records(
    database_session, monkeypatch
):
    principal = _principal()
    record = _queued_record(database_session, principal, 765432112)
    other_user = User(id=uuid.uuid4(), display_name="Other", email=None)
    other_workspace = Workspace(
        id=uuid.uuid4(),
        name="Other workspace",
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
            token_hash="e" * 64,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        ),
    )
    app.dependency_overrides[get_current_principal] = lambda: other_principal
    monkeypatch.setattr(
        analyses_api,
        "resolve_repository_access",
        lambda *_args: pytest.fail("another workspace's analysis must not be checked"),
    )
    try:
        response = client.get("/api/analyses")
    finally:
        app.dependency_overrides[get_current_principal] = lambda: principal

    assert response.status_code == 200
    assert response.json()["total_count"] == 0
    assert response.json()["items"] == []


def test_retry_creates_new_job_only_for_retryable_terminal_failure(
    database_session, monkeypatch
):
    principal = _principal()
    record = _queued_record(database_session, principal, 765432113)
    record.status = "failed"
    record.error_category = "repository_unavailable"
    record.completed_at = datetime.now(timezone.utc)
    database_session.commit()
    monkeypatch.setattr(
        analyses_api,
        "resolve_repository_access",
        lambda _db, _principal, repo_id: _repository_access(repo_id),
    )
    dispatched = []
    monkeypatch.setattr(
        analyses_api,
        "dispatch_analysis_job",
        lambda analysis_id: dispatched.append(analysis_id) or True,
    )

    missing_origin = client.post(f"/api/analyses/{record.id}/retry")
    assert missing_origin.status_code == 403

    response = client.post(
        f"/api/analyses/{record.id}/retry",
        headers=TRUSTED_ORIGIN,
    )

    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    assert response.json()["analysis_id"] != str(record.id)
    assert dispatched == [uuid.UUID(response.json()["analysis_id"])]

    record.error_category = "resource_limit"
    database_session.commit()
    rejected = client.post(
        f"/api/analyses/{record.id}/retry",
        headers=TRUSTED_ORIGIN,
    )
    assert rejected.status_code == 409


def test_delete_requires_origin_access_and_terminal_state_and_cascades_data(
    database_session, monkeypatch
):
    principal = _principal()
    record = _queued_record(database_session, principal, 765432114)
    analysis_id = record.id
    monkeypatch.setattr(
        analyses_api,
        "resolve_repository_access",
        lambda _db, _principal, repo_id: _repository_access(repo_id),
    )
    active_delete = client.delete(
        f"/api/analyses/{analysis_id}",
        headers=TRUSTED_ORIGIN,
    )
    assert active_delete.status_code == 409

    record.status = "succeeded"
    database_session.add(
        AnalysisFinding(
            analysis_id=analysis_id,
            finding_id="delete-finding",
            status="CONFIRMED_DRIFT",
            severity="HIGH",
            confidence=0.95,
            evidence={"finding_id": "delete-finding"},
        )
    )
    database_session.add(
        GeminiSpendReservation(
            workspace_id=record.workspace_id,
            user_id=record.created_by_user_id,
            analysis_id=analysis_id,
            model_name="test-model",
            reserved_usd="0.000001",
        )
    )
    database_session.commit()

    rejected = client.delete(f"/api/analyses/{analysis_id}")
    assert rejected.status_code == 403
    deleted = client.delete(
        f"/api/analyses/{analysis_id}",
        headers=TRUSTED_ORIGIN,
    )

    assert deleted.status_code == 204
    database_session.expire_all()
    assert database_session.get(AnalysisRecord, analysis_id) is None
    assert (
        database_session.query(AnalysisFinding)
        .filter_by(analysis_id=analysis_id)
        .count()
        == 0
    )
    reservation = database_session.query(GeminiSpendReservation).one()
    assert reservation.analysis_id is None
    assert reservation.reserved_usd == Decimal("0.000001")
