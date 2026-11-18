"""
Deterministic Documentation Drift Detection Rules (Rules A–I) for DocGuard (Milestone 5).

Implements:
- RULE_A_CHANGED_DEFAULT
- RULE_B_REMOVED_OR_RENAMED_PARAMETER
- RULE_C_ADDED_REQUIRED_PARAMETER
- RULE_D_RETURN_CONTRACT_CHANGED
- RULE_E_SYMBOL_REMOVED
- RULE_F_SYMBOL_RENAMED
- RULE_G_DELETED_SOURCE_FILE
- RULE_H_SIGNATURE_CHANGED
- RULE_I_DOCUMENTATION_UPDATED

Includes strict false-positive prevention guards (Section 5).
"""

import re
from typing import List, Optional, Tuple

from app.analyzers.documentation_mapper import _has_call_syntax, _has_whole_word
from app.analyzers.evidence_builder import (
    build_code_evidence_pair,
    compute_finding_confidence,
    compute_finding_severity,
)
from app.schemas.code_analysis import SymbolChange
from app.schemas.documentation import (
    DocumentationMapping,
    MappingConfidence,
    RelatedSymbolMatch,
)
from app.schemas.drift import (
    DocumentationUnitDiff,
    DriftFinding,
    DriftRuleId,
    DriftStatus,
)


def _strip_quotes(val: Optional[str]) -> str:
    """Strip surrounding single or double quotes from a string literal representation."""
    if not val:
        return ""
    s = val.strip()
    if len(s) >= 2 and ((s[0] == "'" and s[-1] == "'") or (s[0] == '"' and s[-1] == '"')):
        return s[1:-1]
    return s


def _text_mentions_value(text: str, raw_expr: Optional[str]) -> bool:
    """Return True if `text` contains the literal value or expression `raw_expr`."""
    if not text or not raw_expr:
        return False
    raw = raw_expr.strip()
    unquoted = _strip_quotes(raw)
    if raw in text:
        return True
    if unquoted and _has_whole_word(text, unquoted):
        return True
    if unquoted and _has_whole_word(text.lower(), unquoted.lower()):
        return True
    return False


def _is_changelog_unit(mapping: DocumentationMapping) -> bool:
    """Guard 9: Never treat historical changelog entries as current API drift."""
    if mapping.unit_type == "changelog":
        return True
    doc_lower = mapping.documentation_file.lower()
    if "changelog" in doc_lower or "history" in doc_lower:
        return True
    return False


def _apply_weak_mapping_guard(
    status: DriftStatus,
    mapping: DocumentationMapping,
    sym_match: RelatedSymbolMatch,
    reason: str,
) -> Tuple[DriftStatus, str]:
    """
    Guard 7 / Test 27: Weak or ambiguous mapping must produce UNCERTAIN rather than
    CONFIRMED_DRIFT or high-confidence POTENTIAL_DRIFT.
    """
    if mapping.mapping_status == "AMBIGUOUS" or sym_match.confidence == "LOW":
        if status in {"CONFIRMED_DRIFT", "POTENTIAL_DRIFT"}:
            return (
                "UNCERTAIN",
                f"{reason} (Marked UNCERTAIN because the documentation reference matches multiple or low-confidence symbols.)",
            )
    return status, reason


def _build_finding(
    finding_idx: int,
    finding_type: str,
    rule_id: DriftRuleId,
    status: DriftStatus,
    base_confidence: float,
    mapping: DocumentationMapping,
    sym_match: RelatedSymbolMatch,
    unit_diff: Optional[DocumentationUnitDiff],
    change: SymbolChange,
    base_source: Optional[str],
    head_source: Optional[str],
    reason: str,
    suggested_action: str,
) -> DriftFinding:
    """Construct a validated DriftFinding with authentic code and documentation evidence."""
    effective_status, effective_reason = _apply_weak_mapping_guard(
        status=status,
        mapping=mapping,
        sym_match=sym_match,
        reason=reason,
    )

    confidence = compute_finding_confidence(
        base_confidence=base_confidence,
        mapping_confidence=sym_match.confidence,
        status=effective_status,
    )
    severity = compute_finding_severity(
        rule_id=rule_id,
        status=effective_status,
        mapping_confidence=sym_match.confidence,
    )
    old_code_ev, new_code_ev = build_code_evidence_pair(
        change=change,
        base_file_source=base_source,
        head_file_source=head_source,
    )

    prev_doc_text: Optional[str] = None
    if unit_diff and unit_diff.change_type == "modified":
        prev_doc_text = unit_diff.base_text

    return DriftFinding(
        finding_id=f"drift-{finding_idx}",
        finding_type=finding_type,
        rule_id=rule_id,
        status=effective_status,
        severity=severity,
        confidence=confidence,
        documentation_file=mapping.documentation_file,
        documentation_line=mapping.start_line,
        documentation_end_line=mapping.end_line,
        documentation_section=mapping.documentation_section,
        documentation_text=mapping.documentation_text,
        previous_documentation_text=prev_doc_text,
        related_symbol=change.symbol,
        qualified_symbol=change.qualified_name,
        source_file=change.file_path,
        source_line=change.new_line or change.old_line,
        old_source_line=change.old_line,
        old_code_evidence=old_code_ev,
        new_code_evidence=new_code_ev,
        mapping_evidence=list(sym_match.evidence),
        reason=effective_reason,
        suggested_action=suggested_action,
    )


