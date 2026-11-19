"""
Abstract Base AI Provider & Exception Hierarchy for DocGuard (Milestone 6).
"""

from abc import ABC, abstractmethod
from typing import Optional

from app.schemas.ai_explanation import AIExplanationPayload, AIProviderType
from app.schemas.drift import DriftFinding


class AIProviderError(Exception):
    """Base exception for AI provider errors."""


class AIProviderConfigurationError(AIProviderError):
    """Raised when an AI provider is missing required configuration (e.g. GEMINI_API_KEY) or is invalid."""


class AIProviderPolicyError(AIProviderError):
    """Raised when a configured provider is disallowed by deployment policy."""


class AIProviderRateLimitError(AIProviderError):
    """Raised when the external AI provider returns a rate-limit or quota error (HTTP 429)."""


class AIProviderTimeoutError(AIProviderError):
    """Raised when a request to the external AI provider times out."""


class AIProviderNetworkError(AIProviderError):
    """Raised when a network connection error occurs while calling the AI provider."""


class AIProviderResponseValidationError(AIProviderError):
    """Raised when the AI provider returns malformed JSON or fails schema validation."""


class AIProviderInputLimitError(AIProviderError):
    """Raised when verified finding evidence exceeds the configured prompt budget."""


class BaseAIProvider(ABC):
    """Provider-independent interface for generating drift explanations and doc fixes."""

    @property
    @abstractmethod
    def provider_name(self) -> AIProviderType:
        """Return the provider identifier ('mock' or 'gemini')."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Return the active model name used by this provider."""

    @abstractmethod
    def generate_explanation(self, finding: DriftFinding) -> AIExplanationPayload:
        """
        Generate a structured, evidence-backed explanation and correction suggestion
        for a deterministic DriftFinding.
        """

    def generate_correction_suggestion(self, finding: DriftFinding) -> Optional[str]:
        """
        Convenience operation returning only the suggested documentation replacement
        text (or None when evidence is insufficient).
        """
        payload = self.generate_explanation(finding)
        return payload.suggested_correction if payload.correction_available else None
