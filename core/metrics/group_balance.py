"""
GroupBalanceEvaluator — グループバランス評価改善 (C-07)
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class GroupBalance:
    total_orgs: int
    avg_score: float
    min_score: float
    max_score: float
    std_dev: float
    weakest_org: str
    strongest_org: str


class GroupBalanceEvaluator:
    def evaluate(self, org_scores: dict[str, float]) -> GroupBalance:
        if not org_scores:
            return GroupBalance(0, 0.0, 0.0, 0.0, 0.0, "", "")

        items = list(org_scores.items())
        scores = [float(score) for _, score in items]
        avg_score = sum(scores) / len(scores)
        if len(scores) > 1:
            variance = sum((score - avg_score) ** 2 for score in scores) / (len(scores) - 1)
            std_dev = variance ** 0.5
        else:
            std_dev = 0.0
        weakest_org = min(items, key=lambda item: item[1])[0]
        strongest_org = max(items, key=lambda item: item[1])[0]
        return GroupBalance(
            total_orgs=len(scores),
            avg_score=round(avg_score, 1),
            min_score=min(scores),
            max_score=max(scores),
            std_dev=round(std_dev, 1),
            weakest_org=weakest_org,
            strongest_org=strongest_org,
        )

    def get_rebalance_recommendations(self, balance: GroupBalance) -> list[str]:
        recommendations: list[str] = []
        if balance.std_dev > 20:
            recommendations.append(
                f"組織間の格差が大きいです。{balance.weakest_org}に注力してください"
            )
        if balance.min_score < 30:
            recommendations.append(f"{balance.weakest_org}が危機的状態です")
        return recommendations
