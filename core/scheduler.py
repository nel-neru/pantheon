"""
Pantheon - Autonomous Scheduler

ユーザー指示なしに改善サイクルを自律実行するスケジューラー。
EventDetector でイベントを検知 → PolicyEngine でルーティング → 自動適用 or 通知 のループを回す。

設計方針:
  - 人間起点とAI起点で「同一フロー」を通る（PolicyEngine 経由で必ず判定）
  - 自動適用は PolicyEngine が AUTO_APPROVE した提案のみ
  - HUMAN_REQUIRED な提案は pending のまま保持（UIで確認）
  - ループは asyncio で非同期実行
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.events.detector import DetectedEvent, EventDetector
from core.policy.engine import ApprovalDecision, OrgBoundaryContext, PolicyEngine
from core.runtime.claude_code import ClaudeRateLimitedError
from core.runtime.rate_limit import DEFAULT_BACKOFF, MAX_BACKOFF, RateLimitInfo
from core.runtime.usage_gate import RateLimitGate

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_SECONDS = 3600
# レート制限 pause 中の sleep チャンク（stop() への即応性を保つ）。
PAUSE_SLEEP_CHUNK_SECONDS = 60.0


class AutonomousScheduler:
    """
    自律改善ループを管理するスケジューラー。

    動作フロー:
    1. EventDetector で全 Org を走査
    2. イベントのある Org に対してコード分析を実行
    3. 生成された提案を PolicyEngine に通す
    4. AUTO_APPROVE → 自動適用
       HUMAN_REQUIRED → pending に保留（UIで人間が判断）
       REJECT → 自動棄却
    5. interval 秒待って繰り返す
    """

    def __init__(
        self,
        platform_home: Optional[Path] = None,
        interval_seconds: int = DEFAULT_INTERVAL_SECONDS,
        max_files_per_org: int = 10,
        **_kwargs: Any,
    ):
        from core.platform.state import PlatformStateManager

        self._psm = PlatformStateManager(platform_home)
        self._interval = interval_seconds
        self._max_files = max_files_per_org
        self._detector = EventDetector(platform_home=self._psm.platform_home)
        self._policy = PolicyEngine(policy_path=self._psm.platform_home / "policy.yaml")
        self._running = False
        self._cycle_count = 0
        self._gate = RateLimitGate()
        self._log_path = self._psm.platform_home / "scheduler_log.jsonl"

    async def start(self) -> None:
        """スケジューラーを起動してループを開始する"""
        self._running = True
        logger.info("AutonomousScheduler started (interval=%ds)", self._interval)
        print(f"[Scheduler] 起動しました (間隔: {self._interval}s)")

        try:
            while self._running:
                # 他プロセス（content daemon 等）が検知した制限も gate 経由で共有される。
                info = self._gate.current()
                if info is not None:
                    await self._pause_until_reset(info)
                    continue
                try:
                    await self._run_cycle()
                except ClaudeRateLimitedError as exc:
                    await self._pause_until_reset(exc.info)
                    continue
                await asyncio.sleep(self._interval)
        except asyncio.CancelledError:
            pass
        finally:
            self._running = False
            print("[Scheduler] 停止しました")

    def stop(self) -> None:
        self._running = False

    async def _pause_until_reset(self, info: RateLimitInfo) -> None:
        """レート制限の reset 時刻まで pause し、窓が開いたら自動 resume する。"""
        now = datetime.now(timezone.utc)
        reset_at = info.reset_at or (now + DEFAULT_BACKOFF)
        reset_at = min(max(reset_at, now), now + MAX_BACKOFF)
        logger.info("AutonomousScheduler paused (rate limit) — resumes at %s", reset_at.isoformat())
        print(f"[Scheduler] レート制限を検知 — {reset_at.isoformat()} まで待機（解除後に自動再開）")
        while self._running:
            remaining = (reset_at - datetime.now(timezone.utc)).total_seconds()
            if remaining <= 0:
                break
            await asyncio.sleep(min(PAUSE_SLEEP_CHUNK_SECONDS, remaining))
        if self._running:
            logger.info("AutonomousScheduler resumed after rate-limit window")
            print("[Scheduler] レート制限解除 — 自動再開します")

    async def _run_cycle(self) -> Dict[str, Any]:
        self._cycle_count += 1
        cycle_start = datetime.now(timezone.utc)
        print(
            f"\n[Scheduler] サイクル #{self._cycle_count} 開始 — {cycle_start.strftime('%H:%M:%S')}"
        )

        events = self._detector.detect_all()
        triggered_orgs = {e.org_name for e in events}

        if not triggered_orgs:
            print("[Scheduler] イベントなし — スキップ")
            return {"cycle": self._cycle_count, "triggered_orgs": 0}

        print(f"[Scheduler] {len(triggered_orgs)} Org でイベント検知: {', '.join(triggered_orgs)}")

        results: List[Dict[str, Any]] = []
        for org_name in triggered_orgs:
            result = await self._process_org(org_name, events)
            results.append(result)

        summary = {
            "cycle": self._cycle_count,
            "triggered_orgs": len(triggered_orgs),
            "results": results,
            "started_at": cycle_start.isoformat(),
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }
        self._write_log(summary)
        return summary

    async def _process_org(self, org_name: str, events: List[DetectedEvent]) -> Dict[str, Any]:
        """対象 Org を分析して PolicyEngine でルーティングし、自動適用 or 保留を決める"""
        from uuid import uuid4

        from agents.base import AgentTask
        from agents.orchestrator_agent import OrchestratorAgent
        from core.models.organization import ImprovementProposal

        psm = self._psm
        org = psm.load_organization_by_name(org_name)
        if not org:
            return {"org": org_name, "status": "not_found"}

        org_events = [e for e in events if e.org_name == org_name]
        event_types = [e.event_type.value for e in org_events]
        print(f"  [{org_name}] イベント: {event_types}")

        repo_path = Path(org.target_repo_path) if org.target_repo_path else None
        if not repo_path or not repo_path.exists():
            return {"org": org_name, "status": "no_repo"}

        # 自律デーモンの分析も中央 OrchestratorAgent（PreTaskOrchestrator）経由にし、
        # パターン学習を蓄積させる（従来は CodeReviewAgent を直接呼んでいた）。
        task = AgentTask(
            task_type="code_review",
            description=f"[Autonomous] {org_name} のコードレビュー",
            input={
                "repo_path": str(repo_path),
                "max_files": self._max_files,
            },
        )
        result = await OrchestratorAgent.create().run(task)
        if not result.success:
            return {"org": org_name, "status": "analysis_failed", "error": result.error}

        suggestions = result.output.get("suggestions", [])
        sm = psm.get_org_state_manager(org)

        auto_applied = 0
        pending_for_human = 0
        rejected = 0

        # 自律適用は人間確認を挟まないため、external 組織の境界ガードはここが最重要。
        # ワークスペース外へ脱出する提案が silent に AUTO_APPROVE 適用されるのを防ぐ。
        org_context = OrgBoundaryContext(
            isolation_level=getattr(org, "isolation_level", "standard"),
            allowed_path_scope=getattr(org, "allowed_path_scope", []),
        )

        for s in suggestions:
            proposal = ImprovementProposal(
                review_id=uuid4(),
                priority=s.get("priority", "medium"),
                category=s.get("category", "general"),
                title=s.get("title", "改善提案"),
                description=s.get("description", ""),
                file_path=s.get("file_path", ""),
                expected_impact=s.get("expected_impact", ""),
            )
            prop_dict = json.loads(proposal.model_dump_json())
            verdict = self._policy.evaluate(prop_dict, org_context=org_context)

            if verdict.decision == ApprovalDecision.REJECT:
                rejected += 1
                logger.debug("Rejected: %s — %s", proposal.title, verdict.reason)

            elif verdict.decision == ApprovalDecision.AUTO_APPROVE:
                applied = await self._apply_proposal(org, prop_dict)
                if applied:
                    proposal.status = "done"
                    sm.save_improvement_proposal(proposal)
                    auto_applied += 1
                    print(f"    ✅ AUTO applied: {proposal.title}")
                else:
                    proposal.status = "pending"
                    sm.save_improvement_proposal(proposal)
                    pending_for_human += 1

            else:
                sm.save_improvement_proposal(proposal)
                pending_for_human += 1
                logger.debug("Pending for human: %s — %s", proposal.title, verdict.reason)

        print(
            f"  [{org_name}] 自動: {auto_applied} / 人間待ち: {pending_for_human} / 棄却: {rejected}"
        )
        return {
            "org": org_name,
            "status": "ok",
            "auto_applied": auto_applied,
            "pending_for_human": pending_for_human,
            "rejected": rejected,
        }

    async def _apply_proposal(self, org, prop_dict: Dict[str, Any]) -> bool:
        """提案を実際に適用する。"""
        from agents.base import AgentTask
        from agents.improvement_executor_agent import ImprovementExecutorAgent
        from core.models.organization import AgentSkill, SpecialistAgent

        specialist = SpecialistAgent(
            name="AutoExecutor",
            skills=[AgentSkill.PROMPT_ENGINEERING, AgentSkill.TOOL_INTEGRATION],
        )
        executor = ImprovementExecutorAgent(specialist)
        task = AgentTask(
            task_type="improvement_execution",
            description=f"[Auto] {prop_dict.get('title')}",
            input={
                "repo_path": org.target_repo_path,
                "suggestion": prop_dict,
            },
        )
        result = await executor.run(task)
        return result.success

    def _write_log(self, data: Dict[str, Any]) -> None:
        with open(self._log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(data, ensure_ascii=False) + "\n")

    def get_recent_logs(self, n: int = 10) -> List[Dict[str, Any]]:
        if not self._log_path.exists():
            return []
        lines = self._log_path.read_text(encoding="utf-8").strip().splitlines()
        return [json.loads(line) for line in lines[-n:] if line]
