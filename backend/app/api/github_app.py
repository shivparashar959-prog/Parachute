"""GitHub App installation, repository catalog, and signed webhook endpoints."""

import hashlib
import hmac
import json
import re
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Path,
    Query,
    Request,
    status,
)
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import github_app
from app.auth.csrf import require_trusted_origin
from app.auth.dependencies import AuthenticatedPrincipal, get_current_principal
from app.config import get_settings
from app.db.session import get_db
from app.models import AuthorizedRepository, GitHubAppInstallation
from app.schemas.github_app import (
    AuthorizedRepositoryListResponse,
    GitHubAppStatusDetailResponse,
    GitHubAppStatusResponse,
    GitHubWebhookAcceptedResponse,
    InstallationStartResponse,
    PullRequestListResponse,
    PullRequestSummary,
    PullRequestAutomationResponse,
    PullRequestAutomationUpdate,
)
from app.services import github_app_service

router = APIRouter(prefix="/api/github", tags=["GitHub App"])
MAX_WEBHOOK_BODY_BYTES = 1_000_000
FULL_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")


def _raise_http_for_github_app_error(exc: Exception) -> None:
    if isinstance(exc, github_app.GitHubAppNotConfiguredError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GitHub App integration is not configured.",
        ) from exc
    if isinstance(exc, github_app.GitHubAppRateLimitError):
        headers = (
            {"Retry-After": str(exc.retry_after)} if exc.retry_after else None
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="GitHub API rate limit reached. Retry later.",
            headers=headers,
        ) from exc
    if isinstance(
        exc,
        (
            github_app.GitHubAppAccessError,
            github_app_service.GitHubAppRepositoryDeniedError,
        ),
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Authorized GitHub resource is unavailable.",
        ) from exc
    if isinstance(exc, github_app_service.GitHubAppStateError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    if isinstance(exc, github_app_service.GitHubAppWorkspaceError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Workspace authorization is required.",
        ) from exc
    if isinstance(exc, github_app_service.GitHubAppConflictError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="GitHub resource is already linked to another workspace.",
        ) from exc
    if isinstance(exc, github_app.GitHubAppUpstreamError):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="GitHub could not complete the request.",
        ) from exc
    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail="GitHub could not complete the request.",
    ) from exc


