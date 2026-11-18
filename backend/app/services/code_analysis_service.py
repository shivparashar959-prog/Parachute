"""
Code Analysis Service for DocGuard (Milestone 3).

Reuses the existing GitHub repository cloning and commit resolution primitives
from `github_service.py` to retrieve Python source blobs at base and head commits
and run static Python AST change analysis.
"""

from typing import Literal, Optional, Tuple
from git import Commit, GitCommandError

from app.analyzers.python_ast_analyzer import (
    analyze_python_file_change,
    is_python_source_file,
)
from app.schemas.code_analysis import (
    AnalyzedPythonFile,
    CodeAnalysisResponse,
    CodeAnalysisSummary,
    ParseErrorItem,
    SkippedFileItem,
    SymbolChange,
)
from app.services import github_service
from app.services.github_service import (
    CLONE_DEPTH_COMPARE,
    MAX_CHANGED_FILES,
    RepositoryValidationError,
    _classify_git_error,
    _clone_bare_repository,
    _get_git_env,
    _resolve_commit_object,
    _resolve_effective_diff_commits,
    _temporary_repo_directory,
    parse_and_validate_github_url,
    validate_commit_sha,
)

MAX_PYTHON_FILE_BYTES = 500_000  # 500 KB per Python source file


def _read_commit_file_source(
    commit_obj: Commit,
    rel_path: str,
) -> Tuple[Optional[str], Optional[str]]:
    """
    Read a UTF-8 Python source file directly from a Git commit tree in a bare repository
    without checking out any files to the filesystem.

    Returns:
        (source_text, skip_reason)
    """
    normalized_path = rel_path.replace("\\", "/").lstrip("/")
    try:
        target_obj = commit_obj.tree / normalized_path
    except KeyError:
        return None, None

    blob_size = getattr(target_obj, "size", 0)
    if blob_size and blob_size > MAX_PYTHON_FILE_BYTES:
        return (
            None,
            f"Python file exceeds maximum size limit ({MAX_PYTHON_FILE_BYTES // 1000} KB)",
        )

    raw_bytes: bytes = target_obj.data_stream.read(MAX_PYTHON_FILE_BYTES + 1)
    if len(raw_bytes) > MAX_PYTHON_FILE_BYTES:
        return (
            None,
            f"Python file exceeds maximum size limit ({MAX_PYTHON_FILE_BYTES // 1000} KB)",
        )

    if b"\x00" in raw_bytes:
        return None, "Binary content detected in file"

    return raw_bytes.decode("utf-8", errors="replace"), None


def analyze_repository_python_changes(
    repository_url: str,
    base_commit: str,
    head_commit: str,
) -> CodeAnalysisResponse:
    """
    Perform static Python AST code change analysis between `base_commit` and `head_commit`
    in a public HTTPS GitHub repository.
    """
    owner, repo_name, canonical_url, clone_url = parse_and_validate_github_url(
        repository_url
    )
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
                raw_diff_index = diff_from_obj.diff(diff_to_obj)
        except GitCommandError as exc:
            raise _classify_git_error(exc, owner, repo_name) from exc

        analyzed_files: list[AnalyzedPythonFile] = []
        changed_symbols: list[SymbolChange] = []
        parse_errors: list[ParseErrorItem] = []
        skipped_files: list[SkippedFileItem] = []

        total_changed_files_in_diff = len(raw_diff_index)

        for idx, diff_item in enumerate(raw_diff_index):
            a_path = diff_item.a_path
            b_path = diff_item.b_path
            change_code = (diff_item.change_type or "").upper()

            if diff_item.renamed_file or change_code.startswith("R"):
                file_change_type: Literal["added", "modified", "deleted", "renamed"] = (
                    "renamed"
                )
                current_path = b_path or a_path or "unknown"
                previous_path = a_path
            elif diff_item.new_file or change_code == "A":
                file_change_type = "added"
                current_path = b_path or a_path or "unknown"
                previous_path = None
            elif diff_item.deleted_file or change_code == "D":
                file_change_type = "deleted"
                current_path = a_path or b_path or "unknown"
                previous_path = None
            else:
                file_change_type = "modified"
                current_path = b_path or a_path or "unknown"
                previous_path = None

            if idx >= MAX_CHANGED_FILES:
                skipped_files.append(
                    SkippedFileItem(
                        file_path=current_path,
                        reason="Exceeded maximum files analyzed per comparison limit",
                    )
                )
                continue

            if not is_python_source_file(current_path):
                skipped_files.append(
                    SkippedFileItem(
                        file_path=current_path,
                        reason="Non-Python file",
                    )
                )
                continue

            base_source: Optional[str] = None
            head_source: Optional[str] = None

            with repo.git.custom_environment(**_get_git_env()):
                if file_change_type != "added":
                    base_lookup_path = previous_path or current_path
                    base_source, base_skip_reason = _read_commit_file_source(
                        diff_from_obj, base_lookup_path
                    )
                    if base_skip_reason:
                        skipped_files.append(
                            SkippedFileItem(
                                file_path=current_path,
                                reason=base_skip_reason,
                            )
                        )
                        continue

                if file_change_type != "deleted":
                    head_source, head_skip_reason = _read_commit_file_source(
                        diff_to_obj, current_path
                    )
                    if head_skip_reason:
                        skipped_files.append(
                            SkippedFileItem(
                                file_path=current_path,
                                reason=head_skip_reason,
                            )
                        )
                        continue

            file_report, file_changes, file_errors = analyze_python_file_change(
                file_path=current_path,
                file_change_type=file_change_type,
                base_source=base_source,
                head_source=head_source,
                previous_path=previous_path,
            )

            analyzed_files.append(file_report)
            changed_symbols.extend(file_changes)
            parse_errors.extend(file_errors)

        counts_by_change_type: dict[str, int] = {}
        for change in changed_symbols:
            counts_by_change_type[change.change_type] = (
                counts_by_change_type.get(change.change_type, 0) + 1
            )

        summary = CodeAnalysisSummary(
            total_changed_files_in_diff=total_changed_files_in_diff,
            analyzed_python_files_count=len(analyzed_files),
            skipped_files_count=len(skipped_files),
            parse_errors_count=len(parse_errors),
            total_symbol_changes=len(changed_symbols),
            counts_by_change_type=counts_by_change_type,
        )

        return CodeAnalysisResponse(
            repository_url=canonical_url,
            owner=owner,
            name=repo_name,
            base_commit=base_obj.hexsha,
            head_commit=head_obj.hexsha,
            summary=summary,
            analyzed_files=analyzed_files,
            changed_symbols=changed_symbols,
            parse_errors=parse_errors,
            skipped_files=skipped_files,
        )
