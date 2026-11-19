"""Persisted, workspace-scoped deterministic analysis metadata."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Float,
    Index,
    JSON,
    String,
    Uuid,
    Boolean,
    Integer,
    func,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class AnalysisRecord(Base):
    __tablename__ = "analyses"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')",
            name="ck_analysis_status",
        ),
        ForeignKeyConstraint(
            ["github_repository_id", "workspace_id"],
            [
                "authorized_repositories.github_repository_id",
                "authorized_repositories.workspace_id",
            ],
            ondelete="CASCADE",
        ),
        Index("ix_analyses_workspace_created", "workspace_id", "created_at"),
        Index(
            "ix_analyses_user_created",
            "created_by_user_id",
            "created_at",
        ),
        Index("ix_analyses_status_queued", "status", "queued_at"),
        Index("ix_analyses_status_heartbeat", "status", "last_heartbeat_at"),
        UniqueConstraint(
            "workspace_id",
            "created_by_user_id",
            "idempotency_key_hash",
            name="uq_analysis_idempotency_key",
        ),
        CheckConstraint(
            "progress_percent >= 0 AND progress_percent <= 100",
            name="ck_analysis_progress_percent",
        ),
        CheckConstraint("attempt_count >= 0", name="ck_analysis_attempt_count"),
        CheckConstraint(
            "scratch_cleanup_status IN ('not_started', 'pending', 'complete', 'failed')",
            name="ck_analysis_scratch_cleanup_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    github_repository_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    base_commit: Mapped[str] = mapped_column(String(40), nullable=False)
    head_commit: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    summary: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error_category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    progress_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cancellation_requested: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    scratch_cleanup_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="not_started"
    )
    idempotency_key_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    request_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    queued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_dispatched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    findings: Mapped[list["AnalysisFinding"]] = relationship(
        back_populates="analysis", cascade="all, delete-orphan"
    )


class AnalysisFinding(Base):
    __tablename__ = "analysis_findings"
    __table_args__ = (
        Index("ix_analysis_findings_status", "analysis_id", "status"),
    )

    analysis_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("analyses.id", ondelete="CASCADE"),
        primary_key=True,
    )
    finding_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

    analysis: Mapped[AnalysisRecord] = relationship(back_populates="findings")
