from __future__ import annotations

import argparse
from importlib.metadata import PackageNotFoundError, version as package_version
from typing import Any


def get_version_string() -> str:
    try:
        current = package_version("pantheon")
    except PackageNotFoundError:
        current = "0.1.0"
    return f"Pantheon {current}"


async def cmd_version(args: argparse.Namespace) -> None:
    print(get_version_string())


def register(subparsers: Any) -> None:
    version_parser = subparsers.add_parser("version", help="バージョン情報を表示する")
    version_parser.set_defaults(handler_name="cmd_version")