def evaluate_rule_a_changed_default(
    finding_idx: int,
    change: SymbolChange,
    mapping: DocumentationMapping,
    sym_match: RelatedSymbolMatch,
    unit_diff: Optional[DocumentationUnitDiff],
    base_source: Optional[str],
    head_source: Optional[str],
) -> Optional[DriftFinding]:
    """
    RULE A — Changed Default Parameter.
    Flags documentation only when it mentions the parameter or default value.
    """
    if change.change_type != "DEFAULT_VALUE_CHANGED" or _is_changelog_unit(mapping):
        return None

    param_name = str(change.details.get("parameter") or "")
    old_default = change.details.get("old_default")
    new_default = change.details.get("new_default")
    if not param_name:
        return None

    doc_text = mapping.documentation_text
    section_text = mapping.documentation_section or ""
    combined_text = f"{section_text}\n{doc_text}"

    mentions_param = _has_whole_word(combined_text, param_name)
    mentions_default_kw = "default" in combined_text.lower()
    mentions_old_val = _text_mentions_value(combined_text, old_default)
    mentions_new_val = _text_mentions_value(combined_text, new_default)

    # Check if documentation was updated in head to reflect the new default
    if unit_diff and unit_diff.change_type == "modified" and unit_diff.base_text:
        base_mentions_old = _text_mentions_value(unit_diff.base_text, old_default)
        if base_mentions_old and mentions_new_val and not mentions_old_val:
            return _build_finding(
                finding_idx=finding_idx,
                finding_type="DEFAULT_VALUE_CHANGED",
                rule_id="RULE_A_CHANGED_DEFAULT",
                status="RESOLVED",
                base_confidence=0.91,
                mapping=mapping,
                sym_match=sym_match,
                unit_diff=unit_diff,
                change=change,
                base_source=base_source,
                head_source=head_source,
                reason=(
                    f"Documentation for '{change.qualified_name}' was updated from old default "
                    f"{old_default} to new default {new_default} for parameter '{param_name}'."
                ),
                suggested_action="No further action required; documentation matches the updated default.",
            )

    # Direct contradiction: docs state the old default value
    if mentions_old_val and (mentions_param or mentions_default_kw) and not mentions_new_val:
        return _build_finding(
            finding_idx=finding_idx,
            finding_type="DEFAULT_VALUE_CHANGED",
            rule_id="RULE_A_CHANGED_DEFAULT",
            status="CONFIRMED_DRIFT",
            base_confidence=0.93,
            mapping=mapping,
            sym_match=sym_match,
            unit_diff=unit_diff,
            change=change,
            base_source=base_source,
            head_source=head_source,
            reason=(
                f"Documentation states default value {old_default} for parameter '{param_name}' "
                f"in '{change.qualified_name}', but the code default is now {new_default}."
            ),
            suggested_action=(
                f"Update '{mapping.documentation_file}' (line {mapping.start_line}) to reflect "
                f"the new default value `{param_name}={new_default}`."
            ),
        )

    # Potential drift: docs discuss the parameter's default/optional behavior without quoting the new default
    if mentions_param and mentions_default_kw and not mentions_new_val:
        return _build_finding(
            finding_idx=finding_idx,
            finding_type="DEFAULT_VALUE_CHANGED",
            rule_id="RULE_A_CHANGED_DEFAULT",
            status="POTENTIAL_DRIFT",
            base_confidence=0.77,
            mapping=mapping,
            sym_match=sym_match,
            unit_diff=unit_diff,
            change=change,
            base_source=base_source,
            head_source=head_source,
            reason=(
                f"Default value for parameter '{param_name}' in '{change.qualified_name}' changed "
                f"from {old_default} to {new_default} while documentation describes its default behavior."
            ),
            suggested_action=(
                f"Review '{mapping.documentation_file}' (line {mapping.start_line}) and verify "
                f"the documented default for `{param_name}`."
            ),
        )

    return None


