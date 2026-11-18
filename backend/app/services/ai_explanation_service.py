"""
AI Explanation & Correction Suggestion Service for DocGuard (Milestone 6).

Coordinates provider selection ('mock' or 'gemini'), deterministic drift finding
retrieval, cost-control request limits, and preservation of deterministic finding
statuses, severities, and confidence scores.
"""

from typing import Dict, List, Optional

from app.ai.base_provider import (
    AIProviderConfigurationError,
    AIProviderError,
    BaseAIProvider,
)
from app.ai.gemini_provider import (
    GeminiAIProvider,
    get_configured_gemini_model,
    is_gemini_api_key_configured,
)
from app.ai.mock_provider import MockAIProvider
from app.schemas.ai_explanation import (
    AIExplanationResponse,
    AIProviderStatusResponse,
    AIProviderType,
    FindingAIExplanation,
)
from app.schemas.drift import DriftFinding
from app.services.drift_analysis_service import analyze_repository_drift
from app.services.github_service import (
    RepositoryValidationError,
    parse_and_validate_github_url,
    validate_commit_sha,
)

MAX_FINDINGS_PER_EXPLANATION_REQUEST = 10


def get_ai_provider_status() -> AIProviderStatusResponse:
    """Return current AI provider availability without exposing any API keys."""
    gemini_ready = is_gemini_api_key_configured()
    return AIProviderStatusResponse(
        gemini_configured=gemini_ready,
        gemini_model=get_configured_gemini_model(),
        mock_available=True,
        active_default_provider="gemini" if gemini_ready else "mock",
        supported_providers=["mock", "gemini"],
    )


def resolve_ai_provider(provider_name: str) -> BaseAIProvider:
    """
    Instantiate the requested AI provider ('mock' or 'gemini').
    Never silently falls back from 'gemini' to 'mock'.
    """
    normalized = (provider_name or "").strip().lower()
    if normalized == "mock":
        return MockAIProvider()
    if normalized == "gemini":
        return GeminiAIProvider()
    raise AIProviderConfigurationError(
        f"Unsupported AI provider '{provider_name}'. Supported providers are 'mock' and 'gemini'."
    )


def generate_explanations_for_repository(
    repository_url: str,
    base_commit: str,
    head_commit: str,
    provider_name: str = "mock",
    finding_ids: Optional[List[str]] = None,
    supplied_findings: Optional[List[DriftFinding]] = None,
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

    # Obtain deterministic drift findings (reuse supplied session findings if provided,
    # otherwise run the deterministic drift analysis service)
    if supplied_findings is not None:
        all_findings = list(supplied_findings)
    else:
        drift_report = analyze_repository_drift(
            repository_url=repository_url,
            base_commit=base_sha,
            head_commit=head_sha,
        )
        all_findings = drift_report.findings
        base_sha = drift_report.base_commit
        head_sha = drift_report.head_commit

    findings_by_id: Dict[str, DriftFinding] = {
        f.finding_id: f for f in all_findings
    }

    unknown_finding_ids: List[str] = []
    target_findings: List[DriftFinding] = []

    if finding_ids is not None:
        seen_ids: set[str] = set()
        for fid in finding_ids:
            cleaned_id = fid.strip()
            if not cleaned_id or cleaned_id in seen_ids:
                continue
            seen_ids.add(cleaned_id)
            if cleaned_id in findings_by_id:
                target_findings.append(findings_by_id[cleaned_id])
            else:
                unknown_finding_ids.append(cleaned_id)
    else:
        # Eligible findings policy when finding_ids is omitted:
        # Explain confirmed, potential, uncertain, and resolved drift findings up to the per-request limit
        target_findings = [
            f for f in all_findings if f.status != "UNCHANGED"
        ]

    bounded_findings = target_findings[:MAX_FINDINGS_PER_EXPLANATION_REQUEST]
    explanations: List[FindingAIExplanation] = []
    provider_errors: List[str] = []

    for finding in bounded_findings:
        try:
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
        unknown_finding_ids=unknown_finding_ids,
        provider_errors=provider_errors,
    )
