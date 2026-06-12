"""
Pytest configuration for Pantheon.

Pantheon's only execution backend is the local ``claude`` CLI (Claude Code).
Tests must stay deterministic and fully offline, so we disable the CLI for the
entire test session: ``core.runtime.claude_code.claude_available()`` returns
False, every generation call raises ``ClaudeUnavailableError``, and each agent
falls back to its built-in heuristic path — exactly the behaviour the suite was
written against. A test that specifically exercises the Claude Code backend can
opt back in by monkeypatching the binary resolver.
"""

from __future__ import annotations

import atexit
import os
import shutil
import tempfile

os.environ.setdefault("PANTHEON_NO_CLAUDE", "1")

# テスト中に実ブラウザ（Playwright ヘッドフル）が起動しないよう全体で無効化する。
# playwright が導入された環境で suite を回しても、接続フロー/実投稿系のコードパスは
# 「未導入」と同じ正直な失敗側に倒れる。実ブラウザを使うテストを書く場合は
# monkeypatch.delenv("PANTHEON_NO_BROWSER") で明示的にオプトインする。
os.environ.setdefault("PANTHEON_NO_BROWSER", "1")

# テストセッション全体で PANTHEON_HOME を一時ディレクトリに隔離する。
# これが無いと、get_platform_home() をパッチも platform_home 注入もしないテストが
# 実ユーザーの ~/.pantheon に Organization 等を書き込んで汚染する（重複 org の温床）。
# setdefault なので、CI/ユーザーが明示的に PANTHEON_HOME を指定していればそれを尊重する。
# モジュールレベルで設定し、import 時（TestClient(app) 構築など）にも効くようにする。
if "PANTHEON_HOME" not in os.environ:
    _test_home = tempfile.mkdtemp(prefix="pantheon-test-home-")
    os.environ["PANTHEON_HOME"] = _test_home
    atexit.register(shutil.rmtree, _test_home, True)
