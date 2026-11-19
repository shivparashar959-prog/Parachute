"""Hashed-actor login rate-limit buckets."""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LoginRateLimit(Base):
    __tablename__ = "login_rate_limits"

    actor_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    window_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True
    )
    request_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
