"""Regression tests protecting stable API contracts."""

from __future__ import annotations

from pathlib import Path

import yaml

from core.goals.abstract_goal_pipeline import AbstractGoalPipeline
from core.goals.goal_decomposer import GoalDecomposer
from core.goals.goal_parser import GoalParser
from core.goals.org_instantiator import OrgInstantiator
from core.hierarchy.org_designer import OrganizationDesigner
from core.intelligence.capability_registry import CapabilityEntry, CapabilityRegistry
from core.models.organization import ImprovementProposal
from core.orchestration.orchestration_pattern_store import OrchestrationPatternStore, PatternRecord
from core.orchestration.pre_task_orchestrator import OrchestrationPattern, TaskAnalysis
from core.policy.engine import ApprovalDecision, PolicyEngine
from core.state.manager import RepoStateManager


def _proposal(priority="low", category="style", file_path="src/utils.py"):
    return {
        "id": "stable-id",
        "priority": priority,
        "category": category,
        "file_path": file_path,
        "title": "Stable proposal",
        "description": "Regression fixture",
    }


class TestPolicyEngineRegression:
    def test_auto_approve_low_priority_non_critical(self):
        verdict = PolicyEngine().evaluate(_proposal(priority="low", category="comment", file_path="src/docs.py"))

        assert verdict.decision == ApprovalDecision.AUTO_APPROVE
        assert verdict.rule_name == "auto_approve"

    def test_human_required_for_critical_files(self):
        verdict = PolicyEngine().evaluate(_proposal(file_path="core/models/organization.py"))

        assert verdict.decision == ApprovalDecision.HUMAN_REQUIRED
        assert verdict.rule_name == "human_required.file_patterns"

    def test_reject_disabled_category(self, tmp_path):
        policy_path = tmp_path / "policy.yaml"
        policy_path.write_text(
            yaml.safe_dump(
                {
                    "version": "1.0",
                    "auto_reject": {"conditions": {"empty_file_path": True, "disabled_categories": ["self_extension"]}},
                    "human_required": {"conditions": {"min_priority": "high", "categories": [], "file_patterns": []}},
                    "auto_approve": {"conditions": {"max_priority": "low", "allowed_categories": ["comment"], "forbidden_patterns": []}},
                },
                allow_unicode=True,
            ),
            encoding="utf-8",
        )

        verdict = PolicyEngine(policy_path=policy_path).evaluate(
            _proposal(category="self_extension", file_path="agents/new_agent.py")
        )

        assert verdict.decision == ApprovalDecision.REJECT
        assert verdict.rule_name == "auto_reject.disabled_categories"


class TestStateManagerRegression:
    def test_proposal_roundtrip_json(self, tmp_path):
        manager = RepoStateManager(tmp_path, "StateOrg")
        proposal = ImprovementProposal(
            review_id="00000000-0000-0000-0000-000000000001",
            title="Roundtrip",
            description="Roundtrip proposal",
            file_path="src/app.py",
        )

        manager.save_improvement_proposal(proposal)
        restored = manager.get_pending_proposals()[0]

        assert restored.title == "Roundtrip"
        assert restored.file_path == "src/app.py"
        assert restored.status == "proposed"

    def test_decision_format_stable(self, tmp_path):
        manager = RepoStateManager(tmp_path, "StateOrg")
        manager.record_decision("decision-1", "Title", "Body", "Tester", tags=["tag-a"])

        decision = manager.get_recent_decisions(limit=1)[0]

        assert set(decision) == {"id", "timestamp", "title", "content", "made_by", "tags"}
        assert decision["tags"] == ["tag-a"]

    def test_get_pending_returns_only_proposed(self, tmp_path):
        manager = RepoStateManager(tmp_path, "StateOrg")
        keep = ImprovementProposal(review_id="00000000-0000-0000-0000-000000000002", title="Keep", description="d")
        done = ImprovementProposal(review_id="00000000-0000-0000-0000-000000000003", title="Done", description="d")
        manager.save_improvement_proposal(keep)
        manager.save_improvement_proposal(done)
        manager.update_proposal_status(str(done.id), "done")

        pending = manager.get_pending_proposals()

        assert [proposal.title for proposal in pending] == ["Keep"]


