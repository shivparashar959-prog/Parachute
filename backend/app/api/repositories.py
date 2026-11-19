"""
API endpoints for Milestone 2: GitHub Repository Inspection & Commit Comparison.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import github_app
from app.auth.dependencies import AuthenticatedPrincipal, get_current_principal
from app.db.session import get_db
from app.schemas.repository import (
    RepositoryCompareRequest,
    RepositoryCompareResponse,
    RepositoryInspectRequest,
    RepositoryInspectResponse,
)
from app.services.github_service import (
    CommitNotFoundError,
    RepositoryEmptyError,
    RepositoryNetworkError,
    RepositoryResourceLimitError,
    RepositoryNotFoundError,
    RepositoryTimeoutError,
    RepositoryValidationError,
    compare_repository_commits,
    inspect_repository,
)
from app.services.github_app_service import (
    GitHubAppConflictError,
    GitHubAppRepositoryDeniedError,
    GitHubAppWorkspaceError,
    resolve_repository_access,
)

router = APIRouter(
    prefix="/api/repositories",
    tags=["Repositories"],
    dependencies=[Depends(get_current_principal)],
)


def _raise_http_for_repository_error(exc: Exception) -> None:
    """Translate domain repository exceptions into clean FastAPI HTTPExceptions."""
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
            GitHubAppRepositoryDeniedError,
            github_app.GitHubAppAccessError,
        ),
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Authorized GitHub repository is unavailable.",
        ) from exc
    if isinstance(exc, GitHubAppWorkspaceError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Workspace authorization is required.",
        ) from exc
    if isinstance(exc, GitHubAppConflictError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="GitHub resource is already linked to another workspace.",
        ) from exc
    if isinstance(exc, github_app.GitHubAppUpstreamError):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="GitHub could not complete the request.",
        ) from exc
    if isinstance(exc, RepositoryValidationError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    if isinstance(exc, (RepositoryNotFoundError, CommitNotFoundError)):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    if isinstance(exc, RepositoryEmptyError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    if isinstance(exc, RepositoryTimeoutError):
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=str(exc),
        ) from exc
    if isinstance(exc, RepositoryResourceLimitError):
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=str(exc),
        ) from exc
    if isinstance(exc, RepositoryNetworkError):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="An unexpected error occurred while processing the repository request.",
    ) from exc


@router.post(
    "/inspect",
    response_model=RepositoryInspectResponse,
    status_code=status.HTTP_200_OK,
    summary="Inspect an authorized GitHub repository and list recent commits",
)
def inspect_github_repository(
    payload: RepositoryInspectRequest,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> RepositoryInspectResponse:
    """
    Inspect an authorized public or private GitHub repository, retrieve its owner, name,
    default branch, and up to 20 recent commits.
    """
    try:
        access = resolve_repository_access(
            db, principal, payload.github_repository_id
        )
        return inspect_repository(
            access.html_url,
            access_token=access.installation_token,
        )
    except Exception as exc:
        _raise_http_for_repository_error(exc)


@router.post(
    "/compare",
    response_model=RepositoryCompareResponse,
    status_code=status.HTTP_200_OK,
    summary="Compare two commits in an authorized GitHub repository",
)
def compare_github_commits(
    payload: RepositoryCompareRequest,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> RepositoryCompareResponse:
    """
    Compare a base commit and a head commit in an authorized GitHub repository
    and return changed files, additions/deletions, and unified diff patches.
    """
    try:
        access = resolve_repository_access(
            db, principal, payload.github_repository_id
        )
        return compare_repository_commits(
            repository_url=access.html_url,
            base_commit=payload.base_commit,
            head_commit=payload.head_commit,
            access_token=access.installation_token,
        )
    except Exception as exc:
        _raise_http_for_repository_error(exc)
