"""Add GitHub App installations, authorized repositories, and callback state.

Revision ID: 0002_github_app_repository_catalog
Revises: 0001_identity_workspace_sessions
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002_github_app_repository_catalog"
down_revision: Union[str, None] = "0001_identity_workspace_sessions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "github_app_installations",
        sa.Column("installation_id", sa.BigInteger(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("installed_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("account_login", sa.String(length=255), nullable=False),
        sa.Column("account_type", sa.String(length=32), nullable=False),
        sa.Column("repository_selection", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('active', 'suspended', 'uninstalled')",
            name="ck_github_app_installation_status",
        ),
        sa.CheckConstraint(
            "repository_selection IN ('all', 'selected')",
            name="ck_github_app_repository_selection",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["installed_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("installation_id"),
    )
    op.create_index(
        "ix_github_app_installations_workspace_id",
        "github_app_installations",
        ["workspace_id"],
    )
    op.create_index(
        "ix_github_app_installations_installed_by_user_id",
        "github_app_installations",
        ["installed_by_user_id"],
    )

    op.create_table(
        "authorized_repositories",
        sa.Column("github_repository_id", sa.BigInteger(), nullable=False),
        sa.Column("installation_id", sa.BigInteger(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("owner_login", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=511), nullable=False),
        sa.Column("html_url", sa.String(length=2048), nullable=False),
        sa.Column("visibility", sa.String(length=16), nullable=False),
        sa.Column("default_branch", sa.String(length=255), nullable=True),
        sa.Column("is_archived", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "last_synced_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "visibility IN ('public', 'private')",
            name="ck_authorized_repository_visibility",
        ),
        sa.ForeignKeyConstraint(
            ["installation_id"],
            ["github_app_installations.installation_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("github_repository_id"),
    )
    op.create_index(
        "ix_authorized_repositories_installation_id",
        "authorized_repositories",
        ["installation_id"],
    )
    op.create_index(
        "ix_authorized_repositories_workspace_id",
        "authorized_repositories",
        ["workspace_id"],
    )
    op.create_index(
        "ix_authorized_repositories_full_name",
        "authorized_repositories",
        ["full_name"],
    )

    op.create_table(
        "github_app_states",
        sa.Column("state_hash", sa.String(length=64), nullable=False),
        sa.Column("purpose", sa.String(length=16), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("installation_id", sa.BigInteger(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("state_hash"),
    )
    op.create_index(
        "ix_github_app_states_user_id", "github_app_states", ["user_id"]
    )
    op.create_index(
        "ix_github_app_states_workspace_id",
        "github_app_states",
        ["workspace_id"],
    )
    op.create_index(
        "ix_github_app_states_expires_at",
        "github_app_states",
        ["expires_at"],
    )

    op.create_table(
        "github_webhook_deliveries",
        sa.Column("delivery_id", sa.String(length=128), nullable=False),
        sa.Column("event_name", sa.String(length=64), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("delivery_id"),
    )


def downgrade() -> None:
    op.drop_table("github_webhook_deliveries")
    op.drop_index("ix_github_app_states_expires_at", table_name="github_app_states")
    op.drop_index("ix_github_app_states_workspace_id", table_name="github_app_states")
    op.drop_index("ix_github_app_states_user_id", table_name="github_app_states")
    op.drop_table("github_app_states")
    op.drop_index(
        "ix_authorized_repositories_full_name", table_name="authorized_repositories"
    )
    op.drop_index(
        "ix_authorized_repositories_workspace_id",
        table_name="authorized_repositories",
    )
    op.drop_index(
        "ix_authorized_repositories_installation_id",
        table_name="authorized_repositories",
    )
    op.drop_table("authorized_repositories")
    op.drop_index(
        "ix_github_app_installations_installed_by_user_id",
        table_name="github_app_installations",
    )
    op.drop_index(
        "ix_github_app_installations_workspace_id",
        table_name="github_app_installations",
    )
    op.drop_table("github_app_installations")
