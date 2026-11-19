"""Authenticated-principal lookup from opaque, hashed browser sessions."""

import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.config import get_settings
from app.db.session import get_db
from app.models import AuthSession, User


@dataclass(frozen=True)
class AuthenticatedPrincipal:
    user: User
    session: AuthSession


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def get_current_principal(
    request: Request,
    db: Session = Depends(get_db),
) -> AuthenticatedPrincipal:
    settings = get_settings()
    raw_token = request.cookies.get(settings.session_cookie_name)
    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication is required.",
        )

    auth_session = db.scalar(
        select(AuthSession)
        .options(joinedload(AuthSession.user))
        .where(AuthSession.token_hash == hash_session_token(raw_token))
    )
    if (
        auth_session is None
        or auth_session.revoked_at is not None
        or _utc(auth_session.expires_at) <= datetime.now(timezone.utc)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication is required.",
        )
    now = datetime.now(timezone.utc)
    if _utc(auth_session.last_seen_at) + timedelta(minutes=5) <= now:
        auth_session.last_seen_at = now
        db.commit()

    if not isinstance(auth_session.user_id, uuid.UUID):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication is required.",
        )
    return AuthenticatedPrincipal(user=auth_session.user, session=auth_session)
