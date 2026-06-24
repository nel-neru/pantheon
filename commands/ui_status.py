"""`pantheon ui-status` — Web GUI 全ページの「実際に動くか」を実測してレポートする。

起動中の Pantheon サーバー（既定 :7860）に対し、各ページがマウント時に叩く GET API を
実際に HTTP probe し、ページ単位（ok / degraded / error）と全体集計を人間可読で表示しつつ
``~/.pantheon/ui_status.json`` へ保存する（GUI の ``/ui-status`` と共有）。

正直さ（facade 禁止）: サーバー未起動（接続不可）は「サーバー未起動: pantheon serve を実行」と
明示し、**非ゼロ終了**する（全 green の捏造はしない）。``--watch N`` は N 秒間隔ループ、
``KeyboardInterrupt`` で正常終了する。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any

_STATUS_MARK = {"ok": "OK", "degraded": "DEGRADED", "error": "ERROR"}


def _print_report(report: dict[str, Any]) -> None:
    """レポートを人間可読サマリで標準出力へ表示する。"""
    overall = report.get("overall", {})
    print(f"\nUI 状態監視  ({report.get('generated_at', '')})")
    print(
        "  全体: ページ {pages}  (ok {ok} / degraded {degraded} / error {error})  "
        "API {ok_apis}/{total_apis} ok".format(
            pages=overall.get("pages", 0),
            ok=overall.get("ok", 0),
            degraded=overall.get("degraded", 0),
            error=overall.get("error", 0),
            ok_apis=overall.get("ok_apis", 0),
            total_apis=overall.get("total_apis", 0),
        )
    )
    print()
    for page in report.get("pages", []):
        apis = page.get("apis", [])
        failed = sum(1 for a in apis if not a.get("ok"))
        mark = _STATUS_MARK.get(page.get("status", ""), page.get("status", "?"))
        detail = ""
        if page.get("static"):
            detail = "  (静的・API なし)"
        elif failed:
            detail = f"  (API 失敗 {failed}/{len(apis)})"
        elif apis:
            detail = f"  (API {len(apis)} ok)"
        print(f"  [{mark:<8}] {page.get('route', ''):<16} {page.get('label', '')}{detail}")
        # 失敗した api は path / status / error を明示する。
        for api in apis:
            if not api.get("ok"):
                err = api.get("error")
                err_s = f" — {err}" if err else ""
                print(f"      ! {api.get('path', '')}  status={api.get('status_code', 0)}{err_s}")


async def cmd_ui_status(args: argparse.Namespace) -> None:
    """起動中サーバーに対し UI 状態を probe し、表示＋保存する（--watch でループ）。"""
    import httpx

    from core.ui.ui_status import build_ui_status, default_status_path, write_ui_status

    port = int(getattr(args, "port", 7860))
    out = getattr(args, "out", None) or default_status_path()
    as_json = bool(getattr(args, "json", False))
    watch = getattr(args, "watch", None)
    base_url = f"http://127.0.0.1:{port}"

    def _run_once() -> bool:
        """1 回 probe する。サーバー未起動なら False（呼び出し側で非ゼロ終了）。"""
        try:
            with httpx.Client(base_url=base_url, timeout=10.0) as client:
                report = build_ui_status(client)
        except httpx.ConnectError:
            print(
                f"サーバー未起動: pantheon serve を実行してください（接続先 {base_url}）。",
                file=sys.stderr,
            )
            return False
        except httpx.HTTPError as exc:
            print(
                f"サーバー未起動: pantheon serve を実行してください（{exc}）。",
                file=sys.stderr,
            )
            return False

        write_ui_status(report, out)
        if as_json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            _print_report(report)
            print(f"\n保存: {out}")
        return True

    if watch is None:
        ok = _run_once()
        if not ok:
            sys.exit(1)
        return

    # --watch N: N 秒間隔ループ。KeyboardInterrupt で正常終了。
    interval = max(1, int(watch))
    try:
        while True:
            ok = _run_once()
            if not ok:
                # サーバー未起動でも watch は継続（起動待ち）。次の間隔で再試行する。
                pass
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n停止しました。")


def register(subparsers: Any) -> None:
    parser = subparsers.add_parser(
        "ui-status",
        help="Web GUI 全ページの稼働状態を実測（GUI /ui-status と同等）",
    )
    parser.add_argument("--port", type=int, default=7860, help="サーバーのポート（既定 7860）")
    parser.add_argument("--json", action="store_true", help="レポートを JSON で出力")
    parser.add_argument(
        "--watch",
        type=int,
        default=None,
        metavar="SEC",
        help="指定秒間隔で繰り返し監視（省略時は 1 回）",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="保存先（既定 ~/.pantheon/ui_status.json）",
    )
    parser.set_defaults(handler_name="cmd_ui_status")
