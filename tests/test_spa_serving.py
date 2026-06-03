"""SPA serving + legacy UI retirement (web/server.py)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

import web.server as server

client = TestClient(server.app)

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_unknown_api_path_returns_404_not_spa():
    """未知の /api/* は SPA HTML で握りつぶさず 404 を返す。"""
    response = client.get("/api/definitely-not-a-real-endpoint")
    assert response.status_code == 404


def test_client_route_serves_spa():
    """クライアントサイドルートは SPA(index.html) または未ビルド案内を返す。"""
    response = client.get("/orgs")
    assert response.status_code in {200, 503}
    assert "text/html" in response.headers.get("content-type", "")


def test_legacy_static_ui_is_archived_not_served():
    """旧 web/static は撤去され、web/legacy にアーカイブされている。"""
    assert not (REPO_ROOT / "web" / "static" / "index.html").exists()
    assert (REPO_ROOT / "web" / "legacy" / "index.html").exists()


def test_static_dir_constant_removed():
    """旧 STATIC_DIR 定数は削除済み（React dist が唯一の配信元）。"""
    assert not hasattr(server, "STATIC_DIR")
    assert hasattr(server, "DIST_DIR")
