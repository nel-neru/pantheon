"""
AbstractGoalPipeline — 抽象目標→自律実行パイプライン (M-01~M-07)

開発者は「何を作りたいか」だけ伝えればあとはシステムが自律実行する。

フロー:
  1. GoalParser.parse()      — 自然言語 → StructuredGoal
  2. GoalDecomposer.decompose() — StructuredGoal → GoalPlan (Epic/Story/Task)
  3. OrgInstantiator.instantiate() — GoalPlan → Organization
  4. ExecutionCoordinator.execute() — GoalPlan を自律実行
  5. GoalVerifier.verify()   — 達成度を評価して推奨事項を返す
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from core.goals.execution_coordinator import ExecutionCoordinator, ExecutionProgress
from core.goals.goal_decomposer import GoalDecomposer, GoalPlan
from core.goals.goal_parser import GoalParser, StructuredGoal
from core.goals.goal_verifier import GoalVerificationResult, GoalVerifier
from core.goals.org_instantiator import InstantiationResult, OrgInstantiator

logger = logging.getLogger(__name__)


def _slug(text: str) -> str:
    """org 名などからワークスペースのディレクトリ名に使う安全なスラッグを生成する。"""
    s = re.sub(r"[^a-zA-Z0-9_-]+", "-", text or "").strip("-").lower()
    return s or "workspace"


@dataclass
class PipelineResult:
    """AbstractGoalPipeline の最終結果。"""

    raw_text: str
    goal: StructuredGoal
    plan: GoalPlan
    org_result: InstantiationResult
    execution_progress: ExecutionProgress
    verification: GoalVerificationResult

    @property
    def success(self) -> bool:
        return self.verification.overall_achieved

    def summary(self) -> str:
        lines = [
            f"目標: {self.goal.description}",
            f"種別: {self.goal.goal_type}  スケール: {self.goal.scale}",
            f"Organization: {self.org_result.organization.name} ({'新規' if self.org_result.is_new else '流用'})",
            f"タスク: {self.execution_progress.done_count}/{self.execution_progress.total} 完了 (失敗: {self.execution_progress.failed_count})",
            f"達成度: {self.verification.achievement_pct:.1f}% ({'✅ 達成' if self.success else '⚠️ 未達成'})",
        ]
        if self.verification.recommendations:
            lines.append("推奨事項:")
            for rec in self.verification.recommendations[:3]:
                lines.append(f"  {rec}")
        return "\n".join(lines)


class AbstractGoalPipeline:
    """
    抽象目標テキストを受け取り、M-01〜M-05 を順に実行して
    自律的にタスクを実行・達成検証するパイプライン。

    全コンポーネントが疎結合で、それぞれ差し替え可能。
    """

    def __init__(
        self,
        parser: Optional[GoalParser] = None,
        decomposer: Optional[GoalDecomposer] = None,
        instantiator: Optional[OrgInstantiator] = None,
        coordinator: Optional[ExecutionCoordinator] = None,
        verifier: Optional[GoalVerifier] = None,
        pre_task_orchestrator: Optional[Any] = None,
        progress_callback: Optional[Any] = None,
    ):
        self._parser = parser or GoalParser()
        self._decomposer = decomposer or GoalDecomposer()
        # 明示注入が無い場合は、永続化済みの既存 Organization を読み込んで OrgInstantiator に
        # 渡す。これが無いと _find_reusable_org が常に空リストを見て毎回新規作成し、同名
        # Organization がディスク上に増殖する（重複表示の原因）。
        self._owns_instantiator = instantiator is None
        self._instantiator = instantiator or OrgInstantiator()
        if self._owns_instantiator:
            self._instantiator.set_existing_orgs(self._load_existing_orgs())
        # 既定で pattern_store 付き PreTaskOrchestrator を配線し、ゴール実行が
        # パターン学習として蓄積されるようにする（明示注入があればそれを優先）。
        if pre_task_orchestrator is None:
            try:
                from core.orchestration.orchestration_pattern_store import (
                    OrchestrationPatternStore,
                )
                from core.orchestration.pre_task_orchestrator import PreTaskOrchestrator

                pre_task_orchestrator = PreTaskOrchestrator(
                    pattern_store=OrchestrationPatternStore()
                )
            except Exception:  # noqa: BLE001 - 最小環境では従来どおり None で続行
                pre_task_orchestrator = None
        # progress_callback は ExecutionCoordinator が各タスクの状態遷移ごとに
        # ExecutionProgress を渡して呼ぶ（SSE などへ実 per-task 進捗を流すために配線）。
        # 明示注入の coordinator があればそれを優先（callback は注入側の責務）。
        self._coordinator = coordinator or ExecutionCoordinator(
            pre_task_orchestrator=pre_task_orchestrator,
            progress_callback=progress_callback,
        )
        self._verifier = verifier or GoalVerifier()

    def _resolve_platform_home(self):
        """永続化／流用判定に使う platform_home を解決する。

        instantiator の OrganizationDesigner が指す platform_home に揃えることで、
        テスト（tmp_path を designer に渡すケース）が誤って本物の ``~/.pantheon`` へ
        書き込む事故を防ぐ。解決できなければ None（= ``get_platform_home()`` 既定）。
        """
        designer = getattr(self._instantiator, "_designer", None)
        return getattr(designer, "platform_home", None)

    def _load_existing_orgs(self) -> list:
        """永続化済みの全 Organization を読み込む（最小環境では空リスト）。"""
        try:
            from core.platform.state import PlatformStateManager

            return PlatformStateManager(
                platform_home=self._resolve_platform_home()
            ).load_organizations()
        except Exception:  # noqa: BLE001 - 未初期化/最小環境では流用なしで続行
            return []

    def _resolve_workspaces_root(self) -> Path:
        """新規ワークスペースを作成する親フォルダ。

        解決順: platform config の ``workspaces_root`` > ``<platform_home>/workspaces``。
        テスト（platform_home=tmp_path）では tmp 配下に作られ、実 home を汚さない。
        """
        from core.platform.state import PlatformStateManager, get_platform_home

        home = self._resolve_platform_home() or get_platform_home()
        try:
            configured = PlatformStateManager(platform_home=home).get_workspaces_root()
            if configured:
                return Path(configured)
        except Exception:  # noqa: BLE001
            pass
        return Path(home) / "workspaces"

    def _ensure_workspace_dir(self, org_name: str, new_workspace: Any) -> Path:
        """新規 Organization 用のワークスペース（ディレクトリ）を用意して返す。

        ``new_workspace`` が明示パスならそこを、True なら既定ルート配下に org 名スラッグで作成。
        None（暗黙）でも repo 無し org を作らないため必ずディレクトリを用意する。明示要求時のみ
        ``git init`` を best-effort で行う（暗黙時は mkdir のみでテストを軽量に保つ）。
        """
        explicit_path = (
            new_workspace
            if isinstance(new_workspace, (str, Path)) and not isinstance(new_workspace, bool)
            else None
        )
        path = (
            Path(explicit_path)
            if explicit_path
            else self._resolve_workspaces_root() / _slug(org_name)
        )
        path.mkdir(parents=True, exist_ok=True)
        if new_workspace is not None and not (path / ".git").exists():
            try:
                import subprocess

                subprocess.run(
                    ["git", "init"], cwd=str(path), capture_output=True, timeout=15, check=False
                )
            except Exception:  # noqa: BLE001 - git 不在環境でも続行
                pass
        return path

    def _load_workspace_org(self, name: str) -> InstantiationResult:
        """既存ワークスペース（Organization 名）を対象として読み込む（新規作成しない）。"""
        from core.platform.state import PlatformStateManager

        org = PlatformStateManager(
            platform_home=self._resolve_platform_home()
        ).load_organization_by_name(name)
        if org is None:
            raise ValueError(
                f"ワークスペース（Organization）'{name}' が見つかりません。"
                "`pantheon org list` で確認するか、--new-workspace で新規作成してください。"
            )
        return InstantiationResult(
            organization=org,
            is_new=False,
            reason=f"既存ワークスペース '{name}' を対象に実行",
        )

    async def run(
        self,
        raw_goal_text: str,
        use_llm: bool = False,
        *,
        workspace: Optional[str] = None,
        new_workspace: Any = None,
        **_kwargs: Any,
    ) -> PipelineResult:
        """
        自然言語の目標テキストからフルパイプラインを実行する。

        Args:
            raw_goal_text: 開発者が入力する自然言語の目標
            use_llm: LLM による高精度パース・分解を行うか
            workspace: 既存ワークスペース（Organization 名）を対象に実行する（新規作成しない）
            new_workspace: 新規ワークスペースを作成して実行する（パス文字列 / True=既定の場所）

        Returns:
            PipelineResult
        """
        logger.info("AbstractGoalPipeline: starting for '%s'", raw_goal_text[:60])

        goal = self._parser.parse(raw_goal_text, use_llm=use_llm)
        logger.info("Goal parsed: type=%s, scale=%s", goal.goal_type, goal.scale)

        plan = self._decomposer.decompose(goal, use_llm=use_llm)
        logger.info("Plan created: %d epics, %d tasks", len(plan.epics), plan.total_tasks)

        if workspace:
            # 既存ワークスペースを対象に実行（新規 org を作らない）。
            org_result = self._load_workspace_org(workspace)
        else:
            # 自前生成した instantiator の場合は、毎回の実行直前に最新の永続化済み
            # Organization を流用候補へ反映する（同一プロセスで連続実行しても重複を作らない）。
            if self._owns_instantiator:
                self._instantiator.set_existing_orgs(self._load_existing_orgs())

            org_result = self._instantiator.instantiate(goal)
            # 中核モデル「1 ワークスペース = 1 Organization（repo 必須）」: 新規 org には必ず
            # ワークスペース（repo）を割り当てる。repo 無し org は二度と作らない。
            new_org = org_result.organization
            if org_result.is_new and not new_org.is_workspace_bound:
                ws_path = self._ensure_workspace_dir(new_org.name, new_workspace)
                new_org.target_repo_path = str(ws_path)
        logger.info(
            "Organization: %s (%s) repo=%s",
            org_result.organization.name,
            "new" if org_result.is_new else "reused",
            org_result.organization.target_repo_path,
        )
        # OrgInstantiator は永続化を呼び出し元に委ねる契約。新規生成した Organization は
        # ここで PlatformStateManager に保存し、以後 CLI/GUI から参照できるようにする
        # （最小構成・テストでは保存失敗してもパイプラインは止めない）。
        if org_result.is_new:
            try:
                from core.platform.state import PlatformStateManager

                PlatformStateManager(platform_home=self._resolve_platform_home()).save_organization(
                    org_result.organization
                )
                logger.info("Persisted new organization: %s", org_result.organization.name)
            except Exception:  # noqa: BLE001
                logger.warning(
                    "Failed to persist organization %s",
                    org_result.organization.name,
                    exc_info=True,
                )

        progress = await self._coordinator.execute(plan)
        logger.info(
            "Execution complete: %d/%d done, %d failed",
            progress.done_count,
            progress.total,
            progress.failed_count,
        )

        verification = self._verifier.verify(goal, plan, progress, use_llm=use_llm)
        logger.info(
            "Verification: %.1f%% achieved (%s)",
            verification.achievement_pct,
            "achieved" if verification.overall_achieved else "not achieved",
        )

        return PipelineResult(
            raw_text=raw_goal_text,
            goal=goal,
            plan=plan,
            org_result=org_result,
            execution_progress=progress,
            verification=verification,
        )
