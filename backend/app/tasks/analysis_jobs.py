"""Durable analysis dispatch, execution, retry, cancellation, and recovery."""

import logging
import os
import re
import shutil
import tempfile
import time
import uuid
from datetime import datetime, timedelta, timezone

from celery.exceptions import SoftTimeLimitExceeded
from kombu.exceptions import OperationalError
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.ai.base_provider import AIProviderError
from app.auth import github_app
from app.config import get_settings, require_database_url
from app.db.session import _session_factory
from app.models import (
    AnalysisRecord,
    AuthorizedRepository,
    PullRequestAutomationResult,
)
from app.services import analysis_service
from app.services.drift_analysis_service import analyze_repository_drift
from app.services.github_app_service import (
    GitHubAppRepositoryDeniedError,
    GitHubAppWorkspaceError,
    resolve_repository_access_for_analysis,
)
from app.services.github_service import (
    RepositoryNetworkError,
    RepositoryResourceLimitError,
    RepositoryTimeoutError,
    RepositoryValidationError,
    _remove_readonly,
)
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)
TASK_NAME = "app.tasks.analysis_jobs.process_analysis_job"
DISPATCH_RETRY_SECONDS = 30


def _session() -> Session:
    return _session_factory(require_database_url())()


def _scratch_root() -> str:
    root = os.getenv(
        "DOCGUARD_SCRATCH_ROOT",
        os.path.join(tempfile.gettempdir(), "docguard_jobs"),
    )
    root = os.path.abspath(root)
    os.makedirs(root, exist_ok=True)
    return root


def _scratch_path(analysis_id: uuid.UUID, attempt: int) -> str:
    root = _scratch_root()
    path = os.path.abspath(
        os.path.join(root, f"analysis-{analysis_id.hex}-attempt-{attempt}")
    )
    if os.path.commonpath((root, path)) != root:
        raise ValueError("Invalid analysis scratch path.")
    return path


def _remove_scratch_path(path: str) -> bool:
    if os.path.islink(path):
        os.unlink(path)
    elif os.path.exists(path):
        shutil.rmtree(path, onerror=_remove_readonly)
    return not os.path.exists(path)


def _cleanup_attempts(analysis_id: uuid.UUID, through_attempt: int) -> bool:
    removed = True
    for attempt in range(1, through_attempt + 1):
        try:
            removed = _remove_scratch_path(_scratch_path(analysis_id, attempt)) and removed
        except OSError:
            removed = False
    return removed


def _safe_error_category(exc: BaseException) -> tuple[str, bool]:
    if isinstance(exc, github_app.GitHubAppRateLimitError):
        return "github_rate_limited", True
    if isinstance(exc, github_app.GitHubAppUpstreamError):
        return "github_temporarily_unavailable", True
    if isinstance(exc, github_app.GitHubAppAccessError):
        return "repository_access_revoked", False
    if isinstance(exc, GitHubAppRepositoryDeniedError):
        return "repository_access_revoked", False
    if isinstance(exc, GitHubAppWorkspaceError):
        return "workspace_access_revoked", False
    if isinstance(exc, RepositoryTimeoutError):
        return "git_timeout", True
    if isinstance(exc, RepositoryNetworkError):
        return "repository_unavailable", True
    if isinstance(exc, SoftTimeLimitExceeded):
        return "analysis_timeout", False
    if isinstance(exc, RepositoryValidationError):
        return "invalid_repository_or_commit", False
    if isinstance(exc, RepositoryResourceLimitError):
        return "resource_limit", False
    if isinstance(exc, analysis_service.AnalysisResourceLimitError):
        return "resource_limit", False
    if isinstance(exc, AIProviderError):
        return "provider_error", False
    return "analysis_failed", False


def _sanitize_pr_text(value: str, limit: int) -> str:
    sanitized = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", value)
    sanitized = re.sub(r"\x1b(?:[@-_]|\[[0-?]*[ -/]*[@-~])", "", sanitized)
    return " ".join(sanitized.split())[:limit]


