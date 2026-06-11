from __future__ import annotations

from core.quality.self_improvement_graph import build_self_improvement_graph, prioritize_proposals


class TestSelfImprovementGraph:
    def test_graph_nodes_exist(self, tmp_path):
        graph = build_self_improvement_graph(str(tmp_path / "graph.db"))
        graph_repr = str(graph.get_graph())
        assert "pickup_proposals" in graph_repr
        assert "execute_improvement" in graph_repr

    def test_graph_can_be_instantiated(self, tmp_path):
        graph = build_self_improvement_graph(str(tmp_path / "graph.db"))
        assert graph is not None

    def test_review_node_processes_state(self):
        proposal = {
            "title": "Critical fix",
            "priority": "high",
            "expected_impact": "large stability gain",
        }
        result = prioritize_proposals({"pending_proposals": [proposal]})
        assert result["current_proposal"]["title"] == "Critical fix"
        assert result["human_approval_required"] is True
