"""
Google Gemini AI Provider for DocGuard (Milestone 6).

Uses the official `google-genai` SDK with environment-driven configuration
(`GEMINI_API_KEY`, `GEMINI_MODEL`), strict JSON schema output, secret scrubbing,
and explicit error classification (never silently falling back to Mock mode).
"""

import os
from typing import Optional

from dotenv import load_dotenv
from google import genai
from google.genai import types

from app.ai.base_provider import (
    AIProviderConfigurationError,
    AIProviderError,
    AIProviderNetworkError,
    AIProviderRateLimitError,
    AIProviderResponseValidationError,
    AIProviderTimeoutError,
    BaseAIProvider,
)
from app.ai.prompt_builder import build_evidence_prompt
from app.ai.response_validator import validate_ai_response
from app.config import get_settings
from app.schemas.ai_explanation import AIExplanationPayload, AIProviderType
from app.schemas.drift import DriftFinding

load_dotenv(override=False)

DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"


def get_configured_gemini_model() -> str:
    """Return the configured Gemini model name from GEMINI_MODEL or the default."""
    model = (os.environ.get("GEMINI_MODEL") or "").strip()
    return model if model else DEFAULT_GEMINI_MODEL


def is_gemini_api_key_configured() -> bool:
    """Return True if a non-empty GEMINI_API_KEY is present in the environment."""
    key = (os.environ.get("GEMINI_API_KEY") or "").strip()
    return len(key) > 0


def _scrub_secret(message: str, api_key: Optional[str]) -> str:
    """Ensure the raw API key is never included in any exception or log message."""
    if not message:
        return ""
    scrubbed = message
    if api_key and len(api_key) >= 4 and api_key in scrubbed:
        scrubbed = scrubbed.replace(api_key, "[REDACTED_API_KEY]")
    return scrubbed


class GeminiAIProvider(BaseAIProvider):
    """
    Google Gemini provider implementation using `google-genai`.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout_ms: Optional[int] = None,
        max_output_tokens: Optional[int] = None,
    ) -> None:
        resolved_key = (
            api_key if api_key is not None else os.environ.get("GEMINI_API_KEY", "")
        ).strip()
        if not resolved_key:
            raise AIProviderConfigurationError(
                "Gemini API is not configured (GEMINI_API_KEY is missing). "
                "Add GEMINI_API_KEY to backend/.env or switch the provider to 'mock'."
            )
        self._api_key = resolved_key
        self._model = (model or get_configured_gemini_model()).strip()
        settings = get_settings()
        self._timeout_ms = timeout_ms or settings.gemini_provider_timeout_ms
        self._max_output_tokens = (
            max_output_tokens or settings.gemini_max_output_tokens
        )

    @property
    def provider_name(self) -> AIProviderType:
        return "gemini"

    @property
    def model_name(self) -> str:
        return self._model

    def _invoke_gemini_sdk(self, system_instruction: str, user_prompt: str) -> str:
        """
        Execute the Gemini `models.generate_content` call at the SDK boundary.
        Can be monkeypatched in automated tests to simulate responses and network/API errors.
        """
        client = genai.Client(
            api_key=self._api_key,
            http_options=types.HttpOptions(timeout=self._timeout_ms),
        )
        response = client.models.generate_content(
            model=self._model,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json",
                temperature=0.1,
                max_output_tokens=self._max_output_tokens,
            ),
        )
        return getattr(response, "text", "") or ""

    def _classify_provider_exception(self, exc: Exception) -> AIProviderError:
        """Translate SDK/HTTP exceptions into safe, secret-scrubbed domain errors."""
        if isinstance(exc, AIProviderError):
            return exc

        raw_msg = _scrub_secret(str(exc), self._api_key)
        lower_msg = raw_msg.lower()

        if isinstance(exc, TimeoutError) or "timed out" in lower_msg or "timeout" in lower_msg:
            return AIProviderTimeoutError(
                "Request to Google Gemini API timed out. Please try again or reduce the number of selected findings."
            )

        if (
            "429" in lower_msg
            or "resource_exhausted" in lower_msg
            or "rate limit" in lower_msg
            or "quota" in lower_msg
        ):
            return AIProviderRateLimitError(
                "Google Gemini API rate limit or quota exceeded (HTTP 429). Please wait before retrying or use Mock AI Mode."
            )

        if (
            "api_key_invalid" in lower_msg
            or "invalid api key" in lower_msg
            or "401" in lower_msg
            or "403" in lower_msg
            or "permission_denied" in lower_msg
        ):
            return AIProviderConfigurationError(
                "Google Gemini API rejected the configured GEMINI_API_KEY. Verify your key in backend/.env."
            )

        return AIProviderNetworkError(
            f"Failed to communicate with Google Gemini API: {raw_msg[:200]}"
        )

    def generate_explanation(self, finding: DriftFinding) -> AIExplanationPayload:
        system_instruction, user_prompt = build_evidence_prompt(finding)
        try:
            raw_text = self._invoke_gemini_sdk(
                system_instruction=system_instruction,
                user_prompt=user_prompt,
            )
        except Exception as exc:
            raise self._classify_provider_exception(exc) from exc

        if not raw_text or not raw_text.strip():
            raise AIProviderResponseValidationError(
                "Google Gemini API returned an empty response body."
            )

        return validate_ai_response(raw_text, finding)
