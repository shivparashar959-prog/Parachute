"""
Pydantic schemas for Milestone 5: Documentation Drift Detection Engine.
"""

import re
import uuid
from typing import Dict, Literal, Optional
from pydantic import BaseModel, Field, field_validator

from app.schemas.code_analysis import ParseErrorItem, SkippedFileItem

DriftStatus = Literal[
    "POTENTIAL_DRIFT",
    "CONFIRMED_DRIFT",
    "UNCERTAIN",
    "RESOLVED",
    "UNCHANGED",
]

DriftSeverity = Literal[
    "LOW",
    "MEDIUM",
    "HIGH",
    "CRITICAL",
]

DriftRuleId = Literal[
    "RULE_A_CHANGED_DEFAULT",
    "RULE_B_REMOVED_OR_RENAMED_PARAMETER",
    "RULE_C_ADDED_REQUIRED_PARAMETER",
    "RULE_D_RETURN_CONTRACT_CHANGED",
    "RULE_E_SYMBOL_REMOVED",
    "RULE_F_SYMBOL_RENAMED",
    "RULE_G_DELETED_SOURCE_FILE",
    "RULE_H_SIGNATURE_CHANGED",
    "RULE_I_DOCUMENTATION_UPDATED",
]


class DocumentationFileChange(BaseModel):
    """Tracks how a Markdown documentation file changed between base and head commits."""

    file_path: str
    previous_path: Optional[str] = None
    change_type: Literal["unchanged", "modified", "added", "deleted", "renamed"]
    base_units_count: int = 0
    head_units_count: int = 0


class DocumentationUnitDiff(BaseModel):
    """Represents the historical comparison of a documentation unit between base and head commits."""

    documentation_file: str
    previous_file: Optional[str] = None
    change_type: Literal["unchanged", "modified", "added", "deleted", "moved"]
    section_heading: Optional[str] = None
    base_unit_id: Optional[str] = None
    head_unit_id: Optional[str] = None
    base_start_line: Optional[int] = None
    base_end_line: Optional[int] = None
    head_start_line: Optional[int] = None
    head_end_line: Optional[int] = None
    base_text: Optional[str] = None
    head_text: Optional[str] = None


class DriftFinding(BaseModel):
    """An evidence-backed documentation drift finding connecting a code change to documentation."""

    finding_id: str
    finding_type: str
    rule_id: DriftRuleId
    status: DriftStatus
    severity: DriftSeverity
    confidence: float = Field(..., ge=0.0, le=1.0)
    documentation_file: str
    documentation_line: int
    documentation_end_line: int
    documentation_section: Optional[str] = None
    documentation_text: str
    previous_documentation_text: Optional[str] = None
    related_symbol: str
    qualified_symbol: str
    source_file: str
    source_line: Optional[int] = None
    old_source_line: Optional[int] = None
    old_code_evidence: str
    new_code_evidence: str
    mapping_evidence: list[str] = Field(default_factory=list)
    reason: str
    suggested_action: str


class DriftAnalysisSummary(BaseModel):
    """Summary metrics for a repository documentation drift detection run."""

    python_files_analyzed: int
    documentation_files_analyzed: int
    code_changes_count: int
    documentation_changes_count: int
    total_findings: int
    confirmed_drift_count: int
    potential_drift_count: int
    uncertain_count: int
    resolved_count: int
    unchanged_count: int
    counts_by_status: Dict[str, int] = Field(default_factory=dict)
    counts_by_severity: Dict[str, int] = Field(default_factory=dict)
    counts_by_rule: Dict[str, int] = Field(default_factory=dict)
    skipped_files_count: int = 0
    parse_errors_count: int = 0


class DriftAnalysisRequest(BaseModel):
    """Request payload for POST /api/analyze/drift."""

    github_repository_id: int = Field(
        ...,
        gt=0,
        description="Stable numeric GitHub repository ID from the authorized catalog",
    )
    base_commit: str = Field(
        ...,
        min_length=40,
        max_length=40,
        description="Full base commit SHA (older/starting commit)",
    )
    head_commit: str = Field(
        ...,
        min_length=40,
        max_length=40,
        description="Full head commit SHA (newer/target commit)",
    )

    @field_validator("base_commit", "head_commit")
    @classmethod
    def require_full_sha(cls, value: str) -> str:
        if not re.fullmatch(r"[0-9a-fA-F]{40}", value):
            raise ValueError("Commit values must be full 40-character SHA-1 hashes.")
        return value.lower()


class DriftAnalysisResponse(BaseModel):
    """Response payload for POST /api/analyze/drift."""

    analysis_id: Optional[uuid.UUID] = None
    repository_url: str
    owner: str
    name: str
    base_commit: str
    head_commit: str
    summary: DriftAnalysisSummary
    findings: list[DriftFinding]
    findings_by_status: Dict[str, list[DriftFinding]] = Field(default_factory=dict)
    findings_by_severity: Dict[str, list[DriftFinding]] = Field(default_factory=dict)
    uncertain_results: list[DriftFinding] = Field(default_factory=list)
    resolved_results: list[DriftFinding] = Field(default_factory=list)
    documentation_changes: list[DocumentationFileChange] = Field(default_factory=list)
    skipped_files: list[SkippedFileItem] = Field(default_factory=list)
    parse_errors: list[ParseErrorItem] = Field(default_factory=list)
