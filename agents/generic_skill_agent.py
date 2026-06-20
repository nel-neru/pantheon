"""
GenericSkillAgent — スキル汎用エージェント

SpecialistAgent のスキルセットを見て AgentSkillEngine でシステムプロンプトを動的生成し、
任意のタスクを処理できる汎用 LLM エージェント。

専用実装がないスキル（STRATEGIC_PLANNING, CORPORATE_RESEARCH, ORG_DESIGN,
AGENT_WORKFLOW_DESIGN, PROMPT_ENGINEERING, TOOL_INTEGRATION, etc.）の
フォールバック実装として機能する。

スキルによる差分の仕組み:
    同じ GenericSkillAgent クラスでも、SpecialistAgent.skills が異なると
    AgentSkillEngine が注入するシステムプロンプトが変わるため、
    LLM は「戦略プランナー」「知識キュレーター」「セキュリティ監査員」等の
    まったく異なる専門家として振る舞う。
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import List

from core.models.organization import AgentSkill, SpecialistAgent

from .base import AgentResult, AgentTask, BaseAgent

logger = logging.getLogger(__name__)

GENERIC_BASE_PROMPT = """\
あなたは高度な専門知識を持つ AI エージェントです。
与えられたタスクを自分のスキルと専門知識を最大限に活かして実行してください。

