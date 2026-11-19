"""Persist deterministic analyses and bounded Gemini usage reservations.

Revision ID: 0003_persisted_analysis_and_ai_budget
Revises: 0002_github_app_repository_catalog
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003_persisted_analysis_and_ai_budget"
down_revision: Union[str, None] = "0002_github_app_repository_catalog"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("authorized_repositories") as batch_op:
        batch_op.create_unique_constraint(
            "uq_authorized_repository_id_workspace",
            ["github_repository_id", "workspace_id"],
        )

    op.create_table(
        "analyses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("github_repository_id", sa.BigInteger(), nullable=False),
        sa.Column("base_commit", sa.String(length=40), nullable=False),
        sa.Column("head_commit", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("summary", sa.JSON(), nullable=True),
        sa.Column("error_category", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')",
            name="ck_analysis_status",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["github_repository_id", "workspace_id"],
            [
                "authorized_repositories.github_repository_id",
                "authorized_repositories.workspace_id",
            ],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_analyses_workspace_created", "analyses", ["workspace_id", "created_at"]
    )
    op.create_index(
        "ix_analyses_user_created",
        "analyses",
        ["created_by_user_id", "created_at"],
    )

    op.create_table(
        "analysis_findings",
        sa.Column("analysis_id", sa.Uuid(), nullable=False),
        sa.Column("finding_id", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["analysis_id"], ["analyses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("analysis_id", "finding_id"),
    )
    op.create_index(
        "ix_analysis_findings_status", "analysis_findings", ["analysis_id", "status"]
    )

    op.create_table(
        "gemini_spend_reservations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_id", sa.Uuid(), nullable=False),
        sa.Column("model_name", sa.String(length=128), nullable=False),
        sa.Column("reserved_usd", sa.Numeric(12, 6), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["analysis_id"], ["analyses.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_gemini_spend_reservations_workspace_id",
        "gemini_spend_reservations",
        ["workspace_id"],
    )
    op.create_index(
        "ix_gemini_spend_reservations_user_id",
        "gemini_spend_reservations",
        ["user_id"],
    )
    op.create_index(
        "ix_gemini_spend_reservations_analysis_id",
        "gemini_spend_reservations",
        ["analysis_id"],
    )
    op.create_index(
        "ix_gemini_spend_reservations_created_at",
        "gemini_spend_reservations",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_gemini_spend_reservations_created_at",
        table_name="gemini_spend_reservations",
    )
    op.drop_index(
        "ix_gemini_spend_reservations_analysis_id",
        table_name="gemini_spend_reservations",
    )
    op.drop_index(
        "ix_gemini_spend_reservations_user_id",
        table_name="gemini_spend_reservations",
    )
    op.drop_index(
        "ix_gemini_spend_reservations_workspace_id",
        table_name="gemini_spend_reservations",
    )
    op.drop_table("gemini_spend_reservations")
    op.drop_index("ix_analysis_findings_status", table_name="analysis_findings")
    op.drop_table("analysis_findings")
    op.drop_index("ix_analyses_user_created", table_name="analyses")
    op.drop_index("ix_analyses_workspace_created", table_name="analyses")
    op.drop_table("analyses")
    with op.batch_alter_table("authorized_repositories") as batch_op:
        batch_op.drop_constraint(
            "uq_authorized_repository_id_workspace",
            type_="unique",
        )
