"""illustration_story_youtube 会社プラグイン（RED THREAD）の検証。

プラグイン install で 4 事業部＋自己改善 seed が立ち上がり、全 SpecialistAgent が 2-3 スキル、
初期KPI/人手タスクが面に出て、独自性・継続性のカノン（スタイルバイブル/キャラ登録簿/
シリーズ正典）がワークスペースへ展開されることを固定する。本番 ~/.pantheon には書かない。
"""

from __future__ import annotations

from pathlib import Path

import yaml

from core.orchestration.company_plugins import (
    _seed_canon,
    get_company_plugin_manifest,
    install_company_plugin,
)
from core.paths import resource_path
from core.platform.state import PlatformStateManager


def test_install_builds_divisions_canon_and_tasks(tmp_path, monkeypatch):
    monkeypatch.setattr("core.platform.state.get_platform_home", lambda: tmp_path)
    psm = PlatformStateManager(platform_home=tmp_path)

    result = install_company_plugin("illustration_story_youtube", psm=psm)
    assert result["ok"]

    org = psm.load_organization_by_name(result["org_name"])
    assert org is not None
    names = {d.name for d in org.divisions}
    # 設計どおりの 4 事業部 + 自動付与の自己改善 seed
    assert {
        "企画・カノン事業部",
        "制作ブリーフ事業部",
        "集客・配信事業部",
        "収益化・分析事業部",
    } <= names
    assert any("改善" in n for n in names), "自己改善シード事業部が無い"

    # genre / KPI / 人手タスク（外部・手動レグ）が面に出る
    assert org.industry_genre == "illustration_story_youtube"
    assert result["initial_kpis"]
    assert result["human_tasks_created"] >= 5  # チャンネル作成/画像生成/動画組立/アップロード等

    # SpecialistAgent.skills は全員 2-3（min2/max3 制約）
    agents = org.get_all_agents()
    assert agents
    for agent in agents:
        assert 2 <= len(agent.skills) <= 3, f"{agent.name} のスキル数が範囲外: {agent.skills}"

    # 独自性・継続性カノンがワークスペースへ展開される
    canon = Path(org.workspace_path) / "canon"
    assert (canon / "style_bible.yaml").exists()
    assert (canon / "character_registry.yaml").exists()
    assert (canon / "series_canon.yaml").exists()
    assert result["canon_files"] == 3


def test_manifest_routes_external_legs_to_human_tasks_honestly():
    """見かけ自動にしない: 画像生成/動画組立/YouTubeアップロードは人手タスクに明記される。"""
    m = get_company_plugin_manifest("illustration_story_youtube")
    assert m is not None
    tasks = " / ".join(m["human_tasks"])
    assert "チャンネル" in tasks  # チャンネル作成は利用者
    assert "画像生成" in tasks  # 画像は外部ツール
    assert "アップロード" in tasks  # YouTube 投稿は人手
    assert m.get("canon_template") == "red_thread"


def test_canon_locks_originality_and_continuity():
    """カノンが署名スタイル（独自性）と固定キャラ/seed（継続性）を実際に持つ。"""
    base = ("config", "canon", "red_thread")
    sb = yaml.safe_load(resource_path(*base, "style_bible.yaml").read_text(encoding="utf-8"))
    assert sb["style_suffix"].strip()  # 全プロンプトに注入する署名スタイル
    assert sb["palette"]["thread_red"]  # 赤い糸の専用色
    assert sb["negative_prompt_bank"]  # AI臭の除外

    reg = yaml.safe_load(
        resource_path(*base, "character_registry.yaml").read_text(encoding="utf-8")
    )
    ids = {c["id"] for c in reg["characters"]}
    assert {"lighthouse_keeper", "lost_kid", "old_cat", "stranger"} <= ids
    assert all(c.get("base_seed") for c in reg["characters"]), (
        "base_seed 未固定（drift 防止が崩れる）"
    )
    assert reg.get("outfit_lock") is True

    sc = yaml.safe_load(resource_path(*base, "series_canon.yaml").read_text(encoding="utf-8"))
    assert sc["structure"]["beats"] == 2  # 2ビート twist 厳守
    assert sc["backlog"]  # 1話目から連続性が成立する初期企画
    assert sc["red_thread_rules"]


def test_canon_seed_is_idempotent_and_preserves_edits(tmp_path):
    """_seed_canon は既存（改訂済み）ファイルを上書きしない（運用中の改訂を保護）。"""
    ws = tmp_path / "ws"
    (ws / "canon").mkdir(parents=True)
    (ws / "canon" / "style_bible.yaml").write_text("edited: true\n", encoding="utf-8")

    copied = _seed_canon(ws, "red_thread")
    # 既存の style_bible は保護され、残り 2 ファイルだけ複製される
    assert (ws / "canon" / "style_bible.yaml").read_text(encoding="utf-8") == "edited: true\n"
    assert (ws / "canon" / "series_canon.yaml").exists()
    assert (ws / "canon" / "character_registry.yaml").exists()
    assert copied == 2


def test_canon_seed_unknown_template_is_safe(tmp_path):
    """未知テンプレートは 0 を返し、install を止めない（best-effort）。"""
    assert _seed_canon(tmp_path / "ws", "no_such_template") == 0
    assert _seed_canon(tmp_path / "ws", "") == 0
