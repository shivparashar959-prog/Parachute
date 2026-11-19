"""Preserve spend accounting when analysis history is deleted.

Revision ID: 0005_preserve_spend_reservations
Revises: 0004_durable_analysis_jobs
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0005_preserve_spend_reservations"
down_revision: Union[str, None] = "0004_durable_analysis_jobs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _analysis_foreign_key_name() -> str | None:
    inspector = sa.inspect(op.get_bind())
    for foreign_key in inspector.get_foreign_keys("gemini_spend_reservations"):
        if (
            foreign_key["constrained_columns"] == ["analysis_id"]
            and foreign_key["referred_table"] == "analyses"
        ):
            return foreign_key["name"] or (
                "fk_gemini_spend_reservations_analysis_id_analyses"
            )
    raise RuntimeError("The Gemini spend analysis foreign key is missing.")


def upgrade() -> None:
    foreign_key_name = _analysis_foreign_key_name()
    naming_convention = {
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"
    }
    with op.batch_alter_table(
        "gemini_spend_reservations",
        naming_convention=naming_convention,
    ) as batch_op:
        batch_op.drop_constraint(op.f(foreign_key_name), type_="foreignkey")
        batch_op.alter_column(
            "analysis_id",
            existing_type=sa.Uuid(),
            nullable=True,
        )
        batch_op.create_foreign_key(
            op.f("fk_gemini_spend_reservations_analysis_id_analyses"),
            "analyses",
            ["analysis_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    bind = op.get_bind()
    reservation_table = sa.table(
        "gemini_spend_reservations",
        sa.column("analysis_id", sa.Uuid()),
    )
    has_orphaned_reservations = bind.execute(
        sa.select(sa.literal(1))
        .select_from(reservation_table)
        .where(reservation_table.c.analysis_id.is_(None))
        .limit(1)
    ).first()
    if has_orphaned_reservations:
        raise RuntimeError(
            "Cannot restore required analysis references while deleted analyses "
            "have retained spend reservations."
        )

    foreign_key_name = _analysis_foreign_key_name()
    naming_convention = {
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"
    }
    with op.batch_alter_table(
        "gemini_spend_reservations",
        naming_convention=naming_convention,
    ) as batch_op:
        batch_op.drop_constraint(op.f(foreign_key_name), type_="foreignkey")
        batch_op.alter_column(
            "analysis_id",
            existing_type=sa.Uuid(),
            nullable=False,
        )
        batch_op.create_foreign_key(
            op.f("fk_gemini_spend_reservations_analysis_id_analyses"),
            "analyses",
            ["analysis_id"],
            ["id"],
            ondelete="CASCADE",
        )
