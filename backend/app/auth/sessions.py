"""Creation, rotation, and revocation of opaque authentication sessions."""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import hash_session_token
from app.config import get_settings
from app.models import AuthSession


def issue_session(
    db: Session,
    user_id,
    response: Response,
    previous_token: str | None = None,
) -> None:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    if previous_token:
        previous_session = db.scalar(
            select(AuthSession).where(
                AuthSession.token_hash == hash_session_token(previous_token),
                AuthSession.revoked_at.is_(None),
            )
        )
        if previous_session is not None:
            previous_session.revoked_at = now

    raw_token = secrets.token_urlsafe(32)
    db.add(
        AuthSession(
            user_id=user_id,
            token_hash=hash_session_token(raw_token),
            created_at=now,
            last_seen_at=now,
            expires_at=now + timedelta(seconds=settings.session_ttl_seconds),
        )
    )
    db.commit()
    response.set_cookie(
        key=settings.session_cookie_name,
        value=raw_token,
        max_age=settings.session_ttl_seconds,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,
        path="/",
    )


def revoke_session(db: Session, session: AuthSession) -> None:
    if session.revoked_at is None:
        session.revoked_at = datetime.now(timezone.utc)
        db.commit()