def evaluate_rule_b_removed_or_renamed_parameter(
    finding_idx: int,
    change: SymbolChange,
    mapping: DocumentationMapping,
    sym_match: RelatedSymbolMatch,
    unit_diff: Optional[DocumentationUnitDiff],
    base_source: Optional[str],
    head_source: Optional[str],
) -> Optional[DriftFinding]:
    """
    RULE B — Removed or Renamed Parameter.
    Flags documentation that still references a removed or renamed parameter belonging to the mapped symbol.
    """
    if (
        change.change_type not in {"PARAMETER_REMOVED", "PARAMETER_RENAMED"}
        or _is_changelog_unit(mapping)
    ):
        return None

    if change.change_type == "PARAMETER_REMOVED":
        old_param = str(change.details.get("parameter") or "")
        new_param: Optional[str] = None
    else:
        old_param = str(change.details.get("old_parameter") or "")
        new_param = str(change.details.get("new_parameter") or "")

    if not old_param:
        return None

    combined_text = f"{mapping.documentation_section or ''}\n{mapping.documentation_text}"
    mentions_old_param = _has_whole_word(combined_text, old_param)
    mentions_new_param = bool(new_param and _has_whole_word(combined_text, new_param))

    # Check if documentation was updated in head to remove/rename the parameter
    if unit_diff and unit_diff.change_type == "modified" and unit_diff.base_text:
        base_mentioned_old = _has_whole_word(unit_diff.base_text, old_param)
        if base_mentioned_old and not mentions_old_param:
            if change.change_type == "PARAMETER_REMOVED" or mentions_new_param:
                return _build_finding(
                    finding_idx=finding_idx,
                    finding_type=change.change_type,
                    rule_id="RULE_B_REMOVED_OR_RENAMED_PARAMETER",
                    status="RESOLVED",
                    base_confidence=0.90,
                    mapping=mapping,
                    sym_match=sym_match,
                    unit_diff=unit_diff,
                    change=change,
                    base_source=base_source,
                    head_source=head_source,
                    reason=(
                        f"Documentation for '{change.qualified_name}' was updated to remove reference "
                        f"to outdated parameter '{old_param}'."
                    ),
                    suggested_action="No action needed; parameter documentation was updated.",
                )

    if mentions_old_param:
        if change.change_type == "PARAMETER_REMOVED":
            reason_msg = (
                f"Documentation references parameter '{old_param}' on '{change.qualified_name}', "
                f"which was removed in the head commit."
            )
            action_msg = (
                f"Remove `{old_param}` from the documentation in '{mapping.documentation_file}' "
                f"(line {mapping.start_line})."
            )
        else:
            reason_msg = (
                f"Documentation still references old parameter name '{old_param}' on "
                f"'{change.qualified_name}', which was renamed to '{new_param}'."
            )
            action_msg = (
                f"Replace parameter reference `{old_param}` with `{new_param}` in "
                f"'{mapping.documentation_file}' (line {mapping.start_line})."
            )

        return _build_finding(
            finding_idx=finding_idx,
            finding_type=change.change_type,
            rule_id="RULE_B_REMOVED_OR_RENAMED_PARAMETER",
            status="CONFIRMED_DRIFT",
            base_confidence=0.92,
            mapping=mapping,
            sym_match=sym_match,
            unit_diff=unit_diff,
            change=change,
            base_source=base_source,
            head_source=head_source,
            reason=reason_msg,
            suggested_action=action_msg,
        )

    return None


