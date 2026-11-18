"""
API endpoints for Milestone 2: GitHub Repository Inspection & Commit Comparison.
"""

from fastapi import APIRouter, HTTPException, status

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
    RepositoryNotFoundError,
    RepositoryValidationError,
    compare_repository_commits,
    inspect_repository,
)

router = APIRouter(prefix="/api/repositories", tags=["Repositories"])


def _raise_http_for_repository_error(exc: Exception) -> None:
    """Translate domain repository exceptions into clean FastAPI HTTPExceptions."""
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
    summary="Inspect a public GitHub repository and list recent commits",
)
def inspect_github_repository(
    payload: RepositoryInspectRequest,
) -> RepositoryInspectResponse:
    """
    Connect to a public HTTPS GitHub repository, retrieve its owner, name,
    default branch, and up to 20 recent commits.
    """
    try:
        return inspect_repository(payload.repository_url)
    except Exception as exc:
        _raise_http_for_repository_error(exc)


@router.post(
    "/compare",
    response_model=RepositoryCompareResponse,
    status_code=status.HTTP_200_OK,
    summary="Compare two commits in a public GitHub repository",
)
def compare_github_commits(
    payload: RepositoryCompareRequest,
) -> RepositoryCompareResponse:
    """
    Compare a base commit and a head commit in a public HTTPS GitHub repository
    and return changed files, additions/deletions, and unified diff patches.
    """
    try:
        return compare_repository_commits(
            repository_url=payload.repository_url,
            base_commit=payload.base_commit,
            head_commit=payload.head_commit,
        )
    except Exception as exc:
        _raise_http_for_repository_error(exc)
