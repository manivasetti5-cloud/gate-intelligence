"""Configurable LLM provider client with retries, timeouts, and strict JSON validation."""

import json
import os
import re
import time
from typing import Any


class LLMUnavailableError(RuntimeError):
    """Raised when no LLM API key is configured or provider is unreachable."""


class LLMSchemaError(ValueError):
    """Raised when the LLM output fails strict JSON or schema validation."""


def is_llm_configured() -> bool:
    """Return True if an LLM API key is configured in environment."""
    return bool(os.getenv("GEMINI_API_KEY", "").strip())


def extract_json_payload(raw_text: str) -> dict | list:
    """Extract and parse JSON from raw LLM text (stripping optional markdown fences)."""
    cleaned = (raw_text or "").strip()
    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned)
    if fence_match:
        cleaned = fence_match.group(1).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise LLMSchemaError(f"Invalid JSON from LLM: {exc}") from exc


def validate_required_keys(data: dict, required_keys: list[str]) -> None:
    """Validate that a parsed JSON object contains all required keys."""
    if not isinstance(data, dict):
        raise LLMSchemaError("Expected JSON object from LLM.")
    missing = [k for k in required_keys if k not in data]
    if missing:
        raise LLMSchemaError(f"LLM JSON missing required keys: {', '.join(missing)}")


def generate_structured_json(
    prompt: str,
    *,
    system_instruction: str = "You are a strict GATE engineering assessment expert. Respond only with valid JSON.",
    model_name: str | None = None,
    required_keys: list[str] | None = None,
    retries: int | None = None,
) -> tuple[dict[str, Any], str]:
    """
    Call the configured LLM provider and return (parsed_json, model_used).
    Raises LLMUnavailableError if API key is missing, or LLMSchemaError on malformed responses.
    """
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise LLMUnavailableError("GEMINI_API_KEY is not configured in environment.")

    target_model = model_name or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    max_retries = retries if retries is not None else int(os.getenv("LLM_MAX_RETRIES", "2"))

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    last_err: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            response = client.models.generate_content(
                model=target_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json",
                    temperature=0.2,
                ),
            )
            raw = getattr(response, "text", "") or ""
            parsed = extract_json_payload(raw)
            if isinstance(parsed, list):
                parsed = {"items": parsed}
            if required_keys:
                validate_required_keys(parsed, required_keys)
            return parsed, target_model
        except (LLMSchemaError, Exception) as exc:
            last_err = exc
            if attempt < max_retries:
                time.sleep(min(2.0, 0.5 * (attempt + 1)))
                continue
            break

    if isinstance(last_err, LLMSchemaError):
        raise last_err
    raise LLMUnavailableError(f"LLM request failed after retries: {last_err}")
