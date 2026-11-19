"""Add opt-in pull request automation and idempotent publication results.

Revision ID: 0006_pull_request_automation
Revises: 0005_preserve_spend_reservations
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0006_pull_request_automation"
down_revision: Union[str, None] = "0005_preserve_spend_reservations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "authorized_repositories",
        sa.Column(
            "pr_automation_enabled",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )
    op.create_table(
        "pull_request_automation_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("github_repository_id", sa.BigInteger(), nullable=False),
        sa.Column("analysis_id", sa.Uuid(), nullable=False),
        sa.Column("pull_request_number", sa.BigInteger(), nullable=False),
        sa.Column("base_sha", sa.String(length=40), nullable=False),
        sa.Column("head_sha", sa.String(length=40), nullable=False),
        sa.Column("check_run_id", sa.BigInteger(), nullable=True),
        sa.Column("published", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["github_repository_id"], ["authorized_repositories.github_repository_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["analysis_id"], ["analyses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("github_repository_id", "pull_request_number", "base_sha", "head_sha", name="uq_pr_automation_repo_pr_base_head"),
        sa.UniqueConstraint("analysis_id"),
    )
    op.create_index(
        "ix_pull_request_automation_results_workspace_id",
        "pull_request_automation_results",
        ["workspace_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_pull_request_automation_results_workspace_id",
        table_name="pull_request_automation_results",
    )
    op.drop_table("pull_request_automation_results")
    op.drop_column("authorized_repositories", "pr_automation_enabled")
