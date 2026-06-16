"""Pantheon eval harness — score agents/skills against golden tasks.

See :mod:`core.eval.harness`. Scoring uses the LLM judge
(``AgentSelfEvaluator.evaluate_llm``) with the heuristic fallback, so the suite
runs deterministically under ``PANTHEON_NO_CLAUDE=1`` / in CI. Each eval emits an
``eval``-kind span (C1 observability) so the dashboard can show pass-rate over time.
"""

from __future__ import annotations

from core.eval.harness import EvalResult, GoldenTask, load_golden, run_suite

__all__ = ["EvalResult", "GoldenTask", "load_golden", "run_suite"]
