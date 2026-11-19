"""Workspace-scoped GitHub App authorization and repository catalog operations."""

import hashlib
import re
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote, urlencode

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.auth import github_app
from app.auth.dependencies import AuthenticatedPrincipal
from app.config import get_settings
from app.models import (
    AuthorizedRepository,
    GitHubAppInstallation,
    GitHubAppState,
    GitHubWebhookDelivery,
    UserIdentity,
    Workspace,
    WorkspaceMembership,
)

GITHUB_ISSUER = "https://github.com"
STATE_TTL_SECONDS = 600
FULL_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")


class GitHubAppWorkspaceError(RuntimeError):
    pass


class GitHubAppConflictError(RuntimeError):
    pass


class GitHubAppStateError(RuntimeError):
    pass


class GitHubAppRepositoryDeniedError(RuntimeError):
    pass


@dataclass(frozen=True)
class RepositoryAccess:
    github_repository_id: int
    installation_id: int
    owner_login: str
    name: str
    full_name: str
    html_url: str
    visibility: str
    default_branch: str | None
    installation_token: str = field(repr=False)


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _hash_state(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def get_personal_workspace(
    db: Session,
    principal: AuthenticatedPrincipal,
) -> Workspace:
    workspace = db.scalar(
        select(Workspace).where(
            Workspace.personal_owner_user_id == principal.user.id,
            Workspace.workspace_type == "personal",
        )
    )
    if workspace is None:
        raise GitHubAppWorkspaceError("The user's workspace is unavailable.")
    membership = db.get(
        WorkspaceMembership,
        {"workspace_id": workspace.id, "user_id": principal.user.id},
    )
    if membership is None or membership.role not in {"owner", "admin", "member"}:
        raise GitHubAppWorkspaceError("The user is not authorized for this workspace.")
    return workspace


def _insert_state(
    db: Session,
    *,
    principal: AuthenticatedPrincipal,
    workspace: Workspace,
    purpose: str,
    installation_id: int | None = None,
) -> str:
    now = datetime.now(timezone.utc)
    db.execute(delete(GitHubAppState).where(GitHubAppState.expires_at <= now))
    raw_state = secrets.token_urlsafe(32)
    db.add(
        GitHubAppState(
            state_hash=_hash_state(raw_state),
            purpose=purpose,
            user_id=principal.user.id,
            workspace_id=workspace.id,
            installation_id=installation_id,
            expires_at=now + timedelta(seconds=STATE_TTL_SECONDS),
        )
    )
    db.commit()
    return raw_state


def start_installation(
    db: Session,
    principal: AuthenticatedPrincipal,
) -> str:
    settings = get_settings()
    if not settings.github_app_configured:
        raise github_app.GitHubAppNotConfiguredError(
            "GitHub App integration is not configured."
        )
    workspace = get_personal_workspace(db, principal)
    raw_state = _insert_state(
        db,
        principal=principal,
        workspace=workspace,
        purpose="install",
    )
    return (
        f"https://github.com/apps/{quote(settings.github_app_slug, safe='')}"
        f"/installations/new?{urlencode({'state': raw_state})}"
    )


def consume_state(
    db: Session,
    raw_state: str,
    *,
    principal: AuthenticatedPrincipal,
    purpose: str,
) -> GitHubAppState:
    if not raw_state or len(raw_state) > 256:
        raise GitHubAppStateError("GitHub authorization state is invalid or expired.")
    state = db.scalar(
        select(GitHubAppState)
        .where(GitHubAppState.state_hash == _hash_state(raw_state))
        .with_for_update()
    )
    now = datetime.now(timezone.utc)
    if (
        state is None
        or state.purpose != purpose
        or state.user_id != principal.user.id
        or _utc(state.expires_at) <= now
    ):
        raise GitHubAppStateError("GitHub authorization state is invalid or expired.")
    db.delete(state)
    db.commit()
    return state


def begin_installation_verification(
    db: Session,
    *,
    principal: AuthenticatedPrincipal,
    raw_state: str,
    installation_id: int,
) -> str:
    install_state = consume_state(
        db,
        raw_state,
        principal=principal,
        purpose="install",
    )
    if installation_id <= 0:
        raise GitHubAppStateError("GitHub installation could not be verified.")
    try:
        installation = github_app.verify_installation(installation_id)
    except github_app.GitHubAppAccessError as exc:
        raise GitHubAppStateError(
            "GitHub installation could not be verified."
        ) from exc
    if installation["suspended"]:
        raise GitHubAppRepositoryDeniedError("GitHub installation is suspended.")

    workspace = db.get(Workspace, install_state.workspace_id)
    if workspace is None or workspace.personal_owner_user_id != principal.user.id:
        raise GitHubAppWorkspaceError("The user's workspace is unavailable.")
    verify_state = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    db.execute(delete(GitHubAppState).where(GitHubAppState.expires_at <= now))
    db.add(
        GitHubAppState(
            state_hash=_hash_state(verify_state),
            purpose="verify",
            user_id=principal.user.id,
            workspace_id=workspace.id,
            installation_id=installation_id,
            expires_at=now + timedelta(seconds=STATE_TTL_SECONDS),
        )
    )
    db.commit()
    settings = get_settings()
    query = urlencode(
        {
            "client_id": settings.github_app_client_id,
            "redirect_uri": settings.github_app_user_callback_url,
            "state": verify_state,
            "allow_signup": "false",
        }
    )
    return f"https://github.com/login/oauth/authorize?{query}"


def _metadata_for_repository(
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    try:
        repository_id = int(payload["id"])
        owner = payload["owner"]
        owner_login = owner["login"]
        name = payload["name"]
        visibility = payload.get("visibility")
        if visibility is None:
            visibility = "private" if payload.get("private") is True else "public"
    except (KeyError, TypeError, ValueError):
        return None
    if (
        repository_id <= 0
        or not isinstance(owner_login, str)
        or not owner_login
        or not isinstance(name, str)
        or not name
        or visibility not in {"public", "private"}
    ):
        return None
    full_name = f"{owner_login}/{name}"
    html_url = (
        f"https://github.com/{quote(owner_login, safe='')}/{quote(name, safe='')}"
    )
    default_branch = payload.get("default_branch")
    if not isinstance(default_branch, str):
        default_branch = None
    return {
        "github_repository_id": repository_id,
        "owner_login": owner_login[:255],
        "name": name[:255],
        "full_name": full_name[:511],
        "html_url": html_url,
        "visibility": visibility,
        "default_branch": default_branch[:255] if default_branch else None,
        "is_archived": payload.get("archived") is True,
    }


def _sync_repository_catalog(
    db: Session,
    installation: GitHubAppInstallation,
    token: str,
) -> None:
    repositories = github_app.list_installation_repositories(token)
    synced_ids: set[int] = set()
    for payload in repositories:
        metadata = _metadata_for_repository(payload)
        if metadata is None:
            continue
        repository_id = metadata["github_repository_id"]
        repository = db.get(AuthorizedRepository, repository_id)
        if repository is not None and (
            repository.installation_id != installation.installation_id
            or repository.workspace_id != installation.workspace_id
        ):
            raise GitHubAppConflictError(
                "The GitHub repository is already linked to another workspace."
            )
        if repository is None:
            repository = AuthorizedRepository(
                installation_id=installation.installation_id,
                workspace_id=installation.workspace_id,
                **metadata,
                is_active=True,
            )
            db.add(repository)
        else:
            for key, value in metadata.items():
                setattr(repository, key, value)
            repository.is_active = True
            repository.last_synced_at = datetime.now(timezone.utc)
        synced_ids.add(repository_id)

    existing = db.scalars(
        select(AuthorizedRepository).where(
            AuthorizedRepository.installation_id == installation.installation_id,
            AuthorizedRepository.workspace_id == installation.workspace_id,
        )
    )
    for repository in existing:
        if repository.github_repository_id not in synced_ids:
            repository.is_active = False
    installation.last_synced_at = datetime.now(timezone.utc)


def _deactivate_installation(
    db: Session,
    installation: GitHubAppInstallation,
    status: str,
) -> None:
    installation.status = status
    for repository in installation.repositories:
        repository.is_active = False


def complete_installation_verification(
    db: Session,
    *,
    principal: AuthenticatedPrincipal,
    raw_state: str,
    code: str | None,
) -> GitHubAppInstallation:
    state = consume_state(
        db,
        raw_state,
        principal=principal,
        purpose="verify",
    )
    if code is None:
        raise GitHubAppStateError("GitHub installation verification was not completed.")
    installation_id = state.installation_id
    if installation_id is None:
        raise GitHubAppStateError("GitHub installation could not be verified.")

    user_access_token = github_app.exchange_user_authorization_code(code)
    github_user = github_app.get_authenticated_github_user(user_access_token)
    try:
        github_user_id = str(int(github_user["id"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise GitHubAppStateError("GitHub user could not be verified.") from exc
    identity = db.scalar(
        select(UserIdentity).where(
            UserIdentity.user_id == principal.user.id,
            UserIdentity.issuer == GITHUB_ISSUER,
        )
    )
    if identity is None or identity.subject != github_user_id:
        raise GitHubAppStateError(
            "The authorized GitHub account does not match the signed-in account."
        )

    accessible_installations = github_app.list_user_installations(user_access_token)
    user_installation = next(
        (
            item
            for item in accessible_installations
            if str(item.get("id")) == str(installation_id)
        ),
        None,
    )
    if user_installation is None:
        raise GitHubAppStateError(
            "This GitHub user cannot access the selected installation."
        )
    verified_installation = github_app.verify_installation(installation_id)
    try:
        user_app_id = int(user_installation["app_id"])
    except (KeyError, TypeError, ValueError) as exc:
        raise GitHubAppStateError("GitHub installation could not be verified.") from exc
    account = user_installation.get("account")
    try:
        user_account_id = int(account["id"]) if isinstance(account, dict) else -1
    except (KeyError, TypeError, ValueError):
        user_account_id = -1
    if user_app_id != int(get_settings().github_app_id) or user_account_id != verified_installation[
        "account_id"
    ]:
        raise GitHubAppStateError("GitHub installation could not be verified.")
    if verified_installation["suspended"]:
        raise GitHubAppRepositoryDeniedError("GitHub installation is suspended.")

    workspace = db.get(Workspace, state.workspace_id)
    if workspace is None or workspace.personal_owner_user_id != principal.user.id:
        raise GitHubAppWorkspaceError("The user's workspace is unavailable.")
    installation = db.get(GitHubAppInstallation, installation_id)
    if installation is not None and installation.workspace_id != workspace.id:
        raise GitHubAppConflictError(
            "This GitHub installation is already linked to another workspace."
        )

    if installation is None:
        installation = GitHubAppInstallation(
            installation_id=installation_id,
            workspace_id=workspace.id,
            installed_by_user_id=principal.user.id,
            account_id=verified_installation["account_id"],
            account_login=verified_installation["account_login"],
            account_type=verified_installation["account_type"],
            repository_selection=verified_installation["repository_selection"],
            status="active",
        )
        db.add(installation)
        db.flush()
    else:
        installation.account_id = verified_installation["account_id"]
        installation.account_login = verified_installation["account_login"]
        installation.account_type = verified_installation["account_type"]
        installation.repository_selection = verified_installation[
            "repository_selection"
        ]
        installation.status = "active"

    install_token = github_app.create_installation_access_token(installation_id)
    _sync_repository_catalog(db, installation, install_token.value)
    db.commit()
    return installation


def list_workspace_repositories(
    db: Session,
    principal: AuthenticatedPrincipal,
) -> list[AuthorizedRepository]:
    workspace = get_personal_workspace(db, principal)
    installations = list(
        db.scalars(
            select(GitHubAppInstallation).where(
                GitHubAppInstallation.workspace_id == workspace.id,
                GitHubAppInstallation.status == "active",
            )
        )
    )
    for installation in installations:
        try:
            token = github_app.create_installation_access_token(
                installation.installation_id
            )
            _sync_repository_catalog(db, installation, token.value)
        except github_app.GitHubAppRateLimitError:
            db.rollback()
            raise
        except github_app.GitHubAppAccessError:
            db.rollback()
            installation = db.get(
                GitHubAppInstallation, installation.installation_id
            )
            if installation is not None:
                _deactivate_installation(db, installation, "suspended")
    db.commit()
    return list(
        db.scalars(
            select(AuthorizedRepository)
            .join(
                GitHubAppInstallation,
                AuthorizedRepository.installation_id
                == GitHubAppInstallation.installation_id,
            )
            .where(
                AuthorizedRepository.workspace_id == workspace.id,
                AuthorizedRepository.is_active.is_(True),
                GitHubAppInstallation.status == "active",
            )
            .order_by(AuthorizedRepository.full_name)
        )
    )


def _current_repository_metadata(
    db: Session,
    principal: AuthenticatedPrincipal,
    github_repository_id: int,
) -> tuple[AuthorizedRepository, GitHubAppInstallation]:
    workspace = get_personal_workspace(db, principal)
    repository = db.get(AuthorizedRepository, github_repository_id)
    if repository is None or repository.workspace_id != workspace.id:
        raise GitHubAppRepositoryDeniedError("Repository is not authorized.")
    installation = db.get(
        GitHubAppInstallation, repository.installation_id
    )
    if (
        not repository.is_active
        or installation is None
        or installation.workspace_id != workspace.id
        or installation.status != "active"
    ):
        raise GitHubAppRepositoryDeniedError("Repository is not authorized.")
    return repository, installation


def _resolve_repository_access(
    db: Session,
    repository: AuthorizedRepository,
    installation: GitHubAppInstallation,
) -> RepositoryAccess:
    try:
        token = github_app.create_installation_access_token(
            installation.installation_id,
            repository_ids=[repository.github_repository_id],
        )
        current = github_app.get_repository_by_id(
            repository.github_repository_id,
            token.value,
        )
    except github_app.GitHubAppRateLimitError:
        raise
    except github_app.GitHubAppAccessError as exc:
        repository.is_active = False
        db.commit()
        raise GitHubAppRepositoryDeniedError("Repository is not authorized.") from exc
    if not isinstance(current, dict) or str(current.get("id")) != str(
        repository.github_repository_id
    ):
        repository.is_active = False
        db.commit()
        raise GitHubAppRepositoryDeniedError("Repository is not authorized.")
    metadata = _metadata_for_repository(current)
    if metadata is None:
        repository.is_active = False
        db.commit()
        raise GitHubAppRepositoryDeniedError("Repository is not authorized.")
    for key, value in metadata.items():
        setattr(repository, key, value)
    repository.last_synced_at = datetime.now(timezone.utc)
    db.commit()
    return RepositoryAccess(
        github_repository_id=repository.github_repository_id,
        installation_id=installation.installation_id,
        owner_login=repository.owner_login,
        name=repository.name,
        full_name=repository.full_name,
        html_url=repository.html_url,
        visibility=repository.visibility,
        default_branch=repository.default_branch,
        installation_token=token.value,
    )


def resolve_repository_access(
    db: Session,
    principal: AuthenticatedPrincipal,
    github_repository_id: int,
) -> RepositoryAccess:
    repository, installation = _current_repository_metadata(
        db, principal, github_repository_id
    )
    return _resolve_repository_access(db, repository, installation)


def resolve_repository_access_for_analysis(
    db: Session,
    *,
    workspace_id: Any,
    user_id: Any,
    github_repository_id: int,
) -> RepositoryAccess:
    workspace = db.get(Workspace, workspace_id)
    membership = db.get(
        WorkspaceMembership,
        {"workspace_id": workspace_id, "user_id": user_id},
    )
    if (
        workspace is None
        or membership is None
        or membership.role not in {"owner", "admin", "member"}
    ):
        raise GitHubAppWorkspaceError("Analysis workspace authorization is unavailable.")

    repository = db.get(AuthorizedRepository, github_repository_id)
    if repository is None or repository.workspace_id != workspace_id:
        raise GitHubAppRepositoryDeniedError("Repository is not authorized.")
    installation = db.get(
        GitHubAppInstallation, repository.installation_id
    )
    if (
        not repository.is_active
        or installation is None
        or installation.workspace_id != workspace_id
        or installation.status != "active"
    ):
        raise GitHubAppRepositoryDeniedError("Repository is not authorized.")
    return _resolve_repository_access(db, repository, installation)


def list_repository_pull_requests(
    db: Session,
    principal: AuthenticatedPrincipal,
    github_repository_id: int,
) -> tuple[RepositoryAccess, list[dict[str, Any]]]:
    access = resolve_repository_access(db, principal, github_repository_id)
    pull_requests = github_app.list_open_pull_requests(
        access.owner_login,
        access.name,
        access.installation_token,
    )
    return access, pull_requests


def process_webhook(
    db: Session,
    *,
    delivery_id: str,
    event_name: str,
    payload: dict[str, Any],
) -> bool:
    if db.get(GitHubWebhookDelivery, delivery_id) is not None:
        return False
    installation_payload = payload.get("installation")
    installation_id = None
    if isinstance(installation_payload, dict):
        try:
            installation_id = int(installation_payload.get("id"))
            app_id = int(installation_payload.get("app_id"))
        except (TypeError, ValueError):
            raise GitHubAppStateError("GitHub webhook payload is invalid.")
        if app_id != int(get_settings().github_app_id):
            raise GitHubAppStateError("GitHub webhook app identity is invalid.")

    installation = (
        db.get(GitHubAppInstallation, installation_id)
        if installation_id is not None
        else None
    )
    action = payload.get("action")
    if event_name == "installation" and installation is not None:
        if action == "deleted":
            _deactivate_installation(db, installation, "uninstalled")
        elif action == "suspend":
            _deactivate_installation(db, installation, "suspended")
        elif action == "unsuspend":
            installation.status = "active"
    elif event_name == "installation_repositories" and installation is not None:
        removed = payload.get("repositories_removed", [])
        if not isinstance(removed, list):
            raise GitHubAppStateError("GitHub webhook payload is invalid.")
        removed_ids: set[int] = set()
        for item in removed:
            if isinstance(item, dict):
                try:
                    removed_ids.add(int(item["id"]))
                except (KeyError, TypeError, ValueError):
                    continue
        if removed_ids:
            removed_repositories = db.scalars(
                select(AuthorizedRepository).where(
                    AuthorizedRepository.installation_id == installation_id,
                    AuthorizedRepository.github_repository_id.in_(removed_ids),
                )
            )
            for repository in removed_repositories:
                repository.is_active = False
        added = payload.get("repositories_added", [])
        if added:
            if installation.status == "active":
                token = github_app.create_installation_access_token(
                    installation.installation_id
                )
                _sync_repository_catalog(db, installation, token.value)

    db.add(
        GitHubWebhookDelivery(
            delivery_id=delivery_id,
            event_name=event_name[:64],
        )
    )
    db.commit()
    return True
