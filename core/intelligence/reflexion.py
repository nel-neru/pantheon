"""Reflexion — a bounded generate → critique → refine loop (opt-in quality mechanism).

Replaces single-shot output with self-critique: score the output via the LLM judge
(:meth:`AgentSelfEvaluator.evaluate_llm`), and if it falls short, ask the agent to
refine it using the critique, up to ``max_iters`` times. The judge falls back to the
heuristic evaluator offline, so ``PANTHEON_NO_CLAUDE=1`` runs are deterministic.

Cost is bounded by construction: ``max_iters`` (default 2), early-exit once the judge
stops asking for a retry, and an optional per-trace cost ceiling read from the C1 span
store (a best-effort soft ceiling, re-checked after each refine before the judge runs) —
so enabling reflexion stays bounded.
"""

from __future__ import annotations

import logging
from typing import Callable, Optional, Tuple

from core.intelligence.self_evaluator import AgentSelfEvaluator, EvaluationResult

logger = logging.getLogger(__name__)

# (previous_output, critique_feedback) -> refined_output
RefineFn = Callable[[str, str], str]


class ReflexionLoop:
    def __init__(
        self,
        llm=None,
        *,
        max_iters: int = 2,
        evaluator: Optional[AgentSelfEvaluator] = None,
        cost_ceiling_usd: Optional[float] = None,
    ) -> None:
        self._llm = llm
        self.max_iters = max(0, int(max_iters))
        self._evaluator = evaluator or AgentSelfEvaluator()
        self.cost_ceiling_usd = cost_ceiling_usd

    def _evaluate(self, output: str, task_type: str) -> EvaluationResult:
        return self._evaluator.evaluate_llm(output, task_type, llm=self._llm)

    def _over_budget(self) -> bool:
        """True when the active trace's accumulated cost has hit the ceiling (best-effort)."""
        if not self.cost_ceiling_usd:
            return False
        try:
            from core.observability.span import TraceStore, current_trace_id

            tid = current_trace_id()
            if not tid:
                return False
            spans = TraceStore().get_trace(tid)
            cost = sum(s.total_cost_usd or 0.0 for s in spans)
            return cost >= self.cost_ceiling_usd
        except Exception:
            return False

    def run(
        self,
        *,
        initial_output: str,
        task_type: str,
        refine_fn: RefineFn,
    ) -> Tuple[str, EvaluationResult, int]:
        """Critique ``initial_output`` and refine it up to ``max_iters`` times.

        Returns ``(best_output, best_evaluation, iterations_run)``. Keeps the
        highest-scoring candidate seen (never returns a worse refinement).
        """
        best = initial_output
        best_eval = self._evaluate(best, task_type)
        iters = 0
        while iters < self.max_iters and best_eval.should_retry:
            if self._over_budget():
                logger.debug("reflexion: cost ceiling reached; stopping at iter %d", iters)
                break
            try:
                candidate = refine_fn(best, best_eval.feedback)
            except Exception as exc:  # a failed refine must not lose the best-so-far
                logger.debug("reflexion: refine_fn failed (%s); keeping best-so-far", exc)
                break
            iters += 1
            if self._over_budget():
                # refine already spent budget; skip the judge call and keep best-so-far
                logger.debug("reflexion: cost ceiling reached after refine; skipping judge")
                break
            cand_eval = self._evaluate(candidate, task_type)
            if cand_eval.score > best_eval.score:
                best, best_eval = candidate, cand_eval
            if not best_eval.should_retry:
                break
        return best, best_eval, iters
