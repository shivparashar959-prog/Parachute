"""Safe current-user and workspace response schemas."""

import uuid

from pydantic import BaseModel, ConfigDict


class AuthStatusResponse(BaseModel):
    sign_in_enabled: bool
    github_oauth_enabled: bool


class UserSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    display_name: str
    email: str | None


class WorkspaceSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    role: str


class CurrentSessionResponse(BaseModel):
    user: UserSummary
    workspace: WorkspaceSummary
