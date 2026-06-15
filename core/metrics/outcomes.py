"""
Outcome Feedback — 収益 Organization 等の実世界成果を第一級シグナルとして記録・集計する
（Phase 8: 閉じたフライホイール / 経済フィードバック）。

子 org（やその自動化スクリプト/外部ランナー）が出力する軽量 JSON イベント
（インプレッション・クリック・コンバージョン・売上・エンゲージメント・コスト等）を
``~/.pantheon/outcomes.json`` に蓄積し、本社(HQ)が「どの組織構造/スキル/施策が成果に
結びつくか」を判断する材料にする。

JSON を正準とする（Phase 4 の方針）。外部 API 連携は持たない（イベントは外から record する）。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from uuid import uuid4


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# 代表的な成果メトリクス（自由文字列も可だが、集計時の意味付けに使う）。
REVENUE_METRICS = ("revenue", "sales", "conversions")
REACH_METRICS = ("impressions", "clicks", "engagement", "followers")


@dataclass
class OutcomeEvent:
    org_name: str
    metric: str
    value: float
    unit: str = ""
    source: str = ""
    note: str = ""
    event_id: str = ""
    occurred_at: str = ""
    recorded_at: str = ""

    def __post_init__(self):
        # 外部（子 org の自動化/外部ランナー）が書いた outcomes.json も安全に扱えるよう、
        # record() 経路だけでなくここでも value/metric を正規化する（型ヒント任せにしない）。
        self.value = float(self.value)
        self.metric = str(self.metric).strip().lower()
        if not self.event_id:
            self.event_id = f"outcome:{uuid4()}"
        if not self.recorded_at:
            self.recorded_at = _now_iso()
        if not self.occurred_at:
            self.occurred_at = self.recorded_at


@dataclass
class OutcomeSummary:
    org_name: str
    by_metric: Dict[str, Dict[str, float]] = field(default_factory=dict)
    event_count: int = 0

    @property
    def total_revenue(self) -> float:
        return sum(
            stats.get("sum", 0.0)
            for metric, stats in self.by_metric.items()
            if metric in REVENUE_METRICS
        )

    @property
    def total_reach(self) -> float:
        return sum(
            stats.get("sum", 0.0)
            for metric, stats in self.by_metric.items()
            if metric in REACH_METRICS
        )


class OutcomeStore:
    """成果イベントの永続ストア（~/.pantheon/outcomes.json）。"""

    def __init__(self, platform_home: Optional[Path] = None):
        if platform_home is None:
            from core.platform.state import get_platform_home

            platform_home = get_platform_home()
        self.platform_home = Path(platform_home)
        self.platform_home.mkdir(parents=True, exist_ok=True)
        self.outcomes_path = self.platform_home / "outcomes.json"

    def record(
        self,
        org_name: str,
        metric: str,
        value: float,
        *,
        unit: str = "",
        source: str = "",
        note: str = "",
        occurred_at: str = "",
        dedupe_on_source: bool = False,
    ) -> OutcomeEvent:
        """成果イベントを 1 件追記する。

        ``dedupe_on_source=True`` は同じ ``source`` のイベントが既にあれば追記せず
        既存を返す（冪等）。「1 回しか起きない事象」（例: 投稿の公開確認）を
        ジョブ固有の source で記録するときの二重計上ガード。
        """
        event = OutcomeEvent(
            org_name=org_name,
            metric=str(metric).strip().lower(),
            value=float(value),
            unit=unit,
            source=source,
            note=note,
            occurred_at=occurred_at,
        )
        events = self._load()
        if dedupe_on_source and source:
            for existing in events:
                if existing.source == source:
                    return existing
        events.append(event)
        self._save(events)
        return event

    def record_many(
        self, rows: Iterable[Dict[str, Any]], *, default_org: str = ""
    ) -> Tuple[List[OutcomeEvent], int]:
        """成果イベントを一括取り込みする（CSV/JSON エクスポートの自動取り込み用）。

        各 row は ``org_name``（省略時 ``default_org``）/ ``metric`` / ``value`` を必須とし、
        ``unit`` / ``source`` / ``note`` / ``occurred_at`` は任意。不正な row はスキップして
        件数を返す（全体を壊さない）。戻り値は ``(取り込んだイベント列, スキップ件数)``。
        """
        events = self._load()
        added: List[OutcomeEvent] = []
        skipped = 0
        for row in rows:
            try:
                org = str(row.get("org_name") or default_org).strip()
                metric = str(row.get("metric") or "").strip()
                if not org or not metric:
                    skipped += 1
                    continue
                event = OutcomeEvent(
                    org_name=org,
                    metric=metric.lower(),
                    value=float(row.get("value")),
                    unit=str(row.get("unit") or ""),
                    source=str(row.get("source") or "import"),
                    note=str(row.get("note") or ""),
                    occurred_at=str(row.get("occurred_at") or ""),
                )
                added.append(event)
            except (TypeError, ValueError, AttributeError):
                skipped += 1
        if added:
            events.extend(added)
            self._save(events)
        return added, skipped

    def list_events(self, org_name: Optional[str] = None) -> List[OutcomeEvent]:
        events = self._load()
        if org_name is None:
            return events
        return [e for e in events if e.org_name == org_name]

    def summary_for_org(self, org_name: str) -> OutcomeSummary:
        events = self.list_events(org_name)
        by_metric: Dict[str, Dict[str, float]] = {}
        for event in events:
            stats = by_metric.setdefault(event.metric, {"sum": 0.0, "count": 0.0, "last": 0.0})
            stats["sum"] += event.value
            stats["count"] += 1
            stats["last"] = event.value
        return OutcomeSummary(org_name=org_name, by_metric=by_metric, event_count=len(events))

    def summary_for_orgs(self, org_names: Iterable[str], *, label: str = "") -> OutcomeSummary:
        """複数 org の成果を 1 つに合算する（Business 単位のロールアップ用）。"""
        names = {str(n) for n in (org_names or [])}
        events = [e for e in self._load() if e.org_name in names]
        by_metric: Dict[str, Dict[str, float]] = {}
        for event in events:
            stats = by_metric.setdefault(event.metric, {"sum": 0.0, "count": 0.0, "last": 0.0})
            stats["sum"] += event.value
            stats["count"] += 1
            stats["last"] = event.value
        return OutcomeSummary(
            org_name=label or ",".join(sorted(names)),
            by_metric=by_metric,
            event_count=len(events),
        )

    def revenue_by_month(self, org_name: Optional[str] = None) -> Dict[str, float]:
        """収益メトリクス（REVENUE_METRICS）を ``YYYY-MM`` バケットで合計する簡易レポート。

        ``org_name`` 省略時は全 org を横断集計する。``occurred_at`` の先頭7文字を月キーに使い、
        日付が読めないイベントは ``"unknown"`` バケットへ寄せて集計を壊さない。戻り値は
        月キーの昇順（``"unknown"`` は末尾）に並べた ``{month: 合計}``。
        """
        buckets: Dict[str, float] = {}
        for event in self.list_events(org_name):
            if event.metric not in REVENUE_METRICS:
                continue
            stamp = (event.occurred_at or event.recorded_at or "")[:7]
            month = stamp if len(stamp) == 7 and stamp[4] == "-" else "unknown"
            buckets[month] = buckets.get(month, 0.0) + event.value
        return {key: buckets[key] for key in sorted(buckets, key=lambda k: (k == "unknown", k))}

    # ---- 内部 ----

    def _load(self) -> List[OutcomeEvent]:
        if not self.outcomes_path.exists():
            return []
        try:
            payload = json.loads(self.outcomes_path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return []
        if not isinstance(payload, list):
            return []
        events: List[OutcomeEvent] = []
        for item in payload:
            try:
                events.append(OutcomeEvent(**item))
            except (TypeError, ValueError):
                # 不正な item（未知キー/数値化できない value 等）はスキップして集計を壊さない
                continue
        return events

    def _save(self, events: List[OutcomeEvent]) -> None:
        self.outcomes_path.write_text(
            json.dumps([asdict(e) for e in events], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