def evaluate_rule_c_added_required_parameter(
    finding_idx: int,
    change: SymbolChange,
    mapping: DocumentationMapping,
    sym_match: RelatedSymbolMatch,
    unit_diff: Optional[DocumentationUnitDiff],
    base_source: Optional[str],
    head_source: Optional[str],
) -> Optional[DriftFinding]:
    """
    RULE C — Added Required Parameter.
    Guard 6 / Test 21: Do NOT flag optional parameters (where default is not None or *args/**kwargs).
    """
    if change.change_type != "PARAMETER_ADDED" or _is_changelog_unit(mapping):
        return None

    param_default = change.details.get("default")
    param_kind = change.details.get("kind")
    if param_default is not None or param_kind in {"var_positional", "var_keyword"}:
        # Optional parameter addition does not invalidate existing documentation
        return None

    new_param = str(change.details.get("parameter") or "")
    if not new_param or new_param in {"self", "cls"}:
        return None

    combined_text = f"{mapping.documentation_section or ''}\n{mapping.documentation_text}"
    mentions_new_param = _has_whole_word(combined_text, new_param)

    if unit_diff and unit_diff.change_type == "modified" and unit_diff.base_text:
        base_mentioned_new = _has_whole_word(unit_diff.base_text, new_param)
        if not base_mentioned_new and mentions_new_param:
            return _build_finding(
                finding_idx=finding_idx,
                finding_type="PARAMETER_ADDED",
                rule_id="RULE_C_ADDED_REQUIRED_PARAMETER",
                status="RESOLVED",
                base_confidence=0.90,
                mapping=mapping,
                sym_match=sym_match,
                unit_diff=unit_diff,
                change=change,
                base_source=base_source,
                head_source=head_source,
                reason=(
                    f"Documentation for '{change.qualified_name}' was updated to document "
                    f"the newly added required parameter '{new_param}'."
                ),
                suggested_action="No action needed; required parameter is documented.",
            )

    if not mentions_new_param:
        has_call_in_doc = _has_call_syntax(
            mapping.documentation_text, change.symbol
        ) or _has_call_syntax(mapping.documentation_section or "", change.symbol)

        if has_call_in_doc:
            status: DriftStatus = "CONFIRMED_DRIFT"
            base_conf = 0.91
            reason_msg = (
                f"Documentation demonstrates calling '{change.qualified_name}(...)' without "
                f"the newly added required parameter '{new_param}'."
            )
        else:
            status = "POTENTIAL_DRIFT"
            base_conf = 0.78
            reason_msg = (
                f"'{change.qualified_name}' now requires parameter '{new_param}', which is "
                f"missing from this documentation section."
            )

        return _build_finding(
            finding_idx=finding_idx,
            finding_type="PARAMETER_ADDED",
            rule_id="RULE_C_ADDED_REQUIRED_PARAMETER",
            status=status,
            base_confidence=base_conf,
            mapping=mapping,
            sym_match=sym_match,
            unit_diff=unit_diff,
            change=change,
            base_source=base_source,
            head_source=head_source,
            reason=reason_msg,
            suggested_action=(
                f"Update '{mapping.documentation_file}' (line {mapping.start_line}) to include "
                f"required parameter `{new_param}` in `{change.new_signature}`."
            ),
        )

    return None