def _publish_pr_result(
    db: Session,
    record: AnalysisRecord,
    access: object,
) -> None:
    result = db.scalar(
        select(PullRequestAutomationResult).where(
            PullRequestAutomationResult.analysis_id == record.id
        )
    )
    if result is None or result.published:
        return
    summary = record.summary if isinstance(record.summary, dict) else {}
    confirmed = int(summary.get("confirmed_drift_count", 0) or 0)
    potential = int(summary.get("potential_drift_count", 0) or 0)
    total = int(summary.get("total_findings", 0) or 0)
    conclusion = "failure" if confirmed > 0 else "success" if total == 0 else "neutral"
    title = "DocGuard: documentation drift detected" if confirmed > 0 else "DocGuard: review complete"
    body = _sanitize_pr_text(
        f"DocGuard reviewed commit {record.head_commit[:12]}: "
        f"{confirmed} confirmed, {potential} potential, {total} total findings. "
        f"[View findings]({get_settings().frontend_origin}/dashboard/history/{record.id})",
        4000,
    )
    try:
        check = github_app.create_or_update_check_run(
            access.owner_login,
            access.name,
            access_token=access.installation_token,
            head_sha=record.head_commit,
            conclusion=conclusion,
            title=title,
            summary=body,
            check_run_id=result.check_run_id,
        )
        check_id = check.get("id")
        if isinstance(check_id, int):
            result.check_run_id = check_id
        result.published = True
    except github_app.GitHubAppError as exc:
        logger.warning(
            "DocGuard Check Run publication is pending "
            "(analysis_id=%s, error_type=%s).",
            record.id,
            type(exc).__name__,
        )
        result.published = False
    db.commit()


def _publish_pending_pr_results(db: Session) -> int:
    pending = list(
        db.scalars(
            select(PullRequestAutomationResult)
            .join(
                AnalysisRecord,
                PullRequestAutomationResult.analysis_id == AnalysisRecord.id,
            )
            .where(
                PullRequestAutomationResult.published.is_(False),
                AnalysisRecord.status == "succeeded",
            )
            .order_by(PullRequestAutomationResult.created_at)
            .limit(50)
        )
    )
    attempted = 0
    for result in pending:
        repository = db.get(
            AuthorizedRepository,
            result.github_repository_id,
        )
        if repository is None or not repository.pr_automation_enabled:
            continue
        record = db.get(AnalysisRecord, result.analysis_id)
        if record is None:
            continue
        try:
            access = resolve_repository_access_for_analysis(
                db,
                workspace_id=result.workspace_id,
                user_id=record.created_by_user_id,
                github_repository_id=result.github_repository_id,
            )
        except (
            github_app.GitHubAppError,
            GitHubAppRepositoryDeniedError,
            GitHubAppWorkspaceError,
        ) as exc:
            logger.warning(
                "DocGuard Check Run remains pending because repository access "
                "could not be verified (analysis_id=%s, error_type=%s).",
                record.id,
                type(exc).__name__,
            )
            continue
        attempted += 1
        _publish_pr_result(db, record, access)
    return attempted


