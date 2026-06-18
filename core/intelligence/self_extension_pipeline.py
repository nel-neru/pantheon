"""
SelfExtensionPipeline — 自律的自己拡張パイプライン (L-07)

CapabilityGap 検出 → ToolDesignAgent 設計 → SelfCodeWriter 実装 →
SelfIntegrationTester テスト → ImprovementProposal 登録 (HUMAN_REQUIRED)
のフルフローを管理する。

人間が `pantheon approve <id>` するまで本番には統合されない。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional
from uuid import NAMESPACE_URL, uuid5

from agents.self_code_writer import CodeOutput
from agents.tool_design_agent import ImplementationSpec
from core.intelligence.capability_gap_analyzer import CapabilityGap
from core.intelligence.self_integration_tester import SelfIntegrationTester, ValidationResult
from core.models.organization import ImprovementProposal
from core.state.manager import RepoStateManager

# 提案 id/review_id を gap_id から決定論的に導出する名前空間。save_improvement_proposal は
# ファイル名 {id}.json で書くため、id を固定しないと再実行のたびに別ファイルが増え、同一ギャップの
# self-extension 提案が /inbox に重複して積み上がる。id を固定して上書き＝冪等にする
# （capability_gap_loop.py の構造提案と同じ idempotency 戦略）。
_SELF_EXT_NS = uuid5(NAMESPACE_URL, "pantheon.self_extension")


@dataclass
class ExtensionResult:
    gap_id: str
    spec: ImplementationSpec | None
    code_output: CodeOutput | None
    validation: ValidationResult | None
    proposal_id: str
    success: bool
    reason: str


class SelfExtensionPipeline:
    """自己拡張フローを提案段階まで管理するパイプライン。"""

    def __init__(
        self,
        gap_analyzer: Any,
        design_agent: Any,
        code_writer: Any,
        integration_tester: SelfIntegrationTester,
        state_manager: Optional[RepoStateManager] = None,
        knowledge_manager: Optional[Any] = None,
    ) -> None:
        self.gap_analyzer = gap_analyzer
        self.design_agent = design_agent
        self.code_writer = code_writer
        self.integration_tester = integration_tester
        self.state_manager = state_manager
        self.knowledge_manager = knowledge_manager

    async def run_for_gap(self, gap: CapabilityGap) -> ExtensionResult:
        """単一の CapabilityGap を ImprovementProposal 化する。"""
        spec = self.design_agent.design(gap)
        code_output = self.code_writer.write_code(spec)
        validation = self.integration_tester.validate_syntax(code_output)

        if not validation.is_valid:
            return ExtensionResult(
                gap_id=gap.gap_id,
                spec=spec,
                code_output=code_output,
                validation=validation,
                proposal_id="",
                success=False,
                reason="Syntax validation failed before proposal creation.",
            )

        proposal = ImprovementProposal(
            # gap_id から決定論的に導出＝再実行で同一ファイルを上書き（/inbox 重複防止・冪等）。
            id=uuid5(_SELF_EXT_NS, f"self-extension-id:{gap.gap_id}"),
            review_id=uuid5(_SELF_EXT_NS, f"self-extension:{gap.gap_id}"),
            priority="high",
            category="self_extension",
            title=f"Self-extension: {spec.class_name}",
            description=(
                f"CapabilityGap {gap.gap_id} を解消する候補実装。\n"
                f"対象: {gap.description}\n"
                f"設計概要: {spec.description}\n"
                "HUMAN_REQUIRED: 承認されるまで本番統合しない。"
            ),
            file_path=code_output.file_path,
            expected_impact=gap.rationale,
            implementation_difficulty=self._estimate_difficulty(spec.estimated_lines),
            status="proposed",
        )
        proposal_id = str(proposal.id)

        if self.state_manager is not None:
            saved = self._save_proposal(proposal)
            if not saved:
                return ExtensionResult(
                    gap_id=gap.gap_id,
                    spec=spec,
                    code_output=code_output,
                    validation=validation,
                    proposal_id=proposal_id,
                    success=False,
                    reason="Proposal persistence failed.",
                )

        return ExtensionResult(
            gap_id=gap.gap_id,
            spec=spec,
            code_output=code_output,
            validation=validation,
            proposal_id=proposal_id,
            success=True,
            reason="Proposal created and awaiting human approval.",
        )

    async def run_all_gaps(self, gaps: list[CapabilityGap]) -> list[ExtensionResult]:
        """複数の CapabilityGap を順に処理する。"""
        results: list[ExtensionResult] = []
        for gap in gaps:
            results.append(await self.run_for_gap(gap))
        return results

    def get_pending_proposals(self) -> list[Any]:
        """state_manager 上の proposed 提案を返す。"""
        if self.state_manager is None:
            return []
        if hasattr(self.state_manager, "get_pending_proposals"):
            return self.state_manager.get_pending_proposals()
        if hasattr(self.state_manager, "get_pending_improvement_proposals"):
            return self.state_manager.get_pending_improvement_proposals()
        return []

    def _save_proposal(self, proposal: ImprovementProposal) -> bool:
        if self.state_manager is None:
            return False
        if hasattr(self.state_manager, "save_proposal"):
            return bool(self.state_manager.save_proposal(proposal))
        if hasattr(self.state_manager, "save_improvement_proposal"):
            return self.state_manager.save_improvement_proposal(proposal).exists()
        return False

    def _estimate_difficulty(self, estimated_lines: int) -> str:
        if estimated_lines >= 120:
            return "high"
        if estimated_lines >= 70:
            return "medium"
        return "low"


def rollback_implementation(proposal_id: str, platform_home: Path = None) -> bool:
    """Rollback a generated implementation using SafeChangeExecutor backups."""
    from core.execution.safe_executor import SafeChangeExecutor
    from core.platform.state import get_platform_home

    root = Path(platform_home) if platform_home else get_platform_home()
    improvements_dir = root / ".pantheon" / "improvements"
    proposal_file = None
    if improvements_dir.exists():
        for path in improvements_dir.glob("*.json"):
            if path.stem.startswith(proposal_id):
                proposal_file = path
                break
    if proposal_file is None:
        return False

    try:
        proposal = json.loads(proposal_file.read_text(encoding="utf-8"))
    except Exception:
        return False

    file_path = proposal.get("file_path", "")
    if not file_path:
        return False

    target_path = root / file_path
    executor = SafeChangeExecutor(project_root=root)
    backups = executor.list_backups(str(target_path))
    if not backups:
        return False

    if target_path.exists():
        target_path.unlink()
    return executor.rollback(backups[0])
