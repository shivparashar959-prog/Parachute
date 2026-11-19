"""Origin checks for state-changing requests authenticated by browser cookies."""

from fastapi import HTTPException, Request, status


def require_trusted_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if not origin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="A trusted request origin is required.",
        )

    from app.main import get_allowed_cors_origins

    if origin not in set(get_allowed_cors_origins()):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Request origin is not allowed.",
        )

    fetch_site = request.headers.get("sec-fetch-site", "").lower()
    if fetch_site in {"cross-site", "none"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cross-site state changes are not allowed.",
        )
