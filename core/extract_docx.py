# File: core/extract_docx.py
"""
DOCX text extraction.
Basically reliably turn a DOCX into clean text, or fail loudly and safely.
v1 scope:
- Accept a .docx uploaded via Streamlit.
- Extract readable plain text in document order.
- Preserve paragraph breaks (blank line between paragraphs).
- Keep it simple and robust.

Later (v2+):
- Add section targeting (Specific Aims, Research Strategy, Innovation).
- Add table extraction if needed.
"""

from __future__ import annotations
from io import BytesIO
from typing import Union


class DocxExtractionError(RuntimeError):
    """Raised when DOCX extraction fails."""


def extract_text_from_docx(file_bytes: Union[bytes, BytesIO]) -> str:
    """
    Extract plain text from a DOCX file.

    Args:
        file_bytes: Raw bytes (or BytesIO) for the .docx file.

    Returns:
        Plain text with paragraphs separated by blank lines.

    Raises:
        DocxExtractionError: if the file cannot be parsed or text is empty.
    """
    try:
        from docx import Document  # python-docx
    except Exception as e:
        raise DocxExtractionError(
            "python-docx is required for DOCX extraction. "
            "Ensure it is installed in requirements.txt."
        ) from e

    try:
        bio = file_bytes if isinstance(file_bytes, BytesIO) else BytesIO(file_bytes)
        doc = Document(bio)
    except Exception as e:
        raise DocxExtractionError(
            "Failed to read DOCX. Please upload a valid .docx file."
        ) from e

    paragraphs = []
    for p in doc.paragraphs:
        text = (p.text or "").strip()
        if text:
            paragraphs.append(text)

    # NOTE: We intentionally ignore headers/footers in v1.
    # Tables are also ignored in v1 unless they are crucial later.

    if not paragraphs:
        raise DocxExtractionError(
            "No readable text found in the DOCX. "
            "If your document is mostly images, export it with selectable text."
        )

    return "\n\n".join(paragraphs)


def clip_text(text: str, max_chars: int) -> str:
    """
    Hard-cap text length to control cost and latency.

    Args:
        text: extracted text
        max_chars: maximum characters allowed

    Returns:
        Possibly truncated text.
    """
    if max_chars <= 0:
        return text
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n\n[TRUNCATED]\n"