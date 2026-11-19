"""Public, credential-free GitHub App and repository catalog responses."""

from pydantic import BaseModel, ConfigDict, Field


class GitHubAppStatusResponse(BaseModel):
    configured: bool
    connected: bool
    installation_count: int


class GitHubAppInstallationSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    installation_id: int
    account_login: str
    account_type: str
    repository_selection: str
    status: str


class GitHubAppStatusDetailResponse(GitHubAppStatusResponse):
    installations: list[GitHubAppInstallationSummary] = Field(default_factory=list)


class InstallationStartResponse(BaseModel):
    installation_url: str


class AuthorizedRepositoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    github_repository_id: int
    installation_id: int
    owner_login: str
    name: str
    full_name: str
    html_url: str
    visibility: str
    default_branch: str | None
    is_archived: bool


class AuthorizedRepositoryListResponse(BaseModel):
    repositories: list[AuthorizedRepositoryResponse]


class PullRequestSummary(BaseModel):
    number: int
    title: str
    state: str
    html_url: str
    author: str
    base_ref: str
    base_sha: str
    head_ref: str
    head_sha: str


class PullRequestListResponse(BaseModel):
    github_repository_id: int
    pull_requests: list[PullRequestSummary]


class GitHubWebhookAcceptedResponse(BaseModel):
    accepted: bool
    duplicate: bool = False
