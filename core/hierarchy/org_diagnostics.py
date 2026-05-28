"""
OrgSelfDiagnostics — 組織自己診断 (E-10)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class DiagnosticReport:
    org_name: str
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)
    health_score: float = 0.0
    generated_at: str = ""

    def __post_init__(self):
        if not self.generated_at:
            self.generated_at = datetime.now(timezone.utc).isoformat()


class OrgSelfDiagnostics:
    def diagnose(
        self,
        org_name: str,
        health_score: float,
        accepted_count: int,
        rejected_count: int,
        knowledge_count: int,
    ) -> DiagnosticReport:
        strengths: list[str] = []
        weaknesses: list[str] = []
        next_steps: list[str] = []

        if health_score >= 80:
            strengths.append("高い自律スコア")
        elif health_score >= 60:
            strengths.append("安定した自律運用")

        if knowledge_count >= 10:
            strengths.append("豊富な知識ベース")
        elif knowledge_count >= 5:
            strengths.append("知識蓄積が進んでいる")

        if accepted_count >= 5:
            strengths.append("改善提案の実行力")

        if not strengths:
            strengths.append("基盤運用を継続できている")

        if health_score < 50:
            weaknesses.append("自律スコアの改善が必要")
            next_steps.append("小さな改善提案を高速に回して成功体験を増やす")

        if rejected_count > accepted_count:
            weaknesses.append("提案の質向上が必要")
            next_steps.append("却下理由を分析して提案テンプレートを改善する")

        if knowledge_count < 3:
            weaknesses.append("知識蓄積の強化が必要")
            next_steps.append("重要な学びを毎週ナレッジとして記録する")

        if not weaknesses:
            next_steps.append("現在の強みを横展開して他領域にも適用する")
            next_steps.append("高品質な提案パターンを標準化する")

        unique_steps: list[str] = []
        for step in next_steps:
            if step not in unique_steps:
                unique_steps.append(step)

        return DiagnosticReport(
            org_name=org_name,
            strengths=strengths,
            weaknesses=weaknesses,
            next_steps=unique_steps[:3],
            health_score=float(health_score),
        )

    def format_report(self, report: DiagnosticReport) -> str:
        strengths = "、".join(report.strengths) if report.strengths else "なし"
        weaknesses = "、".join(report.weaknesses) if report.weaknesses else "なし"
        next_steps = "\n".join(f"- {step}" for step in report.next_steps) if report.next_steps else "- なし"
        return (
            f"🩺 組織自己診断: {report.org_name}\n"
            f"Health Score: {report.health_score:.1f}\n"
            f"強み: {strengths}\n"
            f"弱み: {weaknesses}\n"
            f"次の一手:\n{next_steps}"
        )
