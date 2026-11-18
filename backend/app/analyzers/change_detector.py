"""
AST Symbol Change Detector for DocGuard (Milestone 3).

Compares extracted Python AST symbols between a base commit and a head commit
and emits structured SymbolChange findings across all 17 supported change types.
"""

from difflib import SequenceMatcher
from typing import Optional, Tuple

from app.schemas.code_analysis import (
    ExtractedSymbol,
    ParameterSymbol,
    SymbolChange,
)


def _enclosing_scope_prefix(qualified_name: str) -> str:
    """Return the enclosing scope prefix (everything before the final `.name`)."""
    if "." not in qualified_name:
        return ""
    return qualified_name.rsplit(".", 1)[0]


def _parameter_structure_tuple(
    params: list[ParameterSymbol],
    include_names: bool = True,
) -> tuple:
    """Create a hashable tuple of parameter metadata for comparison."""
    if include_names:
        return tuple((p.name, p.kind, p.default, p.annotation) for p in params)
    return tuple((p.kind, p.default, p.annotation) for p in params)


def _is_confident_function_rename(
    old_fn: ExtractedSymbol,
    new_fn: ExtractedSymbol,
) -> Tuple[bool, float]:
    """
    Conservatively evaluate whether `old_fn` was renamed to `new_fn`.
    Requires identical enclosing scope, matching symbol category, and strong
    AST body or signature+body similarity evidence.
    """
    if old_fn.parent_class != new_fn.parent_class:
        return False, 0.0

    if _enclosing_scope_prefix(old_fn.qualified_name) != _enclosing_scope_prefix(
        new_fn.qualified_name
    ):
        return False, 0.0

    # Methods are reported via METHOD_REMOVED / METHOD_ADDED unless they are top/nested functions
    if old_fn.symbol_type == "method" or new_fn.symbol_type == "method":
        return False, 0.0

    if not old_fn.body_hash or not new_fn.body_hash:
        return False, 0.0

    body_identical = old_fn.body_hash == new_fn.body_hash
    body_similarity = (
        1.0
        if body_identical
        else SequenceMatcher(None, old_fn.body_hash, new_fn.body_hash).ratio()
    )
    exact_params = _parameter_structure_tuple(
        old_fn.parameters, include_names=True
    ) == _parameter_structure_tuple(new_fn.parameters, include_names=True)
    same_param_types = _parameter_structure_tuple(
        old_fn.parameters, include_names=False
    ) == _parameter_structure_tuple(new_fn.parameters, include_names=False)
    name_similarity = SequenceMatcher(None, old_fn.name, new_fn.name).ratio()

    # Trivial body guard (e.g. `pass` or `return None`) requires identical parameter names + similar function name
    is_trivial_body = len(old_fn.body_hash) < 35 and old_fn.body_hash in {
        "Pass()",
        "Return()",
        "Expr(value=Constant(value=Ellipsis))",
    }
    if is_trivial_body:
        if exact_params and len(old_fn.parameters) > 0 and name_similarity >= 0.6:
            return True, 0.75 + (name_similarity * 0.2)
        return False, 0.0

    if body_identical and (exact_params or same_param_types or len(old_fn.body_hash) >= 40):
        score = 0.90 + (0.05 if exact_params else 0.0) + (name_similarity * 0.05)
        return True, score

    if body_similarity >= 0.82 and (exact_params or (same_param_types and name_similarity >= 0.5)):
        score = body_similarity * 0.85 + (name_similarity * 0.15)
        return True, score

    return False, 0.0


