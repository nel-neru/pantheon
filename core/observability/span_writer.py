"""Best-effort append writer for the spans JSONL log.

The single source of truth is ``~/.pantheon/spans.jsonl`` (override via
``PANTHEON_SPANS_LOG``; set it to ``""``/``off``/``0`` to disable). Writing mirrors
``core.runtime.claude_code._log_call_timing``: one JSON object per line, append-only,
and **never raises** — observability must not affect a generation's result.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

SPANS_LOG_ENV = "PANTHEON_SPANS_LOG"
_DISABLED = {"", "off", "0", "false", "none"}


def spans_log_path(platform_home: Optional[Path] = None) -> Optional[Path]:
    """Resolve the spans log path, or ``None`` when disabled/unavailable."""
    override = os.getenv(SPANS_LOG_ENV)
    if override is not None:
        override = override.strip()
        if override.lower() in _DISABLED:
            return None
        return Path(override)
    if platform_home is not None:
        return Path(platform_home) / "spans.jsonl"
    try:
        from core.platform.state import get_platform_home

        return Path(get_platform_home()) / "spans.jsonl"
    except Exception:  # pragma: no cover - platform state optional
        return None


def write_span(record: dict) -> None:
    """Append one span record as a JSONL line. Best-effort; swallows all errors."""
    path = spans_log_path()
    if not path:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as exc:  # pragma: no cover - logging must not break calls
        logger.debug("failed to write span: %s", exc)
