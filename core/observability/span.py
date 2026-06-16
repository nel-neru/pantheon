"""Structured spans + read-only trace aggregation.

A *span* is one timed unit of work (an orchestration, an LLM call, later a tool
call / reflexion iteration / verify / eval). Spans carry correlation IDs
(``trace_id`` + ``parent_span_id``) so a ``TraceStore`` can group them into a
trace and roll up cost / tokens / quality / latency — like ``TokenLedger`` does
for the timing log, but hierarchical.

Correlation is propagated via ``contextvars`` (``start_trace`` sets them; an
LLM call inside reads them). Writing is best-effort (see ``span_writer``); the
``TraceStore`` only reads, so any process can consult it.
"""

from __future__ import annotations

import contextlib
import contextvars
import time
import uuid
from dataclasses import asdict, dataclass, fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

from core.observability.span_writer import spans_log_path, write_span

# Kinds of span (forward-compatible with later cycles: tool_call/reflexion_iter/verify/eval).
SPAN_KINDS = (
    "orchestration",
    "agent_run",
    "llm_call",
    "tool_call",
    "reflexion_iter",
    "verify",
    "eval",
)

_CURRENT_TRACE: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "pantheon_trace_id", default=None
)
_CURRENT_SPAN: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "pantheon_span_id", default=None
)


def new_id(prefix: str) -> str:
    return f"{prefix}:{uuid.uuid4().hex[:12]}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def current_trace_id() -> Optional[str]:
    return _CURRENT_TRACE.get()


def current_span_id() -> Optional[str]:
    return _CURRENT_SPAN.get()


@dataclass
class Span:
    span_id: str
    trace_id: str
    kind: str
    name: str
    parent_span_id: Optional[str] = None
    task_type: Optional[str] = None
    agent_id: Optional[str] = None
    pattern: Optional[str] = None
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    elapsed_ms: Optional[int] = None
    status: str = "ok"
    model: Optional[str] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    cache_read_tokens: Optional[int] = None
    total_cost_usd: Optional[float] = None
    quality_score: Optional[float] = None
    tool_name: Optional[str] = None

    def to_dict(self) -> dict:
        # Drop None fields so records stay compact and forward-compatible.
        return {k: v for k, v in asdict(self).items() if v is not None}

    @classmethod
    def from_dict(cls, data: dict) -> "Span":
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})


class _TraceHandle:
    """Yielded by :func:`start_trace`; lets the caller attach a quality score."""

    def __init__(self) -> None:
        self.quality_score: Optional[float] = None

    def set_quality(self, score: Optional[float]) -> None:
        self.quality_score = score


@contextlib.contextmanager
def start_trace(
    name: str,
    *,
    kind: str = "orchestration",
    task_type: Optional[str] = None,
    pattern: Optional[str] = None,
    agent_id: Optional[str] = None,
) -> Iterator[_TraceHandle]:
    """Open a trace root span. Sets the trace/span contextvars for the body.

    Nesting is supported: if a trace is already active, this opens a child span
    under the same ``trace_id``. Works around ``await`` (contextvars propagate).
    """
    trace_id = current_trace_id() or new_id("tr")
    parent = current_span_id()
    span_id = new_id("sp")
    t_tok = _CURRENT_TRACE.set(trace_id)
    s_tok = _CURRENT_SPAN.set(span_id)
    started = time.monotonic()
    started_at = _now_iso()
    status = "ok"
    handle = _TraceHandle()
    try:
        yield handle
    except BaseException:
        status = "error"
        raise
    finally:
        try:
            span = Span(
                span_id=span_id,
                trace_id=trace_id,
                parent_span_id=parent,
                kind=kind,
                name=name,
                task_type=task_type,
                pattern=pattern,
                agent_id=agent_id,
                started_at=started_at,
                ended_at=_now_iso(),
                elapsed_ms=int((time.monotonic() - started) * 1000),
                status=status,
                quality_score=handle.quality_score,
            )
            write_span(span.to_dict())
        except Exception:  # observability must never break the wrapped work
            pass
        finally:
            _CURRENT_SPAN.reset(s_tok)
            _CURRENT_TRACE.reset(t_tok)


