"""
Evidence-Based Documentation-to-Code Mapping Engine for DocGuard (Milestone 4).

Maps extracted DocumentationUnit items to Python AST symbols (ExtractedSymbol)
using deterministic, explainable evidence:
- Exact qualified name & symbol name references
- API section headings & heading hierarchy context
- Inline code spans & explicit call syntax `symbol(...)`
- Source file / module path references
- Parameter name and return annotation corroboration
"""

import os
import re
from typing import Dict, List, Optional, Set, Tuple

from app.schemas.code_analysis import ExtractedSymbol
from app.schemas.documentation import (
    DocumentationMapping,
    DocumentationUnit,
    MappingConfidence,
    MappingStatus,
    RelatedSymbolMatch,
)

# Short single-word English verbs/nouns that require code formatting (`...`),
# call parentheses `name()`, qualified prefix `Class.name`, API heading context,
# or explicit code keywords ("function name", "method name") to avoid matching ordinary prose.
_COMMON_PROSE_WORDS: Set[str] = {
    "get",
    "set",
    "run",
    "add",
    "put",
    "pop",
    "map",
    "log",
    "app",
    "api",
    "url",
    "key",
    "all",
    "any",
    "new",
    "old",
    "end",
    "use",
    "try",
    "fix",
    "main",
    "test",
    "open",
    "read",
    "save",
    "load",
    "send",
    "call",
    "find",
    "list",
    "dict",
    "info",
    "help",
    "init",
    "name",
    "type",
    "data",
    "user",
    "file",
    "path",
    "line",
    "text",
    "code",
    "item",
    "view",
    "form",
    "next",
    "stop",
    "done",
    "copy",
    "move",
    "join",
    "sort",
    "show",
    "hide",
    "edit",
    "post",
    "head",
    "base",
    "root",
}


def _module_stem_from_path(file_path: str) -> str:
    """Return the Python module stem from a file path (e.g. `src/calculator.py` -> `calculator`)."""
    norm = file_path.replace("\\", "/")
    base = os.path.basename(norm)
    if base.endswith(".py"):
        base = base[:-3]
    if base == "__init__":
        parent = os.path.basename(os.path.dirname(norm))
        return parent or base
    return base


def _dotted_module_from_path(file_path: str) -> str:
    """Convert `src/pkg/calculator.py` to `pkg.calculator` / `src.pkg.calculator`."""
    norm = file_path.replace("\\", "/").strip("/")
    if norm.endswith(".py"):
        norm = norm[:-3]
    parts = [p for p in norm.split("/") if p and p != "__init__"]
    return ".".join(parts)


def _strip_heading_to_symbol_token(heading: Optional[str]) -> str:
    """Extract the core symbol identifier from a heading like `## calculate_total(price, tax=0)`."""
    if not heading:
        return ""
    cleaned = heading.strip().strip("`")
    for prefix in ("async def ", "def ", "class ", "method ", "function "):
        if cleaned.lower().startswith(prefix):
            cleaned = cleaned[len(prefix) :].strip()
    if "(" in cleaned:
        cleaned = cleaned.split("(", 1)[0].strip()
    return cleaned.strip("`").strip()


def _has_whole_word(text: str, token: str) -> bool:
    """Return True if `token` appears as an exact case-sensitive whole word in `text`."""
    if not text or not token:
        return False
    pattern = r"(?<![A-Za-z0-9_])" + re.escape(token) + r"(?![A-Za-z0-9_])"
    return bool(re.search(pattern, text))


def _has_call_syntax(text: str, token: str) -> bool:
    """Return True if `token(` appears as a function/method call in `text`."""
    if not text or not token:
        return False
    pattern = r"(?<![A-Za-z0-9_])" + re.escape(token) + r"\s*\("
    return bool(re.search(pattern, text))


def _has_explicit_code_descriptor(text: str, token: str) -> bool:
    """Return True if `text` explicitly says `function <token>`, `class <token>`, `<token> method`, etc."""
    if not text or not token:
        return False
    escaped = re.escape(token)
    forward = rf"\b(?:function|method|class|def|callable|decorator|endpoint)\s+`?{escaped}`?(?![A-Za-z0-9_])"
    backward = rf"(?<![A-Za-z0-9_])`?{escaped}`?\s+(?:function|method|class|callable|decorator|endpoint)\b"
    return bool(
        re.search(forward, text, re.IGNORECASE)
        or re.search(backward, text, re.IGNORECASE)
    )


def _is_generic_prose_word(symbol_name: str) -> bool:
    """Return True if `symbol_name` is a short single-word identifier prone to prose collisions."""
    if "_" in symbol_name:
        return False
    if any(ch.isupper() for ch in symbol_name):
        return False
    return symbol_name.lower() in _COMMON_PROSE_WORDS or len(symbol_name) <= 3


