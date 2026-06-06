"""
Atlas（リポジトリ俯瞰）: 静的イントロスペクションモデル / /api/atlas / 明示的 404 ガード。
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from core.atlas import build_atlas
from web.server import app

client = TestClient(app)


def test_build_atlas_model_shape():
    atlas = build_atlas()
    assert {"overview", "flows", "cli", "api", "frontend", "graph", "subsystems"} <= set(atlas)
    ov = atlas["overview"]
    assert ov["cli_commands"] >= 30
    assert ov["api_routes"] >= 30
    assert ov["pages"] >= 10
    assert ov["websockets"] >= 2
    assert ov["modules"] >= 100


def test_atlas_flows_are_curated_and_consistent():
    atlas = build_atlas()
    flows = atlas["flows"]
    assert len(flows) >= 12
    ids = {f["id"] for f in flows}
    assert "analyze-propose-approve-apply" in ids
    assert "abstract-goal-pipeline" in ids
    assert "atlas-introspection" in ids
    for flow in flows:
        assert {"id", "name", "summary", "trigger", "steps", "surfaces", "status"} <= set(flow)
        assert flow["status"] in {"solid", "partial", "fragile", "unknown"}


def test_atlas_cli_includes_atlas_command_with_handler():
    atlas = build_atlas()
    handled = [c for c in atlas["cli"] if c.get("handler")]
    assert any(c["command"] == "pantheon atlas" for c in handled)
    assert all(c["command"].startswith("pantheon ") for c in handled)


def test_atlas_graph_edges_reference_known_nodes():
    atlas = build_atlas()
    nodes = {n["id"] for n in atlas["graph"]["nodes"]}
    assert "state" in nodes
    assert "web-api" in nodes
    for edge in atlas["graph"]["edges"]:
        assert edge["source"] in nodes
        assert edge["target"] in nodes
        assert edge["source"] != edge["target"]
        assert edge["weight"] >= 1


def test_api_atlas_endpoint_returns_model():
    response = client.get("/api/atlas")
    assert response.status_code == 200
    body = response.json()
    assert body["overview"]["flows"] == len(body["flows"])
    assert body["generated_at"]


def test_unknown_api_path_returns_json_404_not_spa():
    response = client.get("/api/definitely-not-a-real-route")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")


def test_unknown_ws_prefixed_path_returns_404():
    response = client.get("/ws/nope")
    assert response.status_code == 404


def test_client_side_route_still_served_as_spa():
    response = client.get("/orgs")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_introspect_private_api_is_best_effort():
    """argparse 内部 API が想定外でも例外で全体を落とさず、フォールバックする。"""
    from types import SimpleNamespace

    from core.atlas.introspect import _collect_args, _walk_cli

    # _actions を持たないオブジェクトでも [] を返す（例外を投げない）
    assert _collect_args(SimpleNamespace()) == []
    out: list = []
    _walk_cli(SimpleNamespace(), "", out)
    assert out == []
