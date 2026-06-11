from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import yaml

from agents.agent_factory import AgentFactory
from agents.base import AgentResult, AgentTask, BaseAgent
from agents.code_review_agent import CodeReviewAgent
from agents.codebase_explorer_agent import _extract_json_object
from agents.generic_skill_agent import GenericSkillAgent
from agents.tool_design_agent import ToolDesignAgent
from core.events.detector import DetectedEvent, EventType
from core.goals.abstract_goal_pipeline import PipelineResult
from core.intelligence.capability_gap_analyzer import CapabilityGap
from core.knowledge.manager import KnowledgeManager
from core.loaders.agent_loader import AgentLoader
from core.models.organization import AgentSkill, Organization, SpecialistAgent
from core.orchestration.pre_task_orchestrator import TaskAnalysis
from core.policy.engine import ApprovalDecision, PolicyEngine
from core.scheduler import AutonomousScheduler
from core.state.backup_manager import BackupManager
from core.state.manager import RepoStateManager


class DummyAgent(BaseAgent):
    async def run(self, task: AgentTask) -> AgentResult:
        return AgentResult(success=True)


def _proposal(
    *, priority: str = "low", category: str = "style", file_path: str = "src/app.py"
) -> dict[str, str]:
    return {
        "id": "proposal-1",
        "priority": priority,
        "category": category,
        "file_path": file_path,
        "title": "PDCA regression",
        "description": "Regression fixture",
    }


def test_save_execution_knowledge_uses_stored_manager(tmp_path: Path):
    agent = DummyAgent(
        SpecialistAgent(
            name="KnowledgeAgent",
            skills=[AgentSkill.DEEP_RESEARCH, AgentSkill.TOOL_INTEGRATION],
        )
    )
    agent.knowledge_manager = KnowledgeManager(tmp_path)

    insight_id = agent._save_execution_knowledge(
        None,
        AgentResult(success=True, thinking_process="learned", execution_log="done"),
        AgentTask(task_type="review", description="Inspect repo"),
    )

    assert insight_id is not None
    assert agent.knowledge_manager.count() == 1


def test_pipeline_result_summary_keeps_combined_lines():
    result = PipelineResult(
        raw_text="goal",
        goal=SimpleNamespace(description="Improve docs", goal_type="documentation", scale="small"),
        plan=SimpleNamespace(),
        org_result=SimpleNamespace(organization=SimpleNamespace(name="DocsOrg"), is_new=True),
        execution_progress=SimpleNamespace(done_count=2, total=3, failed_count=1),
        verification=SimpleNamespace(
            overall_achieved=False,
            achievement_pct=66.7,
            recommendations=[],
        ),
    )

    summary = result.summary()

    assert "Organization: DocsOrg (新規)" in summary
    assert "タスク: 2/3 完了 (失敗: 1)" in summary
    assert "達成度: 66.7% (⚠️ 未達成)" in summary


def test_scheduler_persists_auto_applied_proposals(tmp_path: Path, monkeypatch):
    repo_path = tmp_path / "repo"
    repo_path.mkdir()

    scheduler = AutonomousScheduler(platform_home=tmp_path)
    org = Organization(name="DemoOrg", purpose="Test org", target_repo_path=str(repo_path))
    scheduler._psm.save_organization(org)

    suggestion = {
        "title": "Tidy comments",
        "description": "Clarify comments",
        "file_path": "src/app.py",
        "priority": "low",
        "category": "comment",
        "expected_impact": "Better readability",
    }
    monkeypatch.setattr(
        CodeReviewAgent,
        "run",
        AsyncMock(return_value=AgentResult(success=True, output={"suggestions": [suggestion]})),
    )
    monkeypatch.setattr(scheduler, "_apply_proposal", AsyncMock(return_value=True))

    result = asyncio.run(
        scheduler._process_org(
            org.name,
            [DetectedEvent(event_type=EventType.SCHEDULED, org_name=org.name, org_id=str(org.id))],
        )
    )

    improvements_dir = repo_path / ".pantheon" / "improvements"
    saved = [
        json.loads(path.read_text(encoding="utf-8")) for path in improvements_dir.glob("*.json")
    ]

    assert result["auto_applied"] == 1
    assert len(saved) == 1
    assert saved[0]["status"] == "done"
    assert scheduler._psm.get_org_state_manager(org).get_pending_improvement_proposals() == []