def _evaluate_symbol_against_unit(
    unit: DocumentationUnit,
    symbol: ExtractedSymbol,
    inline_set: Set[str],
    identifier_set: Set[str],
    heading_symbol_token: str,
    hierarchy_symbol_tokens: Set[str],
) -> Optional[Tuple[int, list[str], list[str]]]:
    """
    Evaluate whether `unit` references `symbol` and compute an evidence score,
    matching reasons, and human-readable evidence statements.

    Returns:
        (score, matching_reasons, evidence_list) or None if no valid evidence exists.
    """
    # Do not force-map installation instructions or license/general info without explicit code tokens
    if unit.unit_type in {"installation", "contribution"} and not unit.is_code_example:
        if (
            symbol.qualified_name not in inline_set
            and f"{symbol.name}()" not in inline_set
        ):
            return None

    score = 0
    reasons: list[str] = []
    evidence: list[str] = []

    sym_name = symbol.name
    q_name = symbol.qualified_name
    text = unit.original_text
    heading = unit.section_heading or ""
    combined_hierarchy = " > ".join(unit.heading_hierarchy)

    is_generic_name = _is_generic_prose_word(sym_name)

    # 1. Check Qualified Name Reference (e.g. `Calculator.calculate_total`)
    has_qualified_ref = False
    if "." in q_name:
        if (
            q_name in inline_set
            or q_name in identifier_set
            or _has_whole_word(text, q_name)
            or _has_whole_word(heading, q_name)
        ):
            has_qualified_ref = True
            score += 95
            reasons.append("Exact qualified symbol name reference")
            evidence.append(f"Documentation explicitly references qualified name '{q_name}'")

    # 2. Check Section Heading Match (e.g. `## calculate_total()` or `### class Calculator`)
    has_heading_match = False
    if heading_symbol_token and (
        heading_symbol_token == sym_name or heading_symbol_token == q_name
    ):
        has_heading_match = True
        score += 85
        reasons.append("Matching API section heading")
        evidence.append(f"Section heading '{heading}' directly targets '{sym_name}'")
    elif sym_name in hierarchy_symbol_tokens or q_name in hierarchy_symbol_tokens:
        has_heading_match = True
        score += 65
        reasons.append("Enclosing section heading reference")
        evidence.append(
            f"Heading hierarchy '{combined_hierarchy}' scopes documentation to '{sym_name}'"
        )
    elif not is_generic_name and _has_whole_word(heading, sym_name):
        has_heading_match = True
        score += 70
        reasons.append("Symbol referenced in section heading")
        evidence.append(f"Section heading '{heading}' mentions '{sym_name}'")

    # 3. Check Inline Code Reference (`symbol` or `symbol(...)`)
    has_inline_match = False
    for span in unit.inline_code:
        if (
            span == sym_name
            or span == q_name
            or span.startswith(f"{sym_name}(")
            or span.startswith(f"{q_name}(")
            or f".{sym_name}(" in span
        ):
            has_inline_match = True
            break

    if has_inline_match:
        score += 80
        reasons.append(f"Exact inline code reference to {symbol.symbol_type}")
        evidence.append(f"Inline code span explicitly references `{sym_name}`")

    # 4. Check Call Syntax `symbol(...)` in Text or Code Block
    has_call_match = _has_call_syntax(text, q_name) or _has_call_syntax(text, sym_name)
    if has_call_match and not has_inline_match:
        if unit.is_code_example:
            score += 65
            reasons.append("Function/method invocation in code example")
            evidence.append(f"Code block invokes `{sym_name}(...)`")
        else:
            score += 80
            reasons.append("Explicit call syntax reference")
            evidence.append(f"Documentation references call `{sym_name}(...)`")

    # 5. Check Explicit Code Descriptor (`the calculate_total function`, `class Calculator`)
    has_descriptor_match = _has_explicit_code_descriptor(text, sym_name)
    if has_descriptor_match:
        score += 80
        reasons.append(f"Explicit {symbol.symbol_type} name reference")
        evidence.append(
            f"Documentation explicitly describes {symbol.symbol_type} '{sym_name}'"
        )

    # 6. Check Exact Identifier Token in Text (non-generic names like `calculate_total`, `PaymentProcessor`)
    has_exact_word_match = False
    if not is_generic_name and (
        sym_name in identifier_set or _has_whole_word(text, sym_name)
    ):
        has_exact_word_match = True
        if not (has_qualified_ref or has_heading_match or has_inline_match or has_call_match or has_descriptor_match):
            if unit.is_code_example:
                score += 55
                reasons.append(f"Exact {symbol.symbol_type} identifier in code block")
                evidence.append(f"Code example references identifier '{sym_name}'")
            else:
                score += 75
                reasons.append(f"Exact {symbol.symbol_type} name reference")
                evidence.append(f"Documentation text references '{sym_name}'")

    # Primary evidence gate: a symbol MUST be referenced either directly (by name, heading,
    # inline code, call syntax, or qualified name) to be considered a candidate.
    has_primary_symbol_reference = (
        has_qualified_ref
        or has_heading_match
        or has_inline_match
        or has_call_match
        or has_descriptor_match
        or has_exact_word_match
    )

    if not has_primary_symbol_reference:
        return None

    # 7. Supporting Evidence: Parent Class Context (for methods)
    if symbol.parent_class:
        if (
            symbol.parent_class in inline_set
            or symbol.parent_class in identifier_set
            or symbol.parent_class in hierarchy_symbol_tokens
            or _has_whole_word(text, symbol.parent_class)
            or _has_whole_word(heading, symbol.parent_class)
        ):
            score += 30
            reasons.append("Enclosing class context match")
            evidence.append(
                f"Documentation also references parent class '{symbol.parent_class}'"
            )

    # 8. Supporting Evidence: Source File or Module Path Reference
    norm_source = symbol.file_path.replace("\\", "/")
    module_stem = _module_stem_from_path(norm_source)
    dotted_mod = _dotted_module_from_path(norm_source)

    if norm_source in text or os.path.basename(norm_source) in text:
        score += 25
        reasons.append("Explicit source file path reference")
        evidence.append(f"Documentation mentions source file '{norm_source}'")
    elif (
        module_stem
        and not _is_generic_prose_word(module_stem)
        and (_has_whole_word(text, module_stem) or _has_whole_word(heading, module_stem))
    ) or (dotted_mod and dotted_mod in text):
        score += 15
        reasons.append("Module name context match")
        evidence.append(f"Documentation references module '{module_stem}'")

    # 9. Supporting Evidence: Parameter Name References
    matched_params: list[str] = []
    for param in symbol.parameters:
        if param.name in {"self", "cls"}:
            continue
        if (
            param.name in inline_set
            or _has_whole_word(text, param.name)
            or _has_whole_word(heading, param.name)
        ):
            matched_params.append(param.name)

    if matched_params:
        score += min(30, 12 * len(matched_params))
        reasons.append("Matching function parameter reference")
        evidence.append(
            f"Documentation references parameter(s): {', '.join(matched_params)}"
        )

    # 10. Supporting Evidence: Return Annotation Reference
    if symbol.return_annotation and (
        symbol.return_annotation in inline_set
        or _has_whole_word(text, symbol.return_annotation)
    ):
        score += 10
        reasons.append("Matching return type annotation reference")
        evidence.append(
            f"Documentation mentions return annotation '{symbol.return_annotation}'"
        )

    # 11. Disambiguation preference: public/primary module symbol vs test-local nested symbol
    is_test_file = (
        norm_source.startswith("tests/")
        or "/tests/" in norm_source
        or os.path.basename(norm_source).startswith("test_")
    )
    is_nested_in_test = symbol.qualified_name.startswith("test_") and "." in symbol.qualified_name
    if not is_test_file and not is_nested_in_test:
        score += 25

    return score, reasons, evidence


