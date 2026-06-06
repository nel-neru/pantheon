"""
CLI 配線の回帰テスト。

build_parser() が登録する全 handler_name が main.HANDLERS に存在し、逆に HANDLERS の
全エントリが到達可能であることを保証する。サブコマンド追加時の「ハンドラ未登録」事故を防ぐ。
"""

from __future__ import annotations

import argparse

import main
from commands import build_parser


def _collect_handler_names(parser: argparse.ArgumentParser) -> set[str]:
    names: set[str] = set()
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for sub in action.choices.values():
                handler = (getattr(sub, "_defaults", {}) or {}).get("handler_name")
                if handler:
                    names.add(handler)
                names |= _collect_handler_names(sub)
    return names


def test_every_registered_handler_name_exists_in_handlers():
    parser = build_parser()
    registered = _collect_handler_names(parser)
    assert registered, "build_parser registered no handlers"
    missing = sorted(registered - set(main.HANDLERS))
    assert not missing, f"handler_name(s) without a HANDLERS entry: {missing}"


def test_handlers_are_callable():
    for name, handler in main.HANDLERS.items():
        assert callable(handler), f"HANDLERS[{name!r}] is not callable"


def test_atlas_command_is_wired():
    parser = build_parser()
    registered = _collect_handler_names(parser)
    assert "cmd_atlas" in registered
    assert "cmd_atlas" in main.HANDLERS


def test_core_flow_commands_present():
    parser = build_parser()
    registered = _collect_handler_names(parser)
    # 中核フローの代表コマンドが配線されていること
    for expected in {
        "cmd_init",
        "cmd_org_add",
        "cmd_analyze",
        "cmd_approve",
        "cmd_goal_run",
        "cmd_chat",
    }:
        assert expected in registered
        assert expected in main.HANDLERS
