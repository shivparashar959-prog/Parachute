"""
High-level Python AST File Analyzer for DocGuard (Milestone 3).

Coordinates symbol extraction (`symbol_extractor.py`) and change detection
(`change_detector.py`) for added, modified, deleted, and renamed Python files.
"""

from typing import Literal, Optional, Tuple

from app.analyzers.change_detector import detect_symbol_changes
from app.analyzers.symbol_extractor import extract_python_symbols
from app.schemas.code_analysis import (
    AnalyzedPythonFile,
    ParseErrorItem,
    SymbolChange,
)


def is_python_source_file(file_path: str) -> bool:
    """Return True if the file path is a Python source file (.py)."""
    if not file_path:
        return False
    return file_path.lower().endswith(".py")


def analyze_python_file_change(
    file_path: str,
    file_change_type: Literal["added", "modified", "deleted", "renamed"],
    base_source: Optional[str],
    head_source: Optional[str],
    previous_path: Optional[str] = None,
) -> Tuple[AnalyzedPythonFile, list[SymbolChange], list[ParseErrorItem]]:
    """
    Statically analyze a single Python file across base and head versions.

    - For 'added' files, only the head version is parsed.
    - For 'deleted' files, only the base version is parsed.
    - For 'modified' and 'renamed' files, both base and head versions are parsed.
    - If a syntax error occurs in either version, a structured ParseErrorItem is
      returned without crashing or producing false removal/addition findings.
    """
    parse_errors: list[ParseErrorItem] = []
    base_symbols = []
    head_symbols = []

    if file_change_type != "added" and base_source is not None:
        base_path_for_ast = previous_path or file_path
        base_symbols, base_err = extract_python_symbols(
            source_code=base_source,
            file_path=base_path_for_ast,
            version="base",
        )
        if base_err is not None:
            # Normalize file_path in the error item so it matches the analyzed file entry
            base_err.file_path = file_path
            parse_errors.append(base_err)

    if file_change_type != "deleted" and head_source is not None:
        head_symbols, head_err = extract_python_symbols(
            source_code=head_source,
            file_path=file_path,
            version="head",
        )
        if head_err is not None:
            parse_errors.append(head_err)

    # Only compute symbol diffs when neither side encountered a syntax error
    if parse_errors:
        symbol_changes: list[SymbolChange] = []
    else:
        symbol_changes = detect_symbol_changes(
            file_path=file_path,
            base_symbols=base_symbols,
            head_symbols=head_symbols,
        )

    analyzed_file = AnalyzedPythonFile(
        file_path=file_path,
        previous_path=previous_path,
        file_change_type=file_change_type,
        base_symbol_count=len(base_symbols),
        head_symbol_count=len(head_symbols),
        changes_count=len(symbol_changes),
        has_parse_error=len(parse_errors) > 0,
    )

    return analyzed_file, symbol_changes, parse_errors
