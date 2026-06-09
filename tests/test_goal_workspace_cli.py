"""goal run のワークスペース指定（--workspace / --new-workspace）の配線テスト。

中核モデル「1 ワークスペース = 1 Organization」: goal は対象ワークスペースを明示させ、
未指定では新規 org を量産しない（重複の根を断つ）。
"""

from __future__ import annotations

import argparse
import asyncio

from commands import build_parser
from commands.goal import cmd_goal_run


def test_goal_run_parses_workspace_flags():
    parser = build_parser()

    a1 = parser.parse_args(["goal", "run", "ゴール", "--workspace", "My App"])
    assert a1.workspace == "My App"
    assert a1.new_workspace is None

    a2 = parser.parse_args(["goal", "run", "ゴール", "--new-workspace"])
    assert a2.new_workspace is True  # 値省略 → 既定の場所に作成

    a3 = parser.parse_args(["goal", "run", "ゴール", "--new-workspace", "/tmp/ws"])
    assert a3.new_workspace == "/tmp/ws"


def test_goal_run_without_target_does_not_invoke_pipeline():
    """対象未指定なら require_api_key もパイプラインも呼ばずに案内表示して return する。"""
    called = {"api": False}

    def fake_require(_label):
        called["api"] = True

    args = argparse.Namespace(goal_text="x", workspace=None, new_workspace=None)
    asyncio.run(cmd_goal_run(args, require_api_key=fake_require))
    assert called["api"] is False
