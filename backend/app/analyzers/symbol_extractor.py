"""
Static AST Symbol Extractor for Python source files.

SECURITY GUARANTEE:
Uses Python's built-in `ast.parse` and `ast.unparse` strictly for static analysis.
Never executes, imports, or evaluates any repository code or expressions.
"""

import ast
from typing import Literal, Optional, Tuple, Union

from app.schemas.code_analysis import (
    ExtractedSymbol,
    ParameterSymbol,
    ParseErrorItem,
    SymbolType,
)

FunctionNode = Union[ast.FunctionDef, ast.AsyncFunctionDef]
ScopeEntry = Tuple[str, Literal["class", "function"]]


def _safe_unparse(node: Optional[ast.AST]) -> Optional[str]:
    """Safely convert an AST node to its source code string without evaluating it."""
    if node is None:
        return None
    try:
        return ast.unparse(node).strip()
    except Exception:
        return "<unparseable>"


def _extract_parameters(args_node: ast.arguments) -> list[ParameterSymbol]:
    """
    Extract all parameters from an ast.arguments node in declaration order:
    1. Positional-only parameters (posonlyargs)
    2. Positional-or-keyword parameters (args)
    3. Var-positional parameter (*args / vararg)
    4. Keyword-only parameters (kwonlyargs)
    5. Var-keyword parameter (**kwargs / kwarg)
    """
    parameters: list[ParameterSymbol] = []

    pos_only = list(args_node.posonlyargs)
    pos_or_kw = list(args_node.args)
    combined_positional = pos_only + pos_or_kw
    defaults = list(args_node.defaults)
    default_offset = len(combined_positional) - len(defaults)

    for idx, arg in enumerate(combined_positional):
        kind: Literal["positional_only", "positional_or_keyword"] = (
            "positional_only" if idx < len(pos_only) else "positional_or_keyword"
        )
        default_node = defaults[idx - default_offset] if idx >= default_offset else None
        parameters.append(
            ParameterSymbol(
                name=arg.arg,
                kind=kind,
                default=_safe_unparse(default_node),
                annotation=_safe_unparse(arg.annotation),
            )
        )

    if args_node.vararg is not None:
        parameters.append(
            ParameterSymbol(
                name=args_node.vararg.arg,
                kind="var_positional",
                default=None,
                annotation=_safe_unparse(args_node.vararg.annotation),
            )
        )

    for kw_arg, kw_default in zip(args_node.kwonlyargs, args_node.kw_defaults):
        parameters.append(
            ParameterSymbol(
                name=kw_arg.arg,
                kind="keyword_only",
                default=_safe_unparse(kw_default),
                annotation=_safe_unparse(kw_arg.annotation),
            )
        )

    if args_node.kwarg is not None:
        parameters.append(
            ParameterSymbol(
                name=args_node.kwarg.arg,
                kind="var_keyword",
                default=None,
                annotation=_safe_unparse(args_node.kwarg.annotation),
            )
        )

    return parameters


def _format_single_param(param: ParameterSymbol) -> str:
    """Format a single ParameterSymbol for a human-readable signature string."""
    prefix = ""
    if param.kind == "var_positional":
        prefix = "*"
    elif param.kind == "var_keyword":
        prefix = "**"

    rendered = f"{prefix}{param.name}"
    if param.annotation is not None:
        rendered += f": {param.annotation}"
    if param.default is not None:
        if param.annotation is not None:
            rendered += f" = {param.default}"
        else:
            rendered += f"={param.default}"
    return rendered


def _build_callable_signature(
    name: str,
    parameters: list[ParameterSymbol],
    return_annotation: Optional[str],
    is_async: bool,
) -> str:
    """Build a canonical signature string including `/`, `*`, annotations, defaults, and return type."""
    pos_only = [p for p in parameters if p.kind == "positional_only"]
    pos_or_kw = [p for p in parameters if p.kind == "positional_or_keyword"]
    var_pos = [p for p in parameters if p.kind == "var_positional"]
    kw_only = [p for p in parameters if p.kind == "keyword_only"]
    var_kw = [p for p in parameters if p.kind == "var_keyword"]

    parts: list[str] = []
    if pos_only:
        parts.extend(_format_single_param(p) for p in pos_only)
        parts.append("/")

    parts.extend(_format_single_param(p) for p in pos_or_kw)

    if var_pos:
        parts.extend(_format_single_param(p) for p in var_pos)
    elif kw_only:
        parts.append("*")

    parts.extend(_format_single_param(p) for p in kw_only)
    parts.extend(_format_single_param(p) for p in var_kw)

    async_prefix = "async " if is_async else ""
    ret_suffix = f" -> {return_annotation}" if return_annotation is not None else ""
    return f"{async_prefix}{name}({', '.join(parts)}){ret_suffix}"


def _compute_body_fingerprint(statements: list[ast.stmt]) -> str:
    """
    Create a normalized structural AST representation of a callable/class body
    (excluding line numbers and column offsets) to detect implementation modifications
    and support cautious rename similarity comparison.
    """
    normalized_parts: list[str] = []
    for stmt in statements:
        try:
            normalized_parts.append(ast.dump(stmt, include_attributes=False))
        except Exception:
            normalized_parts.append("<stmt>")
    return "\n".join(normalized_parts)


def _classify_method_kind(
    decorators: list[str],
) -> Literal["instance", "classmethod", "staticmethod"]:
    """Determine whether a class method is an instance method, @classmethod, or @staticmethod."""
    for dec in decorators:
        cleaned = dec.split("(")[0].strip()
        if cleaned == "classmethod" or cleaned.endswith(".classmethod"):
            return "classmethod"
        if cleaned == "staticmethod" or cleaned.endswith(".staticmethod"):
            return "staticmethod"
    return "instance"


