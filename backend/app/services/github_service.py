"""
GitHub Repository Integration Service for DocGuard (Milestone 2).

Responsibilities:
- Strict validation of public HTTPS GitHub repository URLs and commit SHAs.
- Ephemeral bare cloning into temporary directories with guaranteed cleanup.
- Retrieving default branch metadata and recent commit history via GitPython.
- Computing commit-to-commit file diffs (added, modified, deleted, renamed)
  with size bounds and binary file protection.
"""

from contextlib import contextmanager
from datetime import timezone
import os
import re
import shutil
import stat
import tempfile
from typing import Generator, Optional, Tuple
from urllib.parse import urlparse

import git
from git import Actor, Commit, GitCommandError, Repo
from git.exc import BadName, BadObject

from app.schemas.repository import (
    CommitInfo,
    FileDiffItem,
    RepositoryCompareResponse,
    RepositoryInspectResponse,
)

# Security & performance bounds
DEFAULT_COMMIT_LIMIT = 20
MAX_COMMIT_LIMIT = 50
CLONE_DEPTH_INSPECT = 75
CLONE_DEPTH_COMPARE = 100
GIT_OPERATION_TIMEOUT_SECONDS = 45
MAX_FILE_PATCH_CHARS = 20_000
MAX_TOTAL_PATCH_CHARS = 150_000
MAX_CHANGED_FILES = 150

ALLOWED_GITHUB_HOSTS = {"github.com", "www.github.com"}
_OWNER_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
_REPO_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
_COMMIT_SHA_PATTERN = re.compile(r"^[0-9a-fA-F]{7,40}$")


class RepositoryError(Exception):
    """Base exception for repository integration errors."""


class RepositoryValidationError(RepositoryError):
    """Raised when a repository URL or commit identifier fails security validation."""


class RepositoryNotFoundError(RepositoryError):
    """Raised when a GitHub repository does not exist or is not publicly accessible."""


class CommitNotFoundError(RepositoryError):
    """Raised when a requested commit SHA does not exist in the repository."""


class RepositoryEmptyError(RepositoryError):
    """Raised when a repository has no accessible commit history."""


class RepositoryNetworkError(RepositoryError):
    """Raised when cloning or fetching fails due to network errors or timeouts."""


def parse_and_validate_github_url(raw_url: str) -> Tuple[str, str, str, str]:
    """
    Validate that the provided string is a strict public HTTPS GitHub repository URL.

    Returns:
        (owner, repo_name, canonical_url, clone_url)

    Raises:
        RepositoryValidationError: If the URL is malformed, uses a non-HTTPS scheme,
        targets a non-GitHub domain, attempts path traversal, or has invalid owner/name.
    """
    if not raw_url or not isinstance(raw_url, str):
        raise RepositoryValidationError("A GitHub repository URL is required.")

    url = raw_url.strip()
    if not url:
        raise RepositoryValidationError("A GitHub repository URL is required.")

    # Reject control characters, backslashes, or local path patterns immediately
    if any(ch in url for ch in ("\x00", "\r", "\n", "\\")) or ".." in url:
        raise RepositoryValidationError(
            "Invalid repository URL: path traversal or local filesystem paths are not allowed."
        )

    parsed = urlparse(url)

    if parsed.scheme.lower() != "https":
        raise RepositoryValidationError(
            "Only HTTPS GitHub repository URLs are accepted (e.g. https://github.com/owner/repository)."
        )

    if parsed.username or parsed.password or parsed.port:
        raise RepositoryValidationError(
            "Repository URL must not contain credentials or custom ports."
        )

    hostname = (parsed.hostname or "").lower()
    if hostname not in ALLOWED_GITHUB_HOSTS or parsed.netloc.lower() not in ALLOWED_GITHUB_HOSTS:
        raise RepositoryValidationError(
            "Only public repositories hosted on github.com are supported."
        )

    if parsed.query or parsed.fragment:
        raise RepositoryValidationError(
            "Repository URL must not include query parameters or URL fragments."
        )

    path_segments = [seg for seg in parsed.path.strip("/").split("/") if seg]
    if len(path_segments) != 2:
        raise RepositoryValidationError(
            "Repository URL must point to a repository root: https://github.com/<owner>/<repository>."
        )

    owner, repo_segment = path_segments
    if repo_segment.endswith(".git"):
        repo_name = repo_segment[:-4]
    else:
        repo_name = repo_segment

    if not owner or not repo_name or repo_name in {".", ".."}:
        raise RepositoryValidationError("Invalid repository owner or repository name.")

    if not _OWNER_PATTERN.match(owner):
        raise RepositoryValidationError(
            f"Invalid GitHub repository owner '{owner}'."
        )

    if not _REPO_PATTERN.match(repo_name):
        raise RepositoryValidationError(
            f"Invalid GitHub repository name '{repo_name}'."
        )

    canonical_url = f"https://github.com/{owner}/{repo_name}"
    clone_url = f"https://github.com/{owner}/{repo_name}.git"
    return owner, repo_name, canonical_url, clone_url


