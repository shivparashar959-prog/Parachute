"""Workspace-scoped persistence and bounded resource accounting for analyses."""

import json
import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_UP

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthenticatedPrincipal
from app.config import get_settings
from app.models import (
    AnalysisFinding,
    AnalysisRecord,
    AuthorizedRepository,
    GeminiSpendReservation,
    User,
    Workspace,
)
from app.schemas.drift import DriftAnalysisResponse, DriftFinding
from app.services.github_app_service import (
    GitHubAppWorkspaceError,
    get_personal_workspace,
)

MAX_FINDINGS_PER_ANALYSIS = 500
MAX_FINDING_EVIDENCE_BYTES = 32_000
MAX_ANALYSIS_EVIDENCE_BYTES = 4_000_000
ANALYSIS_EVIDENCE_LIMIT_ERROR = "analysis_evidence_limit"


class AnalysisQuotaExceededError(RuntimeError):
    """Raised when an analysis or AI request exceeds a configured account limit."""


class AnalysisNotFoundError(LookupError):
    """Raised when an analysis is not available in the authenticated workspace."""


class AnalysisActiveError(RuntimeError):
    """Raised when an active analysis cannot be deleted or retried."""


class AnalysisResourceLimitError(RuntimeError):
    """Raised when bounded analysis evidence exceeds the persistence limits."""


class GeminiSpendConfigurationError(RuntimeError):
    """Raised when Gemini is selected without complete spend-control settings."""


class AnalysisIdempotencyConflictError(RuntimeError):
    """Raised when an idempotency key is reused for different analysis input."""


class AnalysisCancelledError(RuntimeError):
    """Raised when a running analysis observes a cancellation request."""


def create_queued_analysis(
    db: Session,
    principal: AuthenticatedPrincipal,
    github_repository_id: int,
    base_commit: str,
    head_commit: str,
    idempotency_key: str | None = None,
    commit: bool = True,
) -> tuple[AnalysisRecord, bool]:
    settings = get_settings()
    workspace = get_personal_workspace(db, principal)
    locked_workspace = db.scalar(
        select(Workspace)
        .where(Workspace.id == workspace.id)
        .with_for_update()
    )
    repository = db.scalar(
        select(AuthorizedRepository).where(
            AuthorizedRepository.github_repository_id == github_repository_id,
            AuthorizedRepository.workspace_id == workspace.id,
            AuthorizedRepository.is_active.is_(True),
        )
    )
    if locked_workspace is None or repository is None:
        raise AnalysisNotFoundError("Authorized repository is unavailable.")

    key_hash = None
    fingerprint = hashlib.sha256(
        f"{github_repository_id}:{base_commit}:{head_commit}".encode("utf-8")
    ).hexdigest()
    if idempotency_key is not None:
        if not 16 <= len(idempotency_key) <= 128:
            raise ValueError("Idempotency-Key must be between 16 and 128 characters.")
        key_hash = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()
        existing = db.scalar(
            select(AnalysisRecord).where(
                AnalysisRecord.workspace_id == workspace.id,
                AnalysisRecord.created_by_user_id == principal.user.id,
                AnalysisRecord.idempotency_key_hash == key_hash,
            )
        )
        if existing is not None:
            if existing.request_fingerprint != fingerprint:
                raise AnalysisIdempotencyConflictError(
                    "Idempotency-Key was already used for different analysis input."
                )
            return existing, False

    now = datetime.now(timezone.utc)
    user_hour_count = db.scalar(
        select(func.count(AnalysisRecord.id)).where(
            AnalysisRecord.created_by_user_id == principal.user.id,
            AnalysisRecord.created_at >= now - timedelta(hours=1),
        )
    ) or 0
    workspace_day_count = db.scalar(
        select(func.count(AnalysisRecord.id)).where(
            AnalysisRecord.workspace_id == workspace.id,
            AnalysisRecord.created_at >= now - timedelta(days=1),
        )
    ) or 0
    active_count = db.scalar(
        select(func.count(AnalysisRecord.id)).where(
            AnalysisRecord.workspace_id == workspace.id,
            AnalysisRecord.status.in_(("running", "queued")),
        )
    ) or 0
    if user_hour_count >= settings.analysis_per_user_hour_limit:
        raise AnalysisQuotaExceededError("User analysis rate limit reached.")
    if workspace_day_count >= settings.analysis_per_workspace_day_limit:
        raise AnalysisQuotaExceededError("Workspace analysis quota reached.")
    if active_count >= settings.analysis_max_concurrent_per_workspace:
        raise AnalysisQuotaExceededError("Workspace analysis concurrency limit reached.")

    record = AnalysisRecord(
        workspace_id=workspace.id,
        created_by_user_id=principal.user.id,
        github_repository_id=github_repository_id,
        base_commit=base_commit,
        head_commit=head_commit,
        status="queued",
        idempotency_key_hash=key_hash,
        request_fingerprint=fingerprint,
    )
    db.add(record)
    if commit:
        db.commit()
        db.refresh(record)
    else:
        db.flush()
    return record, True


