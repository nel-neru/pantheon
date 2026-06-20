"""承認インボックスの労力加重 ROI ランキング（拡張: 高収益・低労力を上位へ）。

各インボックス項目に「概算労力（時間）」と「ROIスコア（= 収益インパクト×優先度 / 労力）」を付け、
「すぐ片付いて収益に効く」項目を上位に並べる決定論ヘルパ。LLM 非依存・読み取り専用（actuate しない）。
HQ/オペレーターのトリアージを「優先度が高いだけで低収益」より「高収益・低労力」へ寄せる。
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List

_PRIORITY_WEIGHT: Dict[str, int] = {"high": 3, "medium": 2, "low": 1}

# 種別 → 概算労力（時間）。小さいほど「すぐ片付く」。
_KIND_EFFORT: Dict[str, float] = {
    "publish": 0.5,
    "human_task": 1.0,
    "handoff": 1.0,
    "proposal": 2.0,
}

# カテゴリ → 概算労力（時間）。カテゴリ指定が優先（種別より具体的）。
_CATEGORY_EFFORT: Dict[str, float] = {
    "external_action": 0.5,
    "content_asset": 1.0,
    "cross_org_handoff": 1.0,
    "performance": 3.0,
    "structural_intervention": 4.0,
    "new_business": 8.0,
}

_MIN_EFFORT = 0.5


def estimate_effort_hours(item: Dict[str, Any]) -> float:
    """インボックス項目の概算労力（時間）を返す（カテゴリ優先・既定 2.0・下限 0.5）。"""
    category = str(item.get("category") or "").lower()
    if category in _CATEGORY_EFFORT:
        base = _CATEGORY_EFFORT[category]
    else:
        base = _KIND_EFFORT.get(str(item.get("kind") or ""), 2.0)
    return round(max(_MIN_EFFORT, base), 2)


def compute_roi_score(revenue_impact: Any, priority: Any, effort_hours: float) -> float:
    """ROIスコア = (収益インパクト×10 + 優先度重み) / 労力。高いほど「効いて速い」。"""
    try:
        impact = int(revenue_impact or 0)
    except (TypeError, ValueError):
        impact = 0
    weight = _PRIORITY_WEIGHT.get(str(priority or "medium").lower(), 2)
    yield_value = impact * 10 + weight
    return round(yield_value / max(_MIN_EFFORT, float(effort_hours or _MIN_EFFORT)), 2)


def annotate_inbox_item(item: Dict[str, Any]) -> Dict[str, Any]:
    """項目に effort_hours / roi_score を付与して返す（破壊的: 同 dict を更新）。"""
    effort = estimate_effort_hours(item)
    item["effort_hours"] = effort
    item["roi_score"] = compute_roi_score(
        item.get("revenue_impact", 0), item.get("priority", "medium"), effort
    )
    return item


_SORT_KEYS: Dict[str, Callable[[Dict[str, Any]], Any]] = {
    "roi": lambda i: i.get("roi_score", 0.0),
    "revenue": lambda i: (
        i.get("revenue_impact", 0),
        _PRIORITY_WEIGHT.get(str(i.get("priority", "medium")).lower(), 2),
    ),
    "urgency": lambda i: _PRIORITY_WEIGHT.get(str(i.get("priority", "medium")).lower(), 2),
}


def sort_inbox(items: List[Dict[str, Any]], sort: str = "roi") -> List[Dict[str, Any]]:
    """インボックス項目を指定キーで並べ替える（roi/revenue/urgency=降順, effort=低労力先）。"""
    if sort == "effort":
        return sorted(items, key=lambda i: i.get("effort_hours", 999.0))
    key = _SORT_KEYS.get(sort, _SORT_KEYS["roi"])
    return sorted(items, key=key, reverse=True)