def validate_commit_sha(commit_ref: str, label: str = "commit") -> str:
    """
    Strictly validate a commit identifier as a 7-to-40 character hexadecimal SHA.
    Prevents option injection (leading '-'), path traversal, and shell metacharacters.
    """
    if not commit_ref or not isinstance(commit_ref, str):
        raise RepositoryValidationError(f"A valid {label} SHA is required.")

    cleaned = commit_ref.strip()
    if not _COMMIT_SHA_PATTERN.match(cleaned):
        raise RepositoryValidationError(
            f"Invalid {label} '{cleaned}'. Must be a 7 to 40 character hexadecimal commit SHA."
        )

    return cleaned.lower()


def _remove_readonly(func, path, _exc_info):
    """Helper for shutil.rmtree on Windows to clear read-only flags on Git packfiles."""
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except OSError:
        pass


@contextmanager
def _temporary_repo_directory() -> Generator[Tuple[str, list[Repo]], None, None]:
    """
    Create an isolated temporary directory for cloning and guarantee its deletion
    along with closing any GitPython Repo handles.
    """
    temp_dir = tempfile.mkdtemp(prefix="docguard_repo_")
    repo_holder: list[Repo] = []
    try:
        yield temp_dir, repo_holder
    finally:
        for repo in repo_holder:
            try:
                repo.git.clear_cache()
            except Exception:
                pass
            try:
                repo.close()
            except Exception:
                pass
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, onerror=_remove_readonly)


def _get_git_env() -> dict[str, str]:
    """Return a non-interactive environment dictionary for Git operations."""
    return {
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_ASKPASS": "",
        "GCM_INTERACTIVE": "never",
    }


def _resolve_clone_source(clone_url: str) -> str:
    """
    Return the clone source for GitPython.
    In production this is always the validated https://github.com/<owner>/<repo>.git URL.
    For the built-in controlled hackathon demo URL (https://github.com/docguard-demo/billing-api.git),
    resolves to the deterministic local demo Git repository created by `ensure_demo_git_repository()`.
    Can also be monkeypatched in automated unit tests to point to a temporary local Git fixture.
    """
    if clone_url.lower() == "https://github.com/docguard-demo/billing-api.git":
        from app.services.demo_fixture import ensure_demo_git_repository

        return ensure_demo_git_repository()["path"]
    return clone_url


def _classify_git_error(exc: GitCommandError, owner: str, repo_name: str) -> RepositoryError:
    """Map a GitPython GitCommandError to a safe, user-friendly domain exception."""
    stderr_lower = f"{exc.stderr or ''} {exc.stdout or ''} {str(exc)}".lower()

    if (
        "repository not found" in stderr_lower
        or "not found" in stderr_lower
        or "does not exist" in stderr_lower
        or "could not read username" in stderr_lower
        or "authentication failed" in stderr_lower
        or "terminal prompts disabled" in stderr_lower
        or "access denied" in stderr_lower
    ):
        return RepositoryNotFoundError(
            f"Repository '{owner}/{repo_name}' was not found or is not a public GitHub repository."
        )

    if (
        "timed out" in stderr_lower
        or "timeout" in stderr_lower
        or "could not resolve host" in stderr_lower
        or "unable to access" in stderr_lower
        or "connection refused" in stderr_lower
        or "failed to connect" in stderr_lower
    ):
        return RepositoryNetworkError(
            f"Unable to connect to GitHub while accessing '{owner}/{repo_name}'. Please check your network connection and try again."
        )

    return RepositoryNetworkError(
        f"Git operation failed while accessing '{owner}/{repo_name}'."
    )