def claim_queued_analysis(db: Session, analysis_id: uuid.UUID) -> AnalysisRecord | None:
    now = datetime.now(timezone.utc)
    result = db.execute(
        update(AnalysisRecord)
        .where(
            AnalysisRecord.id == analysis_id,
            AnalysisRecord.status == "queued",
            AnalysisRecord.cancellation_requested.is_(False),
        )
        .values(
            status="running",
            attempt_count=AnalysisRecord.attempt_count + 1,
            progress_percent=1,
            started_at=now,
            last_heartbeat_at=now,
            completed_at=None,
            scratch_cleanup_status="pending",
        )
    )
    if result.rowcount != 1:
        queued = db.scalar(
            select(AnalysisRecord).where(
                AnalysisRecord.id == analysis_id,
                AnalysisRecord.status == "queued",
                AnalysisRecord.cancellation_requested.is_(True),
            )
        )
        if queued is not None:
            queued.status = "cancelled"
            queued.completed_at = now
            db.commit()
        return None
    db.commit()
    return db.get(AnalysisRecord, analysis_id)


def update_analysis_progress(
    db: Session,
    analysis_id: uuid.UUID,
    progress_percent: int,
) -> bool:
    now = datetime.now(timezone.utc)
    result = db.execute(
        update(AnalysisRecord)
        .where(
            AnalysisRecord.id == analysis_id,
            AnalysisRecord.status == "running",
            AnalysisRecord.cancellation_requested.is_(False),
        )
        .values(
            progress_percent=max(1, min(99, progress_percent)),
            last_heartbeat_at=now,
        )
    )
    db.commit()
    return result.rowcount == 1


def analysis_cancellation_requested(db: Session, analysis_id: uuid.UUID) -> bool:
    return bool(
        db.scalar(
            select(AnalysisRecord.cancellation_requested).where(
                AnalysisRecord.id == analysis_id,
                AnalysisRecord.status == "running",
            )
        )
    )


def request_analysis_cancellation(
    db: Session,
    principal: AuthenticatedPrincipal,
    analysis_id: uuid.UUID,
) -> AnalysisRecord:
    record = get_workspace_analysis(db, principal, analysis_id)
    if record.status == "queued":
        record.status = "cancelled"
        record.cancellation_requested = True
        record.completed_at = datetime.now(timezone.utc)
    elif record.status == "running":
        record.cancellation_requested = True
    db.commit()
    db.refresh(record)
    return record


def mark_analysis_cancelled(db: Session, analysis_id: uuid.UUID) -> None:
    record = db.get(AnalysisRecord, analysis_id)
    if record is None or record.status != "running":
        return
    record.status = "cancelled"
    record.cancellation_requested = True
    record.completed_at = datetime.now(timezone.utc)
    db.commit()


def schedule_analysis_retry(
    db: Session,
    analysis_id: uuid.UUID,
    error_category: str,
) -> None:
    record = db.get(AnalysisRecord, analysis_id)
    if record is None or record.status != "running":
        return
    if record.cancellation_requested:
        mark_analysis_cancelled(db, analysis_id)
        return
    record.status = "queued"
    record.progress_percent = 0
    record.started_at = None
    record.last_heartbeat_at = None
    record.error_category = error_category
    record.completed_at = None
    record.last_dispatched_at = datetime.now(timezone.utc)
    db.commit()


def set_analysis_cleanup_status(
    db: Session,
    analysis_id: uuid.UUID,
    cleanup_status: str,
) -> None:
    record = db.get(AnalysisRecord, analysis_id)
    if record is None:
        return
    record.scratch_cleanup_status = cleanup_status
    db.commit()


