# File: core/analyze_demo.py
"""
Demo (no-LLM) analyzer for CUI-IP-ID.

Purpose:
- Provide a deterministic, offline proof-of-concept for the full pipeline:
  DOCX -> extracted text -> "analysis" -> schema-validated report -> PDF.
- In DEMO mode, we intentionally do NOT analyze the uploaded document.
- We still return a valid schema output so PDF generation and UI flow can be demoed.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from core.schema import IPIDReport, NextStep, Opportunity


class DemoAnalysisError(RuntimeError):
    """Raised when demo analysis cannot produce a valid report."""


def analyze_grant_text_demo(
    grant_text: str,
    department: str,
    person_name: Optional[str] = None,
) -> Tuple[IPIDReport, Dict[str, Any]]:
    """
    Demo analyzer: produces a valid IPIDReport without calling any model.

    Behavior:
    - Requires that a document was uploaded (i.e., non-trivial text exists),
      but does NOT use it for the demo "analysis".
    - Returns a fixed example report with 2 opportunities and placeholder evidence.

    Returns:
      (report, meta)
    """
    if not grant_text or len(grant_text.strip()) < 25:
        raise DemoAnalysisError("Grant text is too short (demo). Please upload a valid DOCX.")
    if not (department or "").strip():
        raise DemoAnalysisError("Department is required (demo).")

    disclaimer = (
        "(DEMO MODE) This report is an example output for demonstration purposes only. "
        "No AI model was used and the uploaded document was not analyzed for IP content. "
        "This tool is decision-support only and does not constitute legal advice. "
        "All items should be reviewed and validated by the CU Innovations team."
    )

    opp1 = Opportunity(
        opportunity_title="Example: Potential novel assay or screening method (DEMO)",
        evidence_quotes=[
            "(DEMO) Example supporting language would be quoted verbatim here.",
            "(DEMO)Another example quote showing key claims/steps/results.",
        ],
        confidence_0_10=7.8,
        suggested_next_step=NextStep.IDF,
    )

    opp2 = Opportunity(
        opportunity_title="Example: Potential software tool / algorithm (DEMO)",
        evidence_quotes=[
            "(DEMO) Example text describing a novel computational method or pipeline."
        ],
        confidence_0_10=6.2,
        suggested_next_step=NextStep.LOW,
    )

    report = IPIDReport(
        opportunities=[opp1, opp2],
        disclaimer=disclaimer,
    )

    meta: Dict[str, Any] = {
        "mode": "demo",
        "department": department,
        "name": person_name.strip() if person_name and person_name.strip() else "NA",
        "doc_char_count": len(grant_text),
        "note": "demo_report_no_document_analysis",
    }

    return report, meta
