# File: app/streamlit_app.py

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, List
import traceback
from core.schema import NextStep

import streamlit as st

from core.extract_docx import DocxExtractionError, clip_text, extract_text_from_docx
from core.params import APP_DESCRIPTION, APP_TITLE, APP_VERSION, MAX_DOC_CHARS
from core.report_pdf import PDFRenderError, render_ipid_pdf_bytes
from core.usage_log import log_usage, new_run_id, utc_now_iso
from core.analyze_demo import DemoAnalysisError, analyze_grant_text_demo
from core.analyze import AnalysisError, analyze_grant_text

# TEMP DEBUG: show full exception details in the browser UI
st.set_option("client.showErrorDetails", "full")

def _load_departments(path: str = "config/departments.json") -> List[str]:
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    return data["departments"]


def _reset_state() -> None:
    for k in ["result_ready", "pdf_bytes", "report_meta", "error_msg", "run_id"]:
        if k in st.session_state:
            del st.session_state[k]
    st.rerun()


def _sort_opportunities_by_confidence(report: Any) -> Any:
    try:
        report.opportunities.sort(key=lambda o: float(o.confidence_0_10), reverse=True)
    except Exception:
        pass
    return report


def _get_app_mode() -> str:
    mode = (os.getenv("APP_MODE", "demo") or "demo").strip().lower()
    return mode if mode in {"demo", "real"} else "demo"


def main() -> None:
    mode = _get_app_mode()

    st.set_page_config(page_title=APP_TITLE, layout="centered")
    st.title(APP_TITLE)
    st.caption(f"v{APP_VERSION} • {APP_DESCRIPTION}")
    if mode == "demo":
        st.markdown(
            """
            <div style="
                border: 2px solid #f59e0b;
                background-color: #fffbeb;
                padding: 12px 16px;
                border-radius: 8px;
                margin-bottom: 16px;
            ">
                <strong>⚠ DEMO MODE</strong><br>
                This is a proof-of-concept demo. No LLM model is queried.
                Results are generated deterministically from the uploaded document
                and are <em>not</em> a real IP assessment.
            </div>
            """,
            unsafe_allow_html=True,
        )


    # Always show restart button
    col_a, col_b = st.columns([1, 1])
    with col_b:
        if st.button("Start new IP ID"):
            _reset_state()

    # Initialize session state keys
    st.session_state.setdefault("result_ready", False)
    st.session_state.setdefault("pdf_bytes", None)
    st.session_state.setdefault("report_meta", None)
    st.session_state.setdefault("error_msg", None)
    st.session_state.setdefault("run_id", new_run_id())

    # Show error message if present
    if st.session_state.get("error_msg"):
        st.error(st.session_state["error_msg"])

    # If we already have a PDF, show download and stop
    if st.session_state.get("result_ready") and st.session_state.get("pdf_bytes"):
        st.success("Report ready.")
        st.download_button(
            label="Download PDF report",
            data=st.session_state["pdf_bytes"],
            file_name="CUI-IP-ID_Report.pdf",
            mime="application/pdf",
        )
        return

    # Load departments
    try:
        departments = _load_departments()
    except Exception:
        st.error('Departments list missing/invalid. Expected config/departments.json with {"departments": [...]} .')
        return

    # Inputs
    dept = st.selectbox("Department (required)", options=departments, index=0)
    name = st.text_input("Name (optional)", value="")
    uploaded = st.file_uploader("Upload DOCX (required)", type=["docx"])

    can_run = bool(dept and uploaded is not None)

    if st.button("Review protectable IP", disabled=not can_run):
        # Clear prior state
        st.session_state["error_msg"] = None
        st.session_state["result_ready"] = False
        st.session_state["pdf_bytes"] = None
        st.session_state["report_meta"] = None
        st.session_state["run_id"] = new_run_id()

        run_id = st.session_state["run_id"]
        ts = utc_now_iso()
        max_chars = int(MAX_DOC_CHARS)

        try:
            with st.spinner("Reviewing protectable IP…"):
                # Extract DOCX text
                file_bytes = uploaded.getvalue()
                text = extract_text_from_docx(file_bytes)
                text = clip_text(text, max_chars=max_chars)

                # Analyze (demo vs real)
                if mode == "demo":
                    report, meta = analyze_grant_text_demo(
                        grant_text=text,
                        department=dept,
                        person_name=name or None,
                    )
                else:
                    # "real" mode: runs the real analyzer (LLM-backed)
                    report, meta = analyze_grant_text(
                        grant_text=text,
                        department=dept,
                        person_name=name or None,
                    )

                report = _sort_opportunities_by_confidence(report)

                # Render PDF bytes
                meta = dict(meta or {})
                meta["run_id"] = run_id
                meta["generated_at_iso"] = ts
                meta["app_version"] = APP_VERSION
                meta["mode"] = mode

                pdf_bytes = render_ipid_pdf_bytes(report=report, meta=meta)

                idf_count = sum(1 for o in report.opportunities if o.suggested_next_step == NextStep.IDF)
                low_count = sum(1 for o in report.opportunities if o.suggested_next_step == NextStep.LOW)

                # Log usage (silent)
                log_usage(
                    department=dept,
                    name=name or None,
                    doc_chars=len(text),
                    run_id=run_id,
                    timestamp_iso=ts,
                    extra={
                        "max_doc_chars": max_chars,
                        "app_version": APP_VERSION,
                        "mode": mode,
                        "IDF": idf_count,
                        "LOW": low_count,
                    },
                )

            # Store results
            st.session_state["result_ready"] = True
            st.session_state["pdf_bytes"] = pdf_bytes
            st.session_state["report_meta"] = meta

            st.success("Report ready.")
            st.download_button(
                label="Download PDF report",
                data=pdf_bytes,
                file_name="CUI-IP-ID_Report.pdf",
                mime="application/pdf",
            )

        except Exception as e:
            st.session_state["error_msg"] = "Internal error: please try again."
            st.error(st.session_state["error_msg"])
            st.code(traceback.format_exc())   # <-- shows full stack trace
            st.stop()                         # <-- do NOT rerun during debug

if __name__ == "__main__":
    main()