def recover_stale_analyses(db: Session) -> list[uuid.UUID]:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    stale_before = now - timedelta(
        seconds=settings.analysis_timeout_seconds + 120
    )
    stale_ids = list(
        db.scalars(
            select(AnalysisRecord.id)
            .where(
                AnalysisRecord.status == "running",
                func.coalesce(
                    AnalysisRecord.last_heartbeat_at,
                    AnalysisRecord.started_at,
                    AnalysisRecord.created_at,
                )
                < stale_before,
            )
            .limit(100)
        )
    )
    recovered: list[uuid.UUID] = []
    for analysis_id in stale_ids:
        record = db.scalar(
            select(AnalysisRecord)
            .where(AnalysisRecord.id == analysis_id)
            .with_for_update(skip_locked=True)
        )
        if record is None:
            continue
        last_active = (
            record.last_heartbeat_at
            or record.started_at
            or record.created_at
        )
        if last_active.tzinfo is None:
            last_active = last_active.replace(tzinfo=timezone.utc)
        if record.status != "running" or last_active >= stale_before:
            db.rollback()
            continue
        if record.cancellation_requested:
            record.status = "cancelled"
            record.completed_at = now
        elif record.attempt_count < settings.analysis_retry_max_attempts:
            record.status = "queued"
            record.progress_percent = 0
            record.started_at = None
            record.last_heartbeat_at = None
            record.last_dispatched_at = None
            record.error_category = "worker_lost"
            recovered.append(record.id)
        else:
            record.status = "failed"
            record.error_category = "worker_lost"
            record.completed_at = now
        db.commit()
    return recovered


