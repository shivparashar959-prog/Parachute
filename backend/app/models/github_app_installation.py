"""GitHub App installations linked to a DocGuard workspace."""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class GitHubAppInstallation(Base):
    __tablename__ = "github_app_installations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'suspended', 'uninstalled')",
            name="ck_github_app_installation_status",
        ),
        CheckConstraint(
            "repository_selection IN ('all', 'selected')",
            name="ck_github_app_repository_selection",
        ),
    )

    installation_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    installed_by_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    account_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    account_login: Mapped[str] = mapped_column(String(255), nullable=False)
    account_type: Mapped[str] = mapped_column(String(32), nullable=False)
    repository_selection: Mapped[str] = mapped_column(
        String(16), nullable=False, default="selected"
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    repositories: Mapped[list["AuthorizedRepository"]] = relationship(
        back_populates="installation", cascade="all, delete-orphan"
    )
