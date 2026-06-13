"""session-heartbeat フック（.claude/hooks/session-heartbeat.mjs）の契約検証。

このフックの存在意義は「生きている Claude Code セッションが ~/.pantheon/
evolve_session.heartbeat を新鮮に保ち、evolve_resume.ps1 が並走 headless /evolve を
二重起動しないようにする」こと。よってここでは **必ずマーカーを書く・常に exit 0・
壊れた/空の stdin でも落ちない** という、壊れたら無音で二重起動が復活する不変条件を固定する。

フックは Node なので `node` が PATH に無い環境では skip する（バックエンド本体テストは
node 非依存。これは .claude インフラの回帰防止）。os.homedir() は USERPROFILE を尊重する
ため、USERPROFILE を tmp_path に向けてフックを隔離実行する。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_HOOK = _REPO_ROOT / ".claude" / "hooks" / "session-heartbeat.mjs"
_NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(_NODE is None, reason="node が PATH に無い")


def _run_hook(tmp_path: Path, stdin: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["USERPROFILE"] = str(tmp_path)  # node os.homedir() はこれを尊重 → 隔離
    env["HOME"] = str(tmp_path)
    return subprocess.run(
        [_NODE, str(_HOOK)],
        input=stdin,
        text=True,
        env=env,
        capture_output=True,
    )


def _marker(tmp_path: Path) -> Path:
    return tmp_path / ".pantheon" / "evolve_session.heartbeat"


def test_hook_writes_fresh_marker(tmp_path):
    """payload 付きで起動 → マーカーを新鮮に書き、event を反映、exit 0。"""
    payload = json.dumps({"cwd": str(_REPO_ROOT), "hook_event_name": "PostToolUse"})
    proc = _run_hook(tmp_path, payload)
    assert proc.returncode == 0, proc.stderr
    marker = _marker(tmp_path)
    assert marker.exists()
    rec = json.loads(marker.read_text(encoding="utf-8"))
    assert {"ts", "pid", "cwd", "event"} <= set(rec)
    assert rec["event"] == "PostToolUse"
    assert rec["cwd"] == str(_REPO_ROOT)
    # 新鮮さ: evolve_resume.ps1 は mtime を見るので mtime が今であることが要
    assert time.time() - marker.stat().st_mtime < 30


def test_hook_writes_without_stdin(tmp_path):
    """stdin 無しでもマーカーを書く（PS 側は stdin に依存しない）。event 既定は 'session'。"""
    proc = _run_hook(tmp_path, "")
    assert proc.returncode == 0, proc.stderr
    marker = _marker(tmp_path)
    assert marker.exists()
    rec = json.loads(marker.read_text(encoding="utf-8"))
    assert rec["event"] == "session"


def test_hook_survives_invalid_stdin(tmp_path):
    """壊れた JSON が来てもクラッシュせず、マーカーを書いて exit 0。"""
    proc = _run_hook(tmp_path, "not json {{{")
    assert proc.returncode == 0, proc.stderr
    assert _marker(tmp_path).exists()


def test_hook_marker_is_valid_json_each_run(tmp_path):
    """連続起動で常に完全な JSON（atomic rename で torn-write を残さない）。"""
    for _ in range(3):
        proc = _run_hook(tmp_path, "")
        assert proc.returncode == 0, proc.stderr
    # 最終ファイルは完全にパースできる（中途半端な .tmp が残っていない）
    rec = json.loads(_marker(tmp_path).read_text(encoding="utf-8"))
    assert "ts" in rec
    leftover = list((tmp_path / ".pantheon").glob("evolve_session.heartbeat.*.tmp"))
    assert leftover == [], f"残骸 tmp ファイル: {leftover}"
