"""Workspace-authorized access to persisted deterministic analyses."""

import uuid

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Query,
    Request,
    status,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import github_app
from app.auth.csrf import require_trusted_origin
from app.auth.dependencies import AuthenticatedPrincipal, get_current_principal
from app.api.repositories import _raise_http_for_repository_error
from app.config import get_settings
from app.db.session import get_db
from app.models import AnalysisFinding
from app.services.github_app_service import (
    GitHubAppConflictError,
    GitHubAppRepositoryDeniedError,
    GitHubAppWorkspaceError,
)
from app.schemas.analysis import (
    AnalysisDetailResponse,
    AnalysisHistoryItem,
    AnalysisHistoryResponse,
    AnalysisJobResponse,
)
from app.schemas.drift import DriftAnalysisRequest
from app.services import analysis_service
from app.services.github_app_service import resolve_repository_access
from app.tasks.analysis_jobs import dispatch_analysis_job

router = APIRouter(
    prefix="/api/analyses",
    tags=["Analyses"],
    dependencies=[Depends(get_current_principal)],
)


def _job_response(record: analysis_service.AnalysisRecord) -> AnalysisJobResponse:
    return AnalysisJobResponse(
        analysis_id=record.id,
        status=record.status,
        progress_percent=record.progress_percent,
        attempt_count=record.attempt_count,
        max_attempts=get_settings().analysis_retry_max_attempts,
        cancellation_requested=record.cancellation_requested,
        scratch_cleanup_status=record.scratch_cleanup_status,
        error_category=record.error_category,
        created_at=record.created_at,
        queued_at=record.queued_at,
        started_at=record.started_at,
        completed_at=record.completed_at,
    )


def _create_analysis(
    payload: DriftAnalysisRequest,
    principal: AuthenticatedPrincipal,
    db: Session,
    idempotency_key: str | None,
) -> AnalysisJobResponse:
    if payload.base_commit == payload.head_commit:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Base and head commits must be different commits.",
        )
    try:
        resolve_repository_access(db, principal, payload.github_repository_id)
        record, created = analysis_service.create_queued_analysis(
            db,
            principal,
            payload.github_repository_id,
            payload.base_commit,
            payload.head_commit,
            idempotency_key,
        )
        if created or record.status == "queued":
            dispatch_analysis_job(record.id)
        db.refresh(record)
        return _job_response(record)
    except analysis_service.AnalysisQuotaExceededError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
        ) from exc
    except analysis_service.AnalysisIdempotencyConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except analysis_service.AnalysisNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Authorized repository is unavailable.",
        ) from exc
    except Exception as exc:
        _raise_http_for_repository_error(exc)


def _raise_http_for_analysis_access_error(exc: Exception) -> None:
    if isinstance(exc, github_app.GitHubAppRateLimitError):
        headers = {"Retry-After": str(exc.retry_after)} if exc.retry_after else None
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="GitHub API rate limit reached. Retry later.",
            headers=headers,
        ) from exc
    if isinstance(exc, github_app.GitHubAppNotConfiguredError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GitHub App integration is not configured.",
        ) from exc
    if isinstance(exc, GitHubAppRepositoryDeniedError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Analysis is unavailable.",
        ) from exc
    if isinstance(
        exc,
        (
            github_app.GitHubAppAccessError,
            github_app.GitHubAppUpstreamError,
        ),
    ):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="GitHub could not verify repository access.",
        ) from exc
    if isinstance(exc, GitHubAppWorkspaceError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Workspace authorization is required.",
        ) from exc
    if isinstance(exc, GitHubAppConflictError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="GitHub resource is unavailable to this workspace.",
        ) from exc
    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail="GitHub could not verify repository access.",
    ) from exc


@router.post(
    "",
    response_model=AnalysisJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Queue a workspace-authorized repository analysis",
)
def create_analysis(
    payload: DriftAnalysisRequest,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(
        default=None,
        alias="Idempotency-Key",
        min_length=16,
        max_length=128,
    ),
) -> AnalysisJobResponse:
    require_trusted_origin(request)
    return _create_analysis(payload, principal, db, idempotency_key)


@router.get(
    "",
    response_model=AnalysisHistoryResponse,
    status_code=status.HTTP_200_OK,
    summary="List workspace analysis history",
)
def list_analysis_history(
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
) -> AnalysisHistoryResponse:
    try:
        records, total_count = analysis_service.list_workspace_analyses(
            db, principal, limit=limit, offset=offset
        )
    except analysis_service.AnalysisNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Analysis history is unavailable.",
        ) from exc

    analysis_ids = [record.id for record in records]
    finding_counts: dict[uuid.UUID, int] = {}
    if analysis_ids:
        finding_counts = {
            analysis_id: count
            for analysis_id, count in db.execute(
                select(
                    AnalysisFinding.analysis_id,
                    func.count(AnalysisFinding.finding_id),
                )
                .where(AnalysisFinding.analysis_id.in_(analysis_ids))
                .group_by(AnalysisFinding.analysis_id)
            ).all()
        }

    access_by_repository: dict[int, tuple[bool, str | None]] = {}
    items: list[AnalysisHistoryItem] = []
    for record in records:
        if record.github_repository_id not in access_by_repository:
            try:
                access = resolve_repository_access(
                    db, principal, record.github_repository_id
                )
                access_by_repository[record.github_repository_id] = (
                    True,
                    access.full_name,
                )
            except GitHubAppRepositoryDeniedError:
                access_by_repository[record.github_repository_id] = (False, None)
            except Exception as exc:
                _raise_http_for_analysis_access_error(exc)
        repository_accessible, repository_full_name = access_by_repository[
            record.github_repository_id
        ]
        items.append(
            AnalysisHistoryItem(
                analysis_id=record.id,
                status=record.status,
                github_repository_id=record.github_repository_id
                if repository_accessible
                else None,
                repository_full_name=repository_full_name,
                repository_accessible=repository_accessible,
                base_commit=record.base_commit if repository_accessible else None,
                head_commit=record.head_commit if repository_accessible else None,
                finding_count=finding_counts.get(record.id, 0)
                if repository_accessible
                else 0,
                progress_percent=record.progress_percent,
                attempt_count=record.attempt_count,
                max_attempts=get_settings().analysis_retry_max_attempts,
                error_category=record.error_category,
                created_at=record.created_at,
                completed_at=record.completed_at,
            )
        )
    return AnalysisHistoryResponse(
        items=items,
        total_count=total_count,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{analysis_id}/status",
    response_model=AnalysisJobResponse,
    status_code=status.HTTP_200_OK,
)
def read_analysis_status(
    analysis_id: uuid.UUID,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> AnalysisJobResponse:
    try:
        record = analysis_service.get_workspace_analysis(db, principal, analysis_id)
    except analysis_service.AnalysisNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Analysis is unavailable.",
        ) from exc
    return _job_response(record)


