"""
API endpoint for Milestone 4: Documentation Parsing and Code Mapping Engine.
Provides POST /api/analyze/documentation.
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthenticatedPrincipal, get_current_principal
from app.api.repositories import _raise_http_for_repository_error
from app.db.session import get_db
from app.schemas.documentation import (
    DocumentationAnalysisRequest,
    DocumentationAnalysisResponse,
)
from app.services.documentation_service import analyze_repository_documentation
from app.services.github_app_service import resolve_repository_access

router = APIRouter(
    prefix="/api/analyze",
    tags=["Documentation Analysis"],
    dependencies=[Depends(get_current_principal)],
)


@router.post(
    "/documentation",
    response_model=DocumentationAnalysisResponse,
    status_code=status.HTTP_200_OK,
    summary="Discover, parse, and map repository Markdown documentation to Python AST symbols",
)
def analyze_repository_documentation_endpoint(
    payload: DocumentationAnalysisRequest,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> DocumentationAnalysisResponse:
    """
    Discover Markdown documentation files at `head_commit`, extract structured
    documentation units, extract Python AST symbols at `head_commit`, and map
    documentation sections and statements to relevant Python functions, classes,
    methods, and modules with confidence levels and evidence.
    """
    try:
        access = resolve_repository_access(
            db, principal, payload.github_repository_id
        )
        return analyze_repository_documentation(
            repository_url=access.html_url,
            head_commit=payload.head_commit,
            base_commit=payload.base_commit,
            access_token=access.installation_token,
        )
    except Exception as exc:
        _raise_http_for_repository_error(exc)
