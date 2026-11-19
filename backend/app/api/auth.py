"""GitHub OAuth sign-in, personal workspace provisioning, and session endpoints."""

import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit

from authlib.integrations.base_client.errors import OAuthError
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
import httpx
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.csrf import require_trusted_origin
from app.auth.dependencies import AuthenticatedPrincipal, get_current_principal
from app.auth.github_oauth import get_github_oauth_client
from app.auth.sessions import issue_session, revoke_session
from app.config import ConfigurationError, get_settings
from app.db.session import get_db
from app.models import (
    LoginRateLimit,
    OAuthLoginState,
    User,
    UserIdentity,
    Workspace,
    WorkspaceMembership,
)
from app.schemas.auth import (
    AuthStatusResponse,
    CurrentSessionResponse,
    UserSummary,
    WorkspaceSummary,
)

router = APIRouter(prefix="/api/auth", tags=["Authentication"])
GITHUB_ISSUER = "https://github.com"
LOGIN_RATE_LIMIT = 10
LOGIN_RATE_WINDOW_SECONDS = 60
OAUTH_STATE_TTL_SECONDS = 600


def _state_hash(state: str) -> str:
    return hashlib.sha256(state.encode("utf-8")).hexdigest()


def _login_actor_hash(request: Request) -> str:
    settings = get_settings()
    address = request.client.host if request.client else "unknown"
    key = settings.github_oauth_client_secret.encode("utf-8")
    return hmac.new(key, address.encode("utf-8"), hashlib.sha256).hexdigest()


def _increment_login_rate_limit(db: Session, request: Request) -> bool:
    now = datetime.now(timezone.utc)
    window_epoch = int(now.timestamp()) // LOGIN_RATE_WINDOW_SECONDS
    window_start = datetime.fromtimestamp(
        window_epoch * LOGIN_RATE_WINDOW_SECONDS, tz=timezone.utc
    )
    values = {
        "actor_hash": _login_actor_hash(request),
        "window_start": window_start,
        "request_count": 1,
    }
    dialect_name = db.get_bind().dialect.name
    if dialect_name == "postgresql":
        statement = pg_insert(LoginRateLimit).values(**values)
    elif dialect_name == "sqlite":
        statement = sqlite_insert(LoginRateLimit).values(**values)
    else:
        raise RuntimeError("The configured database does not support login throttling.")

    statement = statement.on_conflict_do_update(
        index_elements=["actor_hash", "window_start"],
        set_={"request_count": LoginRateLimit.request_count + 1},
    ).returning(LoginRateLimit.request_count)
    request_count = db.execute(statement).scalar_one()
    if int(now.timestamp()) % 3600 < LOGIN_RATE_WINDOW_SECONDS:
        db.execute(
            delete(LoginRateLimit).where(
                LoginRateLimit.window_start
                < now - timedelta(hours=2)
            )
        )
    db.commit()
    return request_count > LOGIN_RATE_LIMIT


def _oauth_configuration_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="GitHub sign-in is not configured.",
    )


@router.get("/status", response_model=AuthStatusResponse)
def read_auth_status() -> AuthStatusResponse:
    return AuthStatusResponse(
        sign_in_enabled=get_settings().github_oauth_configured
    )


@router.get("/login")
async def start_github_sign_in(
    request: Request,
    db: Session = Depends(get_db),
):
    settings = get_settings()
    if not settings.github_oauth_configured or len(
        settings.github_oauth_state_secret
    ) < 32:
        raise _oauth_configuration_error()
    if _increment_login_rate_limit(db, request):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many sign-in attempts. Try again shortly.",
        )

    try:
        client = get_github_oauth_client()
        redirect_response = await client.authorize_redirect(
            request, settings.github_oauth_redirect_uri
        )
        state_values = parse_qs(urlsplit(redirect_response.headers["location"]).query)
        state = state_values.get("state", [None])[0]
        if not state:
            raise RuntimeError("OAuth provider did not return a state value.")
        now = datetime.now(timezone.utc)
        db.execute(delete(OAuthLoginState).where(OAuthLoginState.expires_at < now))
        db.add(
            OAuthLoginState(
                state_hash=_state_hash(state),
                expires_at=now + timedelta(seconds=OAUTH_STATE_TTL_SECONDS),
            )
        )
        db.commit()
        return redirect_response
    except ConfigurationError as exc:
        raise _oauth_configuration_error() from exc


def _verified_github_profile(profile: object) -> tuple[str, str]:
    if not isinstance(profile, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="GitHub sign-in could not verify the account.",
        )
    github_id = profile.get("id")
    login = profile.get("login")
    if not isinstance(github_id, (int, str)) or not str(github_id).isdigit():
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="GitHub sign-in could not verify the account.",
        )
    if not isinstance(login, str) or not login.strip():
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="GitHub sign-in could not verify the account.",
        )
    name = profile.get("name")
    display_name = name.strip() if isinstance(name, str) and name.strip() else login
    return str(github_id), display_name[:200]


