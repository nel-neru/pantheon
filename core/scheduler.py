"""
RepoCorp AI - Autonomous Scheduler

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
from core.policy.engine import ApprovalDecision, PolicyEngine

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_SECONDS = 3600


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
        self._policy = PolicyEngine(
            policy_path=self._psm.platform_home / "policy.yaml"
        )
        self._running = False
        self._cycle_count = 0
        self._log_path = self._psm.platform_home / "scheduler_log.jsonl"

    async def start(self) -> None:
        """スケジューラーを起動してループを開始する"""
        self._running = True
        logger.info("AutonomousScheduler started (interval=%ds)", self._interval)
        print(f"[Scheduler] 起動しました (間隔: {self._interval}s)")

        try:
            while self._running:
                await self._run_cycle()
                await asyncio.sleep(self._interval)
        except asyncio.CancelledError:
            pass
        finally:
            self._running = False
            print("[Scheduler] 停止しました")

    def stop(self) -> None:
        self._running = False

    async def _run_cycle(self) -> Dict[str, Any]:
        self._cycle_count += 1
        cycle_start = datetime.now(timezone.utc)
        print(f"\n[Scheduler] サイクル #{self._cycle_count} 開始 — {cycle_start.strftime('%H:%M:%S')}")

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

    async def _process_org(
        self, org_name: str, events: List[DetectedEvent]
    ) -> Dict[str, Any]:
        """対象 Org を分析して PolicyEngine でルーティングし、自動適用 or 保留を決める"""
        from uuid import uuid4

        from agents.base import AgentTask
        from agents.code_review_agent import CodeReviewAgent
        from core.models.organization import AgentSkill, ImprovementProposal, SpecialistAgent

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

        specialist = SpecialistAgent(
            name="AutoReviewer",
            skills=[AgentSkill.DEEP_RESEARCH, AgentSkill.PERFORMANCE_ANALYSIS],
        )
        agent = CodeReviewAgent(specialist)
        task = AgentTask(
            task_type="code_review",
            description=f"[Autonomous] {org_name} のコードレビュー",
            input={
                "repo_path": str(repo_path),
                "max_files": self._max_files,
            },
        )
        result = await agent.run(task)
        if not result.success:
            return {"org": org_name, "status": "analysis_failed", "error": result.error}

        suggestions = result.output.get("suggestions", [])
        sm = psm.get_org_state_manager(org)

        auto_applied = 0
        pending_for_human = 0
        rejected = 0

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
            verdict = self._policy.evaluate(prop_dict)

            if verdict.decision == ApprovalDecision.REJECT:
                rejected += 1
                logger.debug("Rejected: %s — %s", proposal.title, verdict.reason)

            elif verdict.decision == ApprovalDecision.AUTO_APPROVE:
                applied = await self._apply_proposal(org, prop_dict)
                if applied:
                    auto_applied += 1
                    print(f"    ✅ AUTO applied: {proposal.title}")
                else:
                    sm.save_improvement_proposal(proposal)
                    pending_for_human += 1

            else:
                sm.save_improvement_proposal(proposal)
                pending_for_human += 1
                logger.debug("Pending for human: %s — %s", proposal.title, verdict.reason)

        print(f"  [{org_name}] 自動: {auto_applied} / 人間待ち: {pending_for_human} / 棄却: {rejected}")
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
            skills=[AgentSkill.PROMPT_ENGINEERING],
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
