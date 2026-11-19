"""Shared isolated database and principal fixtures for backend tests."""

import os
import hashlib
import inspect
import re
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

os.environ["APP_ENV"] = "development"
os.environ["DATABASE_URL"] = os.getenv("TEST_POSTGRES_URL", "sqlite://")
os.environ["GITHUB_OAUTH_CLIENT_ID"] = "docguard-test-client"
os.environ["GITHUB_OAUTH_CLIENT_SECRET"] = "test-only-github-oauth-secret"
os.environ["GITHUB_OAUTH_STATE_SECRET"] = (
    "test-only-state-signing-secret-not-a-production-credential"
)
os.environ["GITHUB_OAUTH_REDIRECT_URI"] = (
    "http://localhost:8000/api/auth/callback"
)
os.environ["SESSION_COOKIE_SECURE"] = "false"
os.environ["SESSION_COOKIE_SAMESITE"] = "lax"
os.environ["FRONTEND_ORIGIN"] = "http://localhost:5173"
os.environ["CORS_ALLOWED_ORIGINS"] = ""
os.environ["ALLOWED_ORIGINS"] = ""
os.environ["GEMINI_DAILY_BUDGET_USD"] = "10"
os.environ["GEMINI_USER_DAILY_BUDGET_USD"] = "5"
os.environ["GEMINI_INPUT_USD_PER_MILLION_TOKENS"] = "0.1"
os.environ["GEMINI_OUTPUT_USD_PER_MILLION_TOKENS"] = "0.4"

from app.auth.dependencies import AuthenticatedPrincipal, get_current_principal
from app.api import (
    analyses as analyses_api,
    ai_explanations as ai_explanations_api,
    code_analysis as code_analysis_api,
    documentation as documentation_api,
    drift as drift_api,
    repositories as repositories_api,
)
from app.tasks import analysis_jobs as worker_jobs
from app.config import get_settings
from app.db.base import Base
from app.db.session import _session_factory
from app.main import app
from app.models import (
    AnalysisFinding,
    AnalysisRecord,
    AuthSession,
    AuthorizedRepository,
    GitHubAppInstallation,
    User,
    Workspace,
    WorkspaceMembership,
)
from app.services import github_service
from app.services.github_app_service import RepositoryAccess

get_settings.cache_clear()


@pytest.fixture(autouse=True)
def isolate_database_and_default_principal(request):
    settings = get_settings()
    engine = _session_factory(settings.database_url).kw["bind"]
    is_migration_test = request.node.path.name == "test_db_migrations.py"
    if not is_migration_test:
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)

    user = User(id=uuid.uuid4(), display_name="Test User", email=None)
    if not is_migration_test:
        workspace = Workspace(
            id=uuid.uuid4(),
            name="Test User's workspace",
            workspace_type="personal",
            personal_owner_user_id=user.id,
        )
        db = _session_factory(settings.database_url)()
        db.add_all(
            [
                user,
                workspace,
                WorkspaceMembership(
                    workspace_id=workspace.id,
                    user_id=user.id,
                    role="owner",
                ),
            ]
        )
        db.commit()
        db.close()
    principal = AuthenticatedPrincipal(
        user=user,
        session=AuthSession(
            id=uuid.uuid4(),
            user_id=user.id,
            token_hash="a" * 64,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        ),
    )
    app.dependency_overrides[get_current_principal] = lambda: principal

    yield

    app.dependency_overrides.clear()
    if not is_migration_test:
        Base.metadata.drop_all(engine)


