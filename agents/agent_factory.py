"""
AgentFactory — agents/definitions/*.yaml からエージェントを生成するファクトリ

YAML が唯一の真実 (Single Source of Truth)。
Python コードにエージェント定義を書かない。

エージェントの追加方法:
    agents/definitions/ に新しい YAML ファイルを作成するだけ。
    implementation フィールドを指定すると専用 Python クラスを使用できる。

YAML フォーマット:
    name: MyAgent
    description: 説明
    skills: [strategic_planning, deep_research]
    tools: [read_file, search_codebase]
    behavior: |
        振る舞いの説明...
    implementation: agents.my_module.MyAgentClass  # 省略時は GenericSkillAgent を使用
    response_format:
        type: json
        fields: [result, key_findings, recommendations, confidence]
"""

from __future__ import annotations

import importlib
import inspect
import logging
from typing import Callable, Dict, List, Optional, Type

from core.models.organization import AgentSkill, SpecialistAgent

from .base import BaseAgent

logger = logging.getLogger(__name__)


def _import_class(class_path: str) -> Type:
    """'module.path.ClassName' を動的インポートして返す。"""
    module_path, class_name = class_path.rsplit(".", 1)
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


def _skills_from_ids(skill_ids: List[str]) -> List[AgentSkill]:
    """スキルID文字列のリストを AgentSkill enum リストに変換する。"""
    skills: List[AgentSkill] = []
    unknown_skill_ids: List[str] = []
    for sid in skill_ids:
        try:
            skills.append(AgentSkill(sid))
        except ValueError:
            unknown_skill_ids.append(sid)

    for fallback in (AgentSkill.DEEP_RESEARCH, AgentSkill.CODEBASE_EXPLORATION):
        if len(skills) >= 2:
            break
        if fallback not in skills:
            skills.append(fallback)

    if unknown_skill_ids:
        logger.warning(
            "AgentFactory: unknown skill ids %s, using fallback skills %s",
            unknown_skill_ids,
            [skill.value for skill in skills[:3]],
        )
    return skills[:3]


