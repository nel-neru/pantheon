"""
Portfolio Allocation — 複数 Organization の収益/リーチから資源配分方針を提案する
（P1.5: ポートフォリオ資源配分 / 経済フィードバックの上位レイヤー）。

OutcomeStore 等が集計した各 org の {revenue, reach, posts} を受け取り、
投資効率 (ROI = revenue / reach) を基準に「どの org を伸ばし/収益化し/最適化し/
オーディエンスを育てるか」を決定論的に振り分ける純粋関数を提供する。

LLM 呼び出しには依存しない。同じ入力からは常に同じ出力を返す（決定論・冪等）。
"""

from __future__ import annotations

import statistics
from typing import Any, Dict, List

# action の優先度（小さいほど先頭に並べる）。
# invest（伸ばす）→ monetize（収益化）→ optimize（最適化）→ grow_audience（読者獲得）。
_ACTION_PRIORITY: Dict[str, int] = {
    "invest": 0,
    "monetize": 1,
    "optimize": 2,
    "grow_audience": 3,
}

_ACTION_REASON: Dict[str, str] = {
    "invest": "収益があり ROI が全体中央値以上。資源を投下して伸ばす",
    "monetize": "リーチはあるが収益化できていない。収益化施策が必要",
    "optimize": "収益はあるが ROI が下位。効率を最適化する",
    "grow_audience": "収益もリーチもない。まずオーディエンスを育てる",
}


def recommend_allocation(org_stats: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """各 org の収益/リーチから資源配分アクションを提案する（純粋関数）。

    引数:
        org_stats: 各要素が ``{"org_name": str, "revenue": float, "reach": float,
            "posts": float}`` の辞書リスト。欠損キーは 0 として頑健に扱う。

    各 org について ROI = ``revenue / max(reach, 1)`` を計算し（ゼロ除算なし）、
    次の優先順位で action を決める:

    1. ``reach > 0`` かつ ``revenue <= 0`` → ``"monetize"``
    2. ``revenue > 0`` の場合（収益が出ている org 同士の ROI 中央値で判定）:
       - ROI が中央値以上 → ``"invest"``
       - それ以外 → ``"optimize"``
    3. それ以外（``reach <= 0`` かつ ``revenue <= 0``）→ ``"grow_audience"``

    戻り値:
        各 org に ``{"org_name", "action", "roi", "reason"}`` を付けたリスト。
        invest → monetize → optimize → grow_audience の優先度昇順、同一 action 内は
        ``revenue`` 降順で並べる。入力が空なら ``[]``。入力辞書は破壊しない。
    """
    if not org_stats:
        return []

    # 入力を頑健に正規化（欠損/型ゆれを float 0 に寄せる）。元の辞書は変更しない。
    normalized: List[Dict[str, Any]] = []
    for stat in org_stats:
        name = str(stat.get("org_name", ""))
        revenue = _as_float(stat.get("revenue"))
        reach = _as_float(stat.get("reach"))
        roi = revenue / max(reach, 1.0)  # max(...,1) でゼロ除算を構造的に回避
        normalized.append({"org_name": name, "revenue": revenue, "reach": reach, "roi": roi})

    # invest/optimize の分岐は「収益が出ている org 同士」の ROI 中央値で行う。
    # 収益0の集客org（ROI=0）を母集団に混ぜると中央値が歪み、収益orgの判定がぶれるため除外する。
    earning_rois = [item["roi"] for item in normalized if item["revenue"] > 0]
    median_roi = statistics.median(earning_rois) if earning_rois else 0.0

    results: List[Dict[str, Any]] = []
    for item in normalized:
        revenue = item["revenue"]
        reach = item["reach"]
        roi = item["roi"]
        if reach > 0 and revenue <= 0:
            action = "monetize"
        elif revenue > 0:
            action = "invest" if roi >= median_roi else "optimize"
        else:
            action = "grow_audience"
        results.append(
            {
                "org_name": item["org_name"],
                "action": action,
                "roi": round(roi, 4),
                "reason": _ACTION_REASON[action],
            }
        )

    # action 優先度昇順 → revenue 降順。安定ソートのため revenue を負値キーで併用。
    revenue_by_name = {item["org_name"]: item["revenue"] for item in normalized}
    results.sort(key=lambda r: (_ACTION_PRIORITY[r["action"]], -revenue_by_name[r["org_name"]]))
    return results


def _as_float(value: Any) -> float:
    """数値化できない値は 0.0 に寄せて集計を壊さない。"""
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
