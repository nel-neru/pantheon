"""Business（会社の合成）モデル・ストア・ロールアップ・合成のテスト。"""

from __future__ import annotations

from core.metrics.outcomes import OutcomeStore
from core.models.business import Business, HandoffRoute
from core.platform.business_store import BusinessStore


def test_business_model_defaults():
    b = Business(name="ShortVideo Affiliate")
    assert b.status == "active"
    assert b.member_orgs == [] and b.handoff_routes == []
    assert b.created_at.tzinfo is not None  # tz-aware


def test_business_store_roundtrip_and_corrupt_tolerant(tmp_path):
    store = BusinessStore(platform_home=tmp_path)
    b = Business(
        name="SVA",
        member_orgs=["VideoCo", "AffiliateCo"],
        roles={"VideoCo": "producer", "AffiliateCo": "monetizer"},
        handoff_routes=[
            HandoffRoute(from_org="VideoCo", to_org="AffiliateCo", kind="content_brief")
        ],
        kpis=["clicks", "revenue"],
    )
    store.save(b)
    # name / id どちらでも引ける
    assert store.get("SVA") is not None
    assert store.get(str(b.id)) is not None
    # upsert（重複しない）
    b.purpose = "更新"
    store.save(b)
    assert len(store.list_businesses()) == 1
    assert store.get("SVA").purpose == "更新"

    # 破損レコード混在 → スキップ（id 欠落は default uuid で有効、5/"bad"/不正idは除外）
    store.path.write_text(
        '[{"name":"OK"}, 5, "bad", {"name":"NG","id":"not-a-uuid"}]', encoding="utf-8"
    )
    names = [x.name for x in store.list_businesses()]
    assert "OK" in names and "NG" not in names
    # 非 list → 空
    store.path.write_text("null", encoding="utf-8")
    assert store.list_businesses() == []


def test_business_store_warns_on_corrupt_file(tmp_path, caplog):
    """businesses.json 破損は黙殺せず warn で観測可能化する（discovery wave3・silent-drop）。"""
    import logging

    store = BusinessStore(platform_home=tmp_path)
    store.path.write_text("{ broken json", encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger="core.platform.state"):
        result = store.list_businesses()
    assert result == []
    assert any("businesses" in r.message for r in caplog.records)


def test_business_delete(tmp_path):
    store = BusinessStore(platform_home=tmp_path)
    store.save(Business(name="Gone"))
    assert store.delete("Gone") is True
    assert store.get("Gone") is None
    assert store.delete("Gone") is False


def test_business_outcomes_rollup(tmp_path):
    out = OutcomeStore(platform_home=tmp_path)
    out.record("VideoCo", "impressions", 1000)
    out.record("AffiliateCo", "revenue", 500)
    out.record("AffiliateCo", "revenue", 250)
    out.record("Unrelated", "revenue", 9999)  # member 外は含めない

    summary = out.summary_for_orgs(["VideoCo", "AffiliateCo"], label="SVA")
    assert summary.org_name == "SVA"
    assert summary.total_revenue == 750  # 500 + 250（Unrelated は除外）
    assert summary.total_reach == 1000
    assert summary.event_count == 3


def test_business_compose_creates_handoffs(tmp_path):
    from core.hierarchy.org_handoff import OrgHandoffStore

    store = BusinessStore(platform_home=tmp_path)
    b = Business(
        name="SVA",
        member_orgs=["VideoCo", "AffiliateCo"],
        handoff_routes=[
            HandoffRoute(from_org="VideoCo", to_org="AffiliateCo", kind="content_brief"),
            HandoffRoute(from_org="X", to_org="X", kind="content_brief"),  # 不正(同一)→スキップ
        ],
    )
    store.save(b)
    created = store.compose_handoffs(b)
    assert len(created) == 1  # 不正ルートはスキップ
    assert created[0].source_org == "VideoCo" and created[0].target_org == "AffiliateCo"
    # OrgHandoffStore に永続化されている
    handoffs = OrgHandoffStore(platform_home=tmp_path).list_handoffs()
    assert any(h.target_org == "AffiliateCo" for h in handoffs)


def test_cli_parser_and_handlers_wired():
    from commands import build_parser

    parser = build_parser()
    args = parser.parse_args(
        ["business", "create", "--name", "B", "--orgs", "A,C", "--route", "A:C:content_brief"]
    )
    assert args.handler_name == "cmd_business_create"
    args = parser.parse_args(["business", "outcomes", "B"])
    assert args.handler_name == "cmd_business_outcomes"

    import main

    for name in (
        "cmd_business_create",
        "cmd_business_list",
        "cmd_business_show",
        "cmd_business_outcomes",
        "cmd_business_compose",
        "cmd_business_update",
        "cmd_business_pause",
        "cmd_business_archive",
        "cmd_business_delete",
    ):
        assert name in main.HANDLERS


async def test_business_update_pause_archive_delete_cli(tmp_path, monkeypatch):
    """update/pause/archive/delete の CLI ハンドラが状態を実効化する（P10/P17）。"""
    import argparse

    monkeypatch.setattr("core.platform.state.get_platform_home", lambda: tmp_path)
    from commands.business import (
        cmd_business_archive,
        cmd_business_delete,
        cmd_business_pause,
        cmd_business_update,
    )

    store = BusinessStore(platform_home=tmp_path)
    store.save(Business(name="Biz", member_orgs=["A"], kpis=["k1"]))

    # update: status / purpose / 会社追加 / KPI 追加
    upd = argparse.Namespace(
        id="Biz",
        name=None,
        purpose="新目的",
        status="active",
        add_org=["B"],
        remove_org=["A"],
        add_kpi=["k2"],
    )
    await cmd_business_update(upd, get_psm=lambda: None)
    b = store.get("Biz")
    assert b.purpose == "新目的" and b.member_orgs == ["B"] and "k2" in b.kpis

    # pause / archive は status を遷移させる
    await cmd_business_pause(argparse.Namespace(id="Biz"), get_psm=lambda: None)
    assert store.get("Biz").status == "paused"
    await cmd_business_archive(argparse.Namespace(id="Biz"), get_psm=lambda: None)
    assert store.get("Biz").status == "archived"

    # delete は除去する
    await cmd_business_delete(argparse.Namespace(id="Biz"), get_psm=lambda: None)
    assert store.get("Biz") is None


async def test_business_update_rejects_unknown_status(tmp_path, monkeypatch):
    """status は active/paused/archived のみ（不正値で SystemExit）。"""
    import argparse

    import pytest

    monkeypatch.setattr("core.platform.state.get_platform_home", lambda: tmp_path)
    from commands.business import cmd_business_update

    BusinessStore(platform_home=tmp_path).save(Business(name="Biz"))
    bad = argparse.Namespace(
        id="Biz", name=None, purpose=None, status="bogus", add_org=[], remove_org=[], add_kpi=[]
    )
    with pytest.raises(SystemExit):
        await cmd_business_update(bad, get_psm=lambda: None)
