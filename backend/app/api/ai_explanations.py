"""
API endpoints for Milestone 6: AI-Powered Explanations and Documentation Correction Suggestions.
Provides:
- GET /api/analyze/explanations/providers
- POST /api/analyze/explanations
"""

from fastapi import APIRouter, HTTPException, status

from app.ai.base_provider import (
    AIProviderConfigurationError,
    AIProviderError,
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

router = APIRouter(prefix="/api/analyze/explanations", tags=["AI Explanations"])


def _raise_http_for_ai_error(exc: Exception) -> None:
    """Translate AI provider and repository exceptions into clean FastAPI HTTPExceptions."""
    if isinstance(exc, AIProviderConfigurationError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
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
) -> AIExplanationResponse:
    """
    Generate evidence-backed AI explanations and documentation correction suggestions
    for deterministic documentation drift findings using either 'mock' or 'gemini'.
    """
    try:
        return generate_explanations_for_repository(
            repository_url=payload.repository_url,
            base_commit=payload.base_commit,
            head_commit=payload.head_commit,
            provider_name=payload.provider,
            finding_ids=payload.finding_ids,
            supplied_findings=payload.findings,
        )
    except Exception as exc:
        _raise_http_for_ai_error(exc)