def _pair_renamed_functions(
    unmatched_removed: list[ExtractedSymbol],
    unmatched_added: list[ExtractedSymbol],
) -> Tuple[
    list[Tuple[ExtractedSymbol, ExtractedSymbol]],
    list[ExtractedSymbol],
    list[ExtractedSymbol],
]:
    """
    Conservatively pair removed and added functions as FUNCTION_RENAMED only when
    there is an unambiguous, unique high-confidence match in both directions.
    """
    candidates_for_old: dict[int, list[Tuple[int, float]]] = {}
    candidates_for_new: dict[int, list[Tuple[int, float]]] = {}

    for old_idx, old_sym in enumerate(unmatched_removed):
        for new_idx, new_sym in enumerate(unmatched_added):
            is_match, score = _is_confident_function_rename(old_sym, new_sym)
            if is_match:
                candidates_for_old.setdefault(old_idx, []).append((new_idx, score))
                candidates_for_new.setdefault(new_idx, []).append((old_idx, score))

    renamed_pairs: list[Tuple[ExtractedSymbol, ExtractedSymbol]] = []
    matched_old_indices: set[int] = set()
    matched_new_indices: set[int] = set()

    # Only accept 1-to-1 unambiguous matches (no guessing when multiple functions look similar)
    for old_idx, matches in candidates_for_old.items():
        if len(matches) != 1:
            continue
        new_idx, _score = matches[0]
        reverse_matches = candidates_for_new.get(new_idx, [])
        if len(reverse_matches) != 1 or reverse_matches[0][0] != old_idx:
            continue

        renamed_pairs.append((unmatched_removed[old_idx], unmatched_added[new_idx]))
        matched_old_indices.add(old_idx)
        matched_new_indices.add(new_idx)

    remaining_removed = [
        sym for idx, sym in enumerate(unmatched_removed) if idx not in matched_old_indices
    ]
    remaining_added = [
        sym for idx, sym in enumerate(unmatched_added) if idx not in matched_new_indices
    ]
    return renamed_pairs, remaining_removed, remaining_added