@router.get(
    "/status",
    response_model=GitHubAppStatusDetailResponse,
)
def read_github_app_status(
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> GitHubAppStatusDetailResponse:
    settings = get_settings()
    try:
        workspace = github_app_service.get_personal_workspace(db, principal)
    except github_app_service.GitHubAppWorkspaceError as exc:
        _raise_http_for_github_app_error(exc)
    installations = list(
        db.scalars(
            select(GitHubAppInstallation)
            .where(GitHubAppInstallation.workspace_id == workspace.id)
            .order_by(GitHubAppInstallation.account_login)
        )
    )
    return GitHubAppStatusDetailResponse(
        configured=settings.github_app_configured,
        connected=any(item.status == "active" for item in installations),
        installation_count=len(
            [item for item in installations if item.status == "active"]
        ),
        installations=installations,
    )


@router.post(
    "/installations/start",
    response_model=InstallationStartResponse,
)
def start_github_app_installation(
    request: Request,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> InstallationStartResponse:
    require_trusted_origin(request)
    try:
        install_url = github_app_service.start_installation(db, principal)
    except github_app.GitHubAppError as exc:
        _raise_http_for_github_app_error(exc)
    except github_app_service.GitHubAppWorkspaceError as exc:
        _raise_http_for_github_app_error(exc)
    return InstallationStartResponse(installation_url=install_url)


@router.get("/installations/callback")
def complete_github_app_installation(
    installation_id: Annotated[int, Query(gt=0)],
    state: Annotated[str, Query(min_length=32, max_length=256)],
    setup_action: Annotated[str, Query(min_length=1, max_length=32)],
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    if setup_action not in {"install", "update"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GitHub installation setup was not completed.",
        )
    try:
        authorization_url = github_app_service.begin_installation_verification(
            db,
            principal=principal,
            raw_state=state,
            installation_id=installation_id,
        )
    except (
        github_app.GitHubAppError,
        github_app_service.GitHubAppStateError,
        github_app_service.GitHubAppWorkspaceError,
        github_app_service.GitHubAppRepositoryDeniedError,
    ) as exc:
        _raise_http_for_github_app_error(exc)
    return RedirectResponse(
        authorization_url,
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/user-callback")
def complete_github_app_user_authorization(
    state: Annotated[str, Query(min_length=32, max_length=256)],
    code: Annotated[str | None, Query(max_length=2048)] = None,
    error: Annotated[str | None, Query(max_length=128)] = None,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    if error:
        try:
            github_app_service.consume_state(
                db,
                state,
                principal=principal,
                purpose="verify",
            )
        except github_app_service.GitHubAppStateError as exc:
            _raise_http_for_github_app_error(exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GitHub installation verification was not completed.",
        )
    try:
        github_app_service.complete_installation_verification(
            db,
            principal=principal,
            raw_state=state,
            code=code,
        )
    except (
        github_app.GitHubAppError,
        github_app_service.GitHubAppStateError,
        github_app_service.GitHubAppWorkspaceError,
        github_app_service.GitHubAppConflictError,
        github_app_service.GitHubAppRepositoryDeniedError,
    ) as exc:
        _raise_http_for_github_app_error(exc)
    return RedirectResponse(
        f"{get_settings().frontend_origin}/?github_app=connected",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/repositories", response_model=AuthorizedRepositoryListResponse)
def list_authorized_repositories(
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> AuthorizedRepositoryListResponse:
    try:
        repositories = github_app_service.list_workspace_repositories(db, principal)
    except (
        github_app.GitHubAppError,
        github_app_service.GitHubAppWorkspaceError,
        github_app_service.GitHubAppConflictError,
    ) as exc:
        _raise_http_for_github_app_error(exc)
    return AuthorizedRepositoryListResponse(repositories=repositories)


@router.get(
    "/repositories/{github_repository_id}/pull-request-automation",
    response_model=PullRequestAutomationResponse,
)
def read_pull_request_automation(
    github_repository_id: Annotated[int, Path(gt=0)],
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> PullRequestAutomationResponse:
    workspace = github_app_service.get_personal_workspace(db, principal)
    repository = db.scalar(
        select(AuthorizedRepository).where(
            AuthorizedRepository.github_repository_id == github_repository_id,
            AuthorizedRepository.workspace_id == workspace.id,
            AuthorizedRepository.is_active.is_(True),
        )
    )
    if repository is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Authorized GitHub resource is unavailable.",
        )
    return PullRequestAutomationResponse(
        github_repository_id=repository.github_repository_id,
        enabled=repository.pr_automation_enabled,
    )


@router.patch(
    "/repositories/{github_repository_id}/pull-request-automation",
    response_model=PullRequestAutomationResponse,
)
def update_pull_request_automation(
    github_repository_id: Annotated[int, Path(gt=0)],
    update: PullRequestAutomationUpdate,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> PullRequestAutomationResponse:
    require_trusted_origin(request)
    try:
        repository = github_app_service.set_pull_request_automation(
            db,
            principal,
            github_repository_id,
            update.enabled,
        )
    except (
        github_app_service.GitHubAppWorkspaceError,
        github_app_service.GitHubAppRepositoryDeniedError,
    ) as exc:
        _raise_http_for_github_app_error(exc)
    return PullRequestAutomationResponse(
        github_repository_id=repository.github_repository_id,
        enabled=repository.pr_automation_enabled,
    )


@router.get(
    "/repositories/{github_repository_id}/pull-requests",
    response_model=PullRequestListResponse,
)
def list_authorized_repository_pull_requests(
    github_repository_id: Annotated[int, Path(gt=0)],
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> PullRequestListResponse:
    try:
        access, raw_pull_requests = github_app_service.list_repository_pull_requests(
            db,
            principal,
            github_repository_id,
        )
    except (
        github_app.GitHubAppError,
        github_app_service.GitHubAppWorkspaceError,
        github_app_service.GitHubAppConflictError,
        github_app_service.GitHubAppRepositoryDeniedError,
    ) as exc:
        _raise_http_for_github_app_error(exc)

    pull_requests: list[PullRequestSummary] = []
    for item in raw_pull_requests:
        try:
            number = int(item["number"])
            title = item["title"]
            state = item["state"]
            html_url = item["html_url"]
            author = item["user"]["login"]
            base = item["base"]
            head = item["head"]
            base_ref = base["ref"]
            base_sha = base["sha"]
            head_ref = head["ref"]
            head_sha = head["sha"]
        except (KeyError, TypeError, ValueError):
            continue
        if (
            number <= 0
            or not isinstance(title, str)
            or not isinstance(state, str)
            or state != "open"
            or not isinstance(html_url, str)
            or not html_url.startswith("https://github.com/")
            or not isinstance(author, str)
            or not isinstance(base_ref, str)
            or not isinstance(head_ref, str)
            or not isinstance(base_sha, str)
            or not FULL_SHA_PATTERN.fullmatch(base_sha)
            or not isinstance(head_sha, str)
            or not FULL_SHA_PATTERN.fullmatch(head_sha)
        ):
            continue
        pull_requests.append(
            PullRequestSummary(
                number=number,
                title=title[:500],
                state=state,
                html_url=html_url,
                author=author[:255],
                base_ref=base_ref[:255],
                base_sha=base_sha,
                head_ref=head_ref[:255],
                head_sha=head_sha,
            )
        )
    return PullRequestListResponse(
        github_repository_id=access.github_repository_id,
        pull_requests=pull_requests,
    )


@router.post(
    "/webhook",
    response_model=GitHubWebhookAcceptedResponse,
)
async def receive_github_webhook(
    request: Request,
    x_hub_signature_256: Annotated[str | None, Header()] = None,
    x_github_event: Annotated[str | None, Header()] = None,
    x_github_delivery: Annotated[str | None, Header()] = None,
    db: Session = Depends(get_db),
) -> GitHubWebhookAcceptedResponse:
    settings = get_settings()
    if not settings.github_app_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GitHub App integration is not configured.",
        )
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_WEBHOOK_BODY_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail="Webhook payload is too large.",
                )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Webhook request is invalid.",
            ) from exc
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > MAX_WEBHOOK_BODY_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Webhook payload is too large.",
            )
    expected_signature = "sha256=" + hmac.new(
        settings.github_app_webhook_secret.encode("utf-8"),
        bytes(body),
        hashlib.sha256,
    ).hexdigest()
    if not x_hub_signature_256 or not hmac.compare_digest(
        expected_signature, x_hub_signature_256
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Webhook signature is invalid.",
        )
    if (
        not x_github_event
        or len(x_github_event) > 64
        or not x_github_delivery
        or len(x_github_delivery) > 128
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Webhook request is invalid.",
        )
    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Webhook request is invalid.",
        ) from exc
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Webhook request is invalid.",
        )
    try:
        accepted = github_app_service.process_webhook(
            db,
            delivery_id=x_github_delivery,
            event_name=x_github_event,
            payload=payload,
        )
    except (
        github_app.GitHubAppError,
        github_app_service.GitHubAppStateError,
        github_app_service.GitHubAppConflictError,
    ) as exc:
        _raise_http_for_github_app_error(exc)
    return GitHubWebhookAcceptedResponse(accepted=True, duplicate=not accepted)