def create_running_analysis(
    db: Session,
    principal: AuthenticatedPrincipal,
    github_repository_id: int,
    base_commit: str,
    head_commit: str,
) -> AnalysisRecord:
    settings = get_settings()
    workspace = get_personal_workspace(db, principal)
    locked_workspace = db.scalar(
        select(Workspace)
        .where(Workspace.id == workspace.id)
        .with_for_update()
    )
    repository = db.scalar(
        select(AuthorizedRepository).where(
            AuthorizedRepository.github_repository_id == github_repository_id,
            AuthorizedRepository.workspace_id == workspace.id,
            AuthorizedRepository.is_active.is_(True),
        )
    )
    if locked_workspace is None or repository is None:
        raise AnalysisNotFoundError("Authorized repository is unavailable.")

    now = datetime.now(timezone.utc)
    stale_running_cutoff = now - timedelta(
        seconds=settings.analysis_timeout_seconds + 60
    )
    db.execute(
        update(AnalysisRecord)
        .where(
            AnalysisRecord.workspace_id == workspace.id,
            AnalysisRecord.status == "running",
            AnalysisRecord.created_at < stale_running_cutoff,
        )
        .values(
            status="failed",
            error_category="analysis_timeout",
            completed_at=now,
        )
    )
    db.flush()
    user_hour_count = db.scalar(
        select(func.count(AnalysisRecord.id)).where(
            AnalysisRecord.created_by_user_id == principal.user.id,
            AnalysisRecord.created_at >= now - timedelta(hours=1),
        )
    ) or 0
    workspace_day_count = db.scalar(
        select(func.count(AnalysisRecord.id)).where(
            AnalysisRecord.workspace_id == workspace.id,
            AnalysisRecord.created_at >= now - timedelta(days=1),
        )
    ) or 0
    active_count = db.scalar(
        select(func.count(AnalysisRecord.id)).where(
            AnalysisRecord.workspace_id == workspace.id,
            AnalysisRecord.status.in_(("running", "queued")),
        )
    ) or 0
    if user_hour_count >= settings.analysis_per_user_hour_limit:
        raise AnalysisQuotaExceededError("User analysis rate limit reached.")
    if workspace_day_count >= settings.analysis_per_workspace_day_limit:
        raise AnalysisQuotaExceededError("Workspace analysis quota reached.")
    if active_count >= settings.analysis_max_concurrent_per_workspace:
        raise AnalysisQuotaExceededError("Workspace analysis concurrency limit reached.")

    record = AnalysisRecord(
        workspace_id=workspace.id,
        created_by_user_id=principal.user.id,
        github_repository_id=github_repository_id,
        base_commit=base_commit,
        head_commit=head_commit,
        status="running",
        started_at=now,
        last_heartbeat_at=now,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def complete_analysis(
    db: Session,
    analysis_id: uuid.UUID,
    response: DriftAnalysisResponse,
) -> AnalysisRecord:
    if len(response.findings) > MAX_FINDINGS_PER_ANALYSIS:
        raise AnalysisResourceLimitError(
            "Analysis produced more findings than the persistence limit."
        )

    finding_rows: list[AnalysisFinding] = []
    seen_ids: set[str] = set()
    total_evidence_bytes = 0
    for finding in response.findings:
        if finding.finding_id in seen_ids:
            raise AnalysisResourceLimitError("Analysis finding IDs must be unique.")
        seen_ids.add(finding.finding_id)
        evidence = finding.model_dump(mode="json")
        serialized = json.dumps(evidence, ensure_ascii=False, separators=(",", ":"))
        evidence_bytes = len(serialized.encode("utf-8"))
        total_evidence_bytes += evidence_bytes
        if (
            evidence_bytes > MAX_FINDING_EVIDENCE_BYTES
            or total_evidence_bytes > MAX_ANALYSIS_EVIDENCE_BYTES
        ):
            raise AnalysisResourceLimitError(
                "Analysis evidence exceeds the persistence size limit."
            )
        finding_rows.append(
            AnalysisFinding(
                analysis_id=analysis_id,
                finding_id=finding.finding_id,
                status=finding.status,
                severity=finding.severity,
                confidence=finding.confidence,
                evidence=evidence,
            )
        )

    record = db.get(AnalysisRecord, analysis_id)
    if record is None or record.status != "running":
        raise AnalysisNotFoundError("Analysis is no longer available.")
    if record.cancellation_requested:
        mark_analysis_cancelled(db, analysis_id)
        raise AnalysisCancelledError("Analysis cancellation was requested.")
    record.base_commit = response.base_commit
    record.head_commit = response.head_commit
    record.summary = response.summary.model_dump(mode="json")
    record.status = "succeeded"
    record.progress_percent = 100
    record.completed_at = datetime.now(timezone.utc)
    record.findings.extend(finding_rows)
    db.commit()
    db.refresh(record)
    return record


def fail_analysis(
    db: Session,
    analysis_id: uuid.UUID,
    error_category: str,
) -> None:
    record = db.get(AnalysisRecord, analysis_id)
    if record is None or record.status != "running":
        return
    if record.cancellation_requested:
        mark_analysis_cancelled(db, analysis_id)
        return
    record.status = "failed"
    record.error_category = error_category
    record.completed_at = datetime.now(timezone.utc)
    db.commit()


def get_workspace_analysis(
    db: Session,
    principal: AuthenticatedPrincipal,
    analysis_id: uuid.UUID,
) -> AnalysisRecord:
    try:
        workspace = get_personal_workspace(db, principal)
    except GitHubAppWorkspaceError as exc:
        raise AnalysisNotFoundError("Analysis is unavailable.") from exc
    record = db.scalar(
        select(AnalysisRecord).where(
            AnalysisRecord.id == analysis_id,
            AnalysisRecord.workspace_id == workspace.id,
        )
    )
    if record is None:
        raise AnalysisNotFoundError("Analysis is unavailable.")
    return record


def list_workspace_analyses(
    db: Session,
    principal: AuthenticatedPrincipal,
    *,
    limit: int,
    offset: int,
) -> tuple[list[AnalysisRecord], int]:
    try:
        workspace = get_personal_workspace(db, principal)
    except GitHubAppWorkspaceError as exc:
        raise AnalysisNotFoundError("Analysis history is unavailable.") from exc

    total_count = db.scalar(
        select(func.count(AnalysisRecord.id)).where(
            AnalysisRecord.workspace_id == workspace.id
        )
    ) or 0
    records = list(
        db.scalars(
            select(AnalysisRecord)
            .where(AnalysisRecord.workspace_id == workspace.id)
            .order_by(AnalysisRecord.created_at.desc(), AnalysisRecord.id.desc())
            .limit(limit)
            .offset(offset)
        )
    )
    return records, total_count


def delete_workspace_analysis(
    db: Session,
    principal: AuthenticatedPrincipal,
    analysis_id: uuid.UUID,
) -> None:
    record = get_workspace_analysis(db, principal, analysis_id)
    if record.status in {"queued", "running"}:
        raise AnalysisActiveError("Active analyses cannot be deleted.")
    db.execute(
        update(GeminiSpendReservation)
        .where(GeminiSpendReservation.analysis_id == record.id)
        .values(analysis_id=None)
    )
    db.delete(record)
    db.commit()


def enforce_analysis_retention(db: Session) -> int:
    settings = get_settings()
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.data_retention_days)
    expired = list(
        db.scalars(
            select(AnalysisRecord)
            .where(
                AnalysisRecord.status.in_(("succeeded", "failed", "cancelled")),
                AnalysisRecord.created_at <= cutoff,
            )
            .limit(500)
        )
    )
    deleted = 0
    for record in expired:
        db.execute(
            update(GeminiSpendReservation)
            .where(GeminiSpendReservation.analysis_id == record.id)
            .values(analysis_id=None)
        )
        db.delete(record)
        deleted += 1
    if deleted:
        db.commit()
    return deleted


