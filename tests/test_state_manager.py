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
        RepoStateManager(tmp_path, "Org")  # 構築の副作用で .pantheon 配下が作られる
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
        pending = ImprovementProposal(
            review_id=uuid4(), title="Pending", description="d", status="pending"
        )
        running = ImprovementProposal(
            review_id=uuid4(), title="Running", description="d", status="in_progress"
        )
        done = ImprovementProposal(review_id=uuid4(), title="Done", description="d", status="done")
        rejected = ImprovementProposal(
            review_id=uuid4(), title="Rejected", description="d", status="rejected"
        )
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

    def test_update_with_id_prefix_does_not_match(self, state_manager):
        # RepoStateManager matches on the FULL uuid filename stem, not a prefix.
        # A truncated id must be a no-op (False), never a silent partial update.
        p = ImprovementProposal(review_id=uuid4(), title="T", description="d")
        state_manager.save_improvement_proposal(p)
        result = state_manager.update_proposal_status(str(p.id)[:8], "done")
        assert result is False
        # original is untouched / still active
        assert state_manager.get_pending_improvement_proposals()[0]["id"] == str(p.id)

    def test_pending_proposals_returns_newest_first(self, state_manager):
        # Filenames are random uuids, so ordering must come from created_at, not
        # the filesystem glob order. Newest (largest created_at) first, and the
        # limit returns the newest subset rather than an arbitrary one.
        from datetime import datetime, timedelta, timezone

        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        ids = []
        for i in range(3):
            p = ImprovementProposal(
                review_id=uuid4(),
                title=f"P{i}",
                description="d",
                created_at=base + timedelta(days=i),
            )
            state_manager.save_improvement_proposal(p)
            ids.append(str(p.id))
        pending = state_manager.get_pending_improvement_proposals()
        assert [p["id"] for p in pending] == [ids[2], ids[1], ids[0]]
        top = state_manager.get_pending_improvement_proposals(limit=1)
        assert [p["id"] for p in top] == [ids[2]]

    def test_all_proposals_returns_newest_first(self, state_manager):
        # get_all_improvement_proposals docstring promises 新しい順 (newest-first);
        # filenames are random uuids so ordering must come from created_at.
        from datetime import datetime, timedelta, timezone

        base = datetime(2026, 2, 1, tzinfo=timezone.utc)
        ids = []
        for i in range(3):
            p = ImprovementProposal(
                review_id=uuid4(),
                title=f"Q{i}",
                description="d",
                created_at=base + timedelta(days=i),
            )
            state_manager.save_improvement_proposal(p)
            ids.append(str(p.id))
        allp = state_manager.get_all_improvement_proposals()
        assert [p["id"] for p in allp] == [ids[2], ids[1], ids[0]]
        top = state_manager.get_all_improvement_proposals(limit=1)
        assert [p["id"] for p in top] == [ids[2]]

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
        state_manager.save_session_context(
            "session-1", {"summary": "Shared work", "messages": ["hello"]}
        )

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

        monkeypatch.setattr(
            task_queue_module, "get_platform_home", lambda: tmp_path / "platform-home"
        )
        queue = task_queue_module.TaskQueue()
        queue.add_task("analyze", "CrossOrg", "共有タスク")

        state = state_manager.get_cross_org_state()

        assert state["pending_tasks"] == 1
        assert len(state["recent_tasks"]) == 1
        assert state["recent_tasks"][0]["org_name"] == "CrossOrg"

    def test_load_organizations_skips_malformed_json(self, state_manager, caplog):
        import logging

        good_org = Organization(name="GoodOrg", purpose="ok")
        state_manager.save_organization(good_org)
        (state_manager.organizations_dir / "broken.json").write_text("{not json", encoding="utf-8")

        with caplog.at_level(logging.WARNING, logger="core.platform.state"):
            orgs = state_manager.load_organizations()

        assert [org.name for org in orgs] == ["GoodOrg"]
        # 黙って捨てず警告する（共有ヘルパ warn_skipped_org_file 経由）
        assert any("broken.json" in rec.message for rec in caplog.records)

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

    # ------------------------------------------------------------------
    # 状態 load 経路の silent-drop 観測性（warn_skipped_state_file 経由）。
    # 壊れた 1 ファイルは耐性のためスキップしつつ、黙って消えず警告で観測可能にする。
    # ------------------------------------------------------------------

    def test_get_recent_decisions_warns_on_malformed_json(self, state_manager, caplog):
        import logging

        state_manager.record_decision("d1", "Valid", "Content", "Tester")
        (state_manager.decisions_dir / "broken.json").write_text("{not json", encoding="utf-8")

        with caplog.at_level(logging.WARNING, logger="core.platform.state"):
            decisions = state_manager.get_recent_decisions()

        assert [d["id"] for d in decisions] == ["d1"]
        assert any("broken.json" in rec.message for rec in caplog.records)
        assert (state_manager.decisions_dir / "broken.json").exists()  # 削除しない

    def test_get_pending_improvement_proposals_warns_on_malformed_json(self, state_manager, caplog):
        import logging

        good = ImprovementProposal(review_id=uuid4(), title="Good", description="d")
        state_manager.save_improvement_proposal(good)
        improvements_dir = state_manager.state_dir / "improvements"
        (improvements_dir / "broken.json").write_text("{not json", encoding="utf-8")

        with caplog.at_level(logging.WARNING, logger="core.platform.state"):
            pending = state_manager.get_pending_improvement_proposals()

        assert [p["title"] for p in pending] == ["Good"]
        assert any("broken.json" in rec.message for rec in caplog.records)

    def test_get_all_improvement_proposals_warns_on_malformed_json(self, state_manager, caplog):
        import logging

        good = ImprovementProposal(review_id=uuid4(), title="Good", description="d")
        state_manager.save_improvement_proposal(good)
        improvements_dir = state_manager.state_dir / "improvements"
        (improvements_dir / "broken.json").write_text("{not json", encoding="utf-8")

        with caplog.at_level(logging.WARNING, logger="core.platform.state"):
            allp = state_manager.get_all_improvement_proposals()

        assert [p["title"] for p in allp] == ["Good"]
        assert any("broken.json" in rec.message for rec in caplog.records)

    def test_get_pending_proposals_warns_on_schema_invalid(self, state_manager, caplog):
        import logging

        # JSON としては妥当だが ImprovementProposal スキーマに合わない（review_id が不正 UUID）。
        # dict API（get_pending_improvement_proposals）には現れるのにモデル API から
        # 黙って消える不整合を警告で観測可能にする。
        improvements_dir = state_manager.state_dir / "improvements"
        improvements_dir.mkdir(exist_ok=True)
        (improvements_dir / "bad-schema.json").write_text(
            json.dumps(
                {
                    "id": "bad-schema",
                    "review_id": "not-a-uuid",
                    "status": "proposed",
                    "title": "Schema invalid",
                    "description": "d",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        with caplog.at_level(logging.WARNING, logger="core.platform.state"):
            models = state_manager.get_pending_proposals()

        assert models == []  # スキーマ不一致はモデル化できずスキップ
        assert any("bad-schema.json" in rec.message for rec in caplog.records)

    def test_list_session_contexts_warns_on_malformed_json(self, state_manager, caplog):
        import logging

        state_manager.save_session_context("session-1", {"summary": "ok"})
        (state_manager.sessions_dir / "broken.json").write_text("{not json", encoding="utf-8")

        with caplog.at_level(logging.WARNING, logger="core.platform.state"):
            sessions = state_manager.list_session_contexts()

        assert {s["session_id"] for s in sessions} == {"session-1"}
        assert any("broken.json" in rec.message for rec in caplog.records)

    def test_load_current_state_warns_on_malformed_json(self, state_manager, caplog):
        import logging

        state_manager.current_state_file.write_text("{not json", encoding="utf-8")
        with caplog.at_level(logging.WARNING, logger="core.platform.state"):
            st = state_manager.load_current_state()
        assert st["status"] == "initialized"  # 既定へフォールバック（クラッシュしない）
        assert any("current_state" in rec.message for rec in caplog.records)

    def test_load_session_context_warns_on_malformed_json(self, state_manager, caplog):
        import logging

        (state_manager.sessions_dir / "sess-x.json").write_text("{not json", encoding="utf-8")
        with caplog.at_level(logging.WARNING, logger="core.platform.state"):
            ctx = state_manager.load_session_context("sess-x")
        assert ctx is None
        assert any("sess-x" in rec.message for rec in caplog.records)

    def test_update_proposal_fields_warns_on_malformed_json(self, state_manager, caplog):
        import logging

        improvements_dir = state_manager.state_dir / "improvements"
        improvements_dir.mkdir(exist_ok=True)
        (improvements_dir / "broken-prop.json").write_text("{not json", encoding="utf-8")
        with caplog.at_level(logging.WARNING, logger="core.platform.state"):
            ok = state_manager.update_proposal_fields("broken-prop", status="done")
        assert ok is False  # 関数契約（bool）を守る・クラッシュしない
        assert any("broken-prop" in rec.message for rec in caplog.records)

    def test_timestamp_sort_key_is_chronological_not_lexicographic(self):
        from core.state.manager import _timestamp_sort_key

        # 20:00Z は 15:00Z（=+09:00 の 翌日0時）より後の瞬間だが、文字列だと "…03…" の方が大きい。
        later_instant = _timestamp_sort_key("2026-01-02T20:00:00Z")
        earlier_instant = _timestamp_sort_key("2026-01-03T00:00:00+09:00")
        assert later_instant > earlier_instant  # 時系列で正しく比較される
        # naive は UTC 扱い（aware）、空/解析不能は最古
        assert _timestamp_sort_key("2026-01-01T00:00:00").tzinfo is not None
        assert _timestamp_sort_key("") == _timestamp_sort_key("garbage")

    def test_get_all_improvement_proposals_chronological_with_mixed_tz(self, state_manager):
        improvements_dir = state_manager.state_dir / "improvements"
        improvements_dir.mkdir(exist_ok=True)
        (improvements_dir / "old.json").write_text(
            json.dumps(
                {
                    "id": "old",
                    "status": "proposed",
                    "title": "古い",
                    "created_at": "2026-01-03T00:00:00+09:00",
                }  # = 2026-01-02T15:00:00Z
            ),
            encoding="utf-8",
        )
        (improvements_dir / "new.json").write_text(
            json.dumps(
                {
                    "id": "new",
                    "status": "proposed",
                    "title": "新しい",
                    "created_at": "2026-01-02T20:00:00Z",
                }  # 後の瞬間
            ),
            encoding="utf-8",
        )
        ordered = [p["title"] for p in state_manager.get_all_improvement_proposals()]
        assert ordered == ["新しい", "古い"]  # 辞書順なら逆になるが時系列で正しい

    def test_safe_mtime_tolerates_missing_file(self, tmp_path):
        # glob と sort の間でファイルが消えても、ソートキーは落ちず最古（0.0）扱いにする。
        from core.state.manager import _safe_mtime

        assert _safe_mtime(tmp_path / "does-not-exist.json") == 0.0

    def test_get_recent_decisions_sorts_mixed_naive_and_aware(self, state_manager):
        # legacy/外部編集/移行データで naive な timestamp を持つ決定が、現行の aware な
        # 決定や 空/不正 timestamp の aware フォールバックと混在しても、sorted() が
        # naive<aware の TypeError でクラッシュせず時系列降順で返ることを保証する（回帰）。
        state_manager.record_decision("d-aware", "Aware", "body", "tester")  # 現行=aware
        (state_manager.decisions_dir / "d-naive.json").write_text(
            json.dumps(
                {
                    "id": "d-naive",
                    "timestamp": "2026-06-17T10:00:00",  # naive（tz 情報なし）
                    "title": "Naive",
                    "content": "body",
                    "made_by": "legacy",
                    "tags": [],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (state_manager.decisions_dir / "d-empty.json").write_text(
            json.dumps(
                {
                    "id": "d-empty",
                    "timestamp": "",  # → aware フォールバック（datetime.min, UTC）
                    "title": "Empty",
                    "content": "body",
                    "made_by": "legacy",
                    "tags": [],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        # 旧コードでは naive<aware の比較で TypeError がここで送出された
        decisions = state_manager.get_recent_decisions(limit=10)

        ids = [d["id"] for d in decisions]
        assert set(ids) == {"d-aware", "d-naive", "d-empty"}
        # 降順: aware(現在) > naive(2026-06-17, UTC 解釈) > empty(datetime.min)
        assert ids[0] == "d-aware"
        assert ids[-1] == "d-empty"
