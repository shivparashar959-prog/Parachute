"""
API endpoint for Milestone 3: Python AST Code Change Analysis.
Provides POST /api/analyze/code.
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthenticatedPrincipal, get_current_principal
from app.api.repositories import _raise_http_for_repository_error
from app.db.session import get_db
from app.schemas.code_analysis import (
    CodeAnalysisRequest,
    CodeAnalysisResponse,
)
from app.services.code_analysis_service import analyze_repository_python_changes
from app.services.github_app_service import resolve_repository_access

router = APIRouter(
    prefix="/api/analyze",
    tags=["Code Analysis"],
    dependencies=[Depends(get_current_principal)],
)


@router.post(
    "/code",
    response_model=CodeAnalysisResponse,
    status_code=status.HTTP_200_OK,
    summary="Perform static Python AST code change analysis between two commits",
)
def analyze_python_code_changes(
    payload: CodeAnalysisRequest,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> CodeAnalysisResponse:
    """
    Retrieve Python source files at `base_commit` and `head_commit` from a public
    HTTPS GitHub repository and perform static AST analysis to detect added,
    removed, modified, and renamed functions, classes, methods, parameters,
    default values, type annotations, and async status changes.
    """
    try:
        access = resolve_repository_access(
            db, principal, payload.github_repository_id
        )
        return analyze_repository_python_changes(
            repository_url=access.html_url,
            base_commit=payload.base_commit,
            head_commit=payload.head_commit,
            access_token=access.installation_token,
        )
    except Exception as exc:
        _raise_http_for_repository_error(exc)
