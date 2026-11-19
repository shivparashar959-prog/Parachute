"""Idempotency records for signed GitHub webhook deliveries."""

from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class GitHubWebhookDelivery(Base):
    __tablename__ = "github_webhook_deliveries"

    delivery_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    event_name: Mapped[str] = mapped_column(String(64), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