def evaluate_rule_d_return_contract_changed(
    finding_idx: int,
    change: SymbolChange,
    mapping: DocumentationMapping,
    sym_match: RelatedSymbolMatch,
    unit_diff: Optional[DocumentationUnitDiff],
    base_source: Optional[str],
    head_source: Optional[str],
) -> Optional[DriftFinding]:
    """
    RULE D — Return Type or Return Contract Changes.
    Guard 5 / Test 26: Annotation changes alone must NEVER become CONFIRMED_DRIFT.
    """
    if change.change_type != "RETURN_ANNOTATION_CHANGED" or _is_changelog_unit(mapping):
        return None

    old_ret = change.details.get("old_return_annotation")
    new_ret = change.details.get("new_return_annotation")
    doc_text = mapping.documentation_text
    doc_lower = doc_text.lower()

    mentions_old_ret = bool(old_ret and _text_mentions_value(doc_text, str(old_ret)))
    mentions_new_ret = bool(new_ret and _text_mentions_value(doc_text, str(new_ret)))
    discusses_return = (
        mapping.unit_type == "return_description"
        or "return" in doc_lower
        or "->" in doc_text
    )

    if not (mentions_old_ret or discusses_return):
        return None

    if unit_diff and unit_diff.change_type == "modified" and mentions_new_ret and not mentions_old_ret:
        return _build_finding(
            finding_idx=finding_idx,
            finding_type="RETURN_ANNOTATION_CHANGED",
            rule_id="RULE_D_RETURN_CONTRACT_CHANGED",
            status="RESOLVED",
            base_confidence=0.86,
            mapping=mapping,
            sym_match=sym_match,
            unit_diff=unit_diff,
            change=change,
            base_source=base_source,
            head_source=head_source,
            reason=(
                f"Return documentation for '{change.qualified_name}' was updated to reflect "
                f"the new return annotation '{new_ret}'."
            ),
            suggested_action="No action needed; return documentation matches new annotation.",
        )

    if not mentions_new_ret:
        return _build_finding(
            finding_idx=finding_idx,
            finding_type="RETURN_ANNOTATION_CHANGED",
            rule_id="RULE_D_RETURN_CONTRACT_CHANGED",
            status="POTENTIAL_DRIFT",
            base_confidence=0.73 if mentions_old_ret else 0.65,
            mapping=mapping,
            sym_match=sym_match,
            unit_diff=unit_diff,
            change=change,
            base_source=base_source,
            head_source=head_source,
            reason=(
                f"Return annotation for '{change.qualified_name}' changed from '{old_ret}' to "
                f"'{new_ret}'. Because an annotation change alone does not prove runtime behavior "
                f"changed, verify whether the documented return contract is still accurate."
            ),
            suggested_action=(
                f"Review the return description in '{mapping.documentation_file}' "
                f"(line {mapping.start_line}) against `-> {new_ret}`."
            ),
        )

    return None


def evaluate_rule_e_symbol_removed(
    finding_idx: int,
    change: SymbolChange,
    mapping: DocumentationMapping,
    sym_match: RelatedSymbolMatch,
    unit_diff: Optional[DocumentationUnitDiff],
    base_source: Optional[str],
    head_source: Optional[str],
    is_deleted_file: bool = False,
) -> Optional[DriftFinding]:
    """
    RULE E — Function, Method, or Class Removed (and RULE G when the entire source file was deleted).
    """
    if (
        change.change_type not in {"FUNCTION_REMOVED", "METHOD_REMOVED", "CLASS_REMOVED"}
        or _is_changelog_unit(mapping)
    ):
        return None

    rule_id: DriftRuleId = (
        "RULE_G_DELETED_SOURCE_FILE" if is_deleted_file else "RULE_E_SYMBOL_REMOVED"
    )
    if is_deleted_file:
        reason_msg = (
            f"Documentation references {change.symbol_type} '{change.qualified_name}' from "
            f"deleted Python source file '{change.file_path}', which no longer exists at the head commit."
        )
    else:
        reason_msg = (
            f"Documentation references {change.symbol_type} '{change.qualified_name}', "
            f"which was removed from '{change.file_path}' in the head commit."
        )

    return _build_finding(
        finding_idx=finding_idx,
        finding_type=change.change_type,
        rule_id=rule_id,
        status="CONFIRMED_DRIFT",
        base_confidence=0.95,
        mapping=mapping,
        sym_match=sym_match,
        unit_diff=unit_diff,
        change=change,
        base_source=base_source,
        head_source=head_source,
        reason=reason_msg,
        suggested_action=(
            f"Remove or replace the reference to `{change.qualified_name}` in "
            f"'{mapping.documentation_file}' (line {mapping.start_line})."
        ),
    )


