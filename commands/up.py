"""
pantheon up — フル起動エントリ。

引数なし起動（exe ダブルクリック / `pantheon`）はこの ``up`` に注入される。やること:

  1. wmux に org 非依存の「汎用チャット」タブ（``pantheon chat``）を立てる
  2. Web GUI（監視・可視化・承認・ガイド）を起動する
  3. 既定ブラウザで GUI を開く

``serve`` は GUI のみ（従来どおり）。``up`` がフル起動。対話・実行系は wmux 側で行う設計
なので、ここでは「監視用の GUI」と「汎用チャットの入口」をまとめて立ち上げる。
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any, List


def _self_command(*args: str) -> List[str]:
    """この Pantheon 自身を再呼び出しする argv を返す。

    frozen(exe) 時は ``Pantheon.exe <args>``（``--daemon-run`` と同じ自己再実行）。
    ソース実行時は同じ Python で ``main.py <args>`` を起動する（``pantheon`` が
    新しいシェルの PATH に無くても確実に動く）。
    """
    if getattr(sys, "frozen", False):
        return [sys.executable, *args]
    from core.paths import resource_root

    return [sys.executable, str(resource_root() / "main.py"), *args]


def _launch_general_chat_tab() -> None:
    """wmux に org 非依存の汎用チャットタブ（``pantheon chat``）を立てる。"""
    from core.runtime.multiplexer import MultiplexerUnavailableError
    from core.runtime.session_orchestrator import SessionOrchestrator

    orchestrator = SessionOrchestrator()
    try:
        surface = orchestrator.open_command_surface(
            group="Pantheon",
            title="chat",
            command=_self_command("chat"),
            agent_id="pantheon:general-chat",
            role="chat",
        )
    except MultiplexerUnavailableError as exc:
        print(f"[INFO] wmux 汎用チャットタブは起動しませんでした: {exc}")
        print("   端末で `pantheon chat` を実行すれば汎用チャットを使えます。")
        return
    except Exception as exc:  # noqa: BLE001 - wmux 連携失敗で GUI 起動を止めない
        print(f"[WARN] wmux 連携でエラー: {exc}")
        print("   GUI の起動は続行します。端末で `pantheon chat` を使えます。")
        return

    tab_name = surface.metadata.get("tab_name", "Pantheon · chat")
    print(f"[OK] wmux に汎用チャットタブを起動しました: {tab_name}")


def cmd_up(args: argparse.Namespace) -> None:
    """フル起動: wmux 汎用チャット + Web GUI(監視) + ブラウザ自動オープン。"""
    if not getattr(args, "no_wmux", False):
        _launch_general_chat_tab()

    # 配信 UI の選択は web.server の import 時（_serve_dir 解決）に効くため、import より先に反映。
    if getattr(args, "ui", None):
        os.environ["PANTHEON_UI"] = args.ui

    try:
        from web.server import run_server
    except ImportError:
        print("[ERROR] Web GUI には fastapi と uvicorn が必要です。")
        print("   pip install 'pantheon[web]' でインストールしてください。")
        sys.exit(1)

    # run_server はブロッキング（uvicorn.run）。ブラウザは listen 開始後に
    # 別スレッドで自動オープンされる（web.server._open_browser_when_ready）。
    run_server(
        host=args.host,
        port=args.port,
        open_browser=not getattr(args, "no_browser", False),
    )


def register(subparsers: Any) -> None:
    parser = subparsers.add_parser(
        "up",
        help="フル起動（Web GUI 監視 + wmux 汎用チャット + ブラウザ）",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help=(
            "バインドホスト (default: 127.0.0.1=ローカルのみ)。"
            "LAN 公開する場合は --host 0.0.0.0 と PANTHEON_API_TOKEN の設定を推奨"
        ),
    )
    parser.add_argument("--port", type=int, default=7860, help="ポート番号 (default: 7860)")
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="起動時にブラウザを自動で開かない（既定は自動で開く）",
    )
    parser.add_argument(
        "--no-wmux",
        action="store_true",
        help="wmux 汎用チャットタブを起動しない（Web GUI のみ）",
    )
    parser.add_argument(
        "--ui",
        choices=("legacy", "atelier"),
        default=None,
        help=(
            "配信する GUI (default: legacy=web/dist)。atelier=新 GUI（web/atelier/dist、"
            "要 `cd web/atelier && npm run build`）。環境変数 PANTHEON_UI でも指定可"
        ),
    )
    parser.set_defaults(handler_name="cmd_up")
