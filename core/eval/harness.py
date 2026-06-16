"""Eval harness: run golden tasks, score them, emit eval spans, roll up pass-rate.

Golden tasks live in ``core/eval/golden/*.yaml`` (fields: ``id``, ``task_type``,
``prompt``, optional ``rubric`` / ``expected_contains`` / ``suite``). The harness is
dependency-injectable — ``runner(task) -> output_text`` and the evaluator are both
overridable — so it is unit-tested with fakes and runs deterministically offline
(``PANTHEON_NO_CLAUDE=1`` -> heuristic scoring, no model needed).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from core.intelligence.self_evaluator import AgentSelfEvaluator

logger = logging.getLogger(__name__)

GOLDEN_DIR = Path(__file__).resolve().parent / "golden"
DEFAULT_PASS_THRESHOLD = 6.0


@dataclass
class GoldenTask:
    id: str
    task_type: str
    prompt: str
    rubric: str = ""
    expected_contains: list[str] = field(default_factory=list)
    suite: str = "default"


@dataclass
class EvalResult:
    id: str
    task_type: str
    score: float
    passed: bool
    feedback: str
    contains_ok: bool

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "task_type": self.task_type,
            "score": self.score,
            "passed": self.passed,
            "feedback": self.feedback,
            "contains_ok": self.contains_ok,
        }


def load_golden(
    suite: Optional[str] = None, *, golden_dir: Optional[Path] = None
) -> list[GoldenTask]:
    """Load golden tasks from YAML, optionally filtered to one ``suite``."""
    import yaml

    directory = Path(golden_dir) if golden_dir else GOLDEN_DIR
    tasks: list[GoldenTask] = []
    if not directory.exists():
        return tasks
    for path in sorted(directory.glob("*.yaml")):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception as exc:  # a malformed golden file must not kill the suite
            logger.debug("skipping golden %s: %s", path.name, exc)
            continue
        if not isinstance(data, dict) or not data.get("id") or not data.get("task_type"):
            continue
        task = GoldenTask(
            id=str(data["id"]),
            task_type=str(data["task_type"]),
            prompt=str(data.get("prompt", "")),
            rubric=str(data.get("rubric", "")),
            expected_contains=[str(s) for s in (data.get("expected_contains") or [])],
            suite=str(data.get("suite", "default")),
        )
        if suite is None or task.suite == suite:
            tasks.append(task)
    return tasks


def _default_runner(task: GoldenTask) -> str:
    """Run a golden task through the claude provider; empty string offline."""
    try:
        from core.llm import LLMMessage
        from core.runtime.claude_code import ClaudeCodeProvider, claude_available

        if not claude_available():
            return ""
        messages = [LLMMessage(role="user", content=task.prompt)]
        return ClaudeCodeProvider().complete(messages, task_type=task.task_type)
    except Exception as exc:  # a runner failure scores as an empty output, never crashes
        logger.debug("eval runner failed for %s: %s", task.id, exc)
        return ""


def _emit_eval_span(task: GoldenTask, score: float, passed: bool) -> None:
    try:
        from core.observability.span import Span, current_trace_id, new_id
        from core.observability.span_writer import write_span

        ts = datetime.now(timezone.utc).isoformat()
        span = Span(
            span_id=new_id("sp"),
            trace_id=current_trace_id() or new_id("tr"),
            kind="eval",
            name=task.id,
            task_type=task.task_type,
            started_at=ts,
            ended_at=ts,
            status="ok" if passed else "error",
            quality_score=score,
        )
        write_span(span.to_dict())
    except Exception:  # observability is best-effort
        pass


def run_suite(
    suite: Optional[str] = None,
    *,
    runner: Optional[Callable[[GoldenTask], str]] = None,
    evaluator: Optional[AgentSelfEvaluator] = None,
    golden_dir: Optional[Path] = None,
    pass_threshold: float = DEFAULT_PASS_THRESHOLD,
    llm=None,
) -> dict:
    """Run every golden task (optionally one suite), score it, emit an eval span.

    Returns ``{suite, total, passed, pass_rate, avg_score, results: [...]}``.
    """
    tasks = load_golden(suite, golden_dir=golden_dir)
    runner = runner or _default_runner
    evaluator = evaluator or AgentSelfEvaluator()

    results: list[EvalResult] = []
    for task in tasks:
        try:
            output = runner(task) or ""
        except Exception as exc:
            logger.debug("eval runner raised for %s: %s", task.id, exc)
            output = ""
        ev = evaluator.evaluate_llm(output, task.task_type, llm=llm)
        contains_ok = all(s in output for s in task.expected_contains)
        passed = ev.score >= pass_threshold and contains_ok
        results.append(
            EvalResult(
                id=task.id,
                task_type=task.task_type,
                score=ev.score,
                passed=passed,
                feedback=ev.feedback,
                contains_ok=contains_ok,
            )
        )
        _emit_eval_span(task, ev.score, passed)

    total = len(results)
    passed_n = sum(1 for r in results if r.passed)
    avg = round(sum(r.score for r in results) / total, 2) if total else 0.0
    return {
        "suite": suite or "all",
        "total": total,
        "passed": passed_n,
        "pass_rate": round(passed_n / total, 3) if total else 0.0,
        "avg_score": avg,
        "results": [r.to_dict() for r in results],
    }
