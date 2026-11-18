"""
Documentation Drift Detection Coordinator for DocGuard (Milestone 5).

Combines:
- Python AST SymbolChanges between base and head commits
- Base and Head Python AST symbol tables
- Base and Head extracted Markdown documentation units
- Evidence-based Documentation-to-Code mappings
- Historical documentation diffs (unchanged, modified, added, deleted, moved)
- Deterministic Drift Rules A–I
"""

from typing import Dict, List, Optional, Set, Tuple

from app.analyzers.documentation_mapper import (
    _has_whole_word,
    map_documentation_units_to_symbols,
)
from app.analyzers.drift_rules import (
    _is_changelog_unit,
    evaluate_rule_a_changed_default,
    evaluate_rule_b_removed_or_renamed_parameter,
    evaluate_rule_c_added_required_parameter,
    evaluate_rule_d_return_contract_changed,
    evaluate_rule_e_symbol_removed,
    evaluate_rule_f_symbol_renamed,
    evaluate_rule_h_signature_changed,
    evaluate_rule_i_documentation_updated,
)
from app.schemas.code_analysis import ExtractedSymbol, SymbolChange
from app.schemas.documentation import (
    DocumentationMapping,
    DocumentationUnit,
    RelatedSymbolMatch,
)
from app.schemas.drift import DocumentationUnitDiff, DriftFinding


