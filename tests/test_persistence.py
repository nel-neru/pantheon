"""``core.persistence.atomic_write_text`` の原子性・堅牢性を固定する回帰テスト。

ここで守りたい不変条件:
- 成功時は内容が正しく書け、孤児 ``.tmp`` を残さない。
- 既存ファイルは原子的に上書きされる（読み手は旧か新のどちらかだけを見る）。
- 書き込み途中で失敗しても、既存ファイルは無傷で孤児 ``.tmp`` も残らない。
- state manager / platform state の保存経路が実際に原子的書き込みを使っている。
"""

from __future__ import annotations

import json

import pytest

from core.persistence import atomic_write_text


def _temp_orphans(directory) -> list:
    """ディレクトリに残った一時ファイル（*.tmp）の一覧。"""
    return list(directory.glob("*.tmp"))


def test_writes_content_and_no_orphan_tmp(tmp_path):
    target = tmp_path / "state.json"
    atomic_write_text(target, '{"a": 1}')
    assert target.read_text(encoding="utf-8") == '{"a": 1}'
    assert _temp_orphans(tmp_path) == []


def test_creates_parent_dirs(tmp_path):
    target = tmp_path / "nested" / "deep" / "state.json"
    atomic_write_text(target, "ok")
    assert target.read_text(encoding="utf-8") == "ok"


def test_overwrites_existing_atomically(tmp_path):
    target = tmp_path / "state.json"
    target.write_text("OLD", encoding="utf-8")
    atomic_write_text(target, "NEW")
    assert target.read_text(encoding="utf-8") == "NEW"
    assert _temp_orphans(tmp_path) == []


def test_non_ascii_roundtrip(tmp_path):
    target = tmp_path / "state.json"
    payload = {"title": "日本語のタイトル", "emoji": "🚀"}
    atomic_write_text(target, json.dumps(payload, ensure_ascii=False))
    assert json.loads(target.read_text(encoding="utf-8")) == payload


def test_failure_mid_write_leaves_original_intact(tmp_path, monkeypatch):
    """os.replace が失敗しても、既存ファイルは旧内容のまま・孤児 .tmp も残らない。"""
    target = tmp_path / "state.json"
    target.write_text("ORIGINAL", encoding="utf-8")

    def boom(_src, _dst):
        raise OSError("simulated replace failure")

    monkeypatch.setattr("core.persistence.os.replace", boom)

    with pytest.raises(OSError):
        atomic_write_text(target, "SHOULD NOT LAND")

    # 元ファイルは破壊されず（torn write を見せない）、半端な .tmp も残さない。
    assert target.read_text(encoding="utf-8") == "ORIGINAL"
    assert _temp_orphans(tmp_path) == []


def test_repo_state_manager_save_uses_atomic_write(tmp_path):
    """RepoStateManager の保存経路が孤児 .tmp を残さない（atomic_write_text 経由）。"""
    from core.state.manager import RepoStateManager

    mgr = RepoStateManager(tmp_path, org_name="demo")
    mgr.save_current_state({"status": "ok"})
    mgr.record_decision("d1", "title", "content", made_by="tester")
    mgr.save_session_context("s1", {"k": "v"})

    # 状態は読み戻せる。
    assert mgr.load_current_state()["status"] == "ok"
    # .pantheon 配下に孤児 .tmp が一切ない。
    assert list((tmp_path / ".pantheon").rglob("*.tmp")) == []


def test_update_proposal_fields_atomic_read_modify_write(tmp_path):
    """update_proposal_fields は「自身が読んだファイルを replace する」唯一の変換 site。

    read→modify→atomic_write_text の往復で内容が正しく更新され、孤児 .tmp を残さない。
    """
    from core.state.manager import RepoStateManager

    mgr = RepoStateManager(tmp_path, org_name="demo")
    improvements_dir = tmp_path / ".pantheon" / "improvements"
    improvements_dir.mkdir(parents=True, exist_ok=True)
    (improvements_dir / "p1.json").write_text(
        json.dumps({"id": "p1", "status": "pending", "title": "t"}), encoding="utf-8"
    )

    assert mgr.update_proposal_fields("p1", status="approved") is True

    data = json.loads((improvements_dir / "p1.json").read_text(encoding="utf-8"))
    assert data["status"] == "approved"
    assert data["title"] == "t"  # 既存フィールドは保持
    assert "last_updated" in data
    assert list(improvements_dir.glob("*.tmp")) == []


def test_platform_state_save_uses_atomic_write(tmp_path):
    """PlatformStateManager の保存経路も孤児 .tmp を残さない。"""
    from core.platform.state import PlatformStateManager

    mgr = PlatformStateManager(platform_home=tmp_path)
    mgr.save_platform_config({"workspaces_root": "C:/tmp"})

    assert mgr.load_platform_config()["workspaces_root"] == "C:/tmp"
    assert list(tmp_path.rglob("*.tmp")) == []
