"""core/vault/graph.py — nodes/edges/backlinks・未解決 leaf・DOT 出力。"""

from __future__ import annotations

from core.intelligence.playbook import PlaybookStore
from core.knowledge.manager import KnowledgeManager
from core.vault import build_default_sync, build_vault_graph, get_vault_dir, to_dot


def _seed_and_export(tmp_path):
    KnowledgeManager(tmp_path).save_insight("Insight", "本文", tags=["t"], source_org="Foo")
    PlaybookStore(tmp_path).add("Play", "施策", category="general", org_name="Foo")
    build_default_sync(tmp_path).export()
    return get_vault_dir(tmp_path)


def test_graph_has_nodes_for_notes_and_unresolved_leaves(tmp_path):
    vault = _seed_and_export(tmp_path)
    graph = build_vault_graph(vault)

    types = {n["group"] for n in graph["nodes"]}
    assert "insight" in types
    assert "playbook" in types
    # source_org への [[org:Foo]] は対応ノートが無いので未解決 leaf として残る。
    org_nodes = [n for n in graph["nodes"] if n["id"] == "org:Foo"]
    assert len(org_nodes) == 1
    assert org_nodes[0]["files"] == 0


def test_graph_edges_point_to_org(tmp_path):
    vault = _seed_and_export(tmp_path)
    graph = build_vault_graph(vault)
    targets = {e["target"] for e in graph["edges"]}
    assert "org:Foo" in targets
    assert graph["counts"]["notes"] == 2
    assert graph["counts"]["edges"] >= 2


def test_graph_backlinks_invert_forward_links(tmp_path):
    vault = _seed_and_export(tmp_path)
    graph = build_vault_graph(vault)
    # org:Foo は insight と playbook の両方から指される（backlink 2 件）。
    assert len(graph["backlinks"].get("org:Foo", [])) == 2


def test_graph_empty_when_no_vault(tmp_path):
    graph = build_vault_graph(tmp_path / "vault")
    assert graph["nodes"] == []
    assert graph["edges"] == []
    assert graph["counts"]["notes"] == 0


def test_to_dot_renders_digraph(tmp_path):
    vault = _seed_and_export(tmp_path)
    dot = to_dot(build_vault_graph(vault))
    assert dot.startswith("digraph vault {")
    assert "->" in dot
    assert dot.rstrip().endswith("}")
