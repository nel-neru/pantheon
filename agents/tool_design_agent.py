"""
ToolDesignAgent — 新ツール設計エージェント (L-04)

CapabilityGapAnalyzer が検出した能力ギャップに対して
「どんなAgent/Skill/Toolを作れば解決するか」を設計するエージェント。

入力: CapabilityGap
出力: ImplementationSpec (クラス名・メソッド・インターフェース・既存コードとの統合方法)
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from agents.base import AgentResult, AgentTask, BaseAgent
from core.intelligence.capability_gap_analyzer import CapabilityGap
from core.models.organization import AgentSkill, SpecialistAgent

logger = logging.getLogger(__name__)

DESIGN_SYSTEM_PROMPT = """あなたは RepoCorp AI のアーキテクトです。
既存コードの命名規則・責務分割・Agent インターフェースに従って、
CapabilityGap を解消するための実装仕様を JSON で返してください。"""


@dataclass
class ImplementationSpec:
    """自己拡張のための実装仕様書。"""

    spec_id: str
    class_name: str
    file_path: str
    method_signatures: list[str]
    description: str
    integration_points: list[str]
    required_imports: list[str]
    estimated_lines: int
    gap_id: str
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()
        if not self.spec_id:
            self.spec_id = f"spec:{self.gap_id}:{uuid4().hex[:8]}"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ImplementationSpec":
        allowed = {key for key in cls.__dataclass_fields__}
        return cls(**{key: value for key, value in data.items() if key in allowed})


def _make_default_specialist() -> SpecialistAgent:
    return SpecialistAgent(
        name="ToolDesignAgent",
        skills=[AgentSkill.STRATEGIC_PLANNING, AgentSkill.AGENT_WORKFLOW_DESIGN],
        description="能力ギャップを既存アーキテクチャへ統合可能な実装仕様に変換する。",
    )


class ToolDesignAgent(BaseAgent):
    """CapabilityGap から実装仕様書を生成する設計専門エージェント。"""

    def __init__(
        self,
        specialist: Optional[SpecialistAgent] = None,
        llm_client: Optional[Any] = None,
    ) -> None:
        super().__init__(specialist or _make_default_specialist())
        self._llm = llm_client

    def design(self, gap: CapabilityGap) -> ImplementationSpec:
        """能力ギャップから実装仕様書を生成する。"""
        if self._llm:
            llm_spec = self._design_with_llm(gap)
            if llm_spec is not None:
                return llm_spec
        return self._design_template(gap)

    async def run(self, task: AgentTask) -> AgentResult:
        raw_gap = task.input.get("gap")
        if raw_gap is None:
            return AgentResult(success=False, error="task.input['gap'] is required")

        gap = raw_gap if isinstance(raw_gap, CapabilityGap) else CapabilityGap.from_dict(raw_gap)
        spec = self.design(gap)
        return AgentResult(
            success=True,
            output={"spec": spec},
            thinking_process=f"CapabilityGap {gap.gap_id} を {spec.class_name} の実装仕様へ変換",
            execution_log=f"Designed {spec.class_name} -> {spec.file_path}",
        )

    def _design_template(self, gap: CapabilityGap) -> ImplementationSpec:
        class_name = gap.suggested_name
        suggested_type = gap.suggested_type.lower()
        file_path = self._suggest_file_path(class_name, suggested_type)
        method_signatures = self._suggest_methods(suggested_type)
        return ImplementationSpec(
            spec_id=f"spec:{gap.gap_id}",
            class_name=class_name,
            file_path=file_path,
            method_signatures=method_signatures,
            description=(
                f"{gap.description} を解消するための {suggested_type} 実装。"
                f" 主目的は {gap.rationale} を既存ワークフローへ統合すること。"
            ),
            integration_points=self._suggest_integration_points(file_path, suggested_type),
            required_imports=self._suggest_imports(suggested_type),
            estimated_lines=self._estimate_lines(suggested_type, len(method_signatures)),
            gap_id=gap.gap_id,
        )

    def _design_with_llm(self, gap: CapabilityGap) -> Optional[ImplementationSpec]:
        prompt = self._build_llm_prompt(gap)
        try:
            response = self._llm.invoke(prompt)
            content = response.content if hasattr(response, "content") else str(response)
            data = self._extract_json_object(content)
            if data is None:
                return None
            return ImplementationSpec(
                spec_id=data.get("spec_id", f"spec:{gap.gap_id}"),
                class_name=data.get("class_name", gap.suggested_name),
                file_path=data.get("file_path", self._suggest_file_path(gap.suggested_name, gap.suggested_type)),
                method_signatures=data.get("method_signatures", self._suggest_methods(gap.suggested_type)),
                description=data.get("description", gap.description),
                integration_points=data.get(
                    "integration_points",
                    self._suggest_integration_points(
                        self._suggest_file_path(gap.suggested_name, gap.suggested_type),
                        gap.suggested_type,
                    ),
                ),
                required_imports=data.get("required_imports", self._suggest_imports(gap.suggested_type)),
                estimated_lines=int(data.get("estimated_lines", self._estimate_lines(gap.suggested_type, 2))),
                gap_id=gap.gap_id,
                created_at=data.get("created_at", datetime.now(timezone.utc).isoformat()),
            )
        except Exception as exc:
            logger.warning("ToolDesignAgent LLM design failed: %s", exc)
            return None

    def _build_llm_prompt(self, gap: CapabilityGap) -> str:
        examples = self._read_existing_patterns()
        return f"""{DESIGN_SYSTEM_PROMPT}

