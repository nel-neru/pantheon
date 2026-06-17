"""
Pantheon - robust JSON extraction from LLM output.

Models rarely return a bare JSON object. They wrap it in prose ("Here is the
JSON:"), fence it in a ```json … ``` block, or append a trailing explanation.
Historically each call site rolled its own brace scan, and they disagreed on
robustness:

- ``re.search(r"\\{.*?\\}", …)`` (non-greedy) stops at the *first* ``}``, so it
  truncates any nested object / any ``}`` inside a string value.
- ``re.search(r"\\{.*\\}", …)`` (greedy) stops at the *last* ``}``, so it
  over-captures a stray ``}`` in trailing prose and then ``json.loads`` raises.
- ``text.find("{")`` / ``text.rfind("}")`` has the same greedy failure mode.

This module is the single canonical replacement. It uses
``json.JSONDecoder.raw_decode``, which consumes exactly one well-formed JSON
value starting at the first ``{`` and ignores any trailing text — correctly
handling nested objects, arrays, and braces inside string literals.
"""

from __future__ import annotations

import json
import re
from typing import Any

# `\n`-anchored (not `\s*`+lazy) to avoid catastrophic backtracking / ReDoS.
_FENCE_RE = re.compile(r"```(?:json)?\n(.*?)```", re.DOTALL)


def extract_json_object(text: str | None) -> Any | None:
    """Extract a single JSON value from LLM output.

    Strategy: strip a ```json``` code fence if present, then from the first
    ``{`` use :meth:`json.JSONDecoder.raw_decode` to parse exactly one
    well-formed JSON value, ignoring any trailing prose. Returns the parsed
    value (typically a ``dict``), or ``None`` if no JSON object can be found or
    the candidate is not valid JSON. Never raises on malformed input — callers
    fall back deterministically on ``None``.
    """
    if not text:
        return None
    fenced = _FENCE_RE.search(text)
    candidate = fenced.group(1) if fenced else text
    start = candidate.find("{")
    if start == -1:
        return None
    try:
        obj, _end = json.JSONDecoder().raw_decode(candidate[start:])
        return obj
    except ValueError:
        return None
