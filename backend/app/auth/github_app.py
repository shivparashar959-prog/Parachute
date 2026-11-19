"""Short-lived GitHub App authentication and bounded REST API requests."""

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import httpx
from joserfc import jwt

from app.config import get_settings

GITHUB_API_URL = "https://api.github.com"
GITHUB_OAUTH_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_API_VERSION = "2022-11-28"
GITHUB_HTTP_TIMEOUT_SECONDS = 12.0
MAX_GITHUB_PAGES = 10
GITHUB_PAGE_SIZE = 100


class GitHubAppError(RuntimeError):
    """Base class for safe GitHub App integration errors."""


class GitHubAppNotConfiguredError(GitHubAppError):
    pass


class GitHubAppAccessError(GitHubAppError):
    pass


class GitHubAppRateLimitError(GitHubAppError):
    def __init__(self, retry_after: int | None = None):
        super().__init__("GitHub API rate limit reached.")
        self.retry_after = retry_after


class GitHubAppUpstreamError(GitHubAppError):
    pass


@dataclass(frozen=True)
class InstallationAccessToken:
    value: str = field(repr=False)
    expires_at: datetime


def _require_configured() -> None:
    if not get_settings().github_app_configured:
        raise GitHubAppNotConfiguredError("GitHub App integration is not configured.")


def create_app_jwt(now: int | None = None) -> str:
    _require_configured()
    settings = get_settings()
    current_time = int(time.time()) if now is None else now
    claims = {
        "iss": settings.github_app_id,
        "iat": current_time - 60,
        "exp": current_time + 8 * 60,
    }
    try:
        return jwt.encode(
            {"alg": "RS256"},
            claims,
            settings.github_app_private_key,
            algorithms=["RS256"],
        )
    except (TypeError, ValueError) as exc:
        raise GitHubAppNotConfiguredError(
            "GitHub App private-key configuration is invalid."
        ) from exc


def _parse_retry_after(response: httpx.Response) -> int | None:
    retry_after = response.headers.get("Retry-After")
    if retry_after:
        try:
            return max(1, min(int(retry_after), 3600))
        except ValueError:
            pass

    reset = response.headers.get("X-RateLimit-Reset")
    if reset:
        try:
            return max(1, min(int(reset) - int(time.time()), 3600))
        except ValueError:
            pass
    return None


def _api_request(
    method: str,
    path: str,
    *,
    token: str | None = None,
    app_auth: bool = False,
    json_body: dict[str, Any] | None = None,
) -> dict[str, Any] | list[Any]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
        "User-Agent": "DocGuard",
    }
    if app_auth:
        headers["Authorization"] = f"Bearer {create_app_jwt()}"
    elif token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        response = httpx.request(
            method,
            f"{GITHUB_API_URL}{path}",
            headers=headers,
            json=json_body,
            timeout=GITHUB_HTTP_TIMEOUT_SECONDS,
        )
    except httpx.TimeoutException as exc:
        raise GitHubAppUpstreamError("GitHub API request timed out.") from exc
    except httpx.HTTPError as exc:
        raise GitHubAppUpstreamError("GitHub API request failed.") from exc

    rate_limited = response.status_code == 429 or (
        response.status_code == 403
        and (
            response.headers.get("X-RateLimit-Remaining") == "0"
            or bool(response.headers.get("Retry-After"))
            or "rate limit" in response.text.lower()
        )
    )
    if rate_limited:
        raise GitHubAppRateLimitError(_parse_retry_after(response))
    if response.status_code in {401, 403, 404}:
        raise GitHubAppAccessError("GitHub did not authorize this repository request.")
    if not response.is_success:
        raise GitHubAppUpstreamError("GitHub API request failed.")
    try:
        payload = response.json()
    except ValueError as exc:
        raise GitHubAppUpstreamError("GitHub returned an invalid response.") from exc
    if not isinstance(payload, (dict, list)):
        raise GitHubAppUpstreamError("GitHub returned an invalid response.")
    return payload


def verify_installation(installation_id: int) -> dict[str, Any]:
    _require_configured()
    if installation_id <= 0:
        raise GitHubAppAccessError("GitHub installation is unavailable.")
    installation = _api_request(
        "GET",
        f"/app/installations/{installation_id}",
        app_auth=True,
    )
    if not isinstance(installation, dict):
        raise GitHubAppUpstreamError("GitHub returned invalid installation metadata.")
    settings = get_settings()
    try:
        returned_id = int(installation["id"])
        app_id = int(installation["app_id"])
        account = installation["account"]
        account_id = int(account["id"])
        account_login = str(account["login"])
        account_type = str(account["type"])
        repository_selection = str(installation["repository_selection"])
    except (KeyError, TypeError, ValueError) as exc:
        raise GitHubAppUpstreamError("GitHub returned invalid installation metadata.") from exc
    if (
        returned_id != installation_id
        or app_id != int(settings.github_app_id)
        or account_id <= 0
        or not account_login
        or repository_selection not in {"all", "selected"}
    ):
        raise GitHubAppAccessError("GitHub installation could not be verified.")
    return {
        "installation_id": returned_id,
        "app_id": app_id,
        "account_id": account_id,
        "account_login": account_login,
        "account_type": account_type,
        "repository_selection": repository_selection,
        "suspended": installation.get("suspended_at") is not None,
    }


