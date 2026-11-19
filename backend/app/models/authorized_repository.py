"""Workspace-scoped GitHub repositories available through an App installation."""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class AuthorizedRepository(Base):
    __tablename__ = "authorized_repositories"
    __table_args__ = (
        CheckConstraint(
            "visibility IN ('public', 'private')",
            name="ck_authorized_repository_visibility",
        ),
        UniqueConstraint(
            "github_repository_id",
            "workspace_id",
            name="uq_authorized_repository_id_workspace",
        ),
    )

    github_repository_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    installation_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("github_app_installations.installation_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    owner_login: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(511), nullable=False, index=True)
    html_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    visibility: Mapped[str] = mapped_column(String(16), nullable=False)
    default_branch: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    installation: Mapped["GitHubAppInstallation"] = relationship(
        back_populates="repositories"
    )