@pytest.fixture(autouse=True)
def legacy_analysis_api_repository_fixture(monkeypatch, request):
    legacy_modules = {
        "test_repositories.py": (
            repositories_api,
            code_analysis_api,
            documentation_api,
            drift_api,
            ai_explanations_api,
        ),
        "test_code_analysis.py": (code_analysis_api,),
        "test_documentation.py": (documentation_api,),
        "test_drift.py": (drift_api, analyses_api, worker_jobs),
        "test_ai_explanations.py": (ai_explanations_api,),
        "test_evaluation.py": (
            repositories_api,
            code_analysis_api,
            documentation_api,
            drift_api,
            analyses_api,
            ai_explanations_api,
            worker_jobs,
        ),
    }
    modules = legacy_modules.get(request.node.path.name)
    if not modules:
        return

    source = inspect.getsource(request.node.function)
    urls = re.findall(r"https://github\.com/[A-Za-z0-9._/-]+", source)
    defaults = {
        "test_repositories.py": "https://github.com/octocat/Sample-Repo",
        "test_code_analysis.py": "https://github.com/octocat/DocGuard-Sample",
        "test_documentation.py": "https://github.com/octocat/DocGuard-Docs",
        "test_drift.py": "https://github.com/octocat/DocGuard-Drift",
        "test_ai_explanations.py": "https://github.com/octocat/DocGuard-AI",
        "test_evaluation.py": "https://github.com/docguard-demo/billing-api",
    }
    urls.append(defaults[request.node.path.name])
    repository_urls = {
        int.from_bytes(hashlib.sha256(url.encode("utf-8")).digest()[:4], "big") or 1: url
        for url in urls
    }
    if request.node.path.name == "test_documentation.py":
        repository_urls[1002713952] = "https://github.com/octocat/NoDocs"
    if request.node.path.name == "test_evaluation.py":
        repository_urls[1] = "https://github.com/docguard-demo/billing-api"

    def fake_repository_access(_db, _principal, github_repository_id):
        repository_url = repository_urls.get(
            github_repository_id, "https://github.com/octocat/Sample-Repo"
        )
        owner, name, canonical_url, _clone_url = (
            github_service.parse_and_validate_github_url(repository_url)
        )
        workspace = _db.scalar(
            select(Workspace).where(
                Workspace.personal_owner_user_id == _principal.user.id
            )
        )
        if workspace is None:
            raise AssertionError("The test principal workspace was not seeded.")
        if _db.get(GitHubAppInstallation, 987654) is None:
            _db.add(
                GitHubAppInstallation(
                    installation_id=987654,
                    workspace_id=workspace.id,
                    installed_by_user_id=_principal.user.id,
                    account_id=987654,
                    account_login=owner,
                    account_type="User",
                    repository_selection="selected",
                    status="active",
                )
            )
            _db.flush()
        if _db.get(AuthorizedRepository, github_repository_id) is None:
            _db.add(
                AuthorizedRepository(
                    github_repository_id=github_repository_id,
                    installation_id=987654,
                    workspace_id=workspace.id,
                    owner_login=owner,
                    name=name,
                    full_name=f"{owner}/{name}",
                    html_url=canonical_url,
                    visibility="public",
                    default_branch="main",
                    is_active=True,
                )
            )
            _db.commit()
        return RepositoryAccess(
            github_repository_id=github_repository_id,
            installation_id=987654,
            owner_login=owner,
            name=name,
            full_name=f"{owner}/{name}",
            html_url=canonical_url,
            visibility="public",
            default_branch="main",
            installation_token="test-only-installation-token",
        )

    if request.node.path.name == "test_ai_explanations.py":
        repository_urls[3380014662] = "https://github.com/octocat/DocGuard-AI"
        module = request.module
        analysis_id = uuid.UUID("11111111-1111-4111-8111-111111111111")
        module.TEST_ANALYSIS_ID = str(analysis_id)
        settings = get_settings()
        db = _session_factory(settings.database_url)()
        user = db.scalar(select(User))
        workspace = db.scalar(
            select(Workspace).where(
                Workspace.personal_owner_user_id == user.id
            )
        )
        fake_repository_access(db, AuthenticatedPrincipal(user, AuthSession(
            id=uuid.uuid4(),
            user_id=user.id,
            token_hash="b" * 64,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )), 3380014662)
        record = AnalysisRecord(
            id=analysis_id,
            workspace_id=workspace.id,
            created_by_user_id=user.id,
            github_repository_id=3380014662,
            base_commit="a" * 40,
            head_commit="b" * 40,
            status="succeeded",
            summary={},
        )
        db.add(record)
        db.flush()
        for finding in (
            module._sample_finding("drift-1"),
            module._sample_finding("drift-2"),
        ):
            db.add(
                AnalysisFinding(
                    analysis_id=analysis_id,
                    finding_id=finding.finding_id,
                    status=finding.status,
                    severity=finding.severity,
                    confidence=finding.confidence,
                    evidence=finding.model_dump(mode="json"),
                )
            )
        db.commit()
        db.close()

    for module in modules:
        if hasattr(module, "resolve_repository_access"):
            monkeypatch.setattr(module, "resolve_repository_access", fake_repository_access)

    if analyses_api in modules:
        monkeypatch.setattr(analyses_api, "dispatch_analysis_job", lambda _analysis_id: True)

    if worker_jobs in modules:
        def fake_worker_repository_access(
            _db, *, workspace_id, user_id, github_repository_id
        ):
            user = _db.get(User, user_id)
            if user is None:
                raise AssertionError("The worker analysis user was not found.")
            worker_principal = AuthenticatedPrincipal(
                user=user,
                session=AuthSession(
                    id=uuid.uuid4(),
                    user_id=user.id,
                    token_hash="f" * 64,
                    expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                ),
            )
            access = fake_repository_access(
                _db, worker_principal, github_repository_id
            )
            if access is None:
                raise AssertionError("The worker repository was not authorized.")
            return access

        monkeypatch.setattr(
            worker_jobs,
            "resolve_repository_access_for_analysis",
            fake_worker_repository_access,
        )


@pytest.fixture
def unauthenticated_client():
    principal_override = app.dependency_overrides.pop(
        get_current_principal, None
    )
    try:
        with TestClient(app) as client:
            yield client
    finally:
        if principal_override is not None:
            app.dependency_overrides[get_current_principal] = principal_override


@pytest.fixture
def real_auth_client(unauthenticated_client):
    return unauthenticated_client


@pytest.fixture
def database_session():
    settings = get_settings()
    factory = _session_factory(settings.database_url)
    db = factory()
    try:
        yield db
    finally:
        db.close()
