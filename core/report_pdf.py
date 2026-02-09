# File: core/report_pdf.py
"""
PDF report generation for CUI IP-ID.
The html-to-pdf rendering
- A4 page
- light blue top band
- dark blue right-side bar
- content column padded away from the bar
- footer text centered (used for disclaimer)

Input:
- IPIDReport (validated) + metadata dict from analysis
Output:
- PDF bytes (for Streamlit download_button)
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, Optional
from jinja2 import Template
import markdown2
from core.schema import IPIDReport


class PDFRenderError(RuntimeError):
    """Raised when PDF rendering fails."""

DEFAULT_TEMPLATE = r"""
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{{ title|e }}</title>
<style>
  @page {
    size: A4;
    margin: 0.45in 0 0.85in 0;
    @bottom-center {
      content: "{{ footer_center }}";
      font-style: italic;
      font-size: calc(7pt * var(--scale, 1));
      color: #6b7280;
      max-width: 8in;
      text-align: center;
      margin-left: auto;
      margin-right: auto;
  
    }
  }

  :root{
    --scale: 1;

    --ink: #111827;
    --blue-dark: #1F3A63;
    --blue-soft: #D9E6F4;

    --sidew: 1.60in;
    --pad-left: 0.90in;
    --pad-right: 2.00in;
    --right-gutter: 1.2in;

    --band-h: 1.8in;
    --header-bottom-pad: 0.05in;
    --content-top-gap: 0.20in;
    --content-bottom-pad: 0.50in;

    --body-size: 10pt;
    --sub-size: 18pt;
    --h2-size: 14pt;
    --h3-size: 12pt;
  }

  html, body { height:auto; }
  * { box-sizing: border-box; }
  body{
    margin:0;
    background:#fff;
    color:var(--ink);
    font-family: Inter, "Helvetica Neue", Arial, system-ui, -apple-system, Segoe UI, Roboto, "Noto Sans", sans-serif;
    font-size: calc(var(--body-size) * var(--scale, 1));
    line-height:1.45;
    -webkit-font-smoothing: antialiased;
    overflow-wrap: anywhere;
  }

  .page-side{
    position: fixed;
    top: 0; right: 0; bottom: 0;
    width: var(--sidew);
    background: var(--blue-dark);
    z-index: 1;
  }
  .top-band{
    position: fixed;
    top: 0; left: 0; right: 0;
    height: var(--band-h);
    background: var(--blue-soft);
    z-index: 2;
  }

  .container{
    position: relative;
    z-index: 3;
    margin-left: var(--pad-left);
    margin-right: var(--pad-right);
    padding-right: calc(var(--sidew) + var(--right-gutter)) !important;
    padding-top: 0.55in;
    width: auto !important;
    padding-bottom: var(--content-bottom-pad);
  }

  .doc-header{
    min-height: var(--band-h);
    display: flex;
    flex-direction: column;
    justify-content: flex-end;
    padding-bottom: var(--header-bottom-pad);
    margin: 0;
  }
  .title{
    font-weight: 800;
    font-size: var(--sub-size);
    line-height: 1.06;
    margin: 0 0 6px 0;
    letter-spacing: -0.01em;
  }
  .subtitle{
    font-weight: 600;
    font-size: 12pt;
    margin: 0 0 2px 0;
  }
  .meta-line{
    font-weight: 400;
    font-size: 10pt;
    margin: 2px 0 0 0;
  }

  .content{
    margin-top: var(--content-top-gap);
  }
  .content h2{
    font-weight: 800;
    font-size: var(--h2-size);
    line-height: 1.25;
    margin: 16px 0 6px 0;
  }
  .content h3{
    font-weight:700;
    font-size: var(--h3-size);
    margin: 12px 0 6px 0;
  }
  .content p{ margin:8px 0; }
  .content li{ margin:4px 0; }
  .content blockquote{
    margin:10px 0;
    padding-left:12px;
    border-left: 3px solid #e5e7eb;
  }
  .content code{
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace;
    font-size: 90%;
    padding:0 3px;
  }
  .content pre code{
    display:block; overflow-x:auto; padding:10px;
    border:1px solid #e5e7eb;
  }

  /* Small helper styling for opportunity blocks */
  .opp{
    border: 1px solid #e5e7eb;
    border-radius: 10px;
    padding: 10px 12px;
    margin: 10px 0;
    background: #ffffff;
  }
  .opp .opp-title{
    font-weight: 800;
    margin: 0 0 6px 0;
  }
  .pill{
    display: inline-block;
    border: 1px solid #d1d5db;
    border-radius: 999px;
    padding: 2px 8px;
    font-size: 9pt;
    margin-right: 6px;
  }
