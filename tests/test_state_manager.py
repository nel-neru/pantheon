"""Unit tests for RepoStateManager"""
import json
from uuid import uuid4

import pytest

from core.models.organization import ImprovementProposal, Organization
from core.state.manager import RepoStateManager


@pytest.fixture
def state_manager(tmp_path):
    return RepoStateManager(tmp_path, "TestOrg")


class TestRepoStateManager:
    def test_dirs_created(self, tmp_path):
        sm = RepoStateManager(tmp_path, "Org")
        assert (tmp_path / ".pantheon").exists()
        assert (tmp_path / ".pantheon" / "improvements").exists() or True  # created lazily
        assert (tmp_path / ".pantheon" / "organizations").exists()

    def test_save_and_load_state(self, state_manager):
        state_manager.save_current_state({"key": "value"})
        loaded = state_manager.load_current_state()
        assert loaded["key"] == "value"
        assert "last_updated" in loaded

    def test_save_current_state_does_not_mutate_input(self, state_manager):
        payload = {"key": "value"}

        state_manager.save_current_state(payload)

        assert payload == {"key": "value"}

    def test_save_and_list_proposals(self, state_manager):
        p = ImprovementProposal(review_id=uuid4(), title="Fix bug", description="desc")
        state_manager.save_improvement_proposal(p)
        proposals = state_manager.get_pending_improvement_proposals()
        assert len(proposals) == 1
        assert proposals[0]["title"] == "Fix bug"

    def test_done_proposals_not_listed(self, state_manager):
        p = ImprovementProposal(review_id=uuid4(), title="Fix", description="d")
        state_manager.save_improvement_proposal(p)
        state_manager.update_proposal_status(str(p.id), "done")
        proposals = state_manager.get_pending_improvement_proposals()
        assert len(proposals) == 0

    def test_active_proposals_include_proposed_pending_and_in_progress(self, state_manager):
        proposed = ImprovementProposal(review_id=uuid4(), title="Proposed", description="d")
        pending = ImprovementProposal(review_id=uuid4(), title="Pending", description="d", status="pending")
        running = ImprovementProposal(review_id=uuid4(), title="Running", description="d", status="in_progress")
        done = ImprovementProposal(review_id=uuid4(), title="Done", description="d", status="done")
        rejected = ImprovementProposal(review_id=uuid4(), title="Rejected", description="d", status="rejected")
        state_manager.save_improvement_proposal(proposed)
        state_manager.save_improvement_proposal(pending)
        state_manager.save_improvement_proposal(running)
        state_manager.save_improvement_proposal(done)
        state_manager.save_improvement_proposal(rejected)

        proposals = state_manager.get_pending_improvement_proposals(limit=10)

        assert {proposal["title"] for proposal in proposals} == {"Proposed", "Pending", "Running"}

    def test_update_proposal_status_returns_true(self, state_manager):
        p = ImprovementProposal(review_id=uuid4(), title="T", description="d")
        state_manager.save_improvement_proposal(p)
        result = state_manager.update_proposal_status(str(p.id), "in_progress")
        assert result is True

    def test_update_nonexistent_returns_false(self, state_manager):
        result = state_manager.update_proposal_status("nonexistent-id", "done")
        assert result is False

    def test_save_and_load_organization(self, state_manager, tmp_path):
        org = Organization(name="MyOrg", purpose="Test purpose")
        state_manager.save_organization(org)
        orgs = state_manager.load_organizations()
        assert len(orgs) == 1
        assert orgs[0].name == "MyOrg"
        assert orgs[0].purpose == "Test purpose"

    def test_load_organization_by_name(self, state_manager):
        org = Organization(name="UniqueOrg", purpose="purpose")
        state_manager.save_organization(org)
        found = state_manager.load_organization_by_name("UniqueOrg")
        assert found is not None
        assert found.id == org.id

    def test_load_organization_by_name_not_found(self, state_manager):
        result = state_manager.load_organization_by_name("DoesNotExist")
        assert result is None

    def test_record_and_get_decisions(self, state_manager):
        state_manager.record_decision("d1", "Decision 1", "Content here", "TestAgent")
        decisions = state_manager.get_recent_decisions()
        assert len(decisions) == 1
        assert decisions[0]["title"] == "Decision 1"

    def test_save_and_load_session_context(self, state_manager):
        state_manager.save_session_context("session-1", {"summary": "Shared work", "messages": ["hello"]})

        loaded = state_manager.load_session_context("session-1")

        assert loaded is not None
        assert loaded["session_id"] == "session-1"
        assert loaded["summary"] == "Shared work"
        assert "saved_at" in loaded

    def test_list_session_contexts(self, state_manager):
        state_manager.save_session_context("session-1", {"summary": "first"})
        state_manager.save_session_context("session-2", {"summary": "second"})

        sessions = state_manager.list_session_contexts()

        assert len(sessions) == 2
        assert {session["session_id"] for session in sessions} == {"session-1", "session-2"}
        assert all("saved_at" in session for session in sessions)

    def test_get_cross_org_state(self, state_manager, tmp_path, monkeypatch):
        from core.orchestration import task_queue as task_queue_module

        monkeypatch.setattr(task_queue_module, "get_platform_home", lambda: tmp_path / "platform-home")
        queue = task_queue_module.TaskQueue()
        queue.add_task("analyze", "CrossOrg", "共有タスク")

        state = state_manager.get_cross_org_state()

        assert state["pending_tasks"] == 1
        assert len(state["recent_tasks"]) == 1
        assert state["recent_tasks"][0]["org_name"] == "CrossOrg"

    def test_load_organizations_skips_malformed_json(self, state_manager):
        good_org = Organization(name="GoodOrg", purpose="ok")
        state_manager.save_organization(good_org)
        (state_manager.organizations_dir / "broken.json").write_text("{not json", encoding="utf-8")

        orgs = state_manager.load_organizations()

        assert [org.name for org in orgs] == ["GoodOrg"]

    def test_get_recent_decisions_places_invalid_timestamp_last(self, state_manager):
        state_manager.record_decision("d1", "Valid", "Content", "Tester")
        invalid = state_manager.decisions_dir / "broken.json"
        invalid.write_text(
            json.dumps(
                {
                    "id": "broken",
                    "timestamp": "not-a-timestamp",
                    "title": "Broken",
                    "content": "bad",
                    "made_by": "Tester",
                    "tags": [],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        decisions = state_manager.get_recent_decisions(limit=2)

        assert [decision["id"] for decision in decisions] == ["d1", "broken"]
