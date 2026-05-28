"""
OrgWizard — Organization設立ウィザード (E-07)
対話形式でOrganizationを設立する
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class WizardStep:
    step_id: str
    question: str
    answer: str = ""
    options: list[str] = field(default_factory=list)


class OrgWizard:
    def get_steps(self) -> list[WizardStep]:
        return [
            WizardStep(
                step_id="step1",
                question="組織の目的を教えてください（例：セキュリティ強化、テスト改善）",
            ),
            WizardStep(
                step_id="step2",
                question="組織の規模を選んでください",
                options=["小（1チーム）", "中（2-3チーム）", "大（4+チーム）"],
            ),
            WizardStep(
                step_id="step3",
                question="主要な担当領域を選んでください",
                options=["セキュリティ", "パフォーマンス", "保守性", "テスト"],
            ),
        ]

    def process_answers(self, answers: dict[str, str]) -> dict:
        purpose = answers.get("step1", "")
        scale = answers.get("step2", "")
        focus_raw = answers.get("step3", "")
        if isinstance(focus_raw, list):
            focus_areas = focus_raw
        else:
            focus_areas = [item.strip() for item in re.split(r"[,、/]+", focus_raw) if item.strip()]
        return {
            "purpose": purpose,
            "scale": scale,
            "focus_areas": focus_areas,
            "suggested_name": self.suggest_name(purpose),
        }

    def suggest_name(self, purpose: str) -> str:
        lower_purpose = purpose.lower()
        keyword_map = {
            "security": "SecurityEnhancement Org",
            "セキュリティ": "SecurityEnhancement Org",
            "test": "TestingImprovement Org",
            "テスト": "TestingImprovement Org",
            "performance": "PerformanceBoost Org",
            "パフォーマンス": "PerformanceBoost Org",
            "maintain": "Maintainability Org",
            "保守": "Maintainability Org",
        }
        for keyword, name in keyword_map.items():
            if keyword in lower_purpose or keyword in purpose:
                return name
        words = re.findall(r"[A-Za-z]+", purpose)
        if words:
            return f"{words[0].title()} Org"
        return "Custom Org"