def create_installation_access_token(
    installation_id: int,
    repository_ids: list[int] | None = None,
) -> InstallationAccessToken:
    _require_configured()
    if installation_id <= 0:
        raise GitHubAppAccessError("GitHub installation is unavailable.")
    body = None
    if repository_ids is not None:
        if not repository_ids or any(value <= 0 for value in repository_ids):
            raise GitHubAppAccessError("Repository authorization is unavailable.")
        body = {"repository_ids": repository_ids}
    payload = _api_request(
        "POST",
        f"/app/installations/{installation_id}/access_tokens",
        app_auth=True,
        json_body=body,
    )
    if not isinstance(payload, dict):
        raise GitHubAppUpstreamError("GitHub returned invalid installation credentials.")
    value = payload.get("token")
    expires_value = payload.get("expires_at")
    if not isinstance(value, str) or not value or not isinstance(expires_value, str):
        raise GitHubAppUpstreamError("GitHub returned invalid installation credentials.")
    try:
        expires_at = datetime.fromisoformat(expires_value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise GitHubAppUpstreamError(
            "GitHub returned invalid installation credentials."
        ) from exc
    if expires_at.tzinfo is None or expires_at <= datetime.now(timezone.utc):
        raise GitHubAppUpstreamError("GitHub returned expired installation credentials.")
    return InstallationAccessToken(value=value, expires_at=expires_at)


def list_installation_repositories(
    access_token: str,
) -> list[dict[str, Any]]:
    repositories: list[dict[str, Any]] = []
    for page in range(1, MAX_GITHUB_PAGES + 1):
        payload = _api_request(
            "GET",
            f"/installation/repositories?per_page={GITHUB_PAGE_SIZE}&page={page}",
            token=access_token,
        )
        if not isinstance(payload, dict):
            raise GitHubAppUpstreamError("GitHub returned invalid repository metadata.")
        current = payload.get("repositories")
        if not isinstance(current, list):
            raise GitHubAppUpstreamError("GitHub returned invalid repository metadata.")
        repositories.extend(item for item in current if isinstance(item, dict))
        total_count = payload.get("total_count")
        if not isinstance(total_count, int) or len(repositories) >= total_count:
            return repositories[:total_count] if isinstance(total_count, int) else repositories
        if len(repositories) >= MAX_GITHUB_PAGES * GITHUB_PAGE_SIZE:
            break
    raise GitHubAppUpstreamError(
        f"GitHub installation exceeds the {MAX_GITHUB_PAGES * GITHUB_PAGE_SIZE} repository limit."
    )


def list_user_installations(access_token: str) -> list[dict[str, Any]]:
    installations: list[dict[str, Any]] = []
    for page in range(1, MAX_GITHUB_PAGES + 1):
        payload = _api_request(
            "GET",
            f"/user/installations?per_page={GITHUB_PAGE_SIZE}&page={page}",
            token=access_token,
        )
        if not isinstance(payload, dict):
            raise GitHubAppUpstreamError("GitHub returned invalid installation metadata.")
        current = payload.get("installations")
        if not isinstance(current, list):
            raise GitHubAppUpstreamError("GitHub returned invalid installation metadata.")
        installations.extend(item for item in current if isinstance(item, dict))
        total_count = payload.get("total_count")
        if not isinstance(total_count, int) or len(installations) >= total_count:
            return installations[:total_count] if isinstance(total_count, int) else installations
    raise GitHubAppUpstreamError(
        f"GitHub user exceeds the {MAX_GITHUB_PAGES * GITHUB_PAGE_SIZE} installation limit."
    )


def get_repository_by_id(
    github_repository_id: int,
    access_token: str,
) -> dict[str, Any]:
    if github_repository_id <= 0:
        raise GitHubAppAccessError("GitHub repository is unavailable.")
    return _api_request(
        "GET",
        f"/repositories/{github_repository_id}",
        token=access_token,
    )


def list_open_pull_requests(
    owner: str,
    name: str,
    access_token: str,
) -> list[dict[str, Any]]:
    safe_owner = quote(owner, safe="")
    safe_name = quote(name, safe="")
    payload = _api_request(
        "GET",
        f"/repos/{safe_owner}/{safe_name}/pulls?state=open&per_page=100&page=1",
        token=access_token,
    )
    if not isinstance(payload, list):
        raise GitHubAppUpstreamError("GitHub returned invalid pull request metadata.")
    return [item for item in payload[:100] if isinstance(item, dict)]


def exchange_user_authorization_code(code: str) -> str:
    _require_configured()
    if not code or len(code) > 2048:
        raise GitHubAppAccessError("GitHub authorization could not be verified.")
    settings = get_settings()
    try:
        response = httpx.post(
            GITHUB_OAUTH_TOKEN_URL,
            headers={
                "Accept": "application/json",
                "User-Agent": "DocGuard",
            },
            data={
                "client_id": settings.github_app_client_id,
                "client_secret": settings.github_app_client_secret,
                "code": code,
                "redirect_uri": settings.github_app_user_callback_url,
            },
            timeout=GITHUB_HTTP_TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as exc:
        raise GitHubAppUpstreamError("GitHub authorization request failed.") from exc
    if not response.is_success:
        raise GitHubAppAccessError("GitHub authorization could not be verified.")
    try:
        payload = response.json()
    except ValueError as exc:
        raise GitHubAppUpstreamError("GitHub returned an invalid authorization response.") from exc
    access_token = payload.get("access_token") if isinstance(payload, dict) else None
    if not isinstance(access_token, str) or not access_token:
        raise GitHubAppAccessError("GitHub authorization could not be verified.")
    return access_token


def get_authenticated_github_user(access_token: str) -> dict[str, Any]:
    payload = _api_request("GET", "/user", token=access_token)
    if not isinstance(payload, dict):
        raise GitHubAppUpstreamError("GitHub returned invalid user metadata.")
    return payload
