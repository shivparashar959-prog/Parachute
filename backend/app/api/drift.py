"""
API endpoint for Milestone 5: Documentation Drift Detection Engine.
Provides POST /api/analyze/drift.
"""

from fastapi import APIRouter, status

from app.api.repositories import _raise_http_for_repository_error
from app.schemas.drift import (
    DriftAnalysisRequest,
    DriftAnalysisResponse,
)
from app.services.drift_analysis_service import analyze_repository_drift

router = APIRouter(prefix="/api/analyze", tags=["Drift Detection"])


@router.post(
    "/drift",
    response_model=DriftAnalysisResponse,
    status_code=status.HTTP_200_OK,
    summary="Perform deterministic, evidence-based documentation drift detection between two commits",
)
def analyze_documentation_drift_endpoint(
    payload: DriftAnalysisRequest,
) -> DriftAnalysisResponse:
    """
    Combine Git commit comparison, Python AST code change analysis, Markdown
    documentation parsing, documentation-to-code mapping, and historical documentation
    comparison across `base_commit` and `head_commit` to detect evidence-backed
    documentation drift findings.
    """
    try:
        return analyze_repository_drift(
            repository_url=payload.repository_url,
            base_commit=payload.base_commit,
            head_commit=payload.head_commit,
        )
    except Exception as exc:
        _raise_http_for_repository_error(exc)
