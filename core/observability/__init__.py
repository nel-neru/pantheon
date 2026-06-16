"""Pantheon observability — structured spans/traces over agent + LLM execution.

Read-only aggregation lives in :mod:`core.observability.span` (``TraceStore``),
mirroring :class:`core.runtime.token_ledger.TokenLedger`. Writing is best-effort
and never breaks a generation (see :mod:`core.observability.span_writer`).
"""

from __future__ import annotations

from core.observability.span import (
    Span,
    TraceStore,
    current_span_id,
    current_trace_id,
    record_llm_call,
    start_trace,
)

__all__ = [
    "Span",
    "TraceStore",
    "current_span_id",
    "current_trace_id",
    "record_llm_call",
    "start_trace",
]
