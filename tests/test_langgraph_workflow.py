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

    def test_prioritize_tolerates_null_expected_impact_in_sort(self):
        """expected_impact が null の提案でソートが落ちない（``None < str`` TypeError 回帰）。

        2 件とも同一 priority → ソート第2キー（expected_impact）が比較される。片方が null
        だと旧コードは TypeError で prioritize_proposals 全体が落ちた。
        """
        proposals = [
            {"title": "null impact", "priority": "low", "expected_impact": None},
            {"title": "string impact", "priority": "low", "expected_impact": "large gain"},
        ]
        result = prioritize_proposals({"pending_proposals": proposals})
        assert {p["title"] for p in result["pending_proposals"]} == {
            "null impact",
            "string impact",
        }

    def test_prioritize_tolerates_null_expected_impact_in_approval_check(self):
        """current の expected_impact が null でも approval 判定が落ちない（``None.lower()`` 回帰）。

        priority != "high" の単一提案 → ``"large" in (expected_impact).lower()`` 分岐に入る。
        null だと旧コードは AttributeError。修正後は coerce され human_approval_required=False。
        """
        proposal = {"title": "null impact", "priority": "low", "expected_impact": None}
        result = prioritize_proposals({"pending_proposals": [proposal]})
        assert result["current_proposal"]["title"] == "null impact"
        assert result["human_approval_required"] is False
