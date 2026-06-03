"""CLI サブコマンドのスモークテスト（F10）。

`build_parser()` が全サブコマンドを構築でき、各 `--help` が正常終了（SystemExit 0）し、
登録ハンドラがすべて callable で `HANDLERS` と整合することを確認する。
副作用のある実行はせず、パーサ構築/ヘルプのみを叩く。
"""

from __future__ import annotations

import argparse

import pytest

import main as cli


def _subcommand_names(parser: argparse.ArgumentParser) -> list[str]:
    names: list[str] = []
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            names.extend(action.choices.keys())
    return names


_SUBCOMMANDS = _subcommand_names(cli.build_parser())


def test_build_parser_returns_parser():
    assert isinstance(cli.build_parser(), argparse.ArgumentParser)


def test_has_subcommands():
    assert len(_SUBCOMMANDS) >= 10  # init/analyze/serve/chat/doctor/version/... 多数


def test_all_handlers_callable():
    assert cli.HANDLERS
    for name, fn in cli.HANDLERS.items():
        assert callable(fn), name


def test_top_level_help_exits_zero():
    with pytest.raises(SystemExit) as exc:
        cli.build_parser().parse_args(["--help"])
    assert exc.value.code == 0


@pytest.mark.parametrize("cmd", _SUBCOMMANDS)
def test_subcommand_help_exits_zero(cmd):
    with pytest.raises(SystemExit) as exc:
        cli.build_parser().parse_args([cmd, "--help"])
    assert exc.value.code == 0


def test_known_subcommands_present():
    # 代表的なコマンドが登録されている
    for expected in ("analyze", "serve", "doctor", "version"):
        assert expected in _SUBCOMMANDS, expected
