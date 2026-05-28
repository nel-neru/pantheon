"""
TaskMatcher — タスクカテゴリ×スキルマッチング最適化 (A-05)
提案カテゴリとAgentスキルをマッチングして最適タスク配分を行う
"""

from __future__ import annotations

CATEGORY_SKILL_MAP: dict[str, list[str]] = {
    "security": ["TOOL_INTEGRATION", "DEEP_RESEARCH"],
    "performance": ["PERFORMANCE_ANALYSIS", "STRATEGIC_PLANNING"],
    "maintainability": ["CODE_REVIEW", "REFACTORING"],
    "testing": ["TESTING", "CODE_REVIEW"],
    "architecture": ["STRATEGIC_PLANNING", "DEEP_RESEARCH"],
    "documentation": ["PROMPT_ENGINEERING", "CODE_REVIEW"],
}


class TaskMatcher:
    """タスクカテゴリに対するエージェント適合度を評価する。"""

    def match(self, category: str, available_agents: list[dict]) -> list[dict]:
        required_skills = set(CATEGORY_SKILL_MAP.get(category, []))
        ranked: list[dict] = []

        for agent in available_agents:
            skills = set(agent.get("skills", []))
            matched_skills = sorted(required_skills & skills)
            score = len(matched_skills) * 2 + float(agent.get("performance_score", 0.0))
            ranked.append({
                **agent,
                "matched_skills": matched_skills,
                "match_score": score,
            })

        return sorted(ranked, key=lambda a: a.get("match_score", 0.0), reverse=True)

    def get_match_rate(self, category: str, agents: list[dict]) -> float:
        if not agents:
            return 0.0

        required_skills = set(CATEGORY_SKILL_MAP.get(category, []))
        if not required_skills:
            return 0.0

        matched_agents = sum(
            1 for agent in agents
            if required_skills & set(agent.get("skills", []))
        )
        return matched_agents / len(agents)
