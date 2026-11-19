"""Idempotent DocGuard result records for GitHub pull requests."""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PullRequestAutomationResult(Base):
    __tablename__ = "pull_request_automation_results"
    __table_args__ = (
        UniqueConstraint(
            "github_repository_id",
            "pull_request_number",
            "base_sha",
            "head_sha",
            name="uq_pr_automation_repo_pr_base_head",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    github_repository_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("authorized_repositories.github_repository_id", ondelete="CASCADE"),
        nullable=False,
    )
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("analyses.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    pull_request_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    base_sha: Mapped[str] = mapped_column(String(40), nullable=False)
    head_sha: Mapped[str] = mapped_column(String(40), nullable=False)
    check_run_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
