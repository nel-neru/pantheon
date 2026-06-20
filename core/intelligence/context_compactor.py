"""ContextCompactor — summarise oversized context before it reaches ``claude``.

Long, redundant context both wastes tokens and raises hallucination risk
(the "lost in the middle" effect). When a context exceeds its task's budget
(:class:`~core.intelligence.token_budget_manager.TokenBudget.max_context_tokens`),
this compactor replaces it with a light-tier ``claude`` summary that preserves
the load-bearing facts. Falls back to the existing char-count truncation
(``TokenBudgetManager.fit_context``) when ``claude`` is unavailable
(``PANTHEON_NO_CLAUDE`` / offline), so behaviour degrades gracefully.

Summaries are cached on a content hash under
``~/.pantheon/compaction_cache/`` so the same context is never re-summarised
(re-compaction would itself spend tokens — the opposite of the goal).
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Optional

from core.intelligence.token_budget_manager import (
    TokenBudgetManager,
    get_token_budget_manager,
)

logger = logging.getLogger(__name__)

CACHE_DIRNAME = "compaction_cache"

_COMPACT_SYSTEM = (
    "あなたは文脈圧縮の専門家です。与えられたコンテキストを、後続タスクが必要とする"
    "事実・制約・固有名詞・数値・依存関係を一切失わずに、簡潔な日本語に要約してください。"
    "意見や冗長な説明は削り、箇条書きを活用し、元の意味を変えないこと。"
)


def _cache_dir(platform_home: Optional[Path]) -> Path:
    if platform_home is None:
        from core.platform.state import get_platform_home

        platform_home = get_platform_home()
    return Path(platform_home) / CACHE_DIRNAME


class ContextCompactor:
    def __init__(
        self,
        budget_manager: Optional[TokenBudgetManager] = None,
        *,
        platform_home: Optional[Path] = None,
    ):
        self._budgets = budget_manager or get_token_budget_manager()
        self._platform_home = platform_home

    def _cache_path(self, task_type: str, context: str, target_chars: int) -> Path:
        key = hashlib.sha256(f"{task_type}:{target_chars}:{context}".encode("utf-8")).hexdigest()
        return _cache_dir(self._platform_home) / f"{key}.txt"

    async def compact(self, context: str, task_type: str = "default") -> str:
        """Return ``context`` unchanged if within budget, else a compacted form.

        Never raises: any failure falls back to char-count truncation so a
        compaction problem can never break the downstream generation.
        """
        if not context:
            return context
        budget = self._budgets.get_budget(task_type)
        max_chars = budget.max_context_tokens * 4
        if len(context) <= max_chars:
            return context

        cache_path = self._cache_path(task_type, context, max_chars)
        try:
            cached = cache_path.read_text(encoding="utf-8")
            if cached:
                return cached
        except OSError:
            pass

        compacted = await self._summarise(context, max_chars)
        if compacted is None:
            # claude 不在/失敗 → 既存の決定論トリミングにフォールバック
            return self._budgets.fit_context(context, task_type)

        try:
            from core.persistence import atomic_write_text

            # 原子的に書く（圧縮キャッシュの torn write で毎回再圧縮しトークンを浪費しないため）。
            atomic_write_text(cache_path, compacted)
        except OSError as exc:  # pragma: no cover - キャッシュ失敗は致命でない
            logger.debug("failed to cache compaction: %s", exc)
        return compacted

    async def _summarise(self, context: str, max_chars: int) -> Optional[str]:
        from core.runtime.claude_code import claude_available

        if not claude_available():
            return None
        try:
            from core.llm import LLMMessage, get_llm_provider

            provider = get_llm_provider()
            target_chars = max(200, max_chars - 200)  # 出力が予算を超えないよう少し余裕
            user = (
                f"以下のコンテキストを {target_chars} 文字以内に圧縮要約してください。\n\n{context}"
            )
            response = await provider.generate(
                messages=[
                    LLMMessage(role="system", content=_COMPACT_SYSTEM),
                    LLMMessage(role="user", content=user),
                ],
                temperature=0.2,
                max_tokens=2000,
                task_type="compaction",  # ModelTierRouter で light ティア
            )
            body = (getattr(response, "content", "") or "").strip()
            return body or None
        except Exception as exc:  # noqa: BLE001
            logger.debug("compaction via claude failed (%s) — will truncate", exc)
            return None