class TestOrchestrationRegression:
    def test_task_analysis_fields_stable(self):
        analysis = TaskAnalysis(task_type="code_review", description="Inspect code")

        assert set(analysis.to_dict()) == {
            "task_type",
            "description",
            "complexity",
            "recommended_pattern",
            "recommended_agent_ids",
            "spawn_new_agent",
            "spawn_spec",
            "research_notes",
            "estimated_tokens",
            "confidence",
            "created_at",
        }

    def test_pattern_store_serialization_stable(self, tmp_path):
        store = OrchestrationPatternStore(platform_home=tmp_path)
        store.record(
            PatternRecord(
                task_type="code_review",
                pattern=OrchestrationPattern.REVIEW_LOOP,
                agent_ids=["agent:reviewer"],
                success=True,
            )
        )

        payload = yaml.safe_load((tmp_path / "orchestration_patterns.json").read_text(encoding="utf-8"))

        assert set(payload) == {"version", "updated_at", "records"}
        assert set(payload["records"][0]) == {
            "task_type",
            "pattern",
            "agent_ids",
            "success",
            "execution_time_ms",
            "quality_score",
            "notes",
            "timestamp",
        }

    def test_capability_registry_list_format_stable(self, tmp_path):
        registry = CapabilityRegistry(platform_home=tmp_path)
        registry.register(
            CapabilityEntry(
                id="agent:reviewer",
                name="Reviewer",
                capability_type="agent",
                description="Stable reviewer",
                skills=["codebase_exploration", "deep_research"],
            )
        )

        entries = registry.list_all("agent")
        data = entries[0].to_dict()

        assert entries[0].name == "Reviewer"
        assert set(data) == {
            "id",
            "name",
            "capability_type",
            "description",
            "source_file",
            "skills",
            "added_at",
            "usage_count",
            "last_used",
            "is_active",
        }


class TestGoalPipelineRegression:
    def test_goal_parser_output_schema(self):
        payload = GoalParser().parse("テストカバレッジを上げたい").to_dict()

        assert set(payload) == {
            "goal_id",
            "raw_text",
            "goal_type",
            "scope",
            "description",
            "success_criteria",
            "constraints",
            "suggested_categories",
            "scale",
            "domain",
            "features",
            "parsed_at",
        }

    def test_goal_decomposer_output_schema(self):
        goal = GoalParser().parse("セキュリティを改善したい")
        payload = GoalDecomposer().decompose(goal).to_dict()

        assert set(payload) == {
            "plan_id",
            "goal_id",
            "goal_description",
            "epics",
            "total_tasks",
            "executable_tasks",
            "created_at",
        }
        assert set(payload["epics"][0]["stories"][0]["tasks"][0]) == {
            "task_id",
            "title",
            "description",
            "required_skills",
            "agent_type",
            "dependencies",
            "success_criteria",
            "estimated_tokens",
            "is_executable",
        }

    def test_pipeline_result_schema(self, tmp_path):
        pipeline = AbstractGoalPipeline(
            instantiator=OrgInstantiator(org_designer=OrganizationDesigner(platform_home=tmp_path))
        )
        loop = __import__("asyncio").new_event_loop()
        try:
            __import__("asyncio").set_event_loop(loop)
            result = loop.run_until_complete(pipeline.run("ドキュメントを整備したい"))
        finally:
            loop.close()
            __import__("asyncio").set_event_loop(__import__("asyncio").new_event_loop())

        assert hasattr(result, "goal")
        assert hasattr(result, "plan")
        assert hasattr(result, "org_result")
        assert hasattr(result, "execution_progress")
        assert hasattr(result, "verification")
        assert isinstance(result.summary(), str)
