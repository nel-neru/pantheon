"""Integration tests for Sprint 6 flows."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from agents.base import AgentResult, AgentTask
from agents.code_review_agent import CodeImprovementSuggestion, CodeReviewAgent
from agents.conversation_agent import ConversationAgent
from agents.improvement_executor_agent import ImprovementExecutorAgent
from core.goals.abstract_goal_pipeline import AbstractGoalPipeline
from core.goals.goal_decomposer import GoalDecomposer
from core.goals.goal_parser import GoalParser, GoalType
from core.goals.org_instantiator import OrgInstantiator
from core.hierarchy.org_designer import OrganizationDesigner
from core.events.detector import DetectedEvent, EventType
from core.intelligence.capability_registry import CapabilityEntry, CapabilityRegistry
from core.models.organization import AgentSkill, ImprovementProposal, Organization, SpecialistAgent
from core.monitoring.proactive_notifier import ProactiveNotifier
from core.orchestration.dynamic_agent_spawner import DynamicAgentSpawner, SpawnRequest
from core.orchestration.orchestration_pattern_store import OrchestrationPatternStore
from core.orchestration.pre_task_orchestrator import OrchestrationPattern, PreTaskOrchestrator, TaskAnalysis
from core.orchestration.task_router import TaskRouter
from core.policy.engine import ApprovalDecision, PolicyEngine
from core.scheduler import AutonomousScheduler
from core.state.manager import RepoStateManager
from core.ui.rich_dashboard import RichDashboard


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        loop.close()
        asyncio.set_event_loop(asyncio.new_event_loop())


def _make_specialist(name: str = "Reviewer") -> SpecialistAgent:
    return SpecialistAgent(
        name=name,
        skills=[AgentSkill.CODEBASE_EXPLORATION, AgentSkill.DEEP_RESEARCH],
    )


def _make_suggestion(
    title: str,
    *,
    file_path: str = "src/module.py",
    priority: str = "low",
    category: str = "style",
) -> CodeImprovementSuggestion:
    return CodeImprovementSuggestion(
        title=title,
        description=f"{title} を適用する",
        file_path=file_path,
        priority=priority,
        category=category,
        expected_impact="品質が向上する",
    )


def _proposal_from_suggestion(suggestion: CodeImprovementSuggestion) -> ImprovementProposal:
    return ImprovementProposal(
        review_id=uuid4(),
        priority=suggestion.priority,
        category=suggestion.category,
        title=suggestion.title,
        description=suggestion.description,
        file_path=suggestion.file_path,
        expected_impact=suggestion.expected_impact,
        status="proposed",
    )


def _register_agent(registry: CapabilityRegistry, agent_id: str, name: str, skills: list[str]) -> None:
    registry.register(
        CapabilityEntry(
            id=agent_id,
            name=name,
            capability_type="agent",
            description=f"{name} integration test agent",
            skills=skills,
        )
    )


class TestCodeReviewToProposalFlow:
    def test_code_review_agent_produces_review(self, tmp_path):
        (tmp_path / "service.py").write_text("def run():\n    return 'ok'\n", encoding="utf-8")
        agent = CodeReviewAgent(_make_specialist())
        suggestions = [_make_suggestion("型ヒントを追加")]

        with patch.object(CodeReviewAgent, "_generate_suggestions", new=AsyncMock(return_value=suggestions)):
            result = _run(
                agent.run(
                    AgentTask(
                        task_type="code_review",
                        description="review repo",
                        input={"repo_path": str(tmp_path)},
                    )
                )
            )

        assert result.success is True
        assert result.output["files_reviewed"] >= 1
        assert result.output["suggestions"][0]["title"] == "型ヒントを追加"

    def test_review_leads_to_proposals(self):
        suggestions = [
            _make_suggestion("ドキュメント更新", category="documentation"),
            _make_suggestion("認証を強化", priority="high", category="security", file_path="core/auth.py"),
        ]

        proposals = [_proposal_from_suggestion(suggestion) for suggestion in suggestions]

        assert len(proposals) == 2
        assert proposals[0].category == "documentation"
        assert proposals[1].priority == "high"
        assert proposals[1].file_path == "core/auth.py"

    def test_proposals_can_be_saved_and_retrieved(self, tmp_path):
        manager = RepoStateManager(tmp_path, "TestOrg")
        proposal = _proposal_from_suggestion(_make_suggestion("軽微な整形"))

        assert manager.save_proposal(proposal) is True
        pending = manager.get_pending_proposals()

        assert len(pending) == 1
        assert pending[0].title == "軽微な整形"

    def test_policy_engine_filters_proposals(self):
        engine = PolicyEngine()
        low_risk = _proposal_from_suggestion(_make_suggestion("コメント整備", category="comment"))
        high_risk = _proposal_from_suggestion(
            _make_suggestion("秘密情報の扱いを修正", priority="high", category="security", file_path="core/secrets.py")
        )

        low_verdict = engine.evaluate(low_risk.model_dump(mode="json"))
        high_verdict = engine.evaluate(high_risk.model_dump(mode="json"))

        assert low_verdict.decision == ApprovalDecision.AUTO_APPROVE
        assert high_verdict.decision == ApprovalDecision.HUMAN_REQUIRED

    def test_full_review_to_decision_flow(self, tmp_path):
        (tmp_path / "module.py").write_text("print('hello')\n", encoding="utf-8")
        manager = RepoStateManager(tmp_path, "DecisionOrg")
        engine = PolicyEngine()
        agent = CodeReviewAgent(_make_specialist())
        suggestions = [
            _make_suggestion("コメント整備", category="comment"),
            _make_suggestion("認証境界の見直し", priority="high", category="security", file_path="core/auth.py"),
        ]

        with patch.object(CodeReviewAgent, "_generate_suggestions", new=AsyncMock(return_value=suggestions)):
            result = _run(
                agent.run(
                    AgentTask(
                        task_type="code_review",
                        description="review repo",
                        input={"repo_path": str(tmp_path)},
                    )
                )
            )

        proposals = [_proposal_from_suggestion(CodeImprovementSuggestion(**item)) for item in result.output["suggestions"]]
        for proposal in proposals:
            manager.save_proposal(proposal)

        decisions = {proposal.title: engine.evaluate(proposal.model_dump(mode="json")) for proposal in proposals}
        auto_titles = [title for title, verdict in decisions.items() if verdict.decision == ApprovalDecision.AUTO_APPROVE]
        human_titles = [title for title, verdict in decisions.items() if verdict.decision == ApprovalDecision.HUMAN_REQUIRED]

        assert auto_titles == ["コメント整備"]
        assert human_titles == ["認証境界の見直し"]

        auto_proposal = next(proposal for proposal in proposals if proposal.title == auto_titles[0])
        assert manager.update_proposal_status(str(auto_proposal.id), "done") is True
        manager.record_decision("decision-1", auto_titles[0], "auto approved", "PolicyEngine")

        pending = manager.get_pending_proposals()
        recent_decisions = manager.get_recent_decisions()

        assert len(pending) == 1
        assert pending[0].title == "認証境界の見直し"
        assert recent_decisions[0]["title"] == "コメント整備"

    def test_mocked_pdca_workflow_applies_low_risk_change(self, tmp_path, monkeypatch):
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        (repo_path / "src").mkdir()
        (repo_path / "src" / "app.py").write_text("print('hello')\n", encoding="utf-8")

        scheduler = AutonomousScheduler(platform_home=tmp_path, max_files_per_org=5)
        org = Organization(name="PDCA Org", purpose="Test end-to-end flow", target_repo_path=str(repo_path))
        scheduler._psm.save_organization(org)

        suggestion = {
            "title": "Comment cleanup",
            "description": "Improve comments for clarity",
            "file_path": "src/app.py",
            "priority": "low",
            "category": "comment",
            "expected_impact": "読みやすさが向上する",
        }

        async def fake_review_run(self, task):
            assert task.task_type == "code_review"
            return AgentResult(
                success=True,
                output={"files_reviewed": 1, "suggestions": [suggestion]},
            )

        async def fake_execute_run(self, task):
            assert task.task_type == "improvement_execution"
            assert task.input["suggestion"]["title"] == "Comment cleanup"
            return AgentResult(
                success=True,
                output={
                    "change_summary": "Applied comment cleanup",
                    "branch": "pantheon/improvement-comment-cleanup",
                    "pr_url": "https://example.com/pr/42",
                },
            )

        monkeypatch.setattr(CodeReviewAgent, "run", fake_review_run)
        monkeypatch.setattr(ImprovementExecutorAgent, "run", fake_execute_run)

        result = asyncio.run(
            scheduler._process_org(
                org.name,
                [DetectedEvent(event_type=EventType.SCHEDULED, org_name=org.name, org_id=str(org.id))],
            )
        )

        saved_proposals = scheduler._psm.get_org_state_manager(org).get_pending_improvement_proposals(limit=10)
        proposal_files = list((repo_path / ".pantheon" / "improvements").glob("*.json"))

        assert result == {
            "org": "PDCA Org",
            "status": "ok",
            "auto_applied": 1,
            "pending_for_human": 0,
            "rejected": 0,
        }
        assert saved_proposals == []
        assert proposal_files
        assert "done" in proposal_files[0].read_text(encoding="utf-8")


class TestOrchestrationFlow:
    def test_pre_task_orchestrator_analyzes_task(self, tmp_path):
        registry = CapabilityRegistry(platform_home=tmp_path)
        _register_agent(registry, "agent:reviewer", "Reviewer", ["codebase_exploration", "performance_analysis"])

        analysis = PreTaskOrchestrator(capability_registry=registry).analyze(
            "code_review", "コードレビューを実行する"
        )

        assert analysis.task_type == "code_review"
        assert analysis.recommended_pattern == OrchestrationPattern.REVIEW_LOOP
        assert analysis.recommended_agent_ids == ["agent:reviewer"]

    def test_task_router_selects_agent(self, tmp_path):
        registry = CapabilityRegistry(platform_home=tmp_path)
        _register_agent(registry, "agent:security", "Security", ["tool_integration", "deep_research"])
        _register_agent(registry, "agent:writer", "Writer", ["knowledge_curation", "prompt_engineering"])

        decision = TaskRouter(capability_registry=registry).route("security_audit")

        assert decision.selected_agent_ids[0] == "agent:security"
        assert decision.fallback_used is False

    def test_dynamic_spawner_creates_agent_when_needed(self, tmp_path):
        registry = CapabilityRegistry(platform_home=tmp_path)
        _register_agent(registry, "agent:planner", "Planner", ["strategic_planning", "org_design"])
        spawner = DynamicAgentSpawner(capability_registry=registry)

        result = spawner.spawn(
            SpawnRequest(
                required_skills=["tool_integration", "deep_research"],
                purpose="security audit support",
                task_type="security_audit",
            )
        )

        assert result.success is True
        assert result.was_cached is False
        assert any(entry.id.startswith("agent:dynamic:") for entry in registry.list_agents())

    def test_orchestration_pattern_stored_after_execution(self, tmp_path):
        store = OrchestrationPatternStore(platform_home=tmp_path)
        orchestrator = PreTaskOrchestrator(pattern_store=store)
        analysis = TaskAnalysis(
            task_type="code_review",
            description="integration execution",
            recommended_pattern=OrchestrationPattern.SINGLE_AGENT,
            recommended_agent_ids=["agent:executor"],
        )
        task = AgentTask(task_type="code_review", description="integration execution")

        class FakeAgent:
            async def run(self, task):
                return AgentResult(success=True, output={"ok": True})

        result = _run(orchestrator.execute(task, analysis, agent_factory=lambda _: FakeAgent()))
        stats = store.get_stats_for_task("code_review")

        assert result.success is True
        assert len(stats) == 1
        assert stats[0].total_runs == 1
        assert stats[0].success_rate == 1.0


class TestGoalPipelineFlow:
    def test_goal_parser_to_decomposer_flow(self):
        goal = GoalParser().parse("セキュリティを強化して脆弱性を減らしたい")
        plan = GoalDecomposer().decompose(goal)

        assert goal.goal_type == GoalType.SECURITY
        assert plan.goal_id == goal.goal_id
        assert plan.total_tasks >= 1

    def test_org_instantiator_creates_org_from_goal(self, tmp_path):
        goal = GoalParser().parse("Eコマースサービスを作りたい")
        instantiator = OrgInstantiator(org_designer=OrganizationDesigner(platform_home=tmp_path))

        result = instantiator.instantiate(goal)

        assert result.organization.name
        assert result.organization.purpose == goal.description
        assert len(result.organization.get_all_agents()) >= 1

    def test_full_goal_pipeline(self, tmp_path):
        pipeline = AbstractGoalPipeline(
            instantiator=OrgInstantiator(org_designer=OrganizationDesigner(platform_home=tmp_path))
        )

        result = _run(pipeline.run("APIのセキュリティを改善したい"))

        assert result.success is True
        assert result.goal.goal_type == GoalType.SECURITY
        assert result.execution_progress.done_count == result.execution_progress.total


class TestConversationMonitoringAndUI:
    def test_conversation_agent_answers_with_history(self, tmp_path):
        class DummyKnowledgeManager:
            def search(self, keywords):
                return [{"title": f"match:{keywords[0]}", "id": "k-1"}] if keywords else []

        agent = ConversationAgent(knowledge_manager=DummyKnowledgeManager(), platform_home=tmp_path)
        response = agent.ask("危険な問題はある？", context={"known_issue_count": 3})

        assert "3件" in response.answer
        assert "pantheon analyze" in response.suggested_actions[0]
        assert agent.get_conversation_history()[0]["question"] == "危険な問題はある？"

    def test_proactive_notifier_persists_notifications(self, tmp_path):
        notifier = ProactiveNotifier(platform_home=tmp_path)
        notifications = notifier.check_org_health("Ops", current_score=20.0, previous_score=40.5)
        backlog_notifications = notifier.check_proposal_backlog("Ops", pending_count=21)

        for notification in notifications + backlog_notifications:
            notifier.save_notification(notification)

        recent = notifier.get_recent_notifications(limit=5)

        assert len(recent) == 3
        assert notifier.format_notification(recent[0]).startswith("[")
        assert {item.level for item in recent} == {"warn", "critical"}

    def test_rich_dashboard_renders_plain_text(self):
        dashboard = RichDashboard(use_rich=False)
        org = {
            "name": "PlatformOrg",
            "health_score": 76.0,
            "proposal_count": 2,
            "agent_count": 5,
            "lifecycle_stage": "active",
        }
        proposals = [
            {
                "id": "abcdef123456",
                "priority": "low",
                "category": "documentation",
                "title": "READMEを更新して最新のフローを反映する",
            }
        ]

        summary = dashboard.render_org_summary(org)
        table = dashboard.render_proposals_table(proposals)
        tree = dashboard.render_org_tree([org])

        assert "PlatformOrg" in summary
        assert "README" in table
        assert "health: 76.0" in tree