def _compare_parameters(
    file_path: str,
    old_sym: ExtractedSymbol,
    new_sym: ExtractedSymbol,
) -> Tuple[list[SymbolChange], bool]:
    """
    Compare parameters between `old_sym` and `new_sym`.
    Returns:
        (parameter_changes, parameter_kind_changed_without_other_event)
    """
    changes: list[SymbolChange] = []
    old_params = old_sym.parameters
    new_params = new_sym.parameters

    old_by_name = {p.name: (idx, p) for idx, p in enumerate(old_params)}
    new_by_name = {p.name: (idx, p) for idx, p in enumerate(new_params)}

    # 1. Check parameter reordering among parameters present in both base and head
    common_in_old_order = [p.name for p in old_params if p.name in new_by_name]
    common_in_new_order = [p.name for p in new_params if p.name in old_by_name]
    if len(common_in_old_order) >= 2 and common_in_old_order != common_in_new_order:
        changes.append(
            SymbolChange(
                file_path=file_path,
                symbol=new_sym.name,
                qualified_name=new_sym.qualified_name,
                symbol_type=new_sym.symbol_type,
                change_type="PARAMETER_REORDERED",
                old_line=old_sym.start_line,
                new_line=new_sym.start_line,
                old_end_line=old_sym.end_line,
                new_end_line=new_sym.end_line,
                old_signature=old_sym.signature,
                new_signature=new_sym.signature,
                summary=f"Parameters reordered in '{new_sym.qualified_name}'",
                details={
                    "old_order": [p.name for p in old_params],
                    "new_order": [p.name for p in new_params],
                },
            )
        )

    unmatched_old = [
        (idx, p) for idx, p in enumerate(old_params) if p.name not in new_by_name
    ]
    unmatched_new = [
        (idx, p) for idx, p in enumerate(new_params) if p.name not in old_by_name
    ]

    paired_by_rename: list[Tuple[ParameterSymbol, ParameterSymbol]] = []
    renamed_old_names: set[str] = set()
    renamed_new_names: set[str] = set()

    # 2. Conservative parameter rename detection:
    # Unambiguous single parameter slot rename at the same index with the same parameter kind
    # and either recognizable name similarity or identical annotation + default signature.
    if (
        len(old_params) == len(new_params)
        and len(unmatched_old) == 1
        and len(unmatched_new) == 1
    ):
        old_idx, old_p = unmatched_old[0]
        new_idx, new_p = unmatched_new[0]
        param_name_ratio = SequenceMatcher(
            None, old_p.name.lower(), new_p.name.lower()
        ).ratio()
        has_name_affinity = (
            param_name_ratio >= 0.45
            or old_p.name.lower() in new_p.name.lower()
            or new_p.name.lower() in old_p.name.lower()
        )
        same_default_And_annotation = (
            old_p.default == new_p.default
            and old_p.annotation is not None
            and old_p.annotation == new_p.annotation
        )
        if old_idx == new_idx and old_p.kind == new_p.kind and (
            has_name_affinity or same_default_And_annotation
        ):
            paired_by_rename.append((old_p, new_p))
            renamed_old_names.add(old_p.name)
            renamed_new_names.add(new_p.name)
            changes.append(
                SymbolChange(
                    file_path=file_path,
                    symbol=new_sym.name,
                    qualified_name=new_sym.qualified_name,
                    symbol_type=new_sym.symbol_type,
                    change_type="PARAMETER_RENAMED",
                    old_line=old_sym.start_line,
                    new_line=new_sym.start_line,
                    old_end_line=old_sym.end_line,
                    new_end_line=new_sym.end_line,
                    old_signature=old_sym.signature,
                    new_signature=new_sym.signature,
                    summary=f"Parameter '{old_p.name}' renamed to '{new_p.name}' in '{new_sym.qualified_name}'",
                    details={
                        "old_parameter": old_p.name,
                        "new_parameter": new_p.name,
                        "position": new_idx,
                        "kind": new_p.kind,
                    },
                )
            )

    # 3. Removed parameters
    for _old_idx, old_p in unmatched_old:
        if old_p.name in renamed_old_names:
            continue
        changes.append(
            SymbolChange(
                file_path=file_path,
                symbol=new_sym.name,
                qualified_name=new_sym.qualified_name,
                symbol_type=new_sym.symbol_type,
                change_type="PARAMETER_REMOVED",
                old_line=old_sym.start_line,
                new_line=new_sym.start_line,
                old_end_line=old_sym.end_line,
                new_end_line=new_sym.end_line,
                old_signature=old_sym.signature,
                new_signature=new_sym.signature,
                summary=f"Parameter '{old_p.name}' removed from '{new_sym.qualified_name}'",
                details={
                    "parameter": old_p.name,
                    "kind": old_p.kind,
                    "default": old_p.default,
                    "annotation": old_p.annotation,
                },
            )
        )

    # 4. Added parameters
    for _new_idx, new_p in unmatched_new:
        if new_p.name in renamed_new_names:
            continue
        changes.append(
            SymbolChange(
                file_path=file_path,
                symbol=new_sym.name,
                qualified_name=new_sym.qualified_name,
                symbol_type=new_sym.symbol_type,
                change_type="PARAMETER_ADDED",
                old_line=old_sym.start_line,
                new_line=new_sym.start_line,
                old_end_line=old_sym.end_line,
                new_end_line=new_sym.end_line,
                old_signature=old_sym.signature,
                new_signature=new_sym.signature,
                summary=f"Parameter '{new_p.name}' added to '{new_sym.qualified_name}'",
                details={
                    "parameter": new_p.name,
                    "kind": new_p.kind,
                    "default": new_p.default,
                    "annotation": new_p.annotation,
                },
            )
        )

    # 5. Default value, annotation, and kind changes on matched parameters
    matched_param_pairs: list[Tuple[ParameterSymbol, ParameterSymbol]] = [
        (old_by_name[name][1], new_by_name[name][1]) for name in common_in_new_order
    ] + paired_by_rename

    param_kind_changed = False
    for old_p, new_p in matched_param_pairs:
        if old_p.kind != new_p.kind:
            param_kind_changed = True

        if old_p.default != new_p.default:
            changes.append(
                SymbolChange(
                    file_path=file_path,
                    symbol=new_sym.name,
                    qualified_name=new_sym.qualified_name,
                    symbol_type=new_sym.symbol_type,
                    change_type="DEFAULT_VALUE_CHANGED",
                    old_line=old_sym.start_line,
                    new_line=new_sym.start_line,
                    old_end_line=old_sym.end_line,
                    new_end_line=new_sym.end_line,
                    old_signature=old_sym.signature,
                    new_signature=new_sym.signature,
                    summary=f"Default value for parameter '{new_p.name}' changed in '{new_sym.qualified_name}'",
                    details={
                        "parameter": new_p.name,
                        "old_default": old_p.default,
                        "new_default": new_p.default,
                    },
                )
            )

        if old_p.annotation != new_p.annotation:
            changes.append(
                SymbolChange(
                    file_path=file_path,
                    symbol=new_sym.name,
                    qualified_name=new_sym.qualified_name,
                    symbol_type=new_sym.symbol_type,
                    change_type="PARAMETER_ANNOTATION_CHANGED",
                    old_line=old_sym.start_line,
                    new_line=new_sym.start_line,
                    old_end_line=old_sym.end_line,
                    new_end_line=new_sym.end_line,
                    old_signature=old_sym.signature,
                    new_signature=new_sym.signature,
                    summary=f"Type annotation for parameter '{new_p.name}' changed in '{new_sym.qualified_name}'",
                    details={
                        "parameter": new_p.name,
                        "old_annotation": old_p.annotation,
                        "new_annotation": new_p.annotation,
                    },
                )
            )

    return changes, param_kind_changed