def get_workspace_analysis_findings(
    db: Session,
    principal: AuthenticatedPrincipal,
    analysis_id: uuid.UUID,
    finding_ids: list[str],
) -> tuple[AnalysisRecord, list[DriftFinding]]:
    record = get_workspace_analysis(db, principal, analysis_id)
    if record.status != "succeeded":
        raise AnalysisNotFoundError("Analysis findings are unavailable.")
    rows = list(
        db.scalars(
            select(AnalysisFinding).where(
                AnalysisFinding.analysis_id == record.id,
                AnalysisFinding.finding_id.in_(finding_ids),
            )
        )
    )
    by_id = {row.finding_id: row for row in rows}
    if len(by_id) != len(set(finding_ids)):
        raise AnalysisNotFoundError("Analysis findings are unavailable.")
    findings: list[DriftFinding] = []
    for finding_id in finding_ids:
        row = by_id[finding_id]
        evidence = dict(row.evidence)
        evidence.update(
            status=row.status,
            severity=row.severity,
            confidence=row.confidence,
        )
        findings.append(DriftFinding.model_validate(evidence))
    return record, findings


def reserve_gemini_spend(
    db: Session,
    principal: AuthenticatedPrincipal,
    analysis: AnalysisRecord,
    model_name: str,
    prompt: str,
) -> Decimal:
    settings = get_settings()
    if not settings.gemini_spend_controls_configured:
        raise GeminiSpendConfigurationError(
            "Gemini spend limits and token rates must be configured before use."
        )

    user = db.scalar(
        select(User).where(User.id == principal.user.id).with_for_update()
    )
    workspace = db.scalar(
        select(Workspace)
        .where(Workspace.id == analysis.workspace_id)
        .with_for_update()
    )
    if user is None or workspace is None:
        raise AnalysisNotFoundError("Analysis is unavailable.")

    input_tokens = (len(prompt.encode("utf-8")) + 2) // 3
    output_tokens = settings.gemini_max_output_tokens
    input_rate = Decimal(str(settings.gemini_input_usd_per_million_tokens))
    output_rate = Decimal(str(settings.gemini_output_usd_per_million_tokens))
    reservation = (
        Decimal(input_tokens) * input_rate + Decimal(output_tokens) * output_rate
    ) / Decimal(1_000_000)
    reservation = max(
        reservation.quantize(Decimal("0.000001"), rounding=ROUND_UP),
        Decimal("0.000001"),
    )

    since = datetime.now(timezone.utc) - timedelta(days=1)
    db.execute(
        delete(GeminiSpendReservation).where(
            GeminiSpendReservation.created_at < since
        )
    )
    db.flush()
    workspace_spend = db.scalar(
        select(func.coalesce(func.sum(GeminiSpendReservation.reserved_usd), 0)).where(
            GeminiSpendReservation.workspace_id == analysis.workspace_id,
            GeminiSpendReservation.created_at >= since,
        )
    ) or Decimal("0")
    user_spend = db.scalar(
        select(func.coalesce(func.sum(GeminiSpendReservation.reserved_usd), 0)).where(
            GeminiSpendReservation.user_id == principal.user.id,
            GeminiSpendReservation.created_at >= since,
        )
    ) or Decimal("0")
    if workspace_spend + reservation > Decimal(str(settings.gemini_daily_budget_usd)):
        raise AnalysisQuotaExceededError("Workspace Gemini daily budget reached.")
    if user_spend + reservation > Decimal(str(settings.gemini_user_daily_budget_usd)):
        raise AnalysisQuotaExceededError("User Gemini daily budget reached.")

    db.add(
        GeminiSpendReservation(
            workspace_id=analysis.workspace_id,
            user_id=principal.user.id,
            analysis_id=analysis.id,
            model_name=model_name,
            reserved_usd=reservation,
        )
    )
    db.commit()
    return reservation
