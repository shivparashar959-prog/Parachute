"""Add durable job lifecycle and dispatch metadata to analyses.

Revision ID: 0004_durable_analysis_jobs
Revises: 0003_persisted_analysis_and_ai_budget
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004_durable_analysis_jobs"
down_revision: Union[str, None] = "0003_persisted_analysis_and_ai_budget"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "analyses",
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "analyses",
        sa.Column(
            "progress_percent", sa.Integer(), server_default="0", nullable=False
        ),
    )
    op.add_column(
        "analyses",
        sa.Column(
            "cancellation_requested",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )
    op.add_column(
        "analyses",
        sa.Column(
            "scratch_cleanup_status",
            sa.String(length=16),
            server_default="not_started",
            nullable=False,
        ),
    )
    op.add_column(
        "analyses", sa.Column("idempotency_key_hash", sa.String(length=64))
    )
    op.add_column(
        "analyses", sa.Column("request_fingerprint", sa.String(length=64))
    )
    op.add_column(
        "analyses",
        sa.Column(
            "queued_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.add_column(
        "analyses", sa.Column("started_at", sa.DateTime(timezone=True))
    )
    op.add_column(
        "analyses", sa.Column("last_heartbeat_at", sa.DateTime(timezone=True))
    )
    op.add_column(
        "analyses", sa.Column("last_dispatched_at", sa.DateTime(timezone=True))
    )

    with op.batch_alter_table("analyses") as batch_op:
        batch_op.create_check_constraint(
            "ck_analysis_progress_percent",
            "progress_percent >= 0 AND progress_percent <= 100",
        )
        batch_op.create_check_constraint(
            "ck_analysis_attempt_count", "attempt_count >= 0"
        )
        batch_op.create_check_constraint(
            "ck_analysis_scratch_cleanup_status",
            "scratch_cleanup_status IN ('not_started', 'pending', 'complete', 'failed')",
        )
        batch_op.create_unique_constraint(
            "uq_analysis_idempotency_key",
            ["workspace_id", "created_by_user_id", "idempotency_key_hash"],
        )

    op.create_index(
        "ix_analyses_status_queued", "analyses", ["status", "queued_at"]
    )
    op.create_index(
        "ix_analyses_status_heartbeat",
        "analyses",
        ["status", "last_heartbeat_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_analyses_status_heartbeat", table_name="analyses")
    op.drop_index("ix_analyses_status_queued", table_name="analyses")
    with op.batch_alter_table("analyses") as batch_op:
        batch_op.drop_constraint("uq_analysis_idempotency_key", type_="unique")
        batch_op.drop_constraint(
            "ck_analysis_scratch_cleanup_status", type_="check"
        )
        batch_op.drop_constraint("ck_analysis_attempt_count", type_="check")
        batch_op.drop_constraint("ck_analysis_progress_percent", type_="check")
    op.drop_column("analyses", "last_dispatched_at")
    op.drop_column("analyses", "last_heartbeat_at")
    op.drop_column("analyses", "started_at")
    op.drop_column("analyses", "queued_at")
    op.drop_column("analyses", "request_fingerprint")
    op.drop_column("analyses", "idempotency_key_hash")
    op.drop_column("analyses", "scratch_cleanup_status")
    op.drop_column("analyses", "cancellation_requested")
    op.drop_column("analyses", "progress_percent")
    op.drop_column("analyses", "attempt_count")