def evaluate_rule_f_symbol_renamed(
    finding_idx: int,
    change: SymbolChange,
    mapping: DocumentationMapping,
    sym_match: RelatedSymbolMatch,
    unit_diff: Optional[DocumentationUnitDiff],
    base_source: Optional[str],
    head_source: Optional[str],
) -> Optional[DriftFinding]:
    """
    RULE F — Function or Method Renamed.
    Detects documentation still referencing `old_name` or resolved documentation updated to `new_name`.
    """
    if change.change_type != "FUNCTION_RENAMED" or _is_changelog_unit(mapping):
        return None

    old_name = str(change.details.get("old_name") or "")
    new_name = str(change.details.get("new_name") or change.symbol)
    old_qname = str(change.details.get("old_qualified_name") or old_name)
    new_qname = str(change.details.get("new_qualified_name") or change.qualified_name)
    if not old_name:
        return None

    combined_text = f"{mapping.documentation_section or ''}\n{mapping.documentation_text}"
    mentions_old = _has_whole_word(combined_text, old_name) or _has_whole_word(
        combined_text, old_qname
    )
    mentions_new = _has_whole_word(combined_text, new_name) or _has_whole_word(
        combined_text, new_qname
    )

    if unit_diff and unit_diff.change_type == "modified" and unit_diff.base_text:
        base_mentioned_old = _has_whole_word(unit_diff.base_text, old_name)
        if base_mentioned_old and mentions_new and not mentions_old:
            return _build_finding(
                finding_idx=finding_idx,
                finding_type="FUNCTION_RENAMED",
                rule_id="RULE_F_SYMBOL_RENAMED",
                status="RESOLVED",
                base_confidence=0.92,
                mapping=mapping,
                sym_match=sym_match,
                unit_diff=unit_diff,
                change=change,
                base_source=base_source,
                head_source=head_source,
                reason=(
                    f"Documentation was updated from old function name '{old_qname}' "
                    f"to new name '{new_qname}'."
                ),
                suggested_action="No action needed; renamed symbol is updated in documentation.",
            )

    if mentions_old:
        return _build_finding(
            finding_idx=finding_idx,
            finding_type="FUNCTION_RENAMED",
            rule_id="RULE_F_SYMBOL_RENAMED",
            status="CONFIRMED_DRIFT",
            base_confidence=0.94,
            mapping=mapping,
            sym_match=sym_match,
            unit_diff=unit_diff,
            change=change,
            base_source=base_source,
            head_source=head_source,
            reason=(
                f"Documentation still references old function name '{old_qname}', "
                f"which was renamed to '{new_qname}' in '{change.file_path}'."
            ),
            suggested_action=(
                f"Update `{old_qname}` to `{new_qname}` in '{mapping.documentation_file}' "
                f"(line {mapping.start_line})."
            ),
        )

    return None


def evaluate_rule_h_signature_changed(
    finding_idx: int,
    change: SymbolChange,
    mapping: DocumentationMapping,
    sym_match: RelatedSymbolMatch,
    unit_diff: Optional[DocumentationUnitDiff],
    base_source: Optional[str],
    head_source: Optional[str],
) -> Optional[DriftFinding]:
    """
    RULE H — Changed Function Signature (PARAMETER_REORDERED, ASYNC_STATUS_CHANGED, PARAMETER_ANNOTATION_CHANGED).
    """
    if _is_changelog_unit(mapping):
        return None

    combined_text = f"{mapping.documentation_section or ''}\n{mapping.documentation_text}"

    if change.change_type == "PARAMETER_REORDERED":
        old_order: List[str] = list(change.details.get("old_order") or [])
        new_order: List[str] = list(change.details.get("new_order") or [])
        has_call = _has_call_syntax(combined_text, change.symbol)
        mentioned_params = [p for p in old_order if _has_whole_word(combined_text, p)]

        if has_call or len(mentioned_params) >= 2:
            return _build_finding(
                finding_idx=finding_idx,
                finding_type="PARAMETER_REORDERED",
                rule_id="RULE_H_SIGNATURE_CHANGED",
                status="POTENTIAL_DRIFT",
                base_confidence=0.82,
                mapping=mapping,
                sym_match=sym_match,
                unit_diff=unit_diff,
                change=change,
                base_source=base_source,
                head_source=head_source,
                reason=(
                    f"Parameters of '{change.qualified_name}' were reordered from {old_order} "
                    f"to {new_order}, which may affect documented calls or parameter order."
                ),
                suggested_action=(
                    f"Update parameter ordering in '{mapping.documentation_file}' "
                    f"(line {mapping.start_line}) to match `{change.new_signature}`."
                ),
            )

    elif change.change_type == "ASYNC_STATUS_CHANGED":
        is_async = bool(change.details.get("is_async"))
        mentions_await = bool(re.search(r"\b(?:await|async)\b", combined_text))

        if is_async and not mentions_await:
            return _build_finding(
                finding_idx=finding_idx,
                finding_type="ASYNC_STATUS_CHANGED",
                rule_id="RULE_H_SIGNATURE_CHANGED",
                status="POTENTIAL_DRIFT",
                base_confidence=0.82,
                mapping=mapping,
                sym_match=sym_match,
                unit_diff=unit_diff,
                change=change,
                base_source=base_source,
                head_source=head_source,
                reason=(
                    f"'{change.qualified_name}' changed from a synchronous function to an "
                    f"asynchronous coroutine (`async def`), but documentation does not mention `await`."
                ),
                suggested_action=(
                    f"Update '{mapping.documentation_file}' (line {mapping.start_line}) to show "
                    f"`await {change.symbol}(...)`."
                ),
            )
        if not is_async and mentions_await:
            return _build_finding(
                finding_idx=finding_idx,
                finding_type="ASYNC_STATUS_CHANGED",
                rule_id="RULE_H_SIGNATURE_CHANGED",
                status="CONFIRMED_DRIFT",
                base_confidence=0.89,
                mapping=mapping,
                sym_match=sym_match,
                unit_diff=unit_diff,
                change=change,
                base_source=base_source,
                head_source=head_source,
                reason=(
                    f"'{change.qualified_name}' changed from `async def` to a regular synchronous "
                    f"function, but documentation still uses `await`/`async`."
                ),
                suggested_action=(
                    f"Remove `await`/`async` for `{change.qualified_name}` in "
                    f"'{mapping.documentation_file}' (line {mapping.start_line})."
                ),
            )

    elif change.change_type == "PARAMETER_ANNOTATION_CHANGED":
        param_name = str(change.details.get("parameter") or "")
        old_ann = change.details.get("old_annotation")
        new_ann = change.details.get("new_annotation")
        if (
            param_name
            and old_ann
            and _has_whole_word(combined_text, param_name)
            and _text_mentions_value(combined_text, str(old_ann))
            and not _text_mentions_value(combined_text, str(new_ann))
        ):
            return _build_finding(
                finding_idx=finding_idx,
                finding_type="PARAMETER_ANNOTATION_CHANGED",
                rule_id="RULE_H_SIGNATURE_CHANGED",
                status="POTENTIAL_DRIFT",
                base_confidence=0.72,
                mapping=mapping,
                sym_match=sym_match,
                unit_diff=unit_diff,
                change=change,
                base_source=base_source,
                head_source=head_source,
                reason=(
                    f"Type annotation for parameter '{param_name}' on '{change.qualified_name}' "
                    f"changed from '{old_ann}' to '{new_ann}', while documentation mentions '{old_ann}'."
                ),
                suggested_action=(
                    f"Verify whether the documented type for `{param_name}` in "
                    f"'{mapping.documentation_file}' (line {mapping.start_line}) should be `{new_ann}`."
                ),
            )

    return None


