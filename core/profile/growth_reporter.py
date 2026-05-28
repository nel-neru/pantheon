"""
GrowthReporter — 成長実感レポート (D-07)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from core.platform.state import get_platform_home


@dataclass
class GrowthReport:
    period_label: str
    improvements: list[str] = field(default_factory=list)
    metrics_delta: dict = field(default_factory=dict)
    generated_at: str = ""

    def __post_init__(self):
        if not self.generated_at:
            self.generated_at = datetime.now(timezone.utc).isoformat()


class GrowthReporter:
    def __init__(self, platform_home: Optional[Path] = None):
        self.platform_home = Path(platform_home) if platform_home else get_platform_home()
        self.platform_home.mkdir(parents=True, exist_ok=True)

    def generate_monthly_report(
        self,
        org_name: str,
        current_score: float,
        prev_score: float,
        accepted_count: int,
        knowledge_count: int,
    ) -> GrowthReport:
        score_delta = round(current_score - prev_score, 1)
        improvements: list[str] = []

        if score_delta > 0:
            improvements.append(f"{org_name} のスコアが {prev_score:.1f} → {current_score:.1f} に向上")
        if accepted_count > 0:
            improvements.append(f"{accepted_count}件の改善提案が承認されました")
        if knowledge_count > 0:
            improvements.append(f"{knowledge_count}件の知識が蓄積されました")
        if not improvements:
            improvements.append("安定した運用を継続しました")

        return GrowthReport(
            period_label="今月",
            improvements=improvements,
            metrics_delta={
                "org_name": org_name,
                "score_delta": score_delta,
                "accepted_count": accepted_count,
                "knowledge_count": knowledge_count,
            },
        )

    def format_for_cli(self, report: GrowthReport) -> str:
        improvements = "\n".join(f"- {item}" for item in report.improvements)
        return (
            "📈 今月の成長レポート\n"
            f"期間: {report.period_label}\n"
            f"改善ポイント:\n{improvements}\n"
            f"スコア差分: {report.metrics_delta.get('score_delta', 0):+.1f}"
        )

    def generate_motivation_message(self, accepted_this_week: int, streak_days: int) -> str:
        if accepted_this_week >= 5:
            return f"今週は{accepted_this_week}件の改善を承認しました！すばらしい進歩です🎉"
        if accepted_this_week >= 1:
            return f"今週も{accepted_this_week}件の改善を進めました。継続は力です💪"
        return "今週はまだ改善がありません。小さな一歩から始めましょう👋"
