"""
Documentation Drift Analysis Service for DocGuard (Milestone 5).

Orchestrates the end-to-end Milestone 5 workflow in a single isolated bare clone:
1. Extracts Python AST symbols and Markdown documentation units at BOTH base and head commits
   (caching unchanged files so they are parsed only once).
2. Computes Python AST code changes between base and head commits.
3. Maps documentation units to Python symbols at base and head commits.
4. Compares documentation files and units between base and head commits.
5. Runs deterministic drift detection rules (Rules A–I) and aggregates findings.
"""

from typing import Dict, List, Literal, Optional, Set, Tuple
from git import Commit, GitCommandError

from app.analyzers.change_detector import detect_symbol_changes
from app.analyzers.documentation_comparator import compare_documentation_across_commits
from app.analyzers.documentation_extractor import extract_documentation_units
from app.analyzers.documentation_mapper import map_documentation_units_to_symbols
from app.analyzers.drift_detector import detect_documentation_drift
from app.analyzers.markdown_parser import parse_markdown_document
from app.analyzers.python_ast_analyzer import is_python_source_file
from app.analyzers.symbol_extractor import extract_python_symbols
from app.schemas.code_analysis import (
    ExtractedSymbol,
    ParseErrorItem,
    SkippedFileItem,
    SymbolChange,
)
from app.schemas.documentation import DocumentationUnit
from app.schemas.drift import (
    DriftAnalysisResponse,
    DriftAnalysisSummary,
    DriftFinding,
)
from app.services.documentation_service import (
    MAX_DOC_FILES,
    MAX_DOC_FILE_BYTES,
    MAX_EXTRACTED_UNITS,
    MAX_PYTHON_FILES,
    MAX_PYTHON_FILE_BYTES,
    MAX_SECTIONS_PER_FILE,
    _doc_file_sort_key,
    _find_ignored_directory,
    _python_file_sort_key,
    _read_blob_bytes,
    is_markdown_documentation_file,
)
from app.services.github_service import (
    CLONE_DEPTH_COMPARE,
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


def _collect_commit_blobs(
    commit_obj: Commit,
    skipped_files: List[SkippedFileItem],
    record_skipped: bool,
) -> Tuple[List[Tuple[str, object]], List[Tuple[str, object]]]:
    """Traverse a commit tree and return sorted `(md_blobs, py_blobs)` lists."""
    md_blobs: List[Tuple[str, object]] = []
    py_blobs: List[Tuple[str, object]] = []

    for item in commit_obj.tree.traverse():
        if getattr(item, "type", None) != "blob":
            continue
        rel_path = str(item.path).replace("\\", "/")
        ignored_dir = _find_ignored_directory(rel_path)

        if is_markdown_documentation_file(rel_path):
            if ignored_dir:
                if record_skipped:
                    skipped_files.append(
                        SkippedFileItem(
                            file_path=rel_path,
                            reason=f"Skipped ignored directory '{ignored_dir}'",
                        )
                    )
                continue
            md_blobs.append((rel_path, item))
        elif is_python_source_file(rel_path):
            if ignored_dir:
                continue
            py_blobs.append((rel_path, item))

    md_blobs.sort(key=lambda pair: _doc_file_sort_key(pair[0]))
    py_blobs.sort(key=lambda pair: _python_file_sort_key(pair[0]))
    return md_blobs, py_blobs


def analyze_repository_drift(
    repository_url: str,
    base_commit: str,
    head_commit: str,
) -> DriftAnalysisResponse:
    """
    Execute full deterministic documentation drift analysis between `base_commit`
    and `head_commit` for a public HTTPS GitHub repository.
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
            include_blobs=False,
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

        skipped_files: List[SkippedFileItem] = []
        parse_errors: List[ParseErrorItem] = []

        # Track changed Python files and renamed documentation files from Git diff
        changed_py_entries: List[
            Tuple[str, Optional[str], Literal["added", "modified", "deleted", "renamed"]]
        ] = []
        deleted_python_files: Set[str] = set()
        git_renamed_docs: Dict[str, str] = {}

        for diff_item in raw_diff_index:
            a_path = (diff_item.a_path or "").replace("\\", "/")
            b_path = (diff_item.b_path or "").replace("\\", "/")
            change_code = (diff_item.change_type or "").upper()

            if diff_item.renamed_file or change_code.startswith("R"):
                f_type: Literal["added", "modified", "deleted", "renamed"] = "renamed"
                cur_path = b_path or a_path
                prev_path: Optional[str] = a_path
                if is_markdown_documentation_file(cur_path) and prev_path:
                    git_renamed_docs[cur_path] = prev_path
            elif diff_item.new_file or change_code == "A":
                f_type = "added"
                cur_path = b_path or a_path
                prev_path = None
            elif diff_item.deleted_file or change_code == "D":
                f_type = "deleted"
                cur_path = a_path or b_path
                prev_path = None
                if is_python_source_file(cur_path):
                    deleted_python_files.add(cur_path)
            else:
                f_type = "modified"
                cur_path = b_path or a_path
                prev_path = None

            if is_python_source_file(cur_path) and not _find_ignored_directory(cur_path):
                changed_py_entries.append((cur_path, prev_path, f_type))

        # Caches keyed by blob hexsha so unchanged files between base and head are parsed only once
        py_blob_cache: Dict[str, Tuple[str, List[ExtractedSymbol]]] = {}
        md_blob_cache: Dict[str, Tuple[str, List[DocumentationUnit]]] = {}

        base_python_sources: Dict[str, str] = {}
        head_python_sources: Dict[str, str] = {}
        base_symbols_by_file: Dict[str, List[ExtractedSymbol]] = {}
        head_symbols_by_file: Dict[str, List[ExtractedSymbol]] = {}

        base_doc_raw_by_file: Dict[str, str] = {}
        head_doc_raw_by_file: Dict[str, str] = {}
        base_doc_units_by_file: Dict[str, List[DocumentationUnit]] = {}
        head_doc_units_by_file: Dict[str, List[DocumentationUnit]] = {}

        with repo.git.custom_environment(**_get_git_env()):
            base_md_blobs, base_py_blobs = _collect_commit_blobs(
                diff_from_obj, skipped_files, record_skipped=False
            )
            head_md_blobs, head_py_blobs = _collect_commit_blobs(
                diff_to_obj, skipped_files, record_skipped=True
            )

            # Ensure all changed Python files are prioritized in extraction
            changed_py_paths_set = {
                p for cur, prev, _t in changed_py_entries for p in (cur, prev) if p
            }

            def _extract_py_map(
                py_blobs: List[Tuple[str, object]],
                version_label: Literal["base", "head"],
                sources_out: Dict[str, str],
                symbols_out: Dict[str, List[ExtractedSymbol]],
            ) -> None:
                # For large repositories (> 20 Python files), analyze only changed Python files
                # to avoid fetching hundreds of unchanged blobs over the network.
                if len(py_blobs) > 20:
                    filtered_blobs = [
                        pair for pair in py_blobs if pair[0] in changed_py_paths_set
                    ]
                else:
                    filtered_blobs = py_blobs

                ordered = sorted(
                    filtered_blobs,
                    key=lambda pair: (
                        0 if pair[0] in changed_py_paths_set else 1,
                        _python_file_sort_key(pair[0]),
                    ),
                )
                for idx, (py_path, blob_obj) in enumerate(ordered):
                    if idx >= MAX_PYTHON_FILES:
                        break
                    blob_sha = getattr(blob_obj, "hexsha", None)
                    if blob_sha and blob_sha in py_blob_cache:
                        cached_src, cached_syms = py_blob_cache[blob_sha]
                        sources_out[py_path] = cached_src
                        # Rebind file_path if file was renamed
                        symbols_out[py_path] = [
                            s.model_copy(update={"file_path": py_path})
                            if s.file_path != py_path
                            else s
                            for s in cached_syms
                        ]
                        continue

                    raw_bytes, skip_reason = _read_blob_bytes(
                        blob_obj, MAX_PYTHON_FILE_BYTES
                    )
                    if skip_reason or raw_bytes is None:
                        if version_label == "head" and skip_reason:
                            skipped_files.append(
                                SkippedFileItem(
                                    file_path=py_path,
                                    reason=skip_reason,
                                )
                            )
                        continue

                    py_text = raw_bytes.decode("utf-8", errors="replace")
                    sources_out[py_path] = py_text
                    syms, py_err = extract_python_symbols(
                        source_code=py_text,
                        file_path=py_path,
                        version=version_label,
                    )
                    if py_err is not None:
                        parse_errors.append(py_err)
                    else:
                        symbols_out[py_path] = syms
                        if blob_sha:
                            py_blob_cache[blob_sha] = (py_text, syms)

            _extract_py_map(
                base_py_blobs, "base", base_python_sources, base_symbols_by_file
            )
            _extract_py_map(
                head_py_blobs, "head", head_python_sources, head_symbols_by_file
            )

            # Extract Markdown documentation at base and head
            def _extract_md_map(
                md_blobs: List[Tuple[str, object]],
                version_label: Literal["base", "head"],
                raw_out: Dict[str, str],
                units_out: Dict[str, List[DocumentationUnit]],
            ) -> None:
                total_units = 0
                for md_path, blob_obj in md_blobs:
                    if len(units_out) >= MAX_DOC_FILES:
                        if version_label == "head":
                            skipped_files.append(
                                SkippedFileItem(
                                    file_path=md_path,
                                    reason=f"Exceeded maximum documentation files limit ({MAX_DOC_FILES})",
                                )
                            )
                        continue

                    blob_sha = getattr(blob_obj, "hexsha", None)
                    if blob_sha and blob_sha in md_blob_cache:
                        cached_raw, cached_units = md_blob_cache[blob_sha]
                        raw_out[md_path] = cached_raw
                        rebound_units = [
                            u.model_copy(
                                update={
                                    "documentation_file": md_path,
                                    "unit_id": f"{md_path}::unit-{i + 1}",
                                }
                            )
                            if u.documentation_file != md_path
                            else u
                            for i, u in enumerate(cached_units)
                        ]
                        units_out[md_path] = rebound_units
                        total_units += len(rebound_units)
                        continue

                    raw_bytes, skip_reason = _read_blob_bytes(
                        blob_obj, MAX_DOC_FILE_BYTES
                    )
                    if skip_reason or raw_bytes is None:
                        if version_label == "head":
                            skipped_files.append(
                                SkippedFileItem(
                                    file_path=md_path,
                                    reason=skip_reason or "Unreadable documentation file",
                                )
                            )
                        continue

                    md_text = raw_bytes.decode("utf-8", errors="replace")
                    raw_out[md_path] = md_text
                    parsed_doc = parse_markdown_document(
                        content=md_text,
                        file_path=md_path,
                        max_sections=MAX_SECTIONS_PER_FILE,
                    )
                    remaining_budget = max(0, MAX_EXTRACTED_UNITS - total_units)
                    file_units = (
                        extract_documentation_units(
                            parsed_doc, max_units=remaining_budget
                        )
                        if remaining_budget > 0
                        else []
                    )
                    units_out[md_path] = file_units
                    total_units += len(file_units)
                    if blob_sha:
                        md_blob_cache[blob_sha] = (md_text, file_units)

            _extract_md_map(
                base_md_blobs, "base", base_doc_raw_by_file, base_doc_units_by_file
            )
            _extract_md_map(
                head_md_blobs, "head", head_doc_raw_by_file, head_doc_units_by_file
            )

        # Compute Python AST symbol changes across changed Python files
        parse_error_paths = {(e.file_path, e.version) for e in parse_errors}
        symbol_changes: List[SymbolChange] = []

        for cur_path, prev_path, f_type in changed_py_entries:
            base_lookup = prev_path or cur_path
            if (base_lookup, "base") in parse_error_paths or (
                cur_path,
                "head",
            ) in parse_error_paths:
                continue

            b_syms = (
                [] if f_type == "added" else base_symbols_by_file.get(base_lookup, [])
            )
            h_syms = (
                [] if f_type == "deleted" else head_symbols_by_file.get(cur_path, [])
            )

            # Keep base source keyed under cur_path as well so evidence builder can look it up
            if prev_path and prev_path in base_python_sources and cur_path not in base_python_sources:
                base_python_sources[cur_path] = base_python_sources[prev_path]

            file_changes = detect_symbol_changes(
                file_path=cur_path,
                base_symbols=b_syms,
                head_symbols=h_syms,
            )
            symbol_changes.extend(file_changes)

        all_base_symbols = [
            s for syms in base_symbols_by_file.values() for s in syms
        ]
        all_head_symbols = [
            s for syms in head_symbols_by_file.values() for s in syms
        ]
        all_base_units = [
            u for units in base_doc_units_by_file.values() for u in units
        ]
        all_head_units = [
            u for units in head_doc_units_by_file.values() for u in units
        ]

        # Map documentation units to symbols at base and head commits
        base_mappings = map_documentation_units_to_symbols(
            units=all_base_units,
            symbols=all_base_symbols,
        )
        head_mappings = map_documentation_units_to_symbols(
            units=all_head_units,
            symbols=all_head_symbols,
        )

        # Compare documentation across commits
        (
            doc_file_changes,
            _unit_diffs,
            diff_by_head_unit_id,
            diff_by_base_unit_id,
        ) = compare_documentation_across_commits(
            base_units_by_file=base_doc_units_by_file,
            head_units_by_file=head_doc_units_by_file,
            base_raw_by_file=base_doc_raw_by_file,
            head_raw_by_file=head_doc_raw_by_file,
            git_renamed_docs=git_renamed_docs,
        )

        # Run deterministic drift detection rules (Rules A–I)
        findings = detect_documentation_drift(
            symbol_changes=symbol_changes,
            deleted_python_files=deleted_python_files,
            base_symbols=all_base_symbols,
            head_symbols=all_head_symbols,
            base_units=all_base_units,
            head_units=all_head_units,
            base_mappings=base_mappings,
            head_mappings=head_mappings,
            diff_by_head_unit_id=diff_by_head_unit_id,
            diff_by_base_unit_id=diff_by_base_unit_id,
            base_python_sources=base_python_sources,
            head_python_sources=head_python_sources,
        )

        # Sort findings by priority: CONFIRMED_DRIFT -> POTENTIAL_DRIFT -> UNCERTAIN -> RESOLVED -> UNCHANGED
        status_rank = {
            "CONFIRMED_DRIFT": 5,
            "POTENTIAL_DRIFT": 4,
            "UNCERTAIN": 3,
            "RESOLVED": 2,
            "UNCHANGED": 1,
        }
        severity_rank = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}
        findings.sort(
            key=lambda f: (
                status_rank.get(f.status, 0),
                severity_rank.get(f.severity, 0),
                f.confidence,
            ),
            reverse=True,
        )

        findings_by_status: Dict[str, List[DriftFinding]] = {}
        findings_by_severity: Dict[str, List[DriftFinding]] = {}
        counts_by_status: Dict[str, int] = {}
        counts_by_severity: Dict[str, int] = {}
        counts_by_rule: Dict[str, int] = {}

        for item in findings:
            findings_by_status.setdefault(item.status, []).append(item)
            findings_by_severity.setdefault(item.severity, []).append(item)
            counts_by_status[item.status] = counts_by_status.get(item.status, 0) + 1
            counts_by_severity[item.severity] = (
                counts_by_severity.get(item.severity, 0) + 1
            )
            counts_by_rule[item.rule_id] = counts_by_rule.get(item.rule_id, 0) + 1

        uncertain_results = findings_by_status.get("UNCERTAIN", [])
        resolved_results = findings_by_status.get("RESOLVED", [])

        doc_changes_count = sum(
            1 for dc in doc_file_changes if dc.change_type != "unchanged"
        )
        all_analyzed_py_paths = set(base_symbols_by_file.keys()) | set(
            head_symbols_by_file.keys()
        )
        all_analyzed_doc_paths = set(base_doc_units_by_file.keys()) | set(
            head_doc_units_by_file.keys()
        )

        summary = DriftAnalysisSummary(
            python_files_analyzed=len(all_analyzed_py_paths),
            documentation_files_analyzed=len(all_analyzed_doc_paths),
            code_changes_count=len(symbol_changes),
            documentation_changes_count=doc_changes_count,
            total_findings=len(findings),
            confirmed_drift_count=counts_by_status.get("CONFIRMED_DRIFT", 0),
            potential_drift_count=counts_by_status.get("POTENTIAL_DRIFT", 0),
            uncertain_count=counts_by_status.get("UNCERTAIN", 0),
            resolved_count=counts_by_status.get("RESOLVED", 0),
            unchanged_count=counts_by_status.get("UNCHANGED", 0),
            counts_by_status=counts_by_status,
            counts_by_severity=counts_by_severity,
            counts_by_rule=counts_by_rule,
            skipped_files_count=len(skipped_files),
            parse_errors_count=len(parse_errors),
        )

        return DriftAnalysisResponse(
            repository_url=canonical_url,
            owner=owner,
            name=repo_name,
            base_commit=base_obj.hexsha,
            head_commit=head_obj.hexsha,
            summary=summary,
            findings=findings,
            findings_by_status=findings_by_status,
            findings_by_severity=findings_by_severity,
            uncertain_results=uncertain_results,
            resolved_results=resolved_results,
            documentation_changes=doc_file_changes,
            skipped_files=skipped_files,
            parse_errors=parse_errors,
        )