class AgentFactory:
    """
    agents/definitions/*.yaml からエージェントを生成するファクトリ。

    解決フロー:
        1. AgentLoader で YAML 定義を検索
        2. implementation フィールドがあれば指定の Python クラスを使用
        3. なければ GenericSkillAgent (skills + behavior で振る舞いを決定)

    使い方:
        factory = AgentFactory()
        agent = factory.create("agent:strategic_planner")  # YAML定義
        agent = factory.create("agent:code_reviewer")      # YAML + Python実装

        # スキルリストから最適なエージェントを選択
        agent = factory.create_for_skills([AgentSkill.STRATEGIC_PLANNING, AgentSkill.ORG_DESIGN])

        # PreTaskOrchestrator への渡し方
        result = await orchestrator.execute(task, analysis, agent_factory=factory.create)
    """

    def __init__(self, llm_client=None, **_kwargs):
        self._llm = llm_client
        self._agent_loader = None
        self._skill_loader = None

    def _get_agent_loader(self):
        if self._agent_loader is None:
            from core.loaders.agent_loader import AgentLoader

            self._agent_loader = AgentLoader()
        return self._agent_loader

    def _get_skill_loader(self):
        if self._skill_loader is None:
            from core.loaders.skill_loader import SkillLoader

            self._skill_loader = SkillLoader()
        return self._skill_loader

    def create(self, capability_id: str) -> Optional[BaseAgent]:
        """
        capability_id からエージェントインスタンスを返す。

        agents/definitions/ の YAML を検索し:
        - implementation フィールドがあれば指定の Python クラスを使用
        - なければ GenericSkillAgent + YAML の behavior/skills で動作

        Args:
            capability_id: "agent:strategic_planner" 等の CapabilityRegistry ID

        Returns:
            BaseAgent インスタンス。未知の ID の場合は None。
        """
        defn = self._get_agent_loader().get(capability_id)
        if defn is None:
            logger.warning("AgentFactory: no definition for %r", capability_id)
            return None

        skills = _skills_from_ids(defn.skills)
        specialist = SpecialistAgent(
            name=defn.name,
            skills=skills,
            description=defn.description,
        )

        if defn.implementation:
            try:
                cls = _import_class(defn.implementation)
                kwargs = {"specialist": specialist}
                signature = inspect.signature(cls)
                if "provider_name" in signature.parameters:
                    kwargs["provider_name"] = getattr(self._llm, "provider_name", None) or "anthropic"
                if "llm_client" in signature.parameters:
                    kwargs["llm_client"] = self._llm
                return cls(**kwargs)
            except Exception as e:
                logger.error(
                    "AgentFactory: failed to import/instantiate %s: %s — falling back to GenericSkillAgent",
                    defn.implementation,
                    e,
                )

        from agents.generic_skill_agent import GenericSkillAgent

        skill_loader = self._get_skill_loader()

        class _YamlAgent(GenericSkillAgent):
            """YAML の behavior + skills/*.yaml のペルソナを組み合わせたエージェント。"""

            def __init__(self, specialist, defn, skill_loader, **kwargs):
                super().__init__(specialist, **kwargs)
                self._yaml_defn = defn
                self._yaml_skill_loader = skill_loader

            def apply_skills_to_prompt(self, base_prompt: str) -> str:
                yaml_prompt = self._yaml_defn.build_system_prompt(self._yaml_skill_loader)
                if yaml_prompt and base_prompt.strip():
                    return f"{base_prompt.rstrip()}\n\n---\n\n{yaml_prompt}"
                return yaml_prompt if yaml_prompt else super().apply_skills_to_prompt(base_prompt)

            def get_skill_tags(self) -> List[str]:
                if self._yaml_defn.skills:
                    return list(dict.fromkeys(self._yaml_defn.skills))
                return super().get_skill_tags()

        return _YamlAgent(
            specialist=specialist,
            defn=defn,
            skill_loader=skill_loader,
            llm_client=self._llm,
        )

    def create_for_skills(
        self,
        skills: List[AgentSkill],
        name: Optional[str] = None,
    ) -> BaseAgent:
        """
        スキルリストから最適なエージェントを選択して返す。

        完全一致 → 部分一致 → GenericSkillAgent の優先順で選択する。
        """
        skills_set = {s.value for s in skills}
        loader = self._get_agent_loader()

        best_id: Optional[str] = None
        best_overlap = 0
        for defn in loader.all():
            overlap = len(skills_set & set(defn.skills))
            if overlap == len(skills_set) == len(defn.skills):
                return self.create(defn.capability_id)
            if overlap > best_overlap:
                best_overlap = overlap
                best_id = defn.capability_id

        if best_id and best_overlap >= max(2, len(skills) - 1):
            return self.create(best_id)

        from agents.generic_skill_agent import GenericSkillAgent

        safe_skills = list(dict.fromkeys(skills))[:3]
        if len(safe_skills) < 2:
            safe_skills.append(AgentSkill.DEEP_RESEARCH)
        specialist = SpecialistAgent(
            name=name or "GenericSpecialist",
            skills=safe_skills[:3],
            description="汎用スキルエージェント",
        )
        return GenericSkillAgent(
            specialist=specialist,
            llm_client=self._llm,
        )

    def get_skills_for_agent(self, capability_id: str) -> List[AgentSkill]:
        """capability_id のスキルリストを返す。"""
        defn = self._get_agent_loader().get(capability_id)
        return _skills_from_ids(defn.skills) if defn else []

    def all_capability_ids(self) -> List[str]:
        """登録されている全 capability_id を返す（YAML定義の全エントリ）。"""
        return self._get_agent_loader().capability_ids()

    def all_entries(self) -> List:
        """全エージェント定義を返す（AgentDefinition のリスト）。"""
        return self._get_agent_loader().all()

    def as_callable(self) -> Callable[[str], Optional[BaseAgent]]:
        """PreTaskOrchestrator の agent_factory 引数として使える callable を返す。"""
        return self.create

    @classmethod
    def get_all_entries(cls) -> Dict:
        """後方互換: 空のdictを返す（_REGISTRYは廃止）。"""
        return {}

    @classmethod
    def get_skills_for_agent_static(cls, capability_id: str) -> List[AgentSkill]:
        """後方互換: インスタンスを生成して取得する。"""
        return cls().get_skills_for_agent(capability_id)