def _clone_bare_repository(
    clone_url: str,
    target_dir: str,
    depth: int,
    owner: str,
    repo_name: str,
    include_blobs: bool = False,
) -> Repo:
    """
    Clone a public repository in bare mode (--bare) without checking out any working tree files.
    """
    source = _resolve_clone_source(clone_url)
    multi_options = [
        "--bare",
        "--single-branch",
        f"--depth={depth}",
    ]
    # Use treeless partial clone for remote HTTPS URLs unless full blobs are requested
    if source.startswith("https://") and not include_blobs:
        multi_options.append("--filter=blob:none")

    try:
        repo = Repo.clone_from(
            url=source,
            to_path=target_dir,
            multi_options=multi_options,
            env=_get_git_env(),
            allow_unsafe_options=False,
            allow_unsafe_protocols=False,
        )
        return repo
    except GitCommandError as exc:
        raise _classify_git_error(exc, owner, repo_name) from exc
    except Exception as exc:
        raise RepositoryNetworkError(
            f"Unexpected error while cloning '{owner}/{repo_name}'."
        ) from exc


def _detect_default_branch(repo: Repo) -> str:
    """Determine the default branch name from the cloned bare repository's HEAD."""
    try:
        if not repo.head.is_detached:
            return repo.head.reference.name
    except Exception:
        pass

    try:
        symref = repo.git.symbolic_ref("HEAD")
        if symref:
            return symref.strip().split("/")[-1]
    except Exception:
        pass

    try:
        if repo.branches:
            return repo.branches[0].name
    except Exception:
        pass

    return "main"


def _format_commit(commit: Commit) -> CommitInfo:
    """Convert a GitPython Commit object into a CommitInfo Pydantic model."""
    full_sha = str(commit.hexsha)
    raw_message = commit.message or ""
    first_line = raw_message.strip().splitlines()[0] if raw_message.strip() else "(no commit message)"

    author_Obj: Optional[Actor] = getattr(commit, "author", None)
    author_name = (author_Obj.name if author_Obj and author_Obj.name else "Unknown Author").strip()

    committed_dt = commit.committed_datetime.astimezone(timezone.utc)
    iso_timestamp = committed_dt.isoformat()

    return CommitInfo(
        sha=full_sha,
        short_sha=full_sha[:7],
        message=first_line,
        author=author_name,
        timestamp=iso_timestamp,
    )


def inspect_repository(
    repository_url: str,
    max_commits: int = DEFAULT_COMMIT_LIMIT,
) -> RepositoryInspectResponse:
    """
    Validate, shallow-clone, and inspect a public GitHub repository.
    Returns owner, name, default branch, and up to `max_commits` recent commits.
    """
    owner, repo_name, canonical_url, clone_url = parse_and_validate_github_url(repository_url)
    bounded_limit = max(1, min(max_commits, MAX_COMMIT_LIMIT))

    with _temporary_repo_directory() as (temp_dir, repo_holder):
        repo = _clone_bare_repository(
            clone_url=clone_url,
            target_dir=temp_dir,
            depth=max(bounded_limit, CLONE_DEPTH_INSPECT),
            owner=owner,
            repo_name=repo_name,
        )
        repo_holder.append(repo)

        default_branch = _detect_default_branch(repo)

        try:
            # Prefer first-parent history on the default branch so --no-ff merge commits
            # do not duplicate their second-parent PR commits that share the exact same Git tree.
            first_parent_commits = list(
                repo.iter_commits("HEAD", max_count=bounded_limit * 2, first_parent=True)
            )
            commits_iter: list[Commit] = []
            seen_trees: set[str] = set()
            for candidate in first_parent_commits:
                tree_sha = candidate.tree.hexsha
                if commits_iter and commits_iter[-1].tree.hexsha == tree_sha:
                    continue
                commits_iter.append(candidate)
                seen_trees.add(tree_sha)
                if len(commits_iter) >= bounded_limit:
                    break

            # If first-parent traversal returned fewer commits than available, supplement
            # with remaining commits that introduce distinct trees.
            if len(commits_iter) < bounded_limit:
                existing_shas = {c.hexsha for c in commits_iter}
                for candidate in repo.iter_commits("HEAD", max_count=bounded_limit * 2):
                    if candidate.hexsha in existing_shas:
                        continue
                    if candidate.tree.hexsha in seen_trees:
                        continue
                    commits_iter.append(candidate)
                    existing_shas.add(candidate.hexsha)
                    seen_trees.add(candidate.tree.hexsha)
                    if len(commits_iter) >= bounded_limit:
                        break
        except (GitCommandError, ValueError, BadName) as exc:
            raise RepositoryEmptyError(
                f"Repository '{owner}/{repo_name}' has no accessible commit history."
            ) from exc

        if not commits_iter:
            raise RepositoryEmptyError(
                f"Repository '{owner}/{repo_name}' has no accessible commits."
            )

        commit_items = [_format_commit(c) for c in commits_iter]

        return RepositoryInspectResponse(
            repository_url=canonical_url,
            owner=owner,
            name=repo_name,
            default_branch=default_branch,
            commits=commit_items,
        )


