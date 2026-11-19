"""Add local email/password authentication credentials.

Revision ID: 0007_local_password_auth
Revises: 0006_pull_request_automation
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0007_local_password_auth"
down_revision: Union[str, None] = "0006_pull_request_automation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "password_credentials",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("password_hash", sa.String(length=256), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_password_credentials_user_id",
        "password_credentials",
        ["user_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_password_credentials_user_id",
        table_name="password_credentials",
    )
    op.drop_table("password_credentials")
