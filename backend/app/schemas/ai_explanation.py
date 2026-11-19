"""
Pydantic schemas for Milestone 6: AI-Powered Explanations and Documentation Correction Suggestions.
"""

import uuid
from typing import List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.drift import DriftFinding, DriftSeverity, DriftStatus

AIProviderType = Literal["mock", "gemini"]

CorrectionStatus = Literal[
    "SUGGESTION_AVAILABLE",
    "INSUFFICIENT_EVIDENCE",
    "REVIEW_REQUIRED",
]


class AIProviderStatusResponse(BaseModel):
    """Configuration status of AI providers (never exposes API keys or secrets)."""

    gemini_configured: bool
    gemini_model: str
    gemini_budget_configured: bool
    mock_available: bool = True
    active_default_provider: Optional[AIProviderType] = None
    availability_message: Optional[str] = None
    supported_providers: List[AIProviderType] = Field(
        default_factory=lambda: ["mock", "gemini"]
    )


class AIExplanationPayload(BaseModel):
    """
    Validated structured output produced by an AI provider for a single drift finding.
    """

    explanation: str = Field(..., min_length=10)
    code_change_summary: str = Field(..., min_length=5)
    documentation_issue: str = Field(..., min_length=5)
    evidence_used: List[str] = Field(..., min_length=1)
    suggested_correction: Optional[str] = None
    correction_status: CorrectionStatus
    correction_available: bool
    insufficient_evidence: bool
    limitations: List[str] = Field(default_factory=list)


class FindingAIExplanation(BaseModel):
    """
    Complete AI explanation and correction suggestion record for a single deterministic
    DriftFinding, preserving the original deterministic status, severity, and confidence.
    """

    finding_id: str
    provider: AIProviderType
    model_name: str
    finding_type: str
    rule_id: str
    original_status: DriftStatus
    original_severity: DriftSeverity
    original_confidence: float
    documentation_file: str
    documentation_line: int
    related_symbol: str
    source_file: str
    explanation: str
    code_change_summary: str
    documentation_issue: str
    evidence_used: List[str] = Field(default_factory=list)
    suggested_correction: Optional[str] = None
    correction_status: CorrectionStatus
    correction_available: bool
    insufficient_evidence: bool
    limitations: List[str] = Field(default_factory=list)
    provider_error: Optional[str] = None


class AIExplanationRequest(BaseModel):
    """Request payload selecting persisted findings from an authorized analysis."""

    model_config = ConfigDict(extra="forbid")

    analysis_id: uuid.UUID
    provider: Optional[AIProviderType] = None
    finding_ids: List[str] = Field(..., min_length=1, max_length=10)

    @field_validator("finding_ids")
    @classmethod
    def validate_finding_ids(cls, values: List[str]) -> List[str]:
        if any(not value.strip() or len(value) > 255 for value in values):
            raise ValueError("Each finding ID must contain 1 to 255 characters.")
        return list(dict.fromkeys(value.strip() for value in values))


class AIExplanationResponse(BaseModel):
    """Response payload for POST /api/analyze/explanations."""

    analysis_id: uuid.UUID
    repository_url: str
    owner: str
    name: str
    base_commit: str
    head_commit: str
    provider: AIProviderType
    model_name: str
    total_requested: int
    explanations_generated: int
    explanations: List[FindingAIExplanation] = Field(default_factory=list)
    unknown_finding_ids: List[str] = Field(default_factory=list)
    provider_errors: List[str] = Field(default_factory=list)