def _get_or_create_user(
    db: Session,
    subject: str,
    display_name: str,
    email: str | None,
) -> User:
    identity = db.scalar(
        select(UserIdentity).where(
            UserIdentity.issuer == GITHUB_ISSUER,
            UserIdentity.subject == subject,
        )
    )
    if identity is not None:
        identity.user.display_name = display_name
        identity.user.email = email
        identity.user.last_login_at = datetime.now(timezone.utc)
        db.commit()
        return identity.user

    user = User(
        display_name=display_name,
        email=email,
        last_login_at=datetime.now(timezone.utc),
    )
    db.add(user)
    try:
        db.flush()
        db.add(
            UserIdentity(
                user_id=user.id,
                issuer=GITHUB_ISSUER,
                subject=subject,
            )
        )
        workspace = Workspace(
            name=f"{display_name}'s workspace"[:120],
            workspace_type="personal",
            personal_owner_user_id=user.id,
        )
        db.add(workspace)
        db.flush()
        db.add(
            WorkspaceMembership(
                workspace_id=workspace.id,
                user_id=user.id,
                role="owner",
            )
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        identity = db.scalar(
            select(UserIdentity).where(
                UserIdentity.issuer == GITHUB_ISSUER,
                UserIdentity.subject == subject,
            )
        )
        if identity is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Account sign-in could not be completed.",
            ) from None
        return identity.user
    return user


@router.get("/callback")
async def complete_github_sign_in(
    request: Request,
    state: str,
    db: Session = Depends(get_db),
):
    settings = get_settings()
    if not settings.github_oauth_configured or len(
        settings.github_oauth_state_secret
    ) < 32:
        raise _oauth_configuration_error()

    now = datetime.now(timezone.utc)
    saved_state = db.scalar(
        select(OAuthLoginState).where(
            OAuthLoginState.state_hash == _state_hash(state),
            OAuthLoginState.expires_at > now,
        )
    )
    if saved_state is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Sign-in request is invalid or expired.",
        )
    db.delete(saved_state)
    db.commit()

    try:
        client = get_github_oauth_client()
        token = await client.authorize_access_token(request)
        user_response = await client.get("user", token=token)
        user_response.raise_for_status()
        profile = user_response.json()
        subject, display_name = _verified_github_profile(profile)
        email_response = await client.get("user/emails", token=token)
        email_response.raise_for_status()
        emails = email_response.json()
        email = None
        if isinstance(emails, list):
            primary_verified = next(
                (
                    entry.get("email")
                    for entry in emails
                    if isinstance(entry, dict)
                    and entry.get("primary") is True
                    and entry.get("verified") is True
                    and isinstance(entry.get("email"), str)
                ),
                None,
            )
            if primary_verified:
                email = primary_verified[:320]
    except HTTPException:
        raise
    except OAuthError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GitHub sign-in could not be completed.",
        ) from None
    except ConfigurationError:
        raise _oauth_configuration_error() from None
    except httpx.HTTPError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="GitHub sign-in could not be completed.",
        ) from None
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="GitHub sign-in could not be completed.",
        ) from None
    except AttributeError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="GitHub sign-in could not be completed.",
        ) from None

    user = _get_or_create_user(db, subject, display_name, email)
    response = RedirectResponse(
        url=f"{settings.frontend_origin}/", status_code=status.HTTP_303_SEE_OTHER
    )
    previous_token = request.cookies.get(settings.session_cookie_name)
    issue_session(db, user.id, response, previous_token=previous_token)
    return response


@router.get("/me", response_model=CurrentSessionResponse)
def read_current_session(
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> CurrentSessionResponse:
    workspace = db.scalar(
        select(Workspace).where(
            Workspace.personal_owner_user_id == principal.user.id
        )
    )
    if workspace is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Personal workspace is unavailable.",
        )
    membership = db.get(
        WorkspaceMembership,
        {
            "workspace_id": workspace.id,
            "user_id": principal.user.id,
        },
    )
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Personal workspace membership is unavailable.",
        )
    return CurrentSessionResponse(
        user=UserSummary(
            id=principal.user.id,
            display_name=principal.user.display_name,
            email=principal.user.email,
        ),
        workspace=WorkspaceSummary(
            id=workspace.id,
            name=workspace.name,
            role=membership.role,
        ),
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> Response:
    require_trusted_origin(request)
    revoke_session(db, principal.session)
    response.delete_cookie(
        key=get_settings().session_cookie_name,
        path="/",
        httponly=True,
        secure=get_settings().session_cookie_secure,
        samesite=get_settings().session_cookie_samesite,
    )
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
