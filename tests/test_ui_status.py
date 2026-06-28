"""UI/UX 状態監視サブシステムのテスト。

``build_ui_status`` が PAGE_REGISTRY 全ページを probe して 200 群を ok にし overall を集計する
こと、``/api/ui/status`` が artifact 未生成時に ``available: false`` を返し ``write_ui_status``
後はその内容を返すこと、PAGE_REGISTRY の route 集合が重複なく必要数を満たすことを検証する。

``tmp_path`` + ``monkeypatch`` で ``get_platform_home`` を隔離する（conftest の規約に準拠）。
"""

from __future__ import annotations

from fastapi.testclient import TestClient

import web.server as server
from core.ui.ui_status import (
    PAGE_REGISTRY,
    build_ui_status,
    default_status_path,
    load_ui_status,
    write_ui_status,
)

client = TestClient(server.app)


def _patch_home(tmp_path, monkeypatch) -> None:
    """get_platform_home を tmp_path に隔離する（モジュール束縛＋根本の両方）。"""
    monkeypatch.setattr("core.ui.ui_status.get_platform_home", lambda: tmp_path)
    monkeypatch.setattr(server, "get_platform_home", lambda: tmp_path)
    monkeypatch.setattr("core.platform.state.get_platform_home", lambda: tmp_path)


def test_registry_routes_unique_and_complete():
    routes = [page["route"] for page in PAGE_REGISTRY]
    # route は重複しない。
    assert len(routes) == len(set(routes)), f"重複した route: {routes}"
    # 少なくとも 25 ページ + 自己参照の /ui-status を含む。
    assert "/ui-status" in routes
    assert len(routes) >= 26
    # 各要素は宣言マップの必須キーを備える。
    for page in PAGE_REGISTRY:
        assert {"route", "label", "group", "apis", "controls", "static"} <= set(page.keys())
        for api in page["apis"]:
            assert api["method"] == "GET"
            assert api["path"].startswith("/api/")


def test_build_ui_status_probes_all_pages(tmp_path, monkeypatch):
    _patch_home(tmp_path, monkeypatch)

    report = build_ui_status(client)

    # 全ページが含まれる。
    report_routes = {p["route"] for p in report["pages"]}
    registry_routes = {p["route"] for p in PAGE_REGISTRY}
    assert report_routes == registry_routes
    assert report["overall"]["pages"] == len(PAGE_REGISTRY)

    # overall 集計は pages の status 分布と一致する。
    status_counts = {"ok": 0, "degraded": 0, "error": 0}
    total_apis = 0
    ok_apis = 0
    for page in report["pages"]:
        status_counts[page["status"]] += 1
        for api in page["apis"]:
            total_apis += 1
            if api["ok"]:
                ok_apis += 1
            # probe は実際に叩いて status_code を記録している（捏造でない）。
            assert "status_code" in api
            assert "latency_ms" in api
            assert api["ok"] == (200 <= api["status_code"] < 400)
    assert report["overall"]["ok"] == status_counts["ok"]
    assert report["overall"]["degraded"] == status_counts["degraded"]
    assert report["overall"]["error"] == status_counts["error"]
    assert report["overall"]["total_apis"] == total_apis
    assert report["overall"]["ok_apis"] == ok_apis

    # 200 群（実在 GET API）は ok。dashboard の /api/organizations は確実に 200。
    dash = next(p for p in report["pages"] if p["route"] == "/dashboard")
    orgs_api = next(a for a in dash["apis"] if a["path"] == "/api/organizations")
    assert orgs_api["status_code"] == 200
    assert orgs_api["ok"] is True

    # 静的ページ（/help）は API を持たず ok。
    help_page = next(p for p in report["pages"] if p["route"] == "/help")
    assert help_page["static"] is True
    assert help_page["apis"] == []
    assert help_page["status"] == "ok"

    # generated_at は ISO8601（tz-aware）で記録される。
    assert report["generated_at"].endswith("+00:00") or "T" in report["generated_at"]


def test_api_ui_status_unavailable_then_available(tmp_path, monkeypatch):
    _patch_home(tmp_path, monkeypatch)

    # artifact 未生成: available:false を 200 で返す（捏造しない）。
    resp = client.get("/api/ui/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["available"] is False
    assert "未生成" in data["message"]

    # write_ui_status 後はその内容をそのまま返す。
    report = build_ui_status(client)
    write_ui_status(report, default_status_path())

    resp2 = client.get("/api/ui/status")
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2.get("available") is not False
    assert data2["overall"]["pages"] == len(PAGE_REGISTRY)
    assert {p["route"] for p in data2["pages"]} == {p["route"] for p in PAGE_REGISTRY}

    # load_ui_status も同じ内容を読める。
    loaded = load_ui_status(default_status_path())
    assert loaded is not None
    assert loaded["overall"]["pages"] == len(PAGE_REGISTRY)


def test_load_ui_status_missing_and_corrupt(tmp_path):
    missing = tmp_path / "nope.json"
    assert load_ui_status(missing) is None

    corrupt = tmp_path / "ui_status.json"
    corrupt.write_text("{ not json", encoding="utf-8")
    assert load_ui_status(corrupt) is None


def test_api_ui_status_refresh_generates_and_persists(tmp_path, monkeypatch):
    _patch_home(tmp_path, monkeypatch)

    resp = client.post("/api/ui/status/refresh")
    assert resp.status_code == 200
    data = resp.json()
    assert data["overall"]["pages"] == len(PAGE_REGISTRY)

    # 永続化され、以後 GET /api/ui/status で読める。
    assert default_status_path().exists()
    got = client.get("/api/ui/status")
    assert got.json()["overall"]["pages"] == len(PAGE_REGISTRY)
