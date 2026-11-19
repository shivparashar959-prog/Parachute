"""
Documentation Discovery, Parsing & Code Mapping Service for DocGuard (Milestone 4).

Reuses the existing GitHub repository cloning and commit resolution primitives
(`github_service.py`) and the static Python AST symbol extractor (`symbol_extractor.py`)
to:
1. Discover Markdown documentation files at the target HEAD commit.
2. Record skipped files (ignored directories, binary files, oversized files).
3. Extract all Python AST symbols from the repository at the same commit.
4. Parse Markdown documents and extract meaningful documentation units.
5. Map documentation units to Python code symbols with confidence and evidence.
"""

from typing import List, Optional, Set, Tuple
from git import Commit

from app.analyzers.documentation_extractor import extract_documentation_units
from app.analyzers.documentation_mapper import map_documentation_units_to_symbols
from app.analyzers.markdown_parser import parse_markdown_document
from app.analyzers.python_ast_analyzer import is_python_source_file
from app.analyzers.symbol_extractor import extract_python_symbols
from app.schemas.code_analysis import (
    ExtractedSymbol,
    ParseErrorItem,
    SkippedFileItem,
)
from app.schemas.documentation import (
    DiscoveredDocFile,
    DocumentationAnalysisResponse,
    DocumentationAnalysisSummary,
    DocumentationUnit,
)
from app.services.github_service import (
    CLONE_DEPTH_INSPECT,
    _clone_bare_repository,
    _get_git_env,
    _resolve_commit_object,
    _temporary_repo_directory,
    parse_and_validate_github_url,
    validate_commit_sha,
)

# Configurable processing bounds
MAX_DOC_FILE_BYTES = 500_000  # 500 KB per Markdown file
MAX_DOC_FILES = 60
MAX_SECTIONS_PER_FILE = 300
MAX_EXTRACTED_UNITS = 600
MAX_PYTHON_FILES = 150
MAX_PYTHON_FILE_BYTES = 500_000

_IGNORED_DIRECTORIES: Set[str] = {
    ".git",
    ".github",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "build",
    "dist",
    "target",
    "out",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    ".eggs",
    "htmlcov",
    "site",
    "_build",
    ".docusaurus",
    ".next",
    "vendor",
}

_MARKDOWN_EXTENSIONS = (".md", ".markdown", ".mdown")


def is_markdown_documentation_file(rel_path: str) -> bool:
    """Return True if the file path has a Markdown documentation extension."""
    if not rel_path:
        return False
    lower = rel_path.lower()
    return lower.endswith(_MARKDOWN_EXTENSIONS)


def _find_ignored_directory(rel_path: str) -> Optional[str]:
    """Return the first ignored directory name in `rel_path`, or None if allowed."""
    norm = rel_path.replace("\\", "/").strip("/")
    segments = norm.split("/")
    for seg in segments[:-1]:
        if seg in _IGNORED_DIRECTORIES or seg.lower() in _IGNORED_DIRECTORIES:
            return seg
    return None


def _doc_file_sort_key(rel_path: str) -> Tuple[int, str]:
    """
    Order discovered Markdown files so root README.md, docs/**/*.md, and
    subdirectory READMEs are analyzed first.
    """
    norm = rel_path.replace("\\", "/")
    lower = norm.lower()
    if lower == "readme.md":
        return (0, norm)
    if lower.startswith("docs/"):
        return (1, norm)
    if lower.endswith("/readme.md"):
        return (2, norm)
    if lower in {"contributing.md", "changelog.md", "changes.md", "history.md"}:
        return (3, norm)
    return (4, norm)


def _python_file_sort_key(rel_path: str) -> Tuple[int, str]:
    """Prioritize primary package/source Python files ahead of test files."""
    norm = rel_path.replace("\\", "/")
    lower = norm.lower()
    if lower.startswith("tests/") or "/tests/" in lower or lower.startswith("test_"):
        return (2, norm)
    if lower.startswith("examples/") or "/examples/" in lower:
        return (1, norm)
    return (0, norm)


