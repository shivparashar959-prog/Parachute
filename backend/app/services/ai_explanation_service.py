"""
AI Explanation & Correction Suggestion Service for DocGuard (Milestone 6).

Coordinates provider selection ('mock' or 'gemini'), deterministic drift finding
retrieval, cost-control request limits, and preservation of deterministic finding
statuses, severities, and confidence scores.
"""

import uuid
from typing import Callable, List, Optional

from app.ai.base_provider import (
    AIProviderConfigurationError,
    AIProviderError,
    AIProviderPolicyError,
    BaseAIProvider,
)
from app.ai.gemini_provider import (
    GeminiAIProvider,
    get_configured_gemini_model,
    is_gemini_api_key_configured,
)
from app.ai.mock_provider import MockAIProvider
from app.ai.prompt_builder import build_evidence_prompt
from app.config import get_settings
from app.schemas.ai_explanation import (
    AIExplanationResponse,
    AIProviderStatusResponse,
    AIProviderType,
    FindingAIExplanation,
)
from app.schemas.drift import DriftFinding
from app.services.github_service import (
    RepositoryValidationError,
    parse_and_validate_github_url,
    validate_commit_sha,
)

MAX_FINDINGS_PER_EXPLANATION_REQUEST = 10


def get_ai_provider_status() -> AIProviderStatusResponse:
    """Return current AI provider availability without exposing any API keys."""
    settings = get_settings()
    gemini_key_configured = is_gemini_api_key_configured()
    production = settings.app_environment == "production"
    gemini_ready = (
        gemini_key_configured and settings.gemini_spend_controls_configured
    )
    providers: list[AIProviderType] = (
        ["gemini"] if production else ["mock", "gemini"]
    )
    active_provider: AIProviderType = "gemini" if production or gemini_ready else "mock"
    availability_message = None
    if production and not gemini_key_configured:
        availability_message = "Gemini must be configured by the service operator."
    elif not settings.gemini_spend_controls_configured:
        availability_message = "Gemini spend limits must be configured by the service operator."
    return AIProviderStatusResponse(
        gemini_configured=gemini_key_configured,
        gemini_model=get_configured_gemini_model(),
        gemini_budget_configured=settings.gemini_spend_controls_configured,
        mock_available=not production,
        active_default_provider=active_provider,
        availability_message=availability_message,
        supported_providers=providers,
    )


def resolve_ai_provider(provider_name: str) -> BaseAIProvider:
    """
    Instantiate the requested AI provider ('mock' or 'gemini').
    Never silently falls back from 'gemini' to 'mock'.
    """
    normalized = (provider_name or "").strip().lower()
    if get_settings().app_environment == "production" and normalized != "gemini":
        raise AIProviderPolicyError(
            "Mock AI is available only in development and test environments."
        )
    if normalized == "mock":
        return MockAIProvider()
    if normalized == "gemini":
        return GeminiAIProvider()
    raise AIProviderConfigurationError(
        f"Unsupported AI provider '{provider_name}'. Supported providers are 'mock' and 'gemini'."
    )


def generate_explanations_for_repository(
    analysis_id: uuid.UUID,
    repository_url: str,
    base_commit: str,
    head_commit: str,
    provider_name: str = "mock",
    supplied_findings: Optional[List[DriftFinding]] = None,
    before_finding: Optional[Callable[[DriftFinding, str], None]] = None,
) -> AIExplanationResponse:
    """
    Generate structured AI explanations and documentation correction suggestions
    for deterministic drift findings.
    """
    owner, repo_name, canonical_url, _clone_url = parse_and_validate_github_url(
        repository_url
    )
    base_sha = validate_commit_sha(base_commit, label="base_commit")
    head_sha = validate_commit_sha(head_commit, label="head_commit")

    if base_sha == head_sha:
        raise RepositoryValidationError(
            "Base commit and head commit must be different commits."
        )

    provider = resolve_ai_provider(provider_name)

    bounded_findings = list(supplied_findings or [])
    if not bounded_findings or len(bounded_findings) > MAX_FINDINGS_PER_EXPLANATION_REQUEST:
        raise AIProviderConfigurationError(
            "Select between 1 and 10 persisted findings for explanation."
        )
    explanations: List[FindingAIExplanation] = []
    provider_errors: List[str] = []

    for finding in bounded_findings:
        try:
            system_prompt, user_prompt = build_evidence_prompt(finding)
            if before_finding is not None:
                before_finding(finding, system_prompt + "\n" + user_prompt)
            payload = provider.generate_explanation(finding)
            explanations.append(
                FindingAIExplanation(
                    finding_id=finding.finding_id,
                    provider=provider.provider_name,
                    model_name=provider.model_name,
                    finding_type=finding.finding_type,
                    rule_id=finding.rule_id,
                    original_status=finding.status,
                    original_severity=finding.severity,
                    original_confidence=finding.confidence,
                    documentation_file=finding.documentation_file,
                    documentation_line=finding.documentation_line,
                    related_symbol=finding.qualified_symbol,
                    source_file=finding.source_file,
                    explanation=payload.explanation,
                    code_change_summary=payload.code_change_summary,
                    documentation_issue=payload.documentation_issue,
                    evidence_used=payload.evidence_used,
                    suggested_correction=payload.suggested_correction,
                    correction_status=payload.correction_status,
                    correction_available=payload.correction_available,
                    insufficient_evidence=payload.insufficient_evidence,
                    limitations=payload.limitations,
                    provider_error=None,
                )
            )
        except AIProviderError:
            # Propagate provider errors so caller/API reports actual provider failure
            # rather than silently faking a result
            raise

    return AIExplanationResponse(
        analysis_id=analysis_id,
        repository_url=canonical_url,
        owner=owner,
        name=repo_name,
        base_commit=base_sha,
        head_commit=head_sha,
        provider=provider.provider_name,
        model_name=provider.model_name,
        total_requested=len(bounded_findings),
        explanations_generated=len(explanations),
        explanations=explanations,
        unknown_finding_ids=[],
        provider_errors=provider_errors,
    )
