"""REV-COLLECT: 外部プラットフォームからの収益自動収集フレームワーク（計画 §8 P1 / §9）。

note / X / ASP 等の売上を定期取得し :class:`~core.metrics.outcomes.OutcomeStore` へ流し込む
ための **アダプタ枠組み** を提供する。本パッケージは枠組みと安全なオーケストレータまでを担い、
各プラットフォームの **実 API 認証・取得は human-gate**（資格情報の接続は人間が行う）。

- 資格情報が未接続のアダプタは ``is_configured() == False`` となり、収集をスキップして
  「接続してください」という人間タスクを **一度だけ**（dedupe）承認キューへ積む。
- 接続済みアダプタの取得結果は ``OutcomeStore.record(..., dedupe_on_source=True)`` で
  二重計上を防いで記録する。

実 API 実装が入るまでの間も、手動入力（``POST /api/outcomes``）/CSV 取り込みが収益記録の
fallback として機能する（このフレームワークはそれを置き換えず、自動化経路を足す）。
"""

from __future__ import annotations

from core.metrics.revenue_collectors.base import CollectedRevenue, RevenueCollector
from core.metrics.revenue_collectors.runner import (
    DEFAULT_COLLECTORS,
    run_revenue_collection,
)

__all__ = [
    "CollectedRevenue",
    "RevenueCollector",
    "DEFAULT_COLLECTORS",
    "run_revenue_collection",
]
