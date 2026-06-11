"""Trend scoring — rank trends by freshness × relevance × genre-fit.

Uses the local ``claude`` CLI (light tier, ``task_type="scoring"``) when
available; falls back to a deterministic heuristic offline so collection never
depends on generation being available.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import List, Optional

from core.trends.models import TrendItem

logger = logging.getLogger(__name__)

_SCORE_SYSTEM = (
    "あなたはトレンド分析の専門家です。与えられた記事/動画のタイトルと要約を読み、"
    "ビジネス活用・コンテンツ化の価値を 0.0〜10.0 で採点してください。新規性・具体性・"
    "需要の大きさを重視します。出力は数値のみ（例: 7.5）。説明は不要です。"
)


def _heuristic_score(item: TrendItem, *, now: Optional[datetime] = None) -> float:
    """claude 不在時の決定論スコア（鮮度＋情報量＋ジャンル一致）。"""
    score = 5.0
    # 鮮度: collected_at が新しいほど加点（最大 +2）
    now = now or datetime.now(timezone.utc)
    try:
        collected = datetime.fromisoformat(item.collected_at)
        if collected.tzinfo is None:
            collected = collected.replace(tzinfo=timezone.utc)
        age_hours = max(0.0, (now - collected).total_seconds() / 3600)
        score += max(0.0, 2.0 - age_hours / 24)  # 24h で +1 減衰
    except ValueError:
        pass
    # 情報量: 要約が充実しているほど加点（最大 +1.5）
    score += min(1.5, len(item.summary) / 400)
    # ジャンル明示で +0.5、トピック数で最大 +1
    if item.genre:
        score += 0.5
    score += min(1.0, len(item.topics) * 0.25)
    return round(min(10.0, score), 2)


async def score_trend(item: TrendItem, *, now: Optional[datetime] = None) -> float:
    """1 件のトレンドを採点する（claude light ティア優先、失敗時はヒューリスティック）。"""
    from core.runtime.claude_code import claude_available

    if claude_available():
        try:
            from core.llm import LLMMessage, get_llm_provider

            provider = get_llm_provider()
            user = (
                f"タイトル: {item.title}\n"
                f"要約: {item.summary or item.raw_excerpt[:500]}\n"
                f"ジャンル: {item.genre or '(未設定)'}"
            )
            response = await provider.generate(
                messages=[
                    LLMMessage(role="system", content=_SCORE_SYSTEM),
                    LLMMessage(role="user", content=user),
                ],
                temperature=0.0,
                max_tokens=20,
                task_type="scoring",
            )
            text = (getattr(response, "content", "") or "").strip()
            m = re.search(r"\d+(?:\.\d+)?", text)
            if m:
                return round(min(10.0, max(0.0, float(m.group()))), 2)
        except Exception as exc:  # noqa: BLE001
            logger.debug("claude scoring failed (%s) — heuristic", exc)
    return _heuristic_score(item, now=now)


async def score_all(items: List[TrendItem], *, now: Optional[datetime] = None) -> List[TrendItem]:
    """各 item に score を設定して返す（in-place 更新）。"""
    for item in items:
        item.score = await score_trend(item, now=now)
    return items
