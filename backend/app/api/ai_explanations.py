"""
API endpoints for Milestone 6: AI-Powered Explanations and Documentation Correction Suggestions.
Provides:
- GET /api/analyze/explanations/providers
- POST /api/analyze/explanations
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthenticatedPrincipal, get_current_principal
from app.ai.base_provider import (
    AIProviderConfigurationError,
    AIProviderError,
    AIProviderInputLimitError,
    AIProviderPolicyError,
    AIProviderNetworkError,
    AIProviderRateLimitError,
    AIProviderResponseValidationError,
    AIProviderTimeoutError,
)
from app.api.repositories import _raise_http_for_repository_error
from app.schemas.ai_explanation import (
    AIExplanationRequest,
    AIExplanationResponse,
    AIProviderStatusResponse,
)
from app.services.ai_explanation_service import (
    generate_explanations_for_repository,
    get_ai_provider_status,
)
from app.services import analysis_service
from app.db.session import get_db
from app.services.github_app_service import resolve_repository_access

router = APIRouter(
    prefix="/api/analyze/explanations",
    tags=["AI Explanations"],
    dependencies=[Depends(get_current_principal)],
)


def _raise_http_for_ai_error(exc: Exception) -> None:
    """Translate AI provider and repository exceptions into clean FastAPI HTTPExceptions."""
    if isinstance(exc, analysis_service.AnalysisQuotaExceededError):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
        ) from exc
    if isinstance(exc, analysis_service.GeminiSpendConfigurationError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    if isinstance(exc, analysis_service.AnalysisNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Analysis findings are unavailable.",
        ) from exc
    if isinstance(exc, AIProviderPolicyError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    if isinstance(exc, AIProviderInputLimitError):
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=str(exc),
        ) from exc
    if isinstance(exc, AIProviderConfigurationError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    if isinstance(exc, AIProviderRateLimitError):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
        ) from exc
    if isinstance(exc, AIProviderTimeoutError):
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=str(exc),
        ) from exc
    if isinstance(exc, (AIProviderNetworkError, AIProviderResponseValidationError)):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    if isinstance(exc, AIProviderError):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    _raise_http_for_repository_error(exc)


@router.get(
    "/providers",
    response_model=AIProviderStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Inspect configured AI providers (Gemini vs Mock) without exposing secrets",
)
def read_ai_providers_status() -> AIProviderStatusResponse:
    """
    Return whether Google Gemini API is configured via GEMINI_API_KEY, the active
    Gemini model name, and Mock AI Mode availability.
    """
    return get_ai_provider_status()


@router.post(
    "",
    response_model=AIExplanationResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate AI explanations and documentation fix suggestions for drift findings",
)
def generate_ai_explanations_endpoint(
    payload: AIExplanationRequest,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> AIExplanationResponse:
    """
    Generate evidence-backed AI explanations and documentation correction suggestions
    for deterministic documentation drift findings using either 'mock' or 'gemini'.
    """
    try:
        analysis, findings = analysis_service.get_workspace_analysis_findings(
            db, principal, payload.analysis_id, payload.finding_ids
        )
        access = resolve_repository_access(db, principal, analysis.github_repository_id)
        provider_name = (
            payload.provider
            or get_ai_provider_status().active_default_provider
            or "mock"
        )

        def reserve_before_provider_call(_finding, prompt: str) -> None:
            if provider_name == "gemini":
                analysis_service.reserve_gemini_spend(
                    db,
                    principal,
                    analysis,
                    get_ai_provider_status().gemini_model,
                    prompt,
                )

        return generate_explanations_for_repository(
            analysis_id=analysis.id,
            repository_url=access.html_url,
            base_commit=analysis.base_commit,
            head_commit=analysis.head_commit,
            provider_name=provider_name,
            supplied_findings=findings,
            before_finding=reserve_before_provider_call,
        )
    except Exception as exc:
        _raise_http_for_ai_error(exc)