def detect_documentation_drift(
    symbol_changes: List[SymbolChange],
    deleted_python_files: Set[str],
    base_symbols: List[ExtractedSymbol],
    head_symbols: List[ExtractedSymbol],
    base_units: List[DocumentationUnit],
    head_units: List[DocumentationUnit],
    base_mappings: List[DocumentationMapping],
    head_mappings: List[DocumentationMapping],
    diff_by_head_unit_id: Dict[str, DocumentationUnitDiff],
    diff_by_base_unit_id: Dict[str, DocumentationUnitDiff],
    base_python_sources: Dict[str, str],
    head_python_sources: Dict[str, str],
) -> List[DriftFinding]:
    """
    Execute deterministic drift detection rules (Rules A–I) and return
    deduplicated, evidence-backed DriftFinding items.
    """
    findings: List[DriftFinding] = []
    seen_finding_keys: Set[Tuple[str, str, str, str]] = set()

    def _add_finding(candidate: Optional[DriftFinding]) -> bool:
        if candidate is None:
            return False
        dedup_key = (
            candidate.documentation_file,
            str(candidate.documentation_line),
            candidate.qualified_symbol,
            candidate.rule_id,
        )
        if dedup_key in seen_finding_keys:
            return False
        seen_finding_keys.add(dedup_key)
        findings.append(candidate)
        return True

    # Index head mappings by (source_file, qualified_name)
    head_mappings_by_symbol: Dict[
        Tuple[str, str], List[Tuple[DocumentationMapping, RelatedSymbolMatch]]
    ] = {}
    for h_map in head_mappings:
        for sym_match in h_map.related_symbols:
            key = (sym_match.source_file, sym_match.qualified_name)
            head_mappings_by_symbol.setdefault(key, []).append((h_map, sym_match))

    # Index base symbols that were removed or renamed so we can check if head documentation
    # still references symbols that no longer exist under their old name in head_symbols
    base_symbol_lookup: Dict[Tuple[str, str], ExtractedSymbol] = {
        (s.file_path, s.qualified_name): s for s in base_symbols
    }

    removed_or_old_symbols: List[ExtractedSymbol] = []
    for ch in symbol_changes:
        if ch.change_type in {"FUNCTION_REMOVED", "METHOD_REMOVED", "CLASS_REMOVED"}:
            old_sym = base_symbol_lookup.get((ch.file_path, ch.qualified_name))
            if old_sym is not None:
                removed_or_old_symbols.append(old_sym)
        elif ch.change_type == "FUNCTION_RENAMED":
            old_qname = str(ch.details.get("old_qualified_name") or ch.details.get("old_name") or "")
            old_sym = base_symbol_lookup.get((ch.file_path, old_qname))
            if old_sym is not None:
                removed_or_old_symbols.append(old_sym)

    head_against_old_by_symbol: Dict[
        Tuple[str, str], List[Tuple[DocumentationMapping, RelatedSymbolMatch]]
    ] = {}
    if removed_or_old_symbols and head_units:
        head_to_old_mappings = map_documentation_units_to_symbols(
            units=head_units,
            symbols=removed_or_old_symbols,
        )
        for h_old_map in head_to_old_mappings:
            for sym_match in h_old_map.related_symbols:
                key = (sym_match.source_file, sym_match.qualified_name)
                head_against_old_by_symbol.setdefault(key, []).append(
                    (h_old_map, sym_match)
                )

    # Also index base mappings by (source_file, qualified_name) to detect when
    # documentation referencing a removed symbol was cleaned up in head (RESOLVED)
    base_mappings_by_symbol: Dict[
        Tuple[str, str], List[Tuple[DocumentationMapping, RelatedSymbolMatch]]
    ] = {}
    for b_map in base_mappings:
        for sym_match in b_map.related_symbols:
            key = (sym_match.source_file, sym_match.qualified_name)
            base_mappings_by_symbol.setdefault(key, []).append((b_map, sym_match))

    # Track which (head_unit_id, source_file, qualified_name) already triggered a specific rule
    specific_rule_fired: Set[Tuple[str, str, str]] = set()

    # Pass 1: Evaluate specific deterministic Rules A–H across all AST SymbolChanges
    for change in symbol_changes:
        # Skip pure additions of brand-new functions/classes/methods or body-only modifications
        if change.change_type in {
            "FUNCTION_ADDED",
            "METHOD_ADDED",
            "CLASS_ADDED",
            "FUNCTION_MODIFIED",
            "METHOD_MODIFIED",
        }:
            continue

        base_src = base_python_sources.get(change.file_path)
        head_src = head_python_sources.get(change.file_path)

        # Case 1: Removed symbol (Rule E / Rule G)
        if change.change_type in {"FUNCTION_REMOVED", "METHOD_REMOVED", "CLASS_REMOVED"}:
            sym_key = (change.file_path, change.qualified_name)
            still_referenced_in_head = head_against_old_by_symbol.get(sym_key, [])
            is_del_file = change.file_path in deleted_python_files

            if still_referenced_in_head:
                for h_map, sym_match in still_referenced_in_head:
                    unit_diff = diff_by_head_unit_id.get(h_map.unit_id)
                    finding = evaluate_rule_e_symbol_removed(
                        finding_idx=len(findings) + 1,
                        change=change,
                        mapping=h_map,
                        sym_match=sym_match,
                        unit_diff=unit_diff,
                        base_source=base_src,
                        head_source=head_src,
                        is_deleted_file=is_del_file,
                    )
                    if _add_finding(finding):
                        specific_rule_fired.add(
                            (h_map.unit_id, change.file_path, change.qualified_name)
                        )
            else:
                # Check if it WAS documented in base_commit and that documentation was updated/deleted in head
                was_documented_in_base = base_mappings_by_symbol.get(sym_key, [])
                for b_map, sym_match in was_documented_in_base:
                    if _is_changelog_unit(b_map):
                        continue
                    b_diff = diff_by_base_unit_id.get(b_map.unit_id)
                    if b_diff and b_diff.change_type in {"deleted", "modified"}:
                        old_ev = (
                            f"def {change.old_signature}:"
                            if change.old_signature
                            else f"{change.symbol_type} {change.qualified_name}"
                        )
                        resolved_finding = DriftFinding(
                            finding_id=f"drift-{len(findings) + 1}",
                            finding_type=change.change_type,
                            rule_id="RULE_E_SYMBOL_REMOVED",
                            status="RESOLVED",
                            severity="LOW",
                            confidence=0.90,
                            documentation_file=b_diff.documentation_file,
                            documentation_line=b_diff.head_start_line or b_map.start_line,
                            documentation_end_line=b_diff.head_end_line or b_map.end_line,
                            documentation_section=b_map.documentation_section,
                            documentation_text=b_diff.head_text or b_map.documentation_text,
                            previous_documentation_text=b_map.documentation_text,
                            related_symbol=change.symbol,
                            qualified_symbol=change.qualified_name,
                            source_file=change.file_path,
                            source_line=change.old_line,
                            old_source_line=change.old_line,
                            old_code_evidence=old_ev,
                            new_code_evidence="[Symbol removed in head commit]",
                            mapping_evidence=list(sym_match.evidence),
                            reason=(
                                f"Documentation referencing removed {change.symbol_type} "
                                f"'{change.qualified_name}' was updated or removed in the head commit."
                            ),
                            suggested_action="No action needed; outdated symbol reference was removed.",
                        )
                        _add_finding(resolved_finding)
            continue

        # Case 2: Renamed function (Rule F)
        if change.change_type == "FUNCTION_RENAMED":
            old_qname = str(
                change.details.get("old_qualified_name")
                or change.details.get("old_name")
                or ""
            )
            old_key = (change.file_path, old_qname)
            new_key = (change.file_path, change.qualified_name)

            candidate_pairs = list(head_against_old_by_symbol.get(old_key, [])) + list(
                head_mappings_by_symbol.get(new_key, [])
            )
            seen_units_for_rename: Set[str] = set()
            for h_map, sym_match in candidate_pairs:
                if h_map.unit_id in seen_units_for_rename:
                    continue
                seen_units_for_rename.add(h_map.unit_id)
                unit_diff = diff_by_head_unit_id.get(h_map.unit_id)
                finding = evaluate_rule_f_symbol_renamed(
                    finding_idx=len(findings) + 1,
                    change=change,
                    mapping=h_map,
                    sym_match=sym_match,
                    unit_diff=unit_diff,
                    base_source=base_src,
                    head_source=head_src,
                )
                if _add_finding(finding):
                    specific_rule_fired.add(
                        (h_map.unit_id, change.file_path, change.qualified_name)
                    )
            continue

        # Case 3: Active symbol in head_commit (Rules A, B, C, D, H)
        sym_key = (change.file_path, change.qualified_name)
        mapped_entries = head_mappings_by_symbol.get(sym_key, [])

        for h_map, sym_match in mapped_entries:
            unit_diff = diff_by_head_unit_id.get(h_map.unit_id)
            finding: Optional[DriftFinding] = None

            if change.change_type == "DEFAULT_VALUE_CHANGED":
                finding = evaluate_rule_a_changed_default(
                    finding_idx=len(findings) + 1,
                    change=change,
                    mapping=h_map,
                    sym_match=sym_match,
                    unit_diff=unit_diff,
                    base_source=base_src,
                    head_source=head_src,
                )
            elif change.change_type in {"PARAMETER_REMOVED", "PARAMETER_RENAMED"}:
                finding = evaluate_rule_b_removed_or_renamed_parameter(
                    finding_idx=len(findings) + 1,
                    change=change,
                    mapping=h_map,
                    sym_match=sym_match,
                    unit_diff=unit_diff,
                    base_source=base_src,
                    head_source=head_src,
                )
            elif change.change_type == "PARAMETER_ADDED":
                finding = evaluate_rule_c_added_required_parameter(
                    finding_idx=len(findings) + 1,
                    change=change,
                    mapping=h_map,
                    sym_match=sym_match,
                    unit_diff=unit_diff,
                    base_source=base_src,
                    head_source=head_src,
                )
            elif change.change_type == "RETURN_ANNOTATION_CHANGED":
                finding = evaluate_rule_d_return_contract_changed(
                    finding_idx=len(findings) + 1,
                    change=change,
                    mapping=h_map,
                    sym_match=sym_match,
                    unit_diff=unit_diff,
                    base_source=base_src,
                    head_source=head_src,
                )
            elif change.change_type in {
                "PARAMETER_REORDERED",
                "ASYNC_STATUS_CHANGED",
                "PARAMETER_ANNOTATION_CHANGED",
            }:
                finding = evaluate_rule_h_signature_changed(
                    finding_idx=len(findings) + 1,
                    change=change,
                    mapping=h_map,
                    sym_match=sym_match,
                    unit_diff=unit_diff,
                    base_source=base_src,
                    head_source=head_src,
                )

            if _add_finding(finding):
                specific_rule_fired.add(
                    (h_map.unit_id, change.file_path, change.qualified_name)
                )

    # Pass 2: Rule G — Explicit references to deleted Python source file paths in head documentation
    if deleted_python_files:
        for h_unit in head_units:
            if h_unit.unit_type == "changelog" or "changelog" in h_unit.documentation_file.lower():
                continue
            for del_py in sorted(deleted_python_files):
                if del_py in h_unit.original_text or _has_whole_word(
                    h_unit.original_text, del_py
                ):
                    already_covered = any(
                        f.documentation_file == h_unit.documentation_file
                        and f.documentation_line == h_unit.start_line
                        and f.source_file == del_py
                        for f in findings
                    )
                    if not already_covered:
                        _add_finding(
                            DriftFinding(
                                finding_id=f"drift-{len(findings) + 1}",
                                finding_type="DELETED_SOURCE_FILE",
                                rule_id="RULE_G_DELETED_SOURCE_FILE",
                                status="CONFIRMED_DRIFT",
                                severity="CRITICAL",
                                confidence=0.95,
                                documentation_file=h_unit.documentation_file,
                                documentation_line=h_unit.start_line,
                                documentation_end_line=h_unit.end_line,
                                documentation_section=h_unit.section_heading,
                                documentation_text=h_unit.original_text,
                                previous_documentation_text=None,
                                related_symbol=del_py,
                                qualified_symbol=del_py,
                                source_file=del_py,
                                source_line=1,
                                old_source_line=1,
                                old_code_evidence=f"# File existed at base commit: {del_py}",
                                new_code_evidence="[Source file deleted in head commit]",
                                mapping_evidence=[
                                    f"Documentation explicitly references file path '{del_py}'"
                                ],
                                reason=(
                                    f"Documentation explicitly references Python source file "
                                    f"'{del_py}', which was deleted in the head commit."
                                ),
                                suggested_action=(
                                    f"Remove or update the reference to deleted file `{del_py}` "
                                    f"in '{h_unit.documentation_file}' (line {h_unit.start_line})."
                                ),
                            )
                        )

    # Pass 3: Rule I — Modified documentation alongside signature-level code changes
    # where no specific deterministic rule (A–H) could confirm drift or confirm resolution
    for change in symbol_changes:
        if change.change_type in {
            "FUNCTION_ADDED",
            "METHOD_ADDED",
            "CLASS_ADDED",
            "FUNCTION_MODIFIED",
            "METHOD_MODIFIED",
            "FUNCTION_REMOVED",
            "METHOD_REMOVED",
            "CLASS_REMOVED",
        }:
            continue

        sym_key = (change.file_path, change.qualified_name)
        mapped_entries = head_mappings_by_symbol.get(sym_key, [])
        base_src = base_python_sources.get(change.file_path)
        head_src = head_python_sources.get(change.file_path)

        for h_map, sym_match in mapped_entries:
            if (h_map.unit_id, change.file_path, change.qualified_name) in specific_rule_fired:
                continue
            unit_diff = diff_by_head_unit_id.get(h_map.unit_id)
            finding = evaluate_rule_i_documentation_updated(
                finding_idx=len(findings) + 1,
                change=change,
                mapping=h_map,
                sym_match=sym_match,
                unit_diff=unit_diff,
                base_source=base_src,
                head_source=head_src,
            )
            if _add_finding(finding):
                specific_rule_fired.add(
                    (h_map.unit_id, change.file_path, change.qualified_name)
                )

    return findings