def evaluate_rule_i_documentation_updated(
    finding_idx: int,
    change: SymbolChange,
    mapping: DocumentationMapping,
    sym_match: RelatedSymbolMatch,
    unit_diff: Optional[DocumentationUnitDiff],
    base_source: Optional[str],
    head_source: Optional[str],
) -> Optional[DriftFinding]:
    """
    RULE I — Changed Documentation.
    When documentation mapped to a changed symbol was modified alongside a signature-level
    code change, but earlier deterministic rules could neither confirm drift nor confirm
    resolution, report UNCERTAIN rather than assuming the edit fixed the drift.
    """
    if _is_changelog_unit(mapping):
        return None

    if not unit_diff or unit_diff.change_type != "modified":
        return None

    # Guard 4 / Test 25: Body-only modification does not trigger drift or uncertainty
    if change.change_type in {"FUNCTION_MODIFIED", "METHOD_MODIFIED"}:
        return None

    # Guard 6 / Test 21: Optional parameter addition does not trigger drift
    if change.change_type == "PARAMETER_ADDED" and (
        change.details.get("default") is not None
        or change.details.get("kind") in {"var_positional", "var_keyword"}
    ):
        return None

    return _build_finding(
        finding_idx=finding_idx,
        finding_type=change.change_type,
        rule_id="RULE_I_DOCUMENTATION_UPDATED",
        status="UNCERTAIN",
        base_confidence=0.48,
        mapping=mapping,
        sym_match=sym_match,
        unit_diff=unit_diff,
        change=change,
        base_source=base_source,
        head_source=head_source,
        reason=(
            f"Documentation for '{change.qualified_name}' was modified in the same commit range "
            f"as a `{change.change_type}` code change, but static analysis cannot deterministically "
            f"confirm whether the edit completely addresses the code change."
        ),
        suggested_action=(
            f"Manually verify the updated documentation in '{mapping.documentation_file}' "
            f"(line {mapping.start_line}) against `{change.new_signature or change.old_signature}`."
        ),
    )
