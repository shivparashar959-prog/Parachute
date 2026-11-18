"""
Strict Structured AI Response Validator for DocGuard (Milestone 6).

Validates raw JSON or dictionary output from an AI provider against
`AIExplanationPayload`, enforcing consistency between `insufficient_evidence`,
`correction_available`, `correction_status`, and the deterministic finding status.
"""

import json
import re
from typing import Any, Dict, Union

from pydantic import ValidationError

from app.ai.base_provider import AIProviderResponseValidationError
from app.schemas.ai_explanation import AIExplanationPayload
from app.schemas.drift import DriftFinding

_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL | re.IGNORECASE)


def _parse_raw_json(raw_output: Union[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Parse a raw string (stripping optional Markdown fences) into a JSON object dict."""
    if isinstance(raw_output, dict):
        return raw_output

    if not raw_output or not isinstance(raw_output, str) or not raw_output.strip():
        raise AIProviderResponseValidationError(
            "AI provider returned an empty response."
        )

    cleaned = raw_output.strip()
    fence_match = _JSON_FENCE_RE.match(cleaned)
    if fence_match:
        cleaned = fence_match.group(1).strip()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise AIProviderResponseValidationError(
            f"AI provider output is not valid JSON: {exc.msg}"
        ) from exc

    if not isinstance(parsed, dict):
        raise AIProviderResponseValidationError(
            "AI provider output must be a JSON object."
        )

    return parsed


def validate_ai_response(
    raw_output: Union[str, Dict[str, Any]],
    finding: DriftFinding,
) -> AIExplanationPayload:
    """
    Validate and normalize raw AI output into an `AIExplanationPayload`.
    Enforces that UNCERTAIN findings or responses flagged with `insufficient_evidence`
    do not claim a verified replacement suggestion.
    """
    data = _parse_raw_json(raw_output)

    try:
        payload = AIExplanationPayload.model_validate(data)
    except ValidationError as exc:
        raise AIProviderResponseValidationError(
            f"AI response failed schema validation: {exc.errors()[0].get('msg', 'invalid field')}"
        ) from exc

    # Consistency normalization:
    # 1. If the deterministic finding is UNCERTAIN or the AI reported insufficient_evidence,
    #    ensure no unreliable suggestion is marked as available.
    if finding.status == "UNCERTAIN" or payload.insufficient_evidence:
        payload.insufficient_evidence = True
        payload.correction_available = False
        payload.suggested_correction = None
        payload.correction_status = "INSUFFICIENT_EVIDENCE"
        if not payload.limitations:
            payload.limitations = [
                "Insufficient deterministic evidence to safely propose an automated replacement statement."
            ]
    elif payload.suggested_correction and payload.suggested_correction.strip():
        payload.suggested_correction = payload.suggested_correction.strip()
        payload.correction_available = True
        if payload.correction_status == "INSUFFICIENT_EVIDENCE":
            payload.correction_status = "SUGGESTION_AVAILABLE"
    else:
        payload.suggested_correction = None
        payload.correction_available = False
        if payload.correction_status == "SUGGESTION_AVAILABLE":
            payload.correction_status = "REVIEW_REQUIRED"

    return payload
