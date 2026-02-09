#core/schema.py
"""
Schema definitions for the CUI IP-ID project.

This module defines the canonical JSON structure returned by the LLM and used
throughout the pipeline (analysis -> PDF rendering -> optional logging metrics).

Defines the “contract” for what the LLM must return (valid JSON structure). 
Everything else in the app depends on this being consistent.

# Example of a model return:
{
"opportunities": [
{
"opportunity_title": "Novel biomarker",
"evidence_quotes": ["We identify a new biomarker..."],
"confidence_0_10": 8,
"suggested_next_step": "IDF"
}
]
}

"""

from __future__ import annotations
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict, field_validator


class NextStep(str, Enum):
    """Suggested next action for the user / CUI team."""
    IDF = "Submit Invention Disclosure Form (IDF)"
    LOW = "Low priority - Revisit later"

class Opportunity(BaseModel):
    """One potential protectable IP opportunity extracted from the grant text."""
    # if the JSON contains any unexpected keys (like "page_number"), validation fails.
    model_config = ConfigDict(extra="forbid")

    opportunity_title: str = Field(
        ...,
        min_length=3,
        description="Short title describing the potential IP opportunity.",
    )
    evidence_quotes: List[str] = Field(
        ...,
        min_length=1,
        description="Verbatim quotes from the input text that support this opportunity.",
    )
    confidence_0_10: float = Field(
        ...,
        ge=0,
        le=10,
        description="Confidence score from 0 to 10.",
    )
    suggested_next_step: NextStep = Field(
        ...,
        description="Recommended next step: IDF, CONSIDER, or LOW.",
    )

    @field_validator("evidence_quotes")
    @classmethod
    def _validate_evidence_quotes(cls, quotes: List[str]) -> List[str]:
        cleaned: List[str] = []
        for q in quotes:
            if not isinstance(q, str):
                continue
            s = q.strip()
            if s:
                cleaned.append(s)

        if len(cleaned) < 1:
            raise ValueError("evidence_quotes must include at least one non-empty quote.")

        # Deduplicate while preserving order
        seen = set()
        deduped: List[str] = []
        for s in cleaned:
            if s not in seen:
                seen.add(s)
                deduped.append(s)

        return deduped


class IPIDReport(BaseModel):
    """
    Full structured output from the model.

    Notes:
    - disclaimer is included in the JSON so the PDF always carries it.
    - opportunities length is capped in the prompt, but we also validate here.
    """
    model_config = ConfigDict(extra="forbid")

    opportunities: List[Opportunity] = Field(
        default_factory=list,
        description="List of identified opportunities (wide net).",
    )
    disclaimer: str = Field(
        default=(
            "This report is a decision-support tool and does not constitute legal advice. "
            "All items should be reviewed and validated by the CU Innovations team."
        ),
        description="Standard disclaimer to include in the PDF.",
    )

    @field_validator("opportunities")
    @classmethod
    def _cap_opportunities(cls, opps: List[Opportunity]) -> List[Opportunity]:
        # Hard cap for safety/cost/UX; prompt should also enforce this.
        if len(opps) > 25:
            raise ValueError("Too many opportunities returned (max 25).")
        return opps


def report_from_llm_json(data: dict) -> IPIDReport:
    """
    Parse and validate a raw dict (from LLM JSON) into an IPIDReport.

    Raises:
        pydantic.ValidationError on invalid schema.
    """
    return IPIDReport.model_validate(data)