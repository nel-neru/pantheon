"""
VelocityCalculator — 改善速度計算改善 (C-08)
"""

from __future__ import annotations


class VelocityCalculator:
    def calculate(self, accepted_count: int, days_elapsed: float, normalization: float = 10.0) -> float:
        velocity = (accepted_count / max(1, days_elapsed)) * normalization
        return round(max(0.0, min(100.0, velocity)), 1)

    def classify_velocity(self, velocity: float) -> str:
        if velocity < 10:
            return "低速"
        if velocity < 30:
            return "標準"
        if velocity <= 60:
            return "高速"
        return "超高速"