</style>
</head>
<body>
  <div class="page-side"></div>
  <div class="top-band"></div>

  <div class="container">
    <header class="doc-header">
      <div class="title">{{ display_title }}</div>
      {% if subtitle %}<div class="subtitle">{{ subtitle }}</div>{% endif %}
      {% if meta_bar %}<div class="meta-line">{{ meta_bar }}</div>{% endif %}
    </header>

    <section class="content">
      {{ html|safe }}
    </section>
  </div>
</body>
</html>
"""


def _require_weasy():
    try:
        from weasyprint import HTML, CSS
        return HTML, CSS
    except Exception as e:
        raise PDFRenderError(
            "WeasyPrint is required to render PDFs. "
            "Ensure 'weasyprint' and system deps are installed in Docker."
        ) from e


def md_to_html(md_text: str) -> str:
    return markdown2.markdown(
        md_text,
        extras=[
            "fenced-code-blocks",
            "tables",
            "strike",
            "task_list",
            "break-on-newline",
            "header-ids",
            "cuddled-lists",
            "smarty-pants",
        ],
    )


def _utc_timestamp_label() -> str:
    return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def report_to_markdown(report: IPIDReport, meta: Dict[str, Any]) -> str:
    """
    Convert a validated report into a simple Markdown body.
    This Markdown will then be converted to HTML and embedded in the template.
    """
    lines = []
    lines.append("## Potential IP Opportunities")
    lines.append("")
    if not report.opportunities:
        lines.append("_No potential IP opportunities were identified._")
        lines.append("")
        return "\n".join(lines)

    for idx, opp in enumerate(report.opportunities, start=1):
        # Use HTML blocks for consistent styling inside markdown2
        lines.append(f'<div class="opp">')
        lines.append(f'<div class="opp-title">{idx}. {opp.opportunity_title}</div>')
        lines.append(
            f'<span class="pill">Next step: {opp.suggested_next_step.value}</span>'
            f'<span class="pill">Confidence: {opp.confidence_0_10:.1f}/10</span>'
        )
        lines.append("<br><br>")
        lines.append("<b>Evidence</b>")
        lines.append("<ul>")
        for q in opp.evidence_quotes:
            safe_q = q.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            lines.append(f"<li>{safe_q}</li>")
        lines.append("</ul>")
        lines.append("</div>")
        lines.append("")

    return "\n".join(lines)


def render_ipid_pdf_bytes(
    report: IPIDReport,
    meta: Dict[str, Any],
    title: str = "CUI-IP-ID: Report",
    template_text: str = DEFAULT_TEMPLATE,
    generated_at_iso: Optional[str] = None,
) -> bytes:
    """
    Render the report as PDF bytes.

    Header requirements from you:
    - Title: "CUI-IP-ID: Report"
    - Subtitle: "<Department> • <Generated time>"
    - Footer: disclaimer text
    """
    HTML, CSS = _require_weasy()

    department = str(meta.get("department", "") or "").strip()
    if not department:
        department = "Unknown Department"

    generated_at_iso = generated_at_iso or _utc_timestamp_label()

    subtitle = f"{department} • Generated {generated_at_iso}"

    # You requested footer statement = decision-support disclaimer.
    footer_center = report.disclaimer.strip()

    md_body = report_to_markdown(report, meta)
    html_body = md_to_html(md_body)

    # Optional meta bar: keep minimal for now (you can change later)
    model_used = str(meta.get("openai_model", "") or "").strip()
    meta_bar = f"Model: {model_used}" if model_used else ""

    tpl = Template(template_text)
    html = tpl.render(
        title=title,
        display_title=title,
        subtitle=subtitle,
        meta_bar=meta_bar,
        html=html_body,
        footer_center=footer_center,
    )

    # Render to bytes (no filesystem writes)
    try:
        doc_bytes = HTML(string=html).write_pdf(stylesheets=[CSS(string=":root{--scale:1;}")])
    except Exception as e:
        raise PDFRenderError(f"Failed to render PDF: {e}") from e

    return doc_bytes