CapabilityGap:
- gap_id: {gap.gap_id}
- pattern_key: {gap.pattern_key}
- suggested_type: {gap.suggested_type}
- suggested_name: {gap.suggested_name}
- description: {gap.description}
- rationale: {gap.rationale}
- priority: {gap.priority}

Existing code patterns:
{examples}

以下の JSON オブジェクトのみを返してください:
{{
  "spec_id": "spec:...",
  "class_name": "{gap.suggested_name}",
  "file_path": "agents/example_agent.py",
  "method_signatures": ["async def run(self, task: AgentTask) -> AgentResult"],
  "description": "...",
  "integration_points": ["..."],
  "required_imports": ["..."],
  "estimated_lines": 80
}}"""

    def _read_existing_patterns(self) -> str:
        repo_root = Path(__file__).resolve().parents[1]
        samples: list[str] = []
        for rel_path in ("agents/base.py", "agents/codebase_explorer_agent.py", "agents/improvement_executor_agent.py"):
            path = repo_root / rel_path
            if not path.exists():
                continue
            try:
                snippet = path.read_text(encoding="utf-8")[:1200]
                samples.append(f"=== {rel_path} ===\n{snippet}")
            except OSError:
                continue
        return "\n\n".join(samples)

    def _suggest_file_path(self, class_name: str, suggested_type: str) -> str:
        snake_name = self._to_snake_case(class_name)
        normalized_type = suggested_type.lower()
        if normalized_type == "agent":
            if not snake_name.endswith("_agent"):
                snake_name = f"{snake_name}_agent"
            return f"agents/{snake_name}.py"
        if normalized_type == "tool":
            return f"core/intelligence/{snake_name}.py"
        if normalized_type == "skill":
            return f"core/intelligence/{snake_name}_skill.py"
        if normalized_type == "mcp_tool":
            return f"core/intelligence/{snake_name}_mcp_tool.py"
        return f"core/intelligence/{snake_name}.py"

    def _suggest_methods(self, suggested_type: str) -> list[str]:
        normalized_type = suggested_type.lower()
        if normalized_type == "agent":
            return [
                "def execute(self, payload: dict[str, Any]) -> dict[str, Any]",
                "async def run(self, task: AgentTask) -> AgentResult",
            ]
        if normalized_type == "tool":
            return [
                "def execute(self, target: str) -> dict[str, Any]",
                "def describe(self) -> str",
            ]
        if normalized_type == "skill":
            return [
                "def apply(self, context: dict[str, Any]) -> dict[str, Any]",
                "def describe(self) -> str",
            ]
        return [
            "def call(self, arguments: dict[str, Any]) -> dict[str, Any]",
            "def describe(self) -> str",
        ]

    def _suggest_integration_points(self, file_path: str, suggested_type: str) -> list[str]:
        integration_points = [
            f"{file_path} として既存の snake_case 配置規則に従って追加する",
            "CapabilityRegistry.scan_and_register_all() で新能力として自動検出できる構成にする",
            "SelfExtensionPipeline から生成・レビュー対象として扱えるようにする",
        ]
        if suggested_type.lower() == "agent":
            integration_points.append("BaseAgent.run() 契約に従って AgentTask / AgentResult を受け渡す")
        return integration_points

    def _suggest_imports(self, suggested_type: str) -> list[str]:
        normalized_type = suggested_type.lower()
        if normalized_type == "agent":
            return [
                "from typing import Any",
                "from agents.base import BaseAgent, AgentTask, AgentResult",
                "from core.models.organization import AgentSkill, SpecialistAgent",
            ]
        return ["from typing import Any"]

    def _estimate_lines(self, suggested_type: str, method_count: int) -> int:
        base = {"agent": 85, "tool": 55, "skill": 45, "mcp_tool": 50}.get(suggested_type.lower(), 50)
        return base + max(method_count - 1, 0) * 12

    def _extract_json_object(self, content: str) -> Optional[dict[str, Any]]:
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if not match:
            return None
        return json.loads(match.group())

    def _to_snake_case(self, value: str) -> str:
        normalized = value.replace("-", "_")
        normalized = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", normalized)
        normalized = re.sub(r"[^a-zA-Z0-9_]+", "_", normalized)
        return normalized.strip("_").lower()
