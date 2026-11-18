"""
API endpoint for Milestone 4: Documentation Parsing and Code Mapping Engine.
Provides POST /api/analyze/documentation.
"""

from fastapi import APIRouter, status

from app.api.repositories import _raise_http_for_repository_error
from app.schemas.documentation import (
    DocumentationAnalysisRequest,
    DocumentationAnalysisResponse,
)
from app.services.documentation_service import analyze_repository_documentation

router = APIRouter(prefix="/api/analyze", tags=["Documentation Analysis"])


@router.post(
    "/documentation",
    response_model=DocumentationAnalysisResponse,
    status_code=status.HTTP_200_OK,
    summary="Discover, parse, and map repository Markdown documentation to Python AST symbols",
)
def analyze_repository_documentation_endpoint(
    payload: DocumentationAnalysisRequest,
) -> DocumentationAnalysisResponse:
    """
    Discover Markdown documentation files at `head_commit`, extract structured
    documentation units, extract Python AST symbols at `head_commit`, and map
    documentation sections and statements to relevant Python functions, classes,
    methods, and modules with confidence levels and evidence.
    """
    try:
        return analyze_repository_documentation(
            repository_url=payload.repository_url,
            head_commit=payload.head_commit,
            base_commit=payload.base_commit,
        )
    except Exception as exc:
        _raise_http_for_repository_error(exc)