def _resolve_commit_object(repo: Repo, commit_sha: str, label: str) -> Commit:
    """
    Resolve a validated commit SHA in the repository.
    If not present in the initial shallow clone, attempt a bounded single-commit fetch.
    """
    try:
        return repo.commit(commit_sha)
    except (BadName, BadObject, ValueError, GitCommandError):
        pass

    # Attempt to fetch the specific commit from origin in case it lies outside shallow depth
    try:
        with repo.git.custom_environment(**_get_git_env()):
            repo.git.fetch(
                "origin",
                commit_sha,
                depth=1,
            )
        return repo.commit(commit_sha)
    except (BadName, BadObject, ValueError, GitCommandError) as exc:
        raise CommitNotFoundError(
            f"The specified {label} '{commit_sha}' could not be found in the repository."
        ) from exc


def _count_patch_lines(patch_text: str) -> Tuple[int, int]:
    """Count added (+) and deleted (-) lines in a unified diff patch."""
    additions = 0
    deletions = 0
    for line in patch_text.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            additions += 1
        elif line.startswith("-") and not line.startswith("---"):
            deletions += 1
    return additions, deletions


def _resolve_effective_diff_commits(
    base_obj: Commit,
    head_obj: Commit,
) -> Tuple[Commit, Commit]:
    """
    Resolve the effective commit objects to diff.
    If a user compares a --no-ff merge commit directly against its merged second parent
    and both share the exact same Git tree (e.g. a fast-forwardable PR merged with --no-ff),
    compare against the merge commit's first parent (the branch target prior to the merge)
    so the actual changes introduced by that merge are returned instead of an empty tree diff.
    """
    if base_obj.tree.hexsha != head_obj.tree.hexsha:
        return base_obj, head_obj

    if len(head_obj.parents) > 1 and any(p.hexsha == base_obj.hexsha for p in head_obj.parents):
        first_parent = head_obj.parents[0]
        if first_parent.tree.hexsha != head_obj.tree.hexsha:
            return first_parent, head_obj

    if len(base_obj.parents) > 1 and any(p.hexsha == head_obj.hexsha for p in base_obj.parents):
        first_parent = base_obj.parents[0]
        if first_parent.tree.hexsha != base_obj.tree.hexsha:
            return base_obj, first_parent

    return base_obj, head_obj


def _extract_file_patch(
    repo: Repo,
    diff_from_sha: str,
    diff_to_sha: str,
    current_path: str,
    previous_path: Optional[str],
) -> str:
    """
    Generate the unified diff patch for a single file using GitPython's git.diff_tree
    with explicit flags so Windows CRLF endings and custom user .gitconfig settings
    never cause patch parsing to fail.
    """
    path_args = (
        [previous_path, current_path]
        if previous_path and previous_path != current_path
        else [current_path]
    )
    with repo.git.custom_environment(**_get_git_env()):
        raw_patch = repo.git.diff_tree(
            "-r",
            "-p",
            "-M",
            "--no-color",
            "--no-ext-diff",
            "--src-prefix=a/",
            "--dst-prefix=b/",
            diff_from_sha,
            diff_to_sha,
            "--",
            *path_args,
        )
    return (raw_patch or "").replace("\r\n", "\n").replace("\r", "\n")