def test_agent_status_filters_by_org(capsys, tmp_path: Path):
    from main import cmd_agent_status

    (tmp_path / "skill_proficiency.json").write_text(
        json.dumps(
            {
                "DemoOrg:agent-1": {"security": {"proficiency": 6.0}},
                "OtherOrg:agent-2": {"testing": {"proficiency": 4.0}},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        with patch("core.platform.state.get_platform_home", return_value=tmp_path):
            loop.run_until_complete(cmd_agent_status(SimpleNamespace(org_name="DemoOrg")))
    finally:
        loop.close()
        asyncio.set_event_loop(asyncio.new_event_loop())

    out = capsys.readouterr().out
    assert "DemoOrg:agent-1" in out
    assert "OtherOrg:agent-2" not in out


def test_chat_agent_definition_falls_back_to_generic_agent():
    definition = AgentLoader().get("agent:chat_agent")
    agent = AgentFactory().create("agent:chat_agent")

    assert definition is not None
    assert definition.implementation == ""
    assert isinstance(agent, GenericSkillAgent)


def test_codebase_explorer_json_extraction_is_not_greedy():
    payload = _extract_json_object('preface {"summary": "ok"} trailing {"ignored": true}')

    assert payload == {"summary": "ok"}


def test_tool_design_json_extraction_is_not_greedy():
    gap = CapabilityGap(
        gap_id="gap:test",
        pattern_key="pattern",
        description="desc",
        suggested_type="tool",
        suggested_name="DependencyGraphBuilder",
        rationale="why",
    )
    agent = ToolDesignAgent(llm_client=None)

    payload = agent._extract_json_object('{"class_name": "One"} trailing {"class_name": "Two"}')

    assert payload == {"class_name": "One"}
    assert agent.design(gap).class_name == "DependencyGraphBuilder"


def test_recent_decisions_are_sorted_by_timestamp(tmp_path: Path):
    manager = RepoStateManager(tmp_path, "StateOrg")
    (manager.decisions_dir / "z-old.json").write_text(
        json.dumps(
            {
                "id": "old",
                "timestamp": "2024-01-01T00:00:00+00:00",
                "title": "Old",
                "content": "old",
                "made_by": "tester",
                "tags": [],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (manager.decisions_dir / "a-new.json").write_text(
        json.dumps(
            {
                "id": "new",
                "timestamp": "2025-01-01T00:00:00+00:00",
                "title": "New",
                "content": "new",
                "made_by": "tester",
                "tags": [],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    decisions = manager.get_recent_decisions(limit=2)

    assert [decision["id"] for decision in decisions] == ["new", "old"]


def test_backup_manager_uses_relative_path_keys_to_avoid_collisions(tmp_path: Path):
    manager = BackupManager(platform_home=tmp_path)
    source_a = tmp_path / "dir_a" / "source.txt"
    source_b = tmp_path / "dir_b" / "source.txt"
    source_a.parent.mkdir()
    source_b.parent.mkdir()
    source_a.write_text("a", encoding="utf-8")
    source_b.write_text("b", encoding="utf-8")

    backup_a = manager.backup_now(source_a)
    backup_b = manager.backup_now(source_b)

    assert backup_a.name != backup_b.name
    assert backup_a.name.startswith("dir_a__source.txt_")
    assert backup_b.name.startswith("dir_b__source.txt_")
    assert len(manager.list_backups(source_a)) == 1
    assert len(manager.list_backups(source_b)) == 1


def test_task_analysis_to_dict_includes_spawn_spec():
    analysis = TaskAnalysis(
        task_type="code_review",
        description="Inspect code",
        spawn_new_agent=True,
        spawn_spec={"name": "OnDemandReviewer"},
    )

    payload = analysis.to_dict()

    assert payload["spawn_spec"] == {"name": "OnDemandReviewer"}


def test_policy_engine_category_matching_requires_exact_match(tmp_path: Path):
    policy_path = tmp_path / "policy.yaml"
    policy_path.write_text(
        yaml.safe_dump(
            {
                "version": "1.0",
                "auto_reject": {
                    "conditions": {"empty_file_path": False, "disabled_categories": []}
                },
                "human_required": {
                    "conditions": {
                        "min_priority": "high",
                        "categories": ["security"],
                        "file_patterns": [],
                    }
                },
                "auto_approve": {
                    "conditions": {
                        "max_priority": "low",
                        "allowed_categories": ["security_review"],
                        "forbidden_patterns": [],
                    }
                },
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )

    verdict = PolicyEngine(policy_path=policy_path).evaluate(_proposal(category="security_review"))

    assert verdict.decision == ApprovalDecision.AUTO_APPROVE
