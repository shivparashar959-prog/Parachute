"""
Pydantic models for Milestone 2: GitHub Repository Inspection & Commit Comparison.
"""

from typing import Literal, Optional
from pydantic import BaseModel, Field


class RepositoryInspectRequest(BaseModel):
    """Request payload for POST /api/repositories/inspect."""

    repository_url: str = Field(
        ...,
        description="Public HTTPS GitHub repository URL (e.g. https://github.com/pallets/flask)",
        examples=["https://github.com/pallets/flask"],
    )


class CommitInfo(BaseModel):
    """Metadata for a single Git commit."""

    sha: str = Field(..., description="Full 40-character commit SHA")
    short_sha: str = Field(..., description="Short 7-character commit SHA")
    message: str = Field(..., description="Commit summary message")
    author: str = Field(..., description="Commit author name")
    timestamp: str = Field(..., description="Commit timestamp in ISO 8601 format")


class RepositoryInspectResponse(BaseModel):
    """Response payload for POST /api/repositories/inspect."""

    repository_url: str
    owner: str
    name: str
    default_branch: str
    commits: list[CommitInfo]


class RepositoryCompareRequest(BaseModel):
    """Request payload for POST /api/repositories/compare."""

    repository_url: str = Field(
        ...,
        description="Public HTTPS GitHub repository URL",
        examples=["https://github.com/pallets/flask"],
    )
    base_commit: str = Field(
        ...,
        description="Base commit SHA (older/starting commit)",
    )
    head_commit: str = Field(
        ...,
        description="Head commit SHA (newer/target commit)",
    )


class FileDiffItem(BaseModel):
    """Detailed diff information for a single changed file between two commits."""

    file_path: str = Field(..., description="Path of the changed file")
    previous_path: Optional[str] = Field(
        default=None,
        description="Original file path when the file was renamed",
    )
    change_type: Literal["added", "modified", "deleted", "renamed"] = Field(
        ...,
        description="Category of file change",
    )
    additions: int = Field(..., description="Number of added lines (+)")
    deletions: int = Field(..., description="Number of removed lines (-)")
    patch: str = Field(..., description="Unified diff patch content")
    is_binary: bool = Field(default=False, description="True if the file is binary")
    truncated: bool = Field(
        default=False,
        description="True if the file diff patch was truncated due to size limits",
    )


class RepositoryCompareResponse(BaseModel):
    """Response payload for POST /api/repositories/compare."""

    repository_url: str
    owner: str
    name: str
    base_commit: str
    head_commit: str
    total_changed_files: int
    added_files: list[str]
    modified_files: list[str]
    deleted_files: list[str]
    renamed_files: list[str]
    file_paths: list[str]
    total_additions: int
    total_deletions: int
    files: list[FileDiffItem]
    diff_truncated: bool = False
