"""Persisted analysis detail responses."""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

from app.schemas.drift import DriftFinding


AnalysisJobStatus = Literal[
    "queued", "running", "succeeded", "failed", "cancelled"
]
ScratchCleanupStatus = Literal["not_started", "pending", "complete", "failed"]


class AnalysisJobResponse(BaseModel):
    analysis_id: uuid.UUID
    status: AnalysisJobStatus
    progress_percent: int
    attempt_count: int
    max_attempts: int
    cancellation_requested: bool
    scratch_cleanup_status: ScratchCleanupStatus
    error_category: str | None = None
    created_at: datetime
    queued_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None


class AnalysisHistoryItem(BaseModel):
    analysis_id: uuid.UUID
    status: AnalysisJobStatus
    github_repository_id: int | None = None
    repository_full_name: str | None = None
    repository_accessible: bool
    base_commit: str | None = None
    head_commit: str | None = None
    finding_count: int
    progress_percent: int
    attempt_count: int
    max_attempts: int
    error_category: str | None = None
    created_at: datetime
    completed_at: datetime | None = None


class AnalysisHistoryResponse(BaseModel):
    items: list[AnalysisHistoryItem]
    total_count: int
    limit: int
    offset: int


class AnalysisDetailResponse(BaseModel):
    analysis_id: uuid.UUID
    status: AnalysisJobStatus
    github_repository_id: int
    repository_full_name: str
    repository_url: str
    owner: str
    name: str
    base_commit: str
    head_commit: str
    summary: dict[str, Any] | None = None
    findings: list[DriftFinding]
    error_category: str | None = None
    progress_percent: int
    attempt_count: int
    max_attempts: int
    cancellation_requested: bool
    scratch_cleanup_status: ScratchCleanupStatus
    created_at: datetime
    queued_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