応答は以下の JSON 形式で返してください（コードブロック不要）:
{{
  "result": "タスクの実行結果（詳細な内容）",
  "key_findings": ["重要な発見事項のリスト"],
  "recommendations": ["推奨事項のリスト（最大3件）"],
  "confidence": 0.0から1.0の自信度
}}"""


def _make_specialist(
    skills: List[AgentSkill],
    name: str = "GenericSpecialist",
    description: str = "汎用スキルエージェント",
) -> SpecialistAgent:
    """デフォルト SpecialistAgent を作成（スキルは 2〜3 個必須）。"""
    safe = list(dict.fromkeys(skills))[:3]
    if len(safe) < 2:
        safe.append(AgentSkill.DEEP_RESEARCH)
    return SpecialistAgent(name=name, skills=safe[:3], description=description)


class GenericSkillAgent(BaseAgent):
    """
    任意のスキルセットに対応する汎用 LLM エージェント。

    AgentSkillEngine がスキルに応じたシステムプロンプトを注入するため、
    同じクラスでも STRATEGIC_PLANNING と KNOWLEDGE_CURATION では
    まったく異なる専門家として振る舞う。

    使い方:
        # 戦略プランナーとして動作
        agent = GenericSkillAgent.from_skills(
            [AgentSkill.STRATEGIC_PLANNING, AgentSkill.ORG_DESIGN]
        )
        result = await agent.run(AgentTask("organization_design", "..."))

        # AgentFactory 経由（推奨）
        factory = AgentFactory()
        agent = factory.create("agent:strategic_planner")
    """

    def __init__(
        self,
        specialist: SpecialistAgent,
        llm_client=None,
        **_kwargs,
    ):
        super().__init__(specialist)
        self._llm = llm_client

    @classmethod
    def from_skills(
        cls,
        skills: List[AgentSkill],
        name: str = "GenericSpecialist",
        llm_client=None,
        **_kwargs,
    ) -> "GenericSkillAgent":
        """スキルリストから GenericSkillAgent を作成するファクトリメソッド。"""
        specialist = _make_specialist(skills, name=name)
        return cls(specialist=specialist, llm_client=llm_client)

    def _build_tool_spec(self):
        """YAML 定義(``_yaml_defn``)に tools/mcp があれば ToolSpec を返す（無ければ None）。

        autonomous 実行なので ``allow_gated=False``: 書込/外部ツールは許可せず
        ``--disallowedTools`` 側に置かれる（Human-in-the-Loop ゲートを保つ）。
        定義を持たない素の GenericSkillAgent は常に None（従来の fast-path 維持）。
        """
        defn = getattr(self, "_yaml_defn", None)
        if defn is None:
            return None
        try:
            from core.runtime.tool_config import ToolSpec

            return ToolSpec.from_definition(defn, allow_gated=False)
        except Exception:  # tool wiring must never break a generation
            return None

    def _maybe_reflexion(self, initial, task, messages, llm, tool_spec):
        """``PANTHEON_REFLEXION`` が有効なら generate→critique→refine を回す（既定 off）。

        既定では initial をそのまま返す（従来挙動・コスト不変）。失敗は best-effort で initial に倒す。
        """
        import os

        if os.getenv("PANTHEON_REFLEXION", "").strip().lower() not in {"1", "true", "yes", "on"}:
            return initial
        try:
            from core.intelligence.reflexion import ReflexionLoop
            from core.llm import LLMMessage

            try:
                max_iters = int(os.getenv("PANTHEON_REFLEXION_MAX_ITERS", "2") or "2")
            except ValueError:
                max_iters = 2
            max_iters = max(0, min(5, max_iters))  # clamp: defense-in-depth upper bound

            def refine_fn(prev: str, feedback: str) -> str:
                refine_messages = list(messages) + [
                    LLMMessage(role="assistant", content=prev),
                    LLMMessage(
                        role="user",
                        content=(
                            "上記の出力を次の批評に基づいて改善し、同じ形式で出力し直してください。\n"
                            f"批評: {feedback}"
                        ),
                    ),
                ]
                return llm.complete(refine_messages, tool_spec=tool_spec)

            best, _ev, _iters = ReflexionLoop(llm, max_iters=max_iters).run(
                initial_output=initial, task_type=task.task_type, refine_fn=refine_fn
            )
            return best
        except Exception:
            return initial

    async def run(self, task: AgentTask) -> AgentResult:
        """スキルを活かしてタスクを実行する。"""
        system_prompt = self.apply_skills_to_prompt(GENERIC_BASE_PROMPT, query=task.description)

        if self._llm is None:
            return self._fallback_result(task)

        try:
            from core.llm import LLMMessage, extract_json_object, get_llm_provider

            llm = self._llm or get_llm_provider()
            messages = [
                LLMMessage(role="system", content=system_prompt),
                LLMMessage(
                    role="user",
                    content=(
                        f"タスク種別: {task.task_type}\n\n"
                        f"{task.description}\n\n"
                        f"追加コンテキスト: {json.dumps(task.input, ensure_ascii=False, default=str)}"
                    ),
                ),
            ]
            tool_spec = self._build_tool_spec()
            # complete() は内部で claude subprocess を同期実行する（数秒ブロックしうる）。
            # async run() の中で直接呼ぶとイベントループを止め並行タスクを停滞させるため、
            # スレッドへオフロードする（complete の契約は変えず＝注入 double とも互換）。
            response = await asyncio.to_thread(llm.complete, messages, tool_spec=tool_spec)
            response = self._maybe_reflexion(response, task, messages, llm, tool_spec)
            data = extract_json_object(response)
            if not isinstance(data, dict):
                data = {
                    "result": response,
                    "key_findings": [],
                    "recommendations": [],
                    "confidence": 0.7,
                }
            return AgentResult(
                success=True,
                output=data,
                thinking_process=f"スキル [{', '.join(s.value for s in self.skills)}] で処理",
                execution_log=f"GenericSkillAgent.run({task.task_type}): {str(data.get('result', ''))[:100]}",
            )
        except Exception as e:
            logger.error("GenericSkillAgent error: %s", e)
            return AgentResult(success=False, error=str(e))

    def _fallback_result(self, task: AgentTask) -> AgentResult:
        skills_str = ", ".join(s.value for s in self.skills)
        return AgentResult(
            success=True,
            output={
                "result": (f"{self.name} ({skills_str}) が タスク '{task.task_type}' を処理します"),
                "key_findings": [f"スキル [{skills_str}] が適用されます"],
                "recommendations": [],
                "confidence": 0.8,
            },
            thinking_process=f"スキル [{skills_str}] を適用",
            execution_log=f"GenericSkillAgent fallback: {task.task_type}",
        )

    def describe(self) -> str:
        """このエージェントの説明文を返す（ログ・UI 向け）。"""
        skills_str = " + ".join(s.value for s in self.skills)
        return f"{self.name} [{skills_str}]"
