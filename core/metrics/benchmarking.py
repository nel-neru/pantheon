"""Organization ベンチマーキング（拡張: コホート内のパーセンタイル順位と外れ値検出）。

各 org の revenue / reach / ROI をポートフォリオ（コホート）内で相対評価し、percentile 順位と
外れ値フラグ（top_performer / underperformer）を付ける純粋関数群。統合コマンドセンターの
「組織健康度パネル」の土台。決定論・LLM 非依存・読み取り専用。
"""

from __future__ import annotations

from typing import Any, Dict, List


def percentile_rank(value: float, population: List[float]) -> float:
    """``value`` がコホート ``population`` の下位何 % に位置するか（0..100, 高いほど上位）。

    「自分以下の割合」= count(v <= value) / n × 100。空コホートは 0.0。
    """
    if not population:
        return 0.0
    le = sum(1 for v in population if v <= value)
    return round(le / len(population) * 100, 1)


def _roi(revenue: float, reach: float) -> float:
    return round(revenue / max(reach, 1.0), 4)  # ゼロ除算を構造的に回避（portfolio と同規約）


def build_benchmark_snapshot(org_stats: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """org ごとに revenue/reach/roi の percentile 順位と外れ値フラグを付けて返す（純粋）。

    引数: 各要素 ``{"org_name", "revenue", "reach", ...}``（欠損は 0 扱い）。
    返り値: revenue 降順で ``{org_name, revenue, reach, roi, revenue_percentile, roi_percentile, flag}``。
    flag: revenue_percentile>=90→"top_performer" / revenue>0 かつ roi_percentile<=25→"underperformer" / 他 ""。
    入力が空なら ``[]``。元 dict は破壊しない。
    """
    if not org_stats:
        return []
    rows = []
    for s in org_stats:
        revenue = float(s.get("revenue", 0) or 0)
        reach = float(s.get("reach", 0) or 0)
        rows.append(
            {
                "org_name": str(s.get("org_name", "")),
                "revenue": revenue,
                "reach": reach,
                "roi": _roi(revenue, reach),
            }
        )
    revenues = [r["revenue"] for r in rows]
    rois = [r["roi"] for r in rows]
    # 「収益はあるが最も非効率（最低 ROI）」を underperformer とする（小コホートでも安定して
    # 1 社を特定できるよう percentile 閾値でなく earner 内の最小 ROI で判定）。
    earner_rois = [r["roi"] for r in rows if r["revenue"] > 0]
    worst_earner_roi = min(earner_rois) if len(earner_rois) >= 2 else None
    for r in rows:
        rev_pct = percentile_rank(r["revenue"], revenues)
        r["revenue_percentile"] = rev_pct
        r["roi_percentile"] = percentile_rank(r["roi"], rois)
        if rev_pct >= 90:
            r["flag"] = "top_performer"
        elif r["revenue"] > 0 and worst_earner_roi is not None and r["roi"] <= worst_earner_roi:
            r["flag"] = "underperformer"
        else:
            r["flag"] = ""
    rows.sort(key=lambda r: r["revenue"], reverse=True)
    return rows