def _execute_analysis_job(analysis_id: uuid.UUID) -> tuple[str, bool, int]:
    settings = get_settings()
    db = _session()
    record = None
    current_scratch = None
    outcome = "failed"
    retryable = False
    error_category = "analysis_failed"
    retry_delay = 0
    prior_cleanup_ok = True
    try:
        record = analysis_service.claim_queued_analysis(db, analysis_id)
        if record is None:
            current = db.get(AnalysisRecord, analysis_id)
            return (current.status if current else "unavailable", False, 0)

        prior_cleanup_ok = _cleanup_attempts(
            analysis_id, record.attempt_count - 1
        )
        if not prior_cleanup_ok:
            error_category = "scratch_cleanup_failed"
            outcome = "failed"
        else:
            current_scratch = _scratch_path(analysis_id, record.attempt_count)
            access = resolve_repository_access_for_analysis(
                db,
                workspace_id=record.workspace_id,
                user_id=record.created_by_user_id,
                github_repository_id=record.github_repository_id,
            )
            latest_progress = 1
            heartbeat_due = time.monotonic() + 5

            def cancellation_check() -> None:
                nonlocal heartbeat_due
                if analysis_service.analysis_cancellation_requested(db, analysis_id):
                    db.rollback()
                    raise analysis_service.AnalysisCancelledError(
                        "Analysis cancellation was requested."
                    )
                db.rollback()
                if time.monotonic() >= heartbeat_due:
                    analysis_service.update_analysis_progress(
                        db, analysis_id, latest_progress
                    )
                    heartbeat_due = time.monotonic() + 5

            def progress_callback(progress_percent: int) -> None:
                nonlocal latest_progress
                latest_progress = progress_percent
                if not analysis_service.update_analysis_progress(
                    db, analysis_id, progress_percent
                ):
                    raise analysis_service.AnalysisCancelledError(
                        "Analysis is no longer active."
                    )

            cancellation_check()
            response = analyze_repository_drift(
                repository_url=access.html_url,
                base_commit=record.base_commit,
                head_commit=record.head_commit,
                access_token=access.installation_token,
                progress_callback=progress_callback,
                cancellation_check=cancellation_check,
                scratch_directory=current_scratch,
            )
            analysis_service.complete_analysis(db, analysis_id, response)
            record = db.get(AnalysisRecord, analysis_id)
            if record is not None:
                _publish_pr_result(db, record, access)
            outcome = "succeeded"
    except analysis_service.AnalysisCancelledError:
        outcome = "cancelled"
    except Exception as exc:
        error_category, retryable = _safe_error_category(exc)
        retryable = retryable and record is not None
        outcome = "retry" if retryable else "failed"
    finally:
        if current_scratch is None and record is not None:
            current_scratch = _scratch_path(analysis_id, record.attempt_count)
        cleanup_ok = prior_cleanup_ok
        if current_scratch is not None:
            try:
                cleanup_ok = _remove_scratch_path(current_scratch) and cleanup_ok
            except OSError:
                cleanup_ok = False
        if record is not None:
            if not cleanup_ok:
                logger.error(
                    "Analysis scratch cleanup failed (analysis_id=%s, attempt=%s).",
                    analysis_id,
                    record.attempt_count,
                )
                analysis_service.set_analysis_cleanup_status(
                    db, analysis_id, "failed"
                )
            else:
                analysis_service.set_analysis_cleanup_status(
                    db, analysis_id, "complete"
                )
            if outcome == "cancelled":
                analysis_service.mark_analysis_cancelled(db, analysis_id)
            elif outcome == "retry":
                if cleanup_ok and record.attempt_count < settings.analysis_retry_max_attempts:
                    analysis_service.schedule_analysis_retry(
                        db, analysis_id, error_category
                    )
                    retry_delay = min(
                        60, 5 * (2 ** max(0, record.attempt_count - 1))
                    )
                    outcome = "queued"
                else:
                    analysis_service.fail_analysis(
                        db,
                        analysis_id,
                        error_category
                        if cleanup_ok
                        else "scratch_cleanup_failed",
                    )
                    outcome = "failed"
            elif outcome == "failed":
                analysis_service.fail_analysis(
                    db,
                    analysis_id,
                    error_category
                    if cleanup_ok
                    else "scratch_cleanup_failed",
                )
        db.close()
    return outcome, outcome == "queued", retry_delay


@celery_app.task(
    bind=True,
    name=TASK_NAME,
    max_retries=4,
    ignore_result=True,
)
def process_analysis_job(self, analysis_id: str) -> dict[str, str]:
    try:
        parsed_id = uuid.UUID(analysis_id)
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError("Analysis task requires a valid analysis ID.") from exc

    outcome, retry, retry_delay = _execute_analysis_job(parsed_id)
    if retry:
        raise self.retry(countdown=retry_delay)
    return {"analysis_id": str(parsed_id), "status": outcome}