def _compare_matched_callable(
    file_path: str,
    old_sym: ExtractedSymbol,
    new_sym: ExtractedSymbol,
    is_renamed: bool = False,
) -> list[SymbolChange]:
    """Compare all signature, annotation, async, and body attributes of a matched callable pair."""
    changes: list[SymbolChange] = []

    if is_renamed:
        changes.append(
            SymbolChange(
                file_path=file_path,
                symbol=new_sym.name,
                qualified_name=new_sym.qualified_name,
                symbol_type=new_sym.symbol_type,
                change_type="FUNCTION_RENAMED",
                old_line=old_sym.start_line,
                new_line=new_sym.start_line,
                old_end_line=old_sym.end_line,
                new_end_line=new_sym.end_line,
                old_signature=old_sym.signature,
                new_signature=new_sym.signature,
                summary=f"Function '{old_sym.qualified_name}' renamed to '{new_sym.qualified_name}'",
                details={
                    "old_name": old_sym.name,
                    "new_name": new_sym.name,
                    "old_qualified_name": old_sym.qualified_name,
                    "new_qualified_name": new_sym.qualified_name,
                },
            )
        )

    # 1. Async status change
    if old_sym.is_async != new_sym.is_async:
        direction = (
            "regular function to async function"
            if new_sym.is_async
            else "async function to regular function"
        )
        changes.append(
            SymbolChange(
                file_path=file_path,
                symbol=new_sym.name,
                qualified_name=new_sym.qualified_name,
                symbol_type=new_sym.symbol_type,
                change_type="ASYNC_STATUS_CHANGED",
                old_line=old_sym.start_line,
                new_line=new_sym.start_line,
                old_end_line=old_sym.end_line,
                new_end_line=new_sym.end_line,
                old_signature=old_sym.signature,
                new_signature=new_sym.signature,
                summary=f"Changed '{new_sym.qualified_name}' from {direction}",
                details={
                    "was_async": old_sym.is_async,
                    "is_async": new_sym.is_async,
                },
            )
        )

    # 2. Return annotation change
    if old_sym.return_annotation != new_sym.return_annotation:
        changes.append(
            SymbolChange(
                file_path=file_path,
                symbol=new_sym.name,
                qualified_name=new_sym.qualified_name,
                symbol_type=new_sym.symbol_type,
                change_type="RETURN_ANNOTATION_CHANGED",
                old_line=old_sym.start_line,
                new_line=new_sym.start_line,
                old_end_line=old_sym.end_line,
                new_end_line=new_sym.end_line,
                old_signature=old_sym.signature,
                new_signature=new_sym.signature,
                summary=f"Return annotation changed on '{new_sym.qualified_name}'",
                details={
                    "old_return_annotation": old_sym.return_annotation,
                    "new_return_annotation": new_sym.return_annotation,
                },
            )
        )

    # 3. Parameter-level changes
    param_changes, param_kind_changed = _compare_parameters(
        file_path=file_path,
        old_sym=old_sym,
        new_sym=new_sym,
    )
    changes.extend(param_changes)

    # 4. Implementation body, decorator, or parameter-kind change
    body_changed = old_sym.body_hash != new_sym.body_hash
    decorators_changed = old_sym.decorators != new_sym.decorators

    if (body_changed or decorators_changed or param_kind_changed) and not is_renamed:
        mod_type = (
            "METHOD_MODIFIED" if new_sym.symbol_type == "method" else "FUNCTION_MODIFIED"
        )
        label = "Method" if new_sym.symbol_type == "method" else "Function"
        changes.append(
            SymbolChange(
                file_path=file_path,
                symbol=new_sym.name,
                qualified_name=new_sym.qualified_name,
                symbol_type=new_sym.symbol_type,
                change_type=mod_type,
                old_line=old_sym.start_line,
                new_line=new_sym.start_line,
                old_end_line=old_sym.end_line,
                new_end_line=new_sym.end_line,
                old_signature=old_sym.signature,
                new_signature=new_sym.signature,
                summary=f"{label} '{new_sym.qualified_name}' implementation changed",
                details={
                    "implementation_changed": body_changed,
                    "decorators_changed": decorators_changed,
                    "parameter_kind_changed": param_kind_changed,
                    "old_decorators": old_sym.decorators,
                    "new_decorators": new_sym.decorators,
                },
            )
        )

    return changes