def compare_repository_commits(
    repository_url: str,
    base_commit: str,
    head_commit: str,
) -> RepositoryCompareResponse:
    """
    Compare two commits in a public GitHub repository using GitPython.
    Returns file categorizations (added, modified, deleted, renamed), line counts,
    and unified diff patches.
    """
    owner, repo_name, canonical_url, clone_url = parse_and_validate_github_url(repository_url)
    base_sha = validate_commit_sha(base_commit, label="base_commit")
    head_sha = validate_commit_sha(head_commit, label="head_commit")

    if base_sha == head_sha:
        raise RepositoryValidationError(
            "Base commit and head commit must be different commits."
        )

    with _temporary_repo_directory() as (temp_dir, repo_holder):
        repo = _clone_bare_repository(
            clone_url=clone_url,
            target_dir=temp_dir,
            depth=CLONE_DEPTH_COMPARE,
            owner=owner,
            repo_name=repo_name,
        )
        repo_holder.append(repo)

        base_obj = _resolve_commit_object(repo, base_sha, label="base commit")
        head_obj = _resolve_commit_object(repo, head_sha, label="head commit")

        if base_obj.hexsha == head_obj.hexsha:
            raise RepositoryValidationError(
                "Base commit and head commit resolve to the same commit."
            )

        diff_from_obj, diff_to_obj = _resolve_effective_diff_commits(base_obj, head_obj)

        try:
            with repo.git.custom_environment(**_get_git_env()):
                # Use raw diff format (create_patch=False -> git diff-tree -r -M --raw -z)
                # for 100% reliable file detection and rename classification.
                raw_diff_index = diff_from_obj.diff(diff_to_obj)
        except GitCommandError as exc:
            raise _classify_git_error(exc, owner, repo_name) from exc

        added_files: list[str] = []
        modified_files: list[str] = []
        deleted_files: list[str] = []
        renamed_files: list[str] = []
        file_paths: list[str] = []
        file_items: list[FileDiffItem] = []

        total_additions = 0
        total_deletions = 0
        running_patch_chars = 0
        overall_truncated = False

        for idx, diff_item in enumerate(raw_diff_index):
            if idx >= MAX_CHANGED_FILES:
                overall_truncated = True
                break

            a_path = diff_item.a_path
            b_path = diff_item.b_path
            change_code = (diff_item.change_type or "").upper()

            if diff_item.renamed_file or change_code.startswith("R"):
                change_type = "renamed"
                current_path = b_path or a_path or "unknown"
                previous_path = a_path
                renamed_files.append(current_path)
            elif diff_item.new_file or change_code == "A":
                change_type = "added"
                current_path = b_path or a_path or "unknown"
                previous_path = None
                added_files.append(current_path)
            elif diff_item.deleted_file or change_code == "D":
                change_type = "deleted"
                current_path = a_path or b_path or "unknown"
                previous_path = None
                deleted_files.append(current_path)
            else:
                change_type = "modified"
                current_path = b_path or a_path or "unknown"
                previous_path = None
                modified_files.append(current_path)

            file_paths.append(current_path)

            full_patch = _extract_file_patch(
                repo=repo,
                diff_from_sha=diff_from_obj.hexsha,
                diff_to_sha=diff_to_obj.hexsha,
                current_path=current_path,
                previous_path=previous_path,
            )

            is_binary = (
                "\x00" in full_patch
                or "Binary files " in full_patch
                or "GIT binary patch" in full_patch
            )
            file_truncated = False

            if is_binary:
                patch_text = "Binary file changed (diff preview not available)."
                additions = 0
                deletions = 0
            else:
                additions, deletions = _count_patch_lines(full_patch)
                total_additions += additions
                total_deletions += deletions

                patch_text = full_patch
                if len(patch_text) > MAX_FILE_PATCH_CHARS:
                    patch_text = (
                        patch_text[:MAX_FILE_PATCH_CHARS]
                        + "\n... [Diff truncated due to per-file size limit]"
                    )
                    file_truncated = True
                    overall_truncated = True

                if running_patch_chars + len(patch_text) > MAX_TOTAL_PATCH_CHARS:
                    remaining_budget = max(0, MAX_TOTAL_PATCH_CHARS - running_patch_chars)
                    patch_text = (
                        patch_text[:remaining_budget]
                        + "\n... [Diff truncated due to total response size limit]"
                    )
                    file_truncated = True
                    overall_truncated = True

                running_patch_chars += len(patch_text)

            file_items.append(
                FileDiffItem(
                    file_path=current_path,
                    previous_path=previous_path,
                    change_type=change_type,
                    additions=additions,
                    deletions=deletions,
                    patch=patch_text,
                    is_binary=is_binary,
                    truncated=file_truncated,
                )
            )

        return RepositoryCompareResponse(
            repository_url=canonical_url,
            owner=owner,
            name=repo_name,
            base_commit=base_obj.hexsha,
            head_commit=head_obj.hexsha,
            total_changed_files=len(file_items),
            added_files=added_files,
            modified_files=modified_files,
            deleted_files=deleted_files,
            renamed_files=renamed_files,
            file_paths=file_paths,
            total_additions=total_additions,
            total_deletions=total_deletions,
            files=file_items,
            diff_truncated=overall_truncated,
        )
