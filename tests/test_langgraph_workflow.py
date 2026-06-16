from __future__ import annotations

import sqlite3

from core.quality.self_improvement_graph import build_self_improvement_graph, prioritize_proposals


def _close(graph):
    conn = getattr(graph, "_pantheon_checkpoint_conn", None)
    if conn is not None:
        conn.close()


class TestSelfImprovementGraph:
    def test_graph_nodes_exist(self, tmp_path):
        graph = build_self_improvement_graph(str(tmp_path / "graph.db"))
        graph_repr = str(graph.get_graph())
        assert "pickup_proposals" in graph_repr
        assert "execute_improvement" in graph_repr
        _close(graph)

    def test_graph_can_be_instantiated(self, tmp_path):
        graph = build_self_improvement_graph(str(tmp_path / "graph.db"))
        assert graph is not None
        _close(graph)

    def test_default_checkpoint_lives_under_platform_home(self, tmp_path, monkeypatch):
        """既定の checkpoint DB は cwd ではなく ~/.pantheon（platform home）配下に作る。"""
        home = tmp_path / "pantheon_home"
        monkeypatch.setattr("core.quality.self_improvement_graph.get_platform_home", lambda: home)
        # cwd を別ディレクトリにして「cwd に作られない」ことも担保する。
        cwd = tmp_path / "workdir"
        cwd.mkdir()
        monkeypatch.chdir(cwd)

        graph = build_self_improvement_graph()  # 明示パスなし＝既定経路
        try:
            expected = home / "self_improvement_checkpoints.db"
            assert expected.exists(), "checkpoint DB が platform home 配下に無い"
            assert not (cwd / "self_improvement_checkpoints.db").exists(), (
                "cwd に checkpoint DB が漏れている（旧バグの再発）"
            )
            conn = getattr(graph, "_pantheon_checkpoint_conn", None)
            assert isinstance(conn, sqlite3.Connection)
        finally:
            _close(graph)

    def test_review_node_processes_state(self):
        proposal = {
            "title": "Critical fix",
            "priority": "high",
            "expected_impact": "large stability gain",
        }
        result = prioritize_proposals({"pending_proposals": [proposal]})
        assert result["current_proposal"]["title"] == "Critical fix"
        assert result["human_approval_required"] is True