def detect_symbol_changes(
    file_path: str,
    base_symbols: list[ExtractedSymbol],
    head_symbols: list[ExtractedSymbol],
) -> list[SymbolChange]:
    """
    Compare `base_symbols` and `head_symbols` for a single Python file and return
    all detected SymbolChange items.
    """
    changes: list[SymbolChange] = []

    # 1. Compare Classes
    base_classes = {s.qualified_name: s for s in base_symbols if s.symbol_type == "class"}
    head_classes = {s.qualified_name: s for s in head_symbols if s.symbol_type == "class"}

    for qname, old_cls in base_classes.items():
        if qname not in head_classes:
            changes.append(
                SymbolChange(
                    file_path=file_path,
                    symbol=old_cls.name,
                    qualified_name=old_cls.qualified_name,
                    symbol_type="class",
                    change_type="CLASS_REMOVED",
                    old_line=old_cls.start_line,
                    new_line=None,
                    old_end_line=old_cls.end_line,
                    new_end_line=None,
                    old_signature=old_cls.signature,
                    new_signature=None,
                    summary=f"Class '{old_cls.qualified_name}' removed",
                    details={"bases": old_cls.bases, "decorators": old_cls.decorators},
                )
            )

    for qname, new_cls in head_classes.items():
        if qname not in base_classes:
            changes.append(
                SymbolChange(
                    file_path=file_path,
                    symbol=new_cls.name,
                    qualified_name=new_cls.qualified_name,
                    symbol_type="class",
                    change_type="CLASS_ADDED",
                    old_line=None,
                    new_line=new_cls.start_line,
                    old_end_line=None,
                    new_end_line=new_cls.end_line,
                    old_signature=None,
                    new_signature=new_cls.signature,
                    summary=f"Class '{new_cls.qualified_name}' added",
                    details={"bases": new_cls.bases, "decorators": new_cls.decorators},
                )
            )

    # 2. Compare Callables (Functions, Async Functions, Methods)
    base_callables = [s for s in base_symbols if s.symbol_type != "class"]
    head_callables = [s for s in head_symbols if s.symbol_type != "class"]

    # Keep the last definition if a file defines the same qualified name twice (e.g. @overload / property)
    base_by_qname: dict[str, ExtractedSymbol] = {s.qualified_name: s for s in base_callables}
    head_by_qname: dict[str, ExtractedSymbol] = {s.qualified_name: s for s in head_callables}

    unmatched_removed: list[ExtractedSymbol] = [
        sym for qname, sym in base_by_qname.items() if qname not in head_by_qname
    ]
    unmatched_added: list[ExtractedSymbol] = [
        sym for qname, sym in head_by_qname.items() if qname not in base_by_qname
    ]

    # 2a. Conservative rename pairing among unmatched removed and added functions
    renamed_pairs, remaining_removed, remaining_added = _pair_renamed_functions(
        unmatched_removed=unmatched_removed,
        unmatched_added=unmatched_added,
    )

    for old_sym, new_sym in renamed_pairs:
        changes.extend(
            _compare_matched_callable(
                file_path=file_path,
                old_sym=old_sym,
                new_sym=new_sym,
                is_renamed=True,
            )
        )

    # 2b. Unmatched removed functions / methods
    for old_sym in remaining_removed:
        rem_type = (
            "METHOD_REMOVED" if old_sym.symbol_type == "method" else "FUNCTION_REMOVED"
        )
        label = "Method" if old_sym.symbol_type == "method" else "Function"
        changes.append(
            SymbolChange(
                file_path=file_path,
                symbol=old_sym.name,
                qualified_name=old_sym.qualified_name,
                symbol_type=old_sym.symbol_type,
                change_type=rem_type,
                old_line=old_sym.start_line,
                new_line=None,
                old_end_line=old_sym.end_line,
                new_end_line=None,
                old_signature=old_sym.signature,
                new_signature=None,
                summary=f"{label} '{old_sym.qualified_name}' removed",
                details={
                    "parent_class": old_sym.parent_class,
                    "is_async": old_sym.is_async,
                    "parameters": [p.name for p in old_sym.parameters],
                },
            )
        )

    # 2c. Unmatched added functions / methods
    for new_sym in remaining_added:
        add_type = (
            "METHOD_ADDED" if new_sym.symbol_type == "method" else "FUNCTION_ADDED"
        )
        label = "Method" if new_sym.symbol_type == "method" else "Function"
        changes.append(
            SymbolChange(
                file_path=file_path,
                symbol=new_sym.name,
                qualified_name=new_sym.qualified_name,
                symbol_type=new_sym.symbol_type,
                change_type=add_type,
                old_line=None,
                new_line=new_sym.start_line,
                old_end_line=None,
                new_end_line=new_sym.end_line,
                old_signature=None,
                new_signature=new_sym.signature,
                summary=f"{label} '{new_sym.qualified_name}' added",
                details={
                    "parent_class": new_sym.parent_class,
                    "is_async": new_sym.is_async,
                    "parameters": [p.name for p in new_sym.parameters],
                },
            )
        )

    # 2d. Matched callables with the same qualified name
    for qname, new_sym in head_by_qname.items():
        if qname in base_by_qname:
            old_sym = base_by_qname[qname]
            changes.extend(
                _compare_matched_callable(
                    file_path=file_path,
                    old_sym=old_sym,
                    new_sym=new_sym,
                    is_renamed=False,
                )
            )

    return changes
