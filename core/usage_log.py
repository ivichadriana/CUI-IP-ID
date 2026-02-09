# File: core/usage_log.py
"""
Usage logging for CUI-IP-ID (Phase 1).

Goal:
- Append a lightweight usage row to a Google Sheet via an Apps Script Web App URL.
- Never block the user flow.
- Fail silently (no exceptions propagated to UI).

This module sends only metadata of user (no grant text).
"""

from __future__ import annotations

import os
import uuid
import datetime
from typing import Any, Dict, Optional


def utc_now_iso() -> str:
    """UTC timestamp like 2026-01-27T18:22:10Z (no microseconds)."""
    return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def new_run_id() -> str:
    """Generate a unique run id for correlating logs."""
    return str(uuid.uuid4())


def _get_env(name: str) -> str:
    return (os.getenv(name, "") or "").strip()


def log_usage(
    *,
    department: str,
    name: Optional[str],
    doc_chars: int,
    run_id: str,
    timestamp_iso: str,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Fire-and-forget usage logging.

    Env vars:
      - USAGE_LOG_URL: Apps Script web app endpoint (POST)
      - USAGE_LOG_TOKEN: shared secret token

    Payload includes:
      token, timestamp_iso, department, name (or "NA"), doc_chars, run_id

    Behavior:
      - If URL or TOKEN is missing: do nothing.
      - Any errors: swallowed silently.
    """
    url = _get_env("USAGE_LOG_URL")
    token = _get_env("USAGE_LOG_TOKEN")
    if not url or not token:
        return

    dept = (department or "").strip()
    if not dept:
        return  # department is required for meaningful analytics

    nm = (name or "").strip() or "NA"

    payload: Dict[str, Any] = {
        "token": token,
        "timestamp_iso": timestamp_iso or utc_now_iso(),
        "department": dept,
        "name": nm,
        "doc_chars": int(doc_chars) if doc_chars is not None else 0,
        "run_id": (run_id or "").strip() or new_run_id(),
    }
    if extra:
        # Keep it shallow and JSON-serializable; ignore failures
        for k, v in extra.items():
            if k in payload:
                continue
            try:
                _ = str(k)
                payload[k] = v
            except Exception:
                continue
    mode = (mode or "").strip().lower()
    if mode == "demo":
        url = _get_env("USAGE_LOG_URL_DEMO")
        token = _get_env("USAGE_LOG_TOKEN_DEMO")
    else:
        url = _get_env("USAGE_LOG_URL")
        token = _get_env("USAGE_LOG_TOKEN")
    # Never block the user. Keep timeouts short and swallow all exceptions.
    try:
        import requests  # lightweight dependency
        timeout_s = float(_get_env("USAGE_LOG_TIMEOUT_S") or "2.5")
        requests.post(url, json=payload, timeout=timeout_s)
    except Exception:
        return