def dispatch_analysis_job(analysis_id: uuid.UUID | str) -> bool:
    parsed_id = uuid.UUID(str(analysis_id))
    db = _session()
    now = datetime.now(timezone.utc)
    try:
        record = db.scalar(
            select(AnalysisRecord)
            .where(AnalysisRecord.id == parsed_id)
            .with_for_update()
        )
        if record is None or record.status != "queued":
            return False
        if record.last_dispatched_at is not None:
            dispatched_at = record.last_dispatched_at
            if dispatched_at.tzinfo is None:
                dispatched_at = dispatched_at.replace(tzinfo=timezone.utc)
            if dispatched_at > now - timedelta(seconds=DISPATCH_RETRY_SECONDS):
                return False
        record.last_dispatched_at = now
        db.commit()
        try:
            celery_app.send_task(TASK_NAME, args=[str(parsed_id)])
        except OperationalError:
            record = db.get(AnalysisRecord, parsed_id)
            if record is not None and record.status == "queued":
                record.error_category = "queue_unavailable"
                db.commit()
            logger.warning(
                "Analysis remains queued because the broker is unavailable "
                "(analysis_id=%s).",
                parsed_id,
            )
            return False
        record = db.get(AnalysisRecord, parsed_id)
        if record is not None and record.error_category == "queue_unavailable":
            record.error_category = None
            db.commit()
        return True
    finally:
        db.close()


def _cleanup_orphaned_scratch(db: Session) -> None:
    records = list(
        db.scalars(
            select(AnalysisRecord).where(
                AnalysisRecord.status.in_(("succeeded", "failed", "cancelled")),
                AnalysisRecord.scratch_cleanup_status.in_(("pending", "failed")),
                AnalysisRecord.attempt_count > 0,
            )
        )
    )
    for record in records:
        cleanup_ok = _cleanup_attempts(record.id, record.attempt_count)
        record.scratch_cleanup_status = "complete" if cleanup_ok else "failed"
        db.commit()
        if not cleanup_ok:
            logger.error(
                "Orphaned analysis scratch cleanup failed (analysis_id=%s).",
                record.id,
            )


@celery_app.task(name="app.tasks.analysis_jobs.maintain_analysis_jobs", ignore_result=True)
def maintain_analysis_jobs() -> dict[str, int]:
    db = _session()
    try:
        recovered_ids = analysis_service.recover_stale_analyses(db)
        for analysis_id in recovered_ids:
            recovered_record = db.get(AnalysisRecord, analysis_id)
            attempt_count = recovered_record.attempt_count if recovered_record else 0
            cleanup_ok = _cleanup_attempts(analysis_id, attempt_count)
            analysis_service.set_analysis_cleanup_status(
                db, analysis_id, "complete" if cleanup_ok else "failed"
            )
            if not cleanup_ok:
                logger.error(
                    "Stale analysis scratch cleanup failed (analysis_id=%s).",
                    analysis_id,
                )
        _cleanup_orphaned_scratch(db)
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=DISPATCH_RETRY_SECONDS)
        queued_ids = list(
            db.scalars(
                select(AnalysisRecord.id)
                .where(
                    AnalysisRecord.status == "queued",
                    (AnalysisRecord.last_dispatched_at.is_(None))
                    | (AnalysisRecord.last_dispatched_at <= cutoff),
                )
                .order_by(AnalysisRecord.queued_at)
                .limit(100)
            )
        )
        retained_deleted = analysis_service.enforce_analysis_retention(db)
        publication_attempted = _publish_pending_pr_results(db)
    finally:
        db.close()
    dispatched = sum(dispatch_analysis_job(item) for item in queued_ids)
    return {
        "recovered": len(recovered_ids),
        "dispatched": dispatched,
        "retention_deleted": retained_deleted,
        "publication_attempted": publication_attempted,
    }
