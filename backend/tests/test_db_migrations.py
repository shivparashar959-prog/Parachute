"""Reversible initial migration tests on an isolated fresh database."""

import os

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from app.config import get_settings


EXPECTED_TABLES = {
    "users",
    "user_identities",
    "auth_sessions",
    "workspaces",
    "workspace_memberships",
    "oauth_login_states",
    "login_rate_limits",
    "github_app_installations",
    "authorized_repositories",
    "github_app_states",
    "github_webhook_deliveries",
    "analyses",
    "analysis_findings",
    "gemini_spend_reservations",
    "pull_request_automation_results",
}
EXPECTED_ANALYSIS_JOB_COLUMNS = {
    "attempt_count",
    "progress_percent",
    "cancellation_requested",
    "scratch_cleanup_status",
    "idempotency_key_hash",
    "request_fingerprint",
    "queued_at",
    "started_at",
    "last_heartbeat_at",
    "last_dispatched_at",
}


def test_fresh_database_migrates_up_down_and_up(monkeypatch, tmp_path):
    postgres_url = os.getenv("TEST_POSTGRES_URL")
    if postgres_url:
        database_url = postgres_url
    else:
        database_url = f"sqlite:///{tmp_path / 'migration-test.sqlite'}"

    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()
    alembic_config = Config("alembic.ini")

    try:
        command.upgrade(alembic_config, "head")
        engine = create_engine(database_url)
        assert EXPECTED_TABLES.issubset(set(inspect(engine).get_table_names()))
        assert EXPECTED_ANALYSIS_JOB_COLUMNS.issubset(
            {column["name"] for column in inspect(engine).get_columns("analyses")}
        )
        reservation_columns = {
            column["name"]: column
            for column in inspect(engine).get_columns("gemini_spend_reservations")
        }
        assert reservation_columns["analysis_id"]["nullable"] is True
        analysis_foreign_key = next(
            foreign_key
            for foreign_key in inspect(engine).get_foreign_keys(
                "gemini_spend_reservations"
            )
            if foreign_key["constrained_columns"] == ["analysis_id"]
        )
        assert analysis_foreign_key["options"]["ondelete"] == "SET NULL"
        command.check(alembic_config)

        command.downgrade(alembic_config, "base")
        assert not EXPECTED_TABLES.intersection(
            set(inspect(engine).get_table_names())
        )

        command.upgrade(alembic_config, "head")
        assert EXPECTED_TABLES.issubset(set(inspect(engine).get_table_names()))
        engine.dispose()
    finally:
        get_settings.cache_clear()
