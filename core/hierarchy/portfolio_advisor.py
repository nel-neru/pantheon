"""
PortfolioAdvisor — 既存の収益コア純粋関数を「HQ が出せる提案ペイロード」に束ねる純粋関数
（WIRE-A: 収益コアの提案化 / HQ から見たポートフォリオ意思決定の入口）。

設計思想:
- 資源配分（``core.metrics.portfolio.recommend_allocation``）と連携推奨
  （``core.hierarchy.handoff_optimizer.recommend_handoffs``）という 2 つの既存純粋コアを
  呼び出し、それぞれの結果を HQ が提示できる「提案 dict」に変換して束ねるだけ。
- 永続化・LLM 呼び出し・外部 API には一切依存しない。同じ入力からは常に同じ出力を
  返す（決定論・冪等）。入力辞書は破壊しない。
“提案ペイロード” は UI / 承認ゲート / 上位オーケストレータがそのまま表示・ランク付け
できるよう、``priority``（整数）と ``kind``・``title`` を付したフラットな dict に揃える。
"""

from __future__ import annotations

from typing import Any, Dict, List

from core.hierarchy.handoff_optimizer import recommend_handoffs
from core.metrics.portfolio import recommend_allocation

# 配分 action → 提案 priority の写像。値が大きいほど先頭に並ぶ（降順）。
# invest（伸ばす）3 → monetize（収益化）2 → optimize（最適化）1 → grow_audience（読者獲得）0。
_ALLOCATION_PRIORITY: Dict[str, int] = {
    "invest": 3,
    "monetize": 2,
    "optimize": 1,
    "grow_audience": 0,
}


def build_portfolio_proposals(
    org_stats: List[Dict[str, Any]],
    *,
    source_org_name: str = "HQ",
) -> List[Dict[str, Any]]:
    """収益コアの 2 関数を束ねて「HQ 提案」の dict リストを返す（純粋・決定論・冪等）。

    Args:
        org_stats: 各 org の統計 dict のリスト。``recommend_allocation`` /
            ``recommend_handoffs`` が受け付ける形式（``org_name``・``revenue``・
            ``reach``・``posts``・任意の ``role``）をそのまま渡す。
        source_org_name: 提案を出す主体（HQ）名。各提案に ``source_org_name`` として付与される。

    生成される提案:
        配分提案 (kind="portfolio_allocation"):
            ``{kind, title, action, org_name, reason, priority, source_org_name}``。
            ``title`` = ``f"[HQ提案] {org_name} を {action}"``、
            ``priority`` = invest/monetize/optimize/grow_audience → 3/2/1/0。
        連携提案 (kind="handoff"):
            ``{kind, title, from_org, to_org, reason, priority, source_org_name}``。
            ``title`` = ``f"[HQ提案] {from_org}→{to_org} へ送客"``、
            ``priority`` = handoff_optimizer の priority（reach 相当）を int に丸めた値。

    Returns:
        全提案を ``priority`` 降順で並べた dict リスト。同 priority は
        ``kind`` 昇順 → ``title`` 昇順の安定タイブレークで決定論的に並べる。
        入力が空なら ``[]``。入力辞書は破壊しない。
    """
    if not org_stats:
        return []

    proposals: List[Dict[str, Any]] = []

    # 1) 資源配分提案: recommend_allocation の各結果を 提案 dict へ写像する。
    for allocation in recommend_allocation(org_stats):
        org_name = str(allocation.get("org_name", ""))
        action = str(allocation.get("action", ""))
        proposals.append(
            {
                "kind": "portfolio_allocation",
                "title": f"[HQ提案] {org_name} を {action}",
                "action": action,
                "org_name": org_name,
                "reason": str(allocation.get("reason", "")),
                # 未知の action でも落ちないよう 0 にフォールバックする。
                "priority": _ALLOCATION_PRIORITY.get(action, 0),
                "source_org_name": source_org_name,
            }
        )

    # 2) 連携（送客）提案: recommend_handoffs の各結果を 提案 dict へ写像する。
    for handoff in recommend_handoffs(org_stats):
        from_org = str(handoff.get("from_org", ""))
        to_org = str(handoff.get("to_org", ""))
        proposals.append(
            {
                "kind": "handoff",
                "title": f"[HQ提案] {from_org}→{to_org} へ送客",
                "from_org": from_org,
                "to_org": to_org,
                "reason": str(handoff.get("reason", "")),
                # handoff の priority は reach 相当の float。提案は int で揃える。
                "priority": _to_int(handoff.get("priority")),
                "source_org_name": source_org_name,
            }
        )

    # priority 降順。同 priority は kind 昇順 → title 昇順で決定論的に安定化する。
    proposals.sort(key=lambda p: (-p["priority"], p["kind"], p["title"]))
    return proposals


def _to_int(value: Any) -> int:
    """priority を int に丸める（None・非数値は 0）。float は切り捨て。"""
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0
