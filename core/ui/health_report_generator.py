"""
HealthReportGenerator — 週次健康診断レポート (I-08)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone


@dataclass
class HealthReport:
    org_name: str
    period: str
    metrics: dict
    issues: list[str]
    recommendations: list[str]
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class HealthReportGenerator:
    """Create weekly health reports from lightweight metrics."""

    def __init__(self):
        pass

    def generate_weekly_report(self, org_name: str, metrics: dict) -> HealthReport:
        now = datetime.now(timezone.utc)
        period = f"{(now - timedelta(days=7)).date()} - {now.date()}"
        issues: list[str] = []
        recommendations: list[str] = []

        health_score = float(metrics.get("health_score", 0))
        proposals_count = int(metrics.get("proposals_count", 0))
        accepted_count = int(metrics.get("accepted_count", 0))
        knowledge_count = int(metrics.get("knowledge_count", 0))
        pending_count = max(proposals_count - accepted_count, 0)
        acceptance_rate = accepted_count / max(1, proposals_count)

        if health_score < 70:
            issues.append(f"健康スコアが低下しています ({health_score:.1f})")
            recommendations.append("高優先度の改善提案から順に対応してください。")
        if pending_count >= 10 or (proposals_count > 0 and pending_count > accepted_count):
            issues.append(f"未処理提案が多い状態です ({pending_count}件)")
            recommendations.append("承認待ち提案を定期的に棚卸しし、古い提案を整理してください。")
        if acceptance_rate < 0.5 and proposals_count > 0:
            issues.append(f"提案受理率が低めです ({acceptance_rate:.0%})")
            recommendations.append("提案品質の見直しと優先度調整を行ってください。")
        if knowledge_count < 5:
            issues.append(f"ナレッジ蓄積が不足しています ({knowledge_count}件)")
            recommendations.append(
                "重要な学びを KnowledgeManager に保存して再利用性を高めてください。"
            )

        if not issues:
            recommendations.append(
                "現在の運用状態は良好です。このまま週次レビューを継続してください。"
            )

        return HealthReport(
            org_name=org_name,
            period=period,
            metrics=dict(metrics),
            issues=issues,
            recommendations=recommendations,
        )

    def format_html(self, report: HealthReport) -> str:
        issues = "".join(f"<li>{issue}</li>" for issue in report.issues) or "<li>問題なし</li>"
        recs = "".join(f"<li>{rec}</li>" for rec in report.recommendations)
        metrics = "".join(
            f"<li><strong>{key}</strong>: {value}</li>"
            for key, value in sorted(report.metrics.items())
        )
        return (
            "<html><body>"
            f"<h1>{report.org_name} Weekly Health Report</h1>"
            f"<p>Period: {report.period}</p>"
            "<h2>Metrics</h2><ul>" + metrics + "</ul>"
            "<h2>Issues</h2><ul>" + issues + "</ul>"
            "<h2>Recommendations</h2><ul>" + recs + "</ul>"
            f"<p>Generated at: {report.generated_at}</p>"
            "</body></html>"
        )

    def format_cli(self, report: HealthReport) -> str:
        lines = [
            f"週次健康診断レポート: {report.org_name}",
            f"期間: {report.period}",
            "メトリクス:",
        ]
        for key, value in sorted(report.metrics.items()):
            lines.append(f"  - {key}: {value}")
        lines.append("課題:")
        if report.issues:
            lines.extend(f"  - {issue}" for issue in report.issues)
        else:
            lines.append("  - 問題なし")
        lines.append("推奨事項:")
        lines.extend(f"  - {rec}" for rec in report.recommendations)
        return "\n".join(lines)