def _read_blob_bytes(blob_obj, max_bytes: int) -> Tuple[Optional[bytes], Optional[str]]:
    """
    Safely read a Git blob up to `max_bytes` and reject oversized or binary content.
    Returns (raw_bytes, skip_reason).
    """
    declared_size = getattr(blob_obj, "size", 0)
    if declared_size and declared_size > max_bytes:
        return (
            None,
            f"File size ({declared_size} bytes) exceeds maximum limit ({max_bytes // 1000} KB)",
        )

    raw_bytes: bytes = blob_obj.data_stream.read(max_bytes + 1)
    if len(raw_bytes) > max_bytes:
        return (
            None,
            f"File size exceeds maximum limit ({max_bytes // 1000} KB)",
        )

    if b"\x00" in raw_bytes:
        return None, "Binary file content detected"

    return raw_bytes, None


def analyze_repository_documentation(
    repository_url: str,
    head_commit: str,
    base_commit: Optional[str] = None,
    max_doc_file_bytes: int = MAX_DOC_FILE_BYTES,
    max_doc_files: int = MAX_DOC_FILES,
    max_sections_per_file: int = MAX_SECTIONS_PER_FILE,
    max_extracted_units: int = MAX_EXTRACTED_UNITS,
) -> DocumentationAnalysisResponse:
    """
    Discover Markdown documentation at `head_commit`, extract documentation units,
    extract Python AST symbols at `head_commit`, and map documentation units to code symbols.
    """
    owner, repo_name, canonical_url, clone_url = parse_and_validate_github_url(
        repository_url
    )
    head_sha = validate_commit_sha(head_commit, label="head_commit")
    validated_base: Optional[str] = None
    if base_commit and base_commit.strip():
        validated_base = validate_commit_sha(base_commit, label="base_commit")

    with _temporary_repo_directory() as (temp_dir, repo_holder):
        repo = _clone_bare_repository(
            clone_url=clone_url,
            target_dir=temp_dir,
            depth=CLONE_DEPTH_INSPECT,
            owner=owner,
            repo_name=repo_name,
            include_blobs=True,
        )
        repo_holder.append(repo)

        head_obj: Commit = _resolve_commit_object(
            repo, head_sha, label="head commit", owner=owner, repo_name=repo_name
        )

        candidate_md_blobs: List[Tuple[str, object]] = []
        candidate_py_blobs: List[Tuple[str, object]] = []
        skipped_files: list[SkippedFileItem] = []
        parse_errors: list[ParseErrorItem] = []

        # 1. Walk the Git commit tree at head_obj
        with repo.git.custom_environment(**_get_git_env()):
            for item in head_obj.tree.traverse():
                if getattr(item, "type", None) != "blob":
                    continue

                rel_path = str(item.path).replace("\\", "/")
                ignored_dir = _find_ignored_directory(rel_path)

                if is_markdown_documentation_file(rel_path):
                    if ignored_dir:
                        skipped_files.append(
                            SkippedFileItem(
                                file_path=rel_path,
                                reason=f"Skipped ignored directory '{ignored_dir}'",
                            )
                        )
                        continue
                    candidate_md_blobs.append((rel_path, item))
                elif is_python_source_file(rel_path):
                    if ignored_dir:
                        continue
                    candidate_py_blobs.append((rel_path, item))

            candidate_md_blobs.sort(key=lambda pair: _doc_file_sort_key(pair[0]))
            candidate_py_blobs.sort(key=lambda pair: _python_file_sort_key(pair[0]))

            # 2. Extract Python AST symbols from the HEAD commit
            all_python_symbols: list[ExtractedSymbol] = []
            for py_idx, (py_path, py_blob) in enumerate(candidate_py_blobs):
                if py_idx >= MAX_PYTHON_FILES:
                    break
                raw_py, py_skip = _read_blob_bytes(py_blob, MAX_PYTHON_FILE_BYTES)
                if py_skip or raw_py is None:
                    continue
                py_text = raw_py.decode("utf-8", errors="replace")
                file_symbols, py_err = extract_python_symbols(
                    source_code=py_text,
                    file_path=py_path,
                    version="head",
                )
                if py_err is not None:
                    parse_errors.append(py_err)
                else:
                    all_python_symbols.extend(file_symbols)

            # 3. Parse discovered Markdown files and extract documentation units
            discovered_files_meta: list[Tuple[str, int, int, list[DocumentationUnit]]] = []
            all_units: list[DocumentationUnit] = []

            for md_path, md_blob in candidate_md_blobs:
                if len(discovered_files_meta) >= max_doc_files:
                    skipped_files.append(
                        SkippedFileItem(
                            file_path=md_path,
                            reason=f"Exceeded maximum documentation files limit ({max_doc_files})",
                        )
                    )
                    continue

                raw_md, md_skip_reason = _read_blob_bytes(md_blob, max_doc_file_bytes)
                if md_skip_reason or raw_md is None:
                    skipped_files.append(
                        SkippedFileItem(
                            file_path=md_path,
                            reason=md_skip_reason or "Unreadable documentation file",
                        )
                    )
                    continue

                md_text = raw_md.decode("utf-8", errors="replace")
                parsed_doc = parse_markdown_document(
                    content=md_text,
                    file_path=md_path,
                    max_sections=max_sections_per_file,
                )

                remaining_budget = max(0, max_extracted_units - len(all_units))
                file_units = (
                    extract_documentation_units(parsed_doc, max_units=remaining_budget)
                    if remaining_budget > 0
                    else []
                )
                all_units.extend(file_units)
                discovered_files_meta.append(
                    (md_path, len(raw_md), len(parsed_doc.sections), file_units)
                )

        # 4. Map extracted documentation units to Python AST symbols
        mappings = map_documentation_units_to_symbols(
            units=all_units,
            symbols=all_python_symbols,
        )

        # Build per-file mapping count lookup
        mapped_count_by_file: dict[str, int] = {}
        for m in mappings:
            if m.mapping_status in {"MAPPED", "AMBIGUOUS"}:
                mapped_count_by_file[m.documentation_file] = (
                    mapped_count_by_file.get(m.documentation_file, 0) + 1
                )

        documentation_files: list[DiscoveredDocFile] = [
            DiscoveredDocFile(
                file_path=f_path,
                size_bytes=f_size,
                sections_count=sec_count,
                extracted_units_count=len(f_units),
                mapped_units_count=mapped_count_by_file.get(f_path, 0),
            )
            for f_path, f_size, sec_count, f_units in discovered_files_meta
        ]

        mapped_units_count = sum(
            1 for m in mappings if m.mapping_status == "MAPPED"
        )
        unmapped_units_count = sum(
            1 for m in mappings if m.mapping_status == "UNMAPPED"
        )
        ambiguous_units_count = sum(
            1 for m in mappings if m.mapping_status == "AMBIGUOUS"
        )
        high_confidence_count = sum(
            1 for m in mappings if m.highest_confidence == "HIGH"
        )
        medium_confidence_count = sum(
            1 for m in mappings if m.highest_confidence == "MEDIUM"
        )
        low_confidence_count = sum(
            1 for m in mappings if m.highest_confidence == "LOW"
        )

        summary = DocumentationAnalysisSummary(
            discovered_doc_files_count=len(documentation_files),
            skipped_files_count=len(skipped_files),
            extracted_python_symbols_count=len(all_python_symbols),
            extracted_units_count=len(all_units),
            mapped_units_count=mapped_units_count,
            unmapped_units_count=unmapped_units_count,
            ambiguous_units_count=ambiguous_units_count,
            high_confidence_count=high_confidence_count,
            medium_confidence_count=medium_confidence_count,
            low_confidence_count=low_confidence_count,
            parse_errors_count=len(parse_errors),
        )

        return DocumentationAnalysisResponse(
            repository_url=canonical_url,
            owner=owner,
            name=repo_name,
            commit_sha=head_obj.hexsha,
            base_commit=validated_base,
            head_commit=head_obj.hexsha,
            summary=summary,
            documentation_files=documentation_files,
            skipped_files=skipped_files,
            mappings=mappings,
            parse_errors=parse_errors,
        )
