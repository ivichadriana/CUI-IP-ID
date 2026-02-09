# File: core/analyze.py
"""
OpenAI analysis for CUI IP-ID — Responses API + Strict JSON Schema.

Responsibilities:
- Build the prompt (system + user) using the extracted grant text.
- Call the OpenAI Responses API (model configurable via env var / core.params).
- Enforce structured JSON output (strict json_schema) matching core/schema.py.
- Validate output with Pydantic schema (fails loudly on invalid JSON).

Notes:
- Uses Responses API (POST /v1/responses), not Chat Completions.
- Keeps provider-ready shape: later swap to Azure OpenAI by changing this module.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from core import params
from core.schema import IPIDReport, report_from_llm_json


class AnalysisError(RuntimeError):
    """Raised when the LLM analysis fails or returns invalid output."""


@dataclass(frozen=True)
class OpenAIConfig:
    api_key: str
    model: str
    timeout_s: float
    max_output_tokens: int
    temperature: float


def load_prompt_text(prompt_path: str = "prompts/ipid_system.txt") -> str:
    """
    Reads prompts/ipid_system.txt from disk.
    If missing: raises AnalysisError.
    """
    p = Path(prompt_path)
    if not p.exists():
        raise AnalysisError(f"Prompt file not found: {prompt_path}")
    return p.read_text(encoding="utf-8")


def _env_str(name: str) -> Optional[str]:
    v = (os.getenv(name, "") or "").strip()
    return v if v else None


def _env_float(name: str) -> Optional[float]:
    v = _env_str(name)
    if v is None:
        return None
    try:
        return float(v)
    except Exception:
        raise AnalysisError(f"Invalid value for {name}: expected a number.")


def _env_int(name: str) -> Optional[int]:
    v = _env_str(name)
    if v is None:
        return None
    try:
        return int(float(v))
    except Exception:
        raise AnalysisError(f"Invalid value for {name}: expected an integer.")


def get_openai_config() -> OpenAIConfig:
    """
    Required:
      OPENAI_API_KEY

    Optional env overrides (env wins if set):
      OPENAI_MODEL
      OPENAI_TIMEOUT_S
      OPENAI_MAX_OUTPUT_TOKENS
      OPENAI_TEMPERATURE

    Defaults come from core/params.py.
    """
    api_key = (os.getenv("OPENAI_API_KEY", "") or "").strip()
    if not api_key:
        raise AnalysisError("OPENAI_API_KEY is not set.")

    model = _env_str("OPENAI_MODEL") or getattr(params, "OPENAI_MODEL", "gpt-4o-mini")

    timeout_s = _env_float("OPENAI_TIMEOUT_S")
    if timeout_s is None:
        timeout_s = float(getattr(params, "OPENAI_TIMEOUT_S", 60.0))

    max_output_tokens = _env_int("OPENAI_MAX_OUTPUT_TOKENS")
    if max_output_tokens is None:
        max_output_tokens = int(getattr(params, "OPENAI_MAX_OUTPUT_TOKENS", 1400))

    temperature = _env_float("OPENAI_TEMPERATURE")
    if temperature is None:
        temperature = float(getattr(params, "OPENAI_TEMPERATURE", 0.2))

    if max_output_tokens <= 0:
        max_output_tokens = 1400
    if timeout_s <= 0:
        timeout_s = 60.0
    if temperature < 0:
        temperature = 0.0

    return OpenAIConfig(
        api_key=api_key,
        model=str(model).strip(),
        timeout_s=float(timeout_s),
        max_output_tokens=int(max_output_tokens),
        temperature=float(temperature),
    )


def _extract_json_from_text(text: str) -> Dict[str, Any]:
    """
    Best-effort JSON extraction.

    With strict json_schema, the SDK should already return clean JSON text,
    but this provides a safety net against any unexpected wrapping.
    """
    s = (text or "").strip()

    # Remove common markdown fences (just in case)
    if s.startswith("```"):
        s = s.strip().strip("`").strip()
        if "\n" in s:
            s = s.split("\n", 1)[1].strip()

    # Try direct parse first
    try:
        return json.loads(s)
    except Exception:
        pass

    # Fallback: substring between first { and last }
    i = s.find("{")
    j = s.rfind("}")
    if i == -1 or j == -1 or j <= i:
        raise AnalysisError("Model output did not contain valid JSON object.")
    try:
        return json.loads(s[i : j + 1])
    except Exception as e:
        raise AnalysisError(f"Failed to parse JSON from model output: {e}") from e


def _ipid_json_schema() -> Dict[str, Any]:
    """
    Strict JSON Schema matching core/schema.py (extra fields forbidden).

    Important: keep in sync with schema.py if schema changes.
    """
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "opportunities": {
                "type": "array",
                "maxItems": 25,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "opportunity_title": {"type": "string", "minLength": 3},
                        "evidence_quotes": {
                            "type": "array",
                            "minItems": 1,
                            "items": {"type": "string", "minLength": 1},
                        },
                        "confidence_0_10": {"type": "number", "minimum": 0, "maximum": 10},
                        "suggested_next_step": {
                            "type": "string",
                            "enum": ["IDF","LOW"],
                        },
                    },
                    "required": [
                        "opportunity_title",
                        "evidence_quotes",
                        "confidence_0_10",
                        "suggested_next_step",
                    ],
                },
            },
            "disclaimer": {"type": "string"},
        },
        "required": ["opportunities"],
    }


def analyze_grant_text(
    grant_text: str,
    department: str,
    person_name: Optional[str] = None,
    prompt_path: str = "prompts/ipid_system.txt",
) -> Tuple[IPIDReport, Dict[str, Any]]:
    """
    Analyze grant text and return a validated IPIDReport plus minimal metadata.

    Returns:
        (report, meta)

    Raises:
        AnalysisError if the API call fails or returns invalid schema.
    """
    if not grant_text or len(grant_text.strip()) < 25:
        raise AnalysisError("Grant text is too short to analyze.")
    if not department.strip():
        raise AnalysisError("Department is required.")

    system_prompt = load_prompt_text(prompt_path=prompt_path)

    user_prompt = (
        "You are analyzing grant proposal text to identify *potentially protectable IP*.\n"
        "Return results as JSON ONLY.\n\n"
        f"Department: {department}\n"
        f"Name: {person_name.strip() if person_name else 'NA'}\n\n"
        "=== GRANT TEXT START ===\n"
        f"{grant_text}\n"
        "=== GRANT TEXT END ===\n"
    )

    cfg = get_openai_config()

    # OpenAI Python SDK (Responses API)
    try:
        from openai import OpenAI
    except Exception as e:
        raise AnalysisError("OpenAI SDK not installed. Ensure 'openai' is in requirements.txt.") from e

    # Prefer client-level timeout if supported; fall back if SDK signature differs.
    try:
        client = OpenAI(api_key=cfg.api_key, timeout=cfg.timeout_s)
    except TypeError:
        client = OpenAI(api_key=cfg.api_key)

    try:
        resp = client.responses.create(
            model=cfg.model,
            instructions=system_prompt,
            input=user_prompt,
            temperature=cfg.temperature,
            max_output_tokens=cfg.max_output_tokens,
            store=False,
            text={
                "format": {
                    "type": "json_schema",
                    "name": "ipid_report",
                    "strict": True,
                    "schema": _ipid_json_schema(),
                }
            },
        )
    except Exception as e:
        raise AnalysisError(f"OpenAI API call failed: {e}") from e

    # SDK convenience: aggregated text output
    try:
        content = (getattr(resp, "output_text", None) or "").strip()
    except Exception as e:
        raise AnalysisError(f"Unexpected OpenAI response format: {e}") from e

    if not content:
        raise AnalysisError("OpenAI returned empty output_text.")

    raw_json = _extract_json_from_text(content)

    try:
        report = report_from_llm_json(raw_json)
    except Exception as e:
        raise AnalysisError(f"Model output failed schema validation: {e}") from e

    meta = {
        "openai_model": cfg.model,
        "temperature": cfg.temperature,
        "max_output_tokens": cfg.max_output_tokens,
        "department": department,
        "name": person_name.strip() if person_name and person_name.strip() else "NA",
        "doc_char_count": len(grant_text),
    }

    return report, meta