def _score_to_confidence(score: int, is_ambiguous_same_name: bool) -> MappingConfidence:
    """Convert a numerical evidence score into HIGH, MEDIUM, or LOW confidence."""
    if is_ambiguous_same_name:
        return "LOW" if score < 85 else "MEDIUM"
    if score >= 80:
        return "HIGH"
    if score >= 50:
        return "MEDIUM"
    return "LOW"


def map_documentation_units_to_symbols(
    units: list[DocumentationUnit],
    symbols: list[ExtractedSymbol],
) -> list[DocumentationMapping]:
    """
    Map a list of extracted DocumentationUnit items against all ExtractedSymbol
    items discovered in the repository's Python files.
    """
    mappings: list[DocumentationMapping] = []

    for idx, unit in enumerate(units, start=1):
        inline_set = set(unit.inline_code)
        identifier_set = set(unit.referenced_identifiers)
        heading_symbol_token = _strip_heading_to_symbol_token(unit.section_heading)
        hierarchy_symbol_tokens = {
            _strip_heading_to_symbol_token(h)
            for h in unit.heading_hierarchy
            if _strip_heading_to_symbol_token(h)
        }

        # Group candidate matches by short symbol name so we can detect genuine
        # ambiguity (same symbol name defined in multiple classes/files) vs
        # multi-symbol references (two distinct symbol names mentioned in one unit).
        candidates_by_name: Dict[
            str, List[Tuple[ExtractedSymbol, int, list[str], list[str]]]
        ] = {}

        for sym in symbols:
            eval_result = _evaluate_symbol_against_unit(
                unit=unit,
                symbol=sym,
                inline_set=inline_set,
                identifier_set=identifier_set,
                heading_symbol_token=heading_symbol_token,
                hierarchy_symbol_tokens=hierarchy_symbol_tokens,
            )
            if eval_result is not None:
                score, reasons, evidence = eval_result
                candidates_by_name.setdefault(sym.name, []).append(
                    (sym, score, reasons, evidence)
                )

        related_matches: list[RelatedSymbolMatch] = []
        has_unresolved_ambiguity = False

        for sym_name, group in candidates_by_name.items():
            # Sort candidates for this symbol name by descending evidence score
            group.sort(key=lambda item: item[1], reverse=True)

            if len(group) == 1:
                sym, score, reasons, evidence = group[0]
                confidence = _score_to_confidence(score, is_ambiguous_same_name=False)
                related_matches.append(
                    RelatedSymbolMatch(
                        symbol=sym.name,
                        qualified_name=sym.qualified_name,
                        source_file=sym.file_path,
                        symbol_type=sym.symbol_type,
                        signature=sym.signature,
                        line_start=sym.start_line,
                        line_end=sym.end_line,
                        confidence=confidence,
                        matching_reasons=reasons,
                        evidence=evidence,
                    )
                )
            else:
                # Multiple symbols share the same short name (e.g. two classes define `validate`).
                # Check if the top candidate has clearly stronger disambiguating evidence (>= 25 points lead).
                top_score = group[0][1]
                second_score = group[1][1]

                if top_score - second_score >= 25:
                    sym, score, reasons, evidence = group[0]
                    confidence = _score_to_confidence(score, is_ambiguous_same_name=False)
                    related_matches.append(
                        RelatedSymbolMatch(
                            symbol=sym.name,
                            qualified_name=sym.qualified_name,
                            source_file=sym.file_path,
                            symbol_type=sym.symbol_type,
                            signature=sym.signature,
                            line_start=sym.start_line,
                            line_end=sym.end_line,
                            confidence=confidence,
                            matching_reasons=reasons,
                            evidence=evidence,
                        )
                    )
                else:
                    # Tied / close candidates for the same short symbol name -> AMBIGUOUS
                    has_unresolved_ambiguity = True
                    tied_candidates = [
                        item for item in group if top_score - item[1] < 25
                    ]
                    for sym, score, reasons, evidence in tied_candidates:
                        ambig_reasons = list(reasons) + [
                            f"Ambiguous reference: '{sym_name}' matches multiple symbols across the codebase"
                        ]
                        confidence = _score_to_confidence(
                            score, is_ambiguous_same_name=True
                        )
                        related_matches.append(
                            RelatedSymbolMatch(
                                symbol=sym.name,
                                qualified_name=sym.qualified_name,
                                source_file=sym.file_path,
                                symbol_type=sym.symbol_type,
                                signature=sym.signature,
                                line_start=sym.start_line,
                                line_end=sym.end_line,
                                confidence=confidence,
                                matching_reasons=ambig_reasons,
                                evidence=evidence,
                            )
                        )

        # Sort related_matches by confidence rank (HIGH -> MEDIUM -> LOW)
        conf_order = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
        related_matches.sort(
            key=lambda m: (conf_order.get(m.confidence, 0), m.qualified_name),
            reverse=True,
        )

        if not related_matches:
            mapping_status: MappingStatus = "UNMAPPED"
            highest_confidence: Optional[MappingConfidence] = None
        elif has_unresolved_ambiguity:
            mapping_status = "AMBIGUOUS"
            highest_confidence = related_matches[0].confidence
        else:
            mapping_status = "MAPPED"
            highest_confidence = related_matches[0].confidence

        mappings.append(
            DocumentationMapping(
                mapping_id=f"map-{idx}",
                unit_id=unit.unit_id,
                documentation_file=unit.documentation_file,
                documentation_section=unit.section_heading,
                heading_hierarchy=list(unit.heading_hierarchy),
                unit_type=unit.unit_type,
                start_line=unit.start_line,
                end_line=unit.end_line,
                documentation_text=unit.original_text,
                referenced_identifiers=list(unit.referenced_identifiers),
                related_symbols=related_matches,
                mapping_status=mapping_status,
                highest_confidence=highest_confidence,
            )
        )

    return mappings
