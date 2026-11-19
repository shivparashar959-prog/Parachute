"""
Pydantic schemas for Milestone 3: Python AST Code Change Analysis.
"""

from typing import Any, Dict, Literal, Optional
from pydantic import BaseModel, Field

ChangeType = Literal[
    "FUNCTION_ADDED",
    "FUNCTION_REMOVED",
    "FUNCTION_MODIFIED",
    "FUNCTION_RENAMED",
    "PARAMETER_ADDED",
    "PARAMETER_REMOVED",
    "PARAMETER_RENAMED",
    "PARAMETER_REORDERED",
    "DEFAULT_VALUE_CHANGED",
    "PARAMETER_ANNOTATION_CHANGED",
    "RETURN_ANNOTATION_CHANGED",
    "ASYNC_STATUS_CHANGED",
    "CLASS_ADDED",
    "CLASS_REMOVED",
    "METHOD_ADDED",
    "METHOD_REMOVED",
    "METHOD_MODIFIED",
]

ParameterKind = Literal[
    "positional_only",
    "positional_or_keyword",
    "var_positional",
    "keyword_only",
    "var_keyword",
]

SymbolType = Literal[
    "function",
    "async_function",
    "class",
    "method",
]


class ParameterSymbol(BaseModel):
    """Static AST representation of a Python function or method parameter."""

    name: str = Field(..., description="Parameter identifier name")
    kind: ParameterKind = Field(..., description="Python parameter category")
    default: Optional[str] = Field(
        default=None,
        description="AST-unparsed default value expression (never evaluated)",
    )
    annotation: Optional[str] = Field(
        default=None,
        description="AST-unparsed type annotation expression (never evaluated)",
    )


class ExtractedSymbol(BaseModel):
    """Static AST metadata for an extracted Python function, async function, class, or method."""

    file_path: str
    name: str
    qualified_name: str
    symbol_type: SymbolType
    start_line: int
    end_line: int
    parameters: list[ParameterSymbol] = Field(default_factory=list)
    return_annotation: Optional[str] = None
    decorators: list[str] = Field(default_factory=list)
    is_async: bool = False
    parent_class: Optional[str] = None
    method_kind: Optional[Literal["instance", "classmethod", "staticmethod"]] = None
    signature: str
    body_hash: str = Field(
        default="",
        description="Normalized AST dump fingerprint of the symbol body",
    )
    bases: list[str] = Field(default_factory=list)


class SymbolChange(BaseModel):
    """A single detected AST-level change between the base and head commit."""

    file_path: str
    symbol: str
    qualified_name: str
    symbol_type: SymbolType
    change_type: ChangeType
    old_line: Optional[int] = None
    new_line: Optional[int] = None
    old_end_line: Optional[int] = None
    new_end_line: Optional[int] = None
    old_signature: Optional[str] = None
    new_signature: Optional[str] = None
    summary: str
    details: Dict[str, Any] = Field(default_factory=dict)


class ParseErrorItem(BaseModel):
    """Structured syntax/parse error report when a Python file cannot be parsed by ast.parse."""

    file_path: str
    version: Literal["base", "head"]
    line: Optional[int] = None
    column: Optional[int] = None
    error_type: str
    message: str


class SkippedFileItem(BaseModel):
    """Information about a changed file in the commit diff that was skipped by the Python AST analyzer."""

    file_path: str
    reason: str


class AnalyzedPythonFile(BaseModel):
    """Summary and extracted symbols for a single analyzed Python source file."""

    file_path: str
    previous_path: Optional[str] = None
    file_change_type: Literal["added", "modified", "deleted", "renamed"]
    base_symbol_count: int
    head_symbol_count: int
    changes_count: int
    has_parse_error: bool = False


class CodeAnalysisSummary(BaseModel):
    """High-level metrics for a repository Python AST analysis run."""

    total_changed_files_in_diff: int
    analyzed_python_files_count: int
    skipped_files_count: int
    parse_errors_count: int
    total_symbol_changes: int
    counts_by_change_type: Dict[str, int] = Field(default_factory=dict)


class CodeAnalysisRequest(BaseModel):
    """Request payload for POST /api/analyze/code."""

    github_repository_id: int = Field(
        ...,
        gt=0,
        description="Stable numeric GitHub repository ID from the authorized catalog",
    )
    base_commit: str = Field(
        ...,
        description="Base commit SHA (older/starting commit)",
    )
    head_commit: str = Field(
        ...,
        description="Head commit SHA (newer/target commit)",
    )


class CodeAnalysisResponse(BaseModel):
    """Response payload for POST /api/analyze/code."""

    repository_url: str
    owner: str
    name: str
    base_commit: str
    head_commit: str
    summary: CodeAnalysisSummary
    analyzed_files: list[AnalyzedPythonFile]
    changed_symbols: list[SymbolChange]
    parse_errors: list[ParseErrorItem]
    skipped_files: list[SkippedFileItem]