def record_llm_call(
    *,
    name: str,
    model: Optional[str],
    elapsed_ms: int,
    task_type: Optional[str] = None,
    status: str = "ok",
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    cache_read_tokens: Optional[int] = None,
    total_cost_usd: Optional[float] = None,
) -> None:
    """Emit a point-in-time ``llm_call`` span under the current trace.

    If no trace is active, the call starts its own singleton trace so every LLM
    call is always attributable. Best-effort; never raises.
    """
    try:
        trace_id = current_trace_id() or new_id("tr")
        span = Span(
            span_id=new_id("sp"),
            trace_id=trace_id,
            parent_span_id=current_span_id(),
            kind="llm_call",
            name=name,
            task_type=task_type,
            started_at=_now_iso(),
            ended_at=_now_iso(),
            elapsed_ms=elapsed_ms,
            status=status,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read_tokens,
            total_cost_usd=total_cost_usd,
        )
        write_span(span.to_dict())
    except Exception:  # pragma: no cover - must not break generation
        pass


# --------------------------------------------------------------------------- #
# Read-only aggregation                                                         #
# --------------------------------------------------------------------------- #


@dataclass
class TraceSummary:
    trace_id: str
    name: str
    task_type: Optional[str]
    pattern: Optional[str]
    started_at: Optional[str]
    span_count: int
    elapsed_ms: Optional[int]
    status: str
    total_cost_usd: float
    input_tokens: int
    output_tokens: int
    quality_score: Optional[float]

    def to_dict(self) -> dict:
        return asdict(self)


class TraceStore:
    """Read-only aggregation over ``spans.jsonl`` (never writes)."""

    def __init__(self, platform_home: Optional[Path] = None) -> None:
        self._explicit_home = Path(platform_home) if platform_home else None

    @property
    def log_path(self) -> Optional[Path]:
        return spans_log_path(self._explicit_home)

    def _iter_spans(self) -> Iterator[Span]:
        path = self.log_path
        if not path:
            return
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return
        import json

        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if isinstance(rec, dict) and rec.get("trace_id") and rec.get("span_id"):
                yield Span.from_dict(rec)

    def get_trace(self, trace_id: str) -> list[Span]:
        """All spans for one trace, in file order."""
        return [s for s in self._iter_spans() if s.trace_id == trace_id]

    def _summarize(self, trace_id: str, spans: list[Span]) -> TraceSummary:
        # Root = the span with no parent (or, failing that, the earliest).
        root = next((s for s in spans if s.parent_span_id is None), spans[0])
        cost = sum(s.total_cost_usd or 0.0 for s in spans)
        in_tok = sum(s.input_tokens or 0 for s in spans)
        out_tok = sum(s.output_tokens or 0 for s in spans)
        qualities = [s.quality_score for s in spans if s.quality_score is not None]
        status = "error" if any(s.status == "error" for s in spans) else root.status
        return TraceSummary(
            trace_id=trace_id,
            name=root.name,
            task_type=root.task_type,
            pattern=root.pattern,
            started_at=root.started_at,
            span_count=len(spans),
            elapsed_ms=root.elapsed_ms,
            status=status,
            total_cost_usd=round(cost, 6),
            input_tokens=in_tok,
            output_tokens=out_tok,
            quality_score=(max(qualities) if qualities else None),
        )

    def recent_traces(self, limit: int = 20) -> list[TraceSummary]:
        """Most-recent traces first (by first-seen order in the log)."""
        order: list[str] = []
        grouped: dict[str, list[Span]] = {}
        for span in self._iter_spans():
            if span.trace_id not in grouped:
                grouped[span.trace_id] = []
                order.append(span.trace_id)
            grouped[span.trace_id].append(span)
        summaries = [self._summarize(tid, grouped[tid]) for tid in order]
        # Newest first by trace start time. Robust to interleaved/concurrent writes:
        # a root span is written at trace END, so raw file order isn't start order.
        summaries.sort(key=lambda s: s.started_at or "", reverse=True)
        return summaries[: max(0, limit)]

    def summary(self, *, limit: int = 20) -> dict:
        """Roll-up for the observability dashboard / CLI."""
        traces = self.recent_traces(limit=limit)
        total_cost = round(sum(t.total_cost_usd for t in traces), 6)
        scored = [t.quality_score for t in traces if t.quality_score is not None]
        return {
            "trace_count": len(traces),
            "total_cost_usd": total_cost,
            "avg_quality": (round(sum(scored) / len(scored), 2) if scored else None),
            "error_traces": sum(1 for t in traces if t.status == "error"),
            "traces": [t.to_dict() for t in traces],
        }
