"""
AgentSkillEngine — スキル→動作変換エンジン (A-01~A-03)

スキル定義は skills/*.yaml で管理する。
Python コードにスキル定義を書かない — YAML が唯一の真実 (Single Source of Truth)。

skills/*.yaml のフォーマット:
    id: strategic_planning
    name: Strategic Planning
    persona: |
        あなたは長期戦略を立案するビジョナリーなアーキテクトです。
    focus: |
        短期的な解決策よりも...
    output_hint: |
        提案には...

新スキルの追加方法:
    skills/ ディレクトリに新しい YAML ファイルを作成するだけ。Python コード変更不要。
"""

from __future__ import annotations

from typing import List

from core.models.organization import AgentSkill


class AgentSkillEngine:
    """
    AgentSkill のリストを受け取り、LLM システムプロンプトへの
    専門家ペルソナ注入を行うエンジン。

    スキル定義は skills/*.yaml から SkillLoader 経由で取得する。
    """

    def _get_skill_section(self, skill: AgentSkill) -> str:
        """スキル1件のプロンプトセクションを返す（skills/*.yaml から）。"""
        from core.loaders.skill_loader import get_skill_loader
        skill_def = get_skill_loader().get(skill.value)
        if skill_def:
            addon = skill_def.to_prompt_addon()
            if addon:
                return f"【{skill.value} の専門知識】\n{addon}"
        return ""

    def apply_skills_to_prompt(self, base_prompt: str, skills: List[AgentSkill]) -> str:
        """
        ベースとなるシステムプロンプトにスキル定義を注入する。

        スキル定義は skills/*.yaml から取得する。

        Args:
            base_prompt: 既存のシステムプロンプト
            skills: SpecialistAgent が保有するスキルのリスト

        Returns:
            スキル注入済みシステムプロンプト
        """
        if not skills:
            return base_prompt

        skill_sections = [
            section
            for skill in skills
            if (section := self._get_skill_section(skill))
        ]

        if not skill_sections:
            return base_prompt

        skill_block = (
            "\n\n===【あなたの専門スキル】===\n"
            + "\n\n".join(skill_sections)
            + "\n===========================\n"
        )
        return base_prompt + skill_block

    def get_skill_tags(self, skills: List[AgentSkill]) -> List[str]:
        """スキルをナレッジ検索用タグに変換する。"""
        return [skill.value for skill in skills]

    def get_primary_skill(self, skills: List[AgentSkill]) -> AgentSkill | None:
        """スキルリストの先頭（最重要スキル）を返す。"""
        return skills[0] if skills else None

    def describe_agent(self, skills: List[AgentSkill]) -> str:
        """エージェントのスキルセットを人間向けに説明する文字列を返す。"""
        if not skills:
            return "スキル未定義のエージェント"
        from core.loaders.skill_loader import get_skill_loader
        loader = get_skill_loader()
        descs = []
        for skill in skills:
            skill_def = loader.get(skill.value)
            if skill_def and skill_def.persona:
                descs.append(skill_def.persona.strip().split("\n")[0])
        return " また、".join(descs) if descs else " + ".join(s.value for s in skills)
