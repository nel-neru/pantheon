"""収益データ整合性 — 「偽データ/疑似モックで収益化を虚偽しない」原則の実装（拡張）。

恒久原則（NON-NEGOTIABLE）:
- **確定収益（confirmed revenue）= OutcomeStore に記録された実イベント由来の金額のみ**を「利益/収益」として扱う。
- 予測（forecast）・到達見通し（projection）・ゴール状況（goal-status）等は **概算（estimate）**であり、
  確定収益として提示しない。API/GUI/CLI では必ず ``estimate=True`` と免責文を併記する。
- 収益コレクタは **偽の数値を生成しない**（未接続ソースは空を返す。実収益は CSV 取り込み/手動入力のみ）。
  ``revenue_collectors`` のアダプタはこの規約に従う（スタブは ``[]`` を返す）。

このモジュールは「確定収益」と「概算」を機械的に区別する単一ソース。GUI は本モジュールの
``assess_revenue_integrity`` で確定収益バッジを描画し、確定データが無いときは警告を出す。
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, TypedDict

from core.metrics.outcomes import REVENUE_METRICS

# 概算（予測・射影）に必ず併記する免責文。これらは確定収益ではない。
ESTIMATE_DISCLAIMER = "予測（概算）です。確定収益（記録済み実データ）ではありません。"
# 確定収益データが無いときの警告（予測を実利益と誤認させない）。
NO_CONFIRMED_REVENUE_WARNING = "確定収益データがありません。表示中の予測・見通しは参考値であり、実利益として扱わないでください。"


class RevenueIntegrity(TypedDict):
    confirmed_revenue: float  # 記録済み実イベント由来の収益のみ
    recorded_event_count: int  # 収益イベント件数（確定データの母数）
    has_confirmed_data: bool  # 確定収益イベントが 1 件でもあるか
    confirmed_sources: List[str]  # 確定収益のあるチャネル（"(unknown)" は手動/出所不明）
    warning: str  # 確定データ無し時の警告（あれば）


def assess_revenue_integrity(
    store: Any, org_names: Optional[Iterable[str]] = None
) -> RevenueIntegrity:
    """確定収益（記録済み実イベントのみ）を集計し、データ整合性の状態を返す。

    ``store`` は OutcomeStore。``org_names`` 省略=全 org / 単一名 / 集合（Business ロールアップ）。
    予測・射影は **一切含めない**（確定収益のみ）。確定データが無ければ ``warning`` を付す。
    """
    names: Optional[set] = None
    if org_names is not None:
        names = {str(org_names)} if isinstance(org_names, str) else {str(n) for n in org_names}

    confirmed = 0.0
    count = 0
    sources: Dict[str, float] = {}
    for event in store._load():  # noqa: SLF001 — 同パッケージ内の確定イベント読み出し
        if event.metric not in REVENUE_METRICS:
            continue
        if names is not None and event.org_name not in names:
            continue
        confirmed += event.value
        count += 1
        src = event.source or "(unknown)"
        sources[src] = sources.get(src, 0.0) + event.value

    has_data = count > 0
    return RevenueIntegrity(
        confirmed_revenue=round(confirmed, 2),
        recorded_event_count=count,
        has_confirmed_data=has_data,
        confirmed_sources=sorted(sources, key=lambda s: sources[s], reverse=True),
        warning="" if has_data else NO_CONFIRMED_REVENUE_WARNING,
    )