@router.post(
    "/{analysis_id}/cancel",
    response_model=AnalysisJobResponse,
    status_code=status.HTTP_200_OK,
)
def cancel_analysis(
    analysis_id: uuid.UUID,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> AnalysisJobResponse:
    require_trusted_origin(request)
    try:
        record = analysis_service.request_analysis_cancellation(
            db, principal, analysis_id
        )
    except analysis_service.AnalysisNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Analysis is unavailable.",
        ) from exc
    return _job_response(record)


@router.post(
    "/{analysis_id}/retry",
    response_model=AnalysisJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Retry an eligible failed or cancelled analysis",
)
def retry_analysis(
    analysis_id: uuid.UUID,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> AnalysisJobResponse:
    require_trusted_origin(request)
    try:
        previous = analysis_service.get_workspace_analysis(
            db, principal, analysis_id
        )
        if previous.status not in {"failed", "cancelled"}:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Only failed or cancelled analyses can be retried.",
            )
        retryable_categories = {
            "analysis_timeout",
            "github_rate_limited",
            "github_temporarily_unavailable",
            "git_timeout",
            "queue_unavailable",
            "repository_unavailable",
            "worker_lost",
        }
        if (
            previous.status == "failed"
            and previous.error_category not in retryable_categories
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This failure is not eligible for automatic retry.",
            )
        resolve_repository_access(
            db, principal, previous.github_repository_id
        )
        record, _created = analysis_service.create_queued_analysis(
            db,
            principal,
            previous.github_repository_id,
            previous.base_commit,
            previous.head_commit,
        )
        dispatch_analysis_job(record.id)
        db.refresh(record)
        return _job_response(record)
    except HTTPException:
        raise
    except analysis_service.AnalysisQuotaExceededError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
        ) from exc
    except analysis_service.AnalysisNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Analysis is unavailable.",
        ) from exc
    except Exception as exc:
        _raise_http_for_analysis_access_error(exc)


@router.delete(
    "/{analysis_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a terminal workspace analysis",
)
def delete_analysis(
    analysis_id: uuid.UUID,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> None:
    require_trusted_origin(request)
    try:
        record = analysis_service.get_workspace_analysis(
            db, principal, analysis_id
        )
        resolve_repository_access(
            db, principal, record.github_repository_id
        )
        analysis_service.delete_workspace_analysis(
            db, principal, analysis_id
        )
    except HTTPException:
        raise
    except analysis_service.AnalysisActiveError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except analysis_service.AnalysisNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Analysis is unavailable.",
        ) from exc
    except Exception as exc:
        _raise_http_for_analysis_access_error(exc)
    return None


@router.get(
    "/{analysis_id}",
    response_model=AnalysisDetailResponse,
    status_code=status.HTTP_200_OK,
)
def read_analysis(
    analysis_id: uuid.UUID,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> AnalysisDetailResponse:
    try:
        record = analysis_service.get_workspace_analysis(db, principal, analysis_id)
        access = resolve_repository_access(
            db, principal, record.github_repository_id
        )
    except analysis_service.AnalysisNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Analysis is unavailable.",
        ) from exc
    except Exception as exc:
        from app.api.repositories import _raise_http_for_repository_error

        _raise_http_for_repository_error(exc)

    findings = [
        {
            **item.evidence,
            "status": item.status,
            "severity": item.severity,
            "confidence": item.confidence,
        }
        for item in record.findings
    ]
    owner, _, name = access.full_name.partition("/")
    return AnalysisDetailResponse(
        analysis_id=record.id,
        status=record.status,
        github_repository_id=record.github_repository_id,
        repository_full_name=access.full_name,
        repository_url=access.html_url,
        owner=owner,
        name=name,
        base_commit=record.base_commit,
        head_commit=record.head_commit,
        summary=record.summary,
        findings=findings,
        error_category=record.error_category,
        progress_percent=record.progress_percent,
        attempt_count=record.attempt_count,
        max_attempts=get_settings().analysis_retry_max_attempts,
        cancellation_requested=record.cancellation_requested,
        scratch_cleanup_status=record.scratch_cleanup_status,
        created_at=record.created_at,
        queued_at=record.queued_at,
        started_at=record.started_at,
        completed_at=record.completed_at,
    )
