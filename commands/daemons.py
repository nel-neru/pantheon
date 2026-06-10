"""`pantheon daemons` - 全デーモンの統合ライフサイクル管理。

improvement（自律改善）/ content（コンテンツ/PDCA）の全 daemon を
:mod:`core.runtime.daemon_registry` 経由で一元的に status/start/stop する。

- ``start`` / ``stop`` はプロセス操作と同時に desired state（enabled.json）も
  更新する。watchdog はこの desired state を見て復元するため、明示的に stop
  した daemon が勝手に蘇ることはない。
- ``enable`` / ``disable`` は desired state **のみ** を切り替える（プロセスには
  触れない）。watchdog 導入前の事前設定や、次回再起動からの反映に使う。
"""

from __future__ import annotations

import argparse
from typing import Any, List, Optional

# argparse の choices 用（core を import せず CLI 起動を軽く保つ）。
# core/runtime/daemon_registry.py の KNOWN_DAEMONS と同期させること。
DAEMON_NAMES = ("improvement", "content")


def _format_age(age: Optional[float]) -> str:
    if age is None:
        return "-"
    if age < 60:
        return f"{age:.0f}s"
    if age < 3600:
        return f"{age / 60:.0f}m"
    return f"{age / 3600:.1f}h"


def _resolve_names(name: str) -> List[str]:
    return list(DAEMON_NAMES) if name == "all" else [name]


async def cmd_daemons_status(args: argparse.Namespace) -> None:
    """全デーモンの稼働状態・heartbeat・レート制限を表示する。"""
    from core.runtime.daemon_registry import all_statuses
    from core.runtime.usage_gate import RateLimitGate

    info = RateLimitGate().current()
    if info is not None:
        reset = info.reset_at.isoformat() if info.reset_at else "(時刻不明)"
        print(f"[!] レート制限中 - {reset} に自動再開予定 (scope={info.scope})")

    # 注意: Windows コンソール (cp932) では絵文字が UnicodeEncodeError になるため
    # マーカーは ASCII に限定する。
    for st in all_statuses():
        if st["healthy"]:
            mark = "[OK]  "
        elif st["running"]:
            mark = "[HANG]"  # 生きているが heartbeat が stale（ハング疑い）
        elif st["enabled"]:
            mark = "[DEAD]"  # 動いているべきなのに死んでいる（watchdog の restart 対象）
        else:
            mark = "[OFF] "
        beat = st.get("heartbeat") or {}
        freshness = "stale" if st["heartbeat_stale"] else "fresh"
        print(
            f"{mark} {st['name']:<12} running={st['running']} enabled={st['enabled']} "
            f"pid={st['pid'] or '-'} state={beat.get('status', '-')} "
            f"heartbeat={_format_age(st['heartbeat_age_seconds'])} ({freshness})"
        )
        print(f"   {st['description']}")
        print(f"   log: {st['log_path']}")


async def cmd_daemons_start(args: argparse.Namespace) -> None:
    """デーモンを起動する（desired state も ON にする）。"""
    from core.runtime.daemon_registry import get_spec, spawn_daemon

    for name in _resolve_names(args.name):
        spec = get_spec(name)
        interval = args.interval or spec.default_interval
        extra = [f"--interval={interval}"]
        if name == "improvement":
            extra.append(f"--max-files={args.max_files}")
        result = spawn_daemon(name, args=extra)
        print(f"[{name}] {result['status']} (pid={result['pid']}, log={result['log_path']})")


async def cmd_daemons_stop(args: argparse.Namespace) -> None:
    """デーモンを停止する（desired state も OFF にする＝watchdog は復元しない）。"""
    from core.runtime.daemon_registry import stop_daemon

    for name in _resolve_names(args.name):
        result = stop_daemon(name)
        print(f"[{name}] {result['status']}")


async def cmd_daemons_enable(args: argparse.Namespace) -> None:
    """desired state のみ ON にする（watchdog/再起動時に起動される）。"""
    from core.runtime.daemon_registry import get_spec, load_enabled, set_enabled

    for name in _resolve_names(args.name):
        spec = get_spec(name)
        # 過去に start で記録された args は保持する（args=None なら set_enabled は
        # 既存値を維持）。未記録の場合のみ既定 interval を入れる。
        has_recorded_args = bool(load_enabled().get(name, {}).get("args"))
        set_enabled(
            name,
            True,
            args=None if has_recorded_args else [f"--interval={spec.default_interval}"],
        )
        print(f"[{name}] enabled（watchdog/次回復元の対象になりました）")


async def cmd_daemons_disable(args: argparse.Namespace) -> None:
    """desired state のみ OFF にする（実行中プロセスには触れない）。"""
    from core.runtime.daemon_registry import set_enabled

    for name in _resolve_names(args.name):
        set_enabled(name, False)
        print(f"[{name}] disabled（watchdog は復元しません）")


def register(subparsers: Any) -> None:
    parser = subparsers.add_parser(
        "daemons",
        help="全デーモンの統合管理（status / start / stop / enable / disable）",
    )
    sub = parser.add_subparsers(dest="daemons_command", required=True)

    sp = sub.add_parser("status", help="全デーモンの稼働状態・heartbeat・レート制限を表示")
    sp.set_defaults(handler_name="cmd_daemons_status")

    sp = sub.add_parser("start", help="デーモンを起動（desired state も ON）")
    sp.add_argument("name", choices=[*DAEMON_NAMES, "all"])
    sp.add_argument("--interval", type=int, default=None, help="サイクル間隔（秒）")
    sp.add_argument(
        "--max-files", type=int, default=10, help="improvement のみ: org あたり最大ファイル数"
    )
    sp.set_defaults(handler_name="cmd_daemons_start")

    sp = sub.add_parser("stop", help="デーモンを停止（desired state も OFF）")
    sp.add_argument("name", choices=[*DAEMON_NAMES, "all"])
    sp.set_defaults(handler_name="cmd_daemons_stop")

    sp = sub.add_parser("enable", help="desired state のみ ON（watchdog 復元対象にする）")
    sp.add_argument("name", choices=[*DAEMON_NAMES, "all"])
    sp.set_defaults(handler_name="cmd_daemons_enable")

    sp = sub.add_parser("disable", help="desired state のみ OFF（プロセスには触れない）")
    sp.add_argument("name", choices=[*DAEMON_NAMES, "all"])
    sp.set_defaults(handler_name="cmd_daemons_disable")
