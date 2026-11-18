"""
Evidence Builder & Confidence/Severity Scoring Helper for DocGuard (Milestone 5).

Builds authentic code and documentation evidence directly from repository contents
and applies transparent, deterministic rules for assigning confidence (0.0–1.0)
and severity (LOW, MEDIUM, HIGH, CRITICAL).
"""

from typing import Optional

from app.schemas.code_analysis import SymbolChange
from app.schemas.documentation import MappingConfidence
from app.schemas.drift import DriftRuleId, DriftSeverity, DriftStatus

MAX_EVIDENCE_LINES = 5


def extract_source_snippet(
    source_text: Optional[str],
    start_line: Optional[int],
    end_line: Optional[int],
    fallback_signature: Optional[str],
    missing_reason: str = "[Not present in this commit]",
) -> str:
    """
    Extract actual source code lines from a repository Python file between
    `start_line` and `end_line` (capped at MAX_EVIDENCE_LINES for readability).
    Never fabricates code; explicitly reports when a file or symbol is absent.
    """
    if source_text and start_line is not None and start_line >= 1:
        lines = source_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        if start_line <= len(lines):
            effective_end = min(
                len(lines),
                end_line if end_line and end_line >= start_line else start_line,
                start_line + MAX_EVIDENCE_LINES - 1,
            )
            snippet_lines = lines[start_line - 1 : effective_end]
            snippet = "\n".join(snippet_lines).rstrip()
            if snippet:
                return snippet

    if fallback_signature:
        if fallback_signature.startswith(("def ", "async def ", "class ")):
            return f"{fallback_signature}:"
        return f"def {fallback_signature}:"

    return missing_reason


def build_code_evidence_pair(
    change: SymbolChange,
    base_file_source: Optional[str],
    head_file_source: Optional[str],
) -> tuple[str, str]:
    """
    Build `(old_code_evidence, new_code_evidence)` for a SymbolChange using actual
    base and head Python file contents.
    """
    if change.change_type in {"FUNCTION_ADDED", "METHOD_ADDED", "CLASS_ADDED"}:
        old_ev = "[Symbol did not exist in base commit]"
    else:
        old_ev = extract_source_snippet(
            source_text=base_file_source,
            start_line=change.old_line,
            end_line=change.old_end_line,
            fallback_signature=change.old_signature,
            missing_reason="[Symbol not present in base commit]",
        )

    if change.change_type in {"FUNCTION_REMOVED", "METHOD_REMOVED", "CLASS_REMOVED"}:
        new_ev = "[Symbol removed in head commit]"
    else:
        new_ev = extract_source_snippet(
            source_text=head_file_source,
            start_line=change.new_line,
            end_line=change.new_end_line,
            fallback_signature=change.new_signature,
            missing_reason="[Symbol not present in head commit]",
        )

    return old_ev, new_ev


def compute_finding_confidence(
    base_confidence: float,
    mapping_confidence: Optional[MappingConfidence],
    status: DriftStatus,
) -> float:
    """
    Deterministically compute a finding confidence score in [0.0, 1.0].

    Methodology:
    - Starts from the rule's base evidence confidence.
    - Adjusts according to the documentation-to-code mapping confidence:
      * HIGH mapping: +0.03
      * MEDIUM mapping: -0.07
      * LOW mapping: -0.22
    - Caps UNCERTAIN status at 0.55 and enforces bounds [0.15, 0.98].
    """
    score = base_confidence
    if mapping_confidence == "HIGH":
        score += 0.03
    elif mapping_confidence == "MEDIUM":
        score -= 0.07
    elif mapping_confidence == "LOW":
        score -= 0.22

    if status == "UNCERTAIN":
        score = min(score, 0.55)
    elif status == "CONFIRMED_DRIFT":
        score = max(score, 0.82)

    return round(max(0.15, min(0.98, score)), 2)


def compute_finding_severity(
    rule_id: DriftRuleId,
    status: DriftStatus,
    mapping_confidence: Optional[MappingConfidence],
) -> DriftSeverity:
    """
    Deterministically assign finding severity (LOW, MEDIUM, HIGH, CRITICAL).

    Methodology:
    - RESOLVED, UNCHANGED, or UNCERTAIN findings are LOW (or MEDIUM if high-impact symbol).
    - CONFIRMED_DRIFT on removed symbols, deleted source files, renamed symbols,
      or missing required parameters in documented calls -> CRITICAL or HIGH.
    - CONFIRMED_DRIFT on contradicted default values or removed parameters -> HIGH.
    - POTENTIAL_DRIFT on signature/default/parameter changes -> HIGH or MEDIUM.
    - POTENTIAL_DRIFT on return type annotations -> MEDIUM.
    """
    if status in {"RESOLVED", "UNCHANGED"}:
        return "LOW"

    if status == "UNCERTAIN":
        return "LOW" if mapping_confidence == "LOW" else "MEDIUM"

    if rule_id in {
        "RULE_E_SYMBOL_REMOVED",
        "RULE_G_DELETED_SOURCE_FILE",
        "RULE_C_ADDED_REQUIRED_PARAMETER",
    }:
        return "CRITICAL" if status == "CONFIRMED_DRIFT" else "HIGH"

    if rule_id in {
        "RULE_F_SYMBOL_RENAMED",
        "RULE_B_REMOVED_OR_RENAMED_PARAMETER",
        "RULE_A_CHANGED_DEFAULT",
    }:
        return "HIGH" if status == "CONFIRMED_DRIFT" else "MEDIUM"

    if rule_id == "RULE_H_SIGNATURE_CHANGED":
        return "HIGH" if status == "CONFIRMED_DRIFT" else "MEDIUM"

    if rule_id in {"RULE_D_RETURN_CONTRACT_CHANGED", "RULE_I_DOCUMENTATION_UPDATED"}:
        return "MEDIUM"

    return "LOW"
