"""_load_all_proposals のキャッシュ（E3）テスト。

(org名, 件数, 最大mtime) シグネチャでキャッシュし、ファイルの追加/削除で無効化されること。
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import web.server as server


def _fake_psm(state_dir):
    org = SimpleNamespace(name="org1")
    sm = SimpleNamespace(state_dir=state_dir)
    return SimpleNamespace(
        load_organizations=lambda: [org],
        get_org_state_manager=lambda o: sm,
    )


def test_load_all_proposals_caches_and_invalidates(tmp_path, monkeypatch):
    improvements = tmp_path / "improvements"
    improvements.mkdir()
    (improvements / "p1.json").write_text(json.dumps({"id": "p1", "title": "A"}), encoding="utf-8")

    monkeypatch.setattr(server, "_psm", lambda: _fake_psm(tmp_path))
    server._invalidate_proposals_cache()

    first = server._load_all_proposals()
    assert len(first) == 1 and first[0]["id"] == "p1"
    assert first[0]["org_name"] == "org1"

    # シグネチャ不変 → 同一オブジェクトを返す（再 read/parse しない）
    assert server._load_all_proposals() is first

    # ファイル追加 → 件数が変わりキャッシュ無効化 → 新しい結果
    (improvements / "p2.json").write_text(json.dumps({"id": "p2", "title": "B"}), encoding="utf-8")
    third = server._load_all_proposals()
    assert third is not first
    assert {p["id"] for p in third} == {"p1", "p2"}


def test_load_all_proposals_handles_no_improvements_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_psm", lambda: _fake_psm(tmp_path))
    server._invalidate_proposals_cache()
    assert server._load_all_proposals() == []