def _walk_statement_block(
    statements: list[ast.stmt],
    file_path: str,
    scope_stack: list[ScopeEntry],
    extracted: list[ExtractedSymbol],
) -> None:
    """
    Recursively walk a list of AST statements, extracting classes, functions,
    async functions, class methods, and nested functions while tracking scope hierarchy.
    """
    for stmt in statements:
        if isinstance(stmt, ast.ClassDef):
            qualified_name = ".".join([s[0] for s in scope_stack] + [stmt.name])
            parent_class = next(
                (name for name, kind in reversed(scope_stack) if kind == "class"),
                None,
            )
            decorators = [d for d in (_safe_unparse(dec) for dec in stmt.decorator_list) if d]
            bases = [b for b in (_safe_unparse(base) for base in stmt.bases) if b]
            signature = (
                f"class {stmt.name}({', '.join(bases)})"
                if bases
                else f"class {stmt.name}"
            )

            extracted.append(
                ExtractedSymbol(
                    file_path=file_path,
                    name=stmt.name,
                    qualified_name=qualified_name,
                    symbol_type="class",
                    start_line=stmt.lineno,
                    end_line=getattr(stmt, "end_lineno", None) or stmt.lineno,
                    parameters=[],
                    return_annotation=None,
                    decorators=decorators,
                    is_async=False,
                    parent_class=parent_class,
                    method_kind=None,
                    signature=signature,
                    body_hash=_compute_body_fingerprint(stmt.body),
                    bases=bases,
                )
            )

            scope_stack.append((stmt.name, "class"))
            _walk_statement_block(stmt.body, file_path, scope_stack, extracted)
            scope_stack.pop()

        elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            is_async = isinstance(stmt, ast.AsyncFunctionDef)
            qualified_name = ".".join([s[0] for s in scope_stack] + [stmt.name])
            decorators = [d for d in (_safe_unparse(dec) for dec in stmt.decorator_list) if d]

            immediate_parent = scope_stack[-1] if scope_stack else None
            if immediate_parent and immediate_parent[1] == "class":
                symbol_type: SymbolType = "method"
                parent_class = ".".join(
                    name for name, kind in scope_stack if kind == "class"
                )
                method_kind: Optional[Literal["instance", "classmethod", "staticmethod"]] = (
                    _classify_method_kind(decorators)
                )
            else:
                symbol_type = "async_function" if is_async else "function"
                parent_class = next(
                    (name for name, kind in reversed(scope_stack) if kind == "class"),
                    None,
                )
                method_kind = None

            parameters = _extract_parameters(stmt.args)
            return_annotation = _safe_unparse(stmt.returns)
            signature = _build_callable_signature(
                name=stmt.name,
                parameters=parameters,
                return_annotation=return_annotation,
                is_async=is_async,
            )

            extracted.append(
                ExtractedSymbol(
                    file_path=file_path,
                    name=stmt.name,
                    qualified_name=qualified_name,
                    symbol_type=symbol_type,
                    start_line=stmt.lineno,
                    end_line=getattr(stmt, "end_lineno", None) or stmt.lineno,
                    parameters=parameters,
                    return_annotation=return_annotation,
                    decorators=decorators,
                    is_async=is_async,
                    parent_class=parent_class,
                    method_kind=method_kind,
                    signature=signature,
                    body_hash=_compute_body_fingerprint(stmt.body),
                    bases=[],
                )
            )

            scope_stack.append((stmt.name, "function"))
            _walk_statement_block(stmt.body, file_path, scope_stack, extracted)
            scope_stack.pop()

        elif isinstance(stmt, (ast.If, ast.For, ast.AsyncFor, ast.While)):
            _walk_statement_block(stmt.body, file_path, scope_stack, extracted)
            _walk_statement_block(stmt.orelse, file_path, scope_stack, extracted)
        elif isinstance(stmt, (ast.With, ast.AsyncWith)):
            _walk_statement_block(stmt.body, file_path, scope_stack, extracted)
        elif isinstance(stmt, ast.Try):
            _walk_statement_block(stmt.body, file_path, scope_stack, extracted)
            for handler in stmt.handlers:
                _walk_statement_block(handler.body, file_path, scope_stack, extracted)
            _walk_statement_block(stmt.orelse, file_path, scope_stack, extracted)
            _walk_statement_block(stmt.finalbody, file_path, scope_stack, extracted)


def extract_python_symbols(
    source_code: str,
    file_path: str,
    version: Literal["base", "head"] = "head",
) -> Tuple[list[ExtractedSymbol], Optional[ParseErrorItem]]:
    """
    Parse a Python source string into an AST and extract all classes, functions,
    async functions, methods, and nested functions.

    If a syntax error is encountered, returns an empty symbol list and a structured
    ParseErrorItem without raising an exception.
    """
    if not source_code or not source_code.strip():
        return [], None

    normalized_source = source_code.replace("\r\n", "\n").replace("\r", "\n")

    try:
        tree = ast.parse(normalized_source, filename=file_path)
    except SyntaxError as exc:
        return [], ParseErrorItem(
            file_path=file_path,
            version=version,
            line=exc.lineno,
            column=exc.offset,
            error_type=type(exc).__name__,
            message=exc.msg or "Invalid Python syntax",
        )
    except (ValueError, TypeError, MemoryError, RecursionError) as exc:
        return [], ParseErrorItem(
            file_path=file_path,
            version=version,
            line=None,
            column=None,
            error_type=type(exc).__name__,
            message=str(exc) or "Unable to parse Python file",
        )

    extracted: list[ExtractedSymbol] = []
    scope_stack: list[ScopeEntry] = []
    _walk_statement_block(tree.body, file_path, scope_stack, extracted)
    return extracted, None
