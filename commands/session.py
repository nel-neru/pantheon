"""
``pantheon session`` — drive multiplexer-backed agent sessions.

A session is a multiplexer workspace (big tab); each agent is a surface (small
tab) running a headless ``claude`` invocation. State lives in the repo under
``.pantheon/sessions/<id>/``.

    pantheon session start --name "MyApp review" --demo [--watch]
    pantheon session start --name X --agents-file agents.json
    pantheon session list
    pantheon session show <id> [--log]
    pantheon session stop <id>
    pantheon session doctor
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, List


def _orchestrator(args: argparse.Namespace):
    from core.runtime.session_orchestrator import SessionOrchestrator

    return SessionOrchestrator(
        repo_root=getattr(args, "repo", None) or Path.cwd(),
        prefer=getattr(args, "prefer", None),
    )


def _load_tasks(args: argparse.Namespace) -> List[Any]:
    from core.runtime.session_orchestrator import AgentTask, demo_tasks

    if getattr(args, "demo", False):
        return demo_tasks()
    path = getattr(args, "agents_file", None)
    if not path:
        return demo_tasks()
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    tasks: List[AgentTask] = []
    for item in data:
        tasks.append(AgentTask(
            agent_id=item["agent_id"],
            title=item.get("title", item["agent_id"]),
            prompt=item["prompt"],
            system_prompt=item.get("system_prompt"),
            model=item.get("model"),
            role=item.get("role", "agent"),
            cwd=item.get("cwd"),
            stream_json=item.get("stream_json", True),
        ))
    return tasks


def _print_surface(sr: dict) -> None:
    status = sr.get("status", "?")
    code = sr.get("exit_code")
    code_str = "" if code is None else f" exit={code}"
    print(f"    - {sr.get('title', sr.get('agent_id'))} [{status}{code_str}]  pty={sr.get('pty_id')}")


async def cmd_session_start(args: argparse.Namespace) -> None:
    orch = _orchestrator(args)
    tasks = _load_tasks(args)
    name = args.name or "Pantheon session"
    record = orch.start_session(name, tasks)
    print(f"[OK] session started: {record.id}")
    print(f"  driver:    {record.driver}")
    print(f"  workspace: {record.workspace.get('name')} ({record.workspace.get('id')})")
    print(f"  agents:    {len(record.surfaces)}")
    for sr in record.surfaces:
        _print_surface(sr)
    print(f"  state:     .pantheon/sessions/{record.id}/")

    if getattr(args, "watch", False):
        print("\nWatching… (Ctrl+C to stop watching; agents keep running)")
        deadline = time.time() + float(getattr(args, "timeout", 0) or 1800)
        try:
            while time.time() < deadline:
                time.sleep(2.0)
                rec = orch.poll_session(record.id)
                if rec is None:
                    break
                # Auto-resume any agent whose usage-limit window has reopened.
                if rec.status == "rate_limited" and orch.due_for_resume(record.id):
                    print("\n[rate-limit] reset window reached — resuming agents…")
                    rec = orch.resume_session(record.id) or rec
                done = sum(1 for s in rec.surfaces
                           if s.get("status") in ("done", "failed", "closed"))
                limited = sum(1 for s in rec.surfaces if s.get("status") == "rate_limited")
                suffix = f" ({limited} rate-limited)" if limited else ""
                print(f"  [{rec.status}] {done}/{len(rec.surfaces)} agents finished{suffix}", end="\r")
                if rec.status in ("completed", "stopped"):
                    print()
                    print("[OK] session complete.")
                    for sr in rec.surfaces:
                        _print_surface(sr)
                    break
        except KeyboardInterrupt:
            print("\n(stopped watching; session still running)")


async def cmd_session_list(args: argparse.Namespace) -> None:
    orch = _orchestrator(args)
    records = orch.list_sessions()
    if not records:
        print("(no sessions)")
        return
    print(f"{'ID':<40} {'DRIVER':<9} {'STATUS':<10} AGENTS")
    for rec in records:
        print(f"{rec.id:<40} {rec.driver:<9} {rec.status:<10} {len(rec.surfaces)}")


async def cmd_session_show(args: argparse.Namespace) -> None:
    orch = _orchestrator(args)
    rec = orch.poll_session(args.id) or orch.get_session(args.id)
    if rec is None:
        print(f"[ERROR] session not found: {args.id}")
        return
    print(f"session {rec.id}")
    print(f"  name:      {rec.name}")
    print(f"  driver:    {rec.driver}")
    print(f"  status:    {rec.status}")
    print(f"  created:   {rec.created_at}")
    print(f"  workspace: {rec.workspace.get('name')} ({rec.workspace.get('id')})")
    print(f"  agents:")
    for sr in rec.surfaces:
        _print_surface(sr)
    if getattr(args, "log", False):
        for sr in rec.surfaces:
            print(f"\n----- {sr.get('title')} ({sr.get('agent_id')}) -----")
            print(orch.agent_log(rec.id, sr.get("agent_id"), tail=4000) or "(no output yet)")


async def cmd_session_stop(args: argparse.Namespace) -> None:
    orch = _orchestrator(args)
    rec = orch.stop_session(args.id)
    if rec is None:
        print(f"[ERROR] session not found: {args.id}")
        return
    print(f"[OK] session stopped: {rec.id}")


async def cmd_session_resume(args: argparse.Namespace) -> None:
    orch = _orchestrator(args)
    rec = orch.resume_session(args.id, force=getattr(args, "force", False))
    if rec is None:
        print(f"[ERROR] session not found: {args.id}")
        return
    limited = sum(1 for s in rec.surfaces if s.get("status") == "rate_limited")
    print(f"[OK] session resumed: {rec.id}  (status: {rec.status}, {limited} still rate-limited)")
    for sr in rec.surfaces:
        _print_surface(sr)


async def cmd_session_doctor(args: argparse.Namespace) -> None:
    from core.runtime.claude_code import claude_available, claude_binary
    from core.runtime.multiplexer import get_driver
    from core.runtime.multiplexer.wmux_rpc import (
        WmuxClient, WmuxNotConfirmedError, is_wmux_running,
    )

    print("Pantheon session doctor")
    print(f"  claude CLI:   {'OK ' + (claude_binary() or '') if claude_available() else 'NOT FOUND'}")
    print(f"  wmux running: {is_wmux_running()}")
    drv = get_driver()
    print(f"  driver(auto): {drv.name}")
    if is_wmux_running():
        client = WmuxClient()
        try:
            client.verify()
            print("  wmux plugin:  CONFIRMED (Pantheon is approved)")
            ws = client.call("workspace.list")
            print(f"  workspaces:   {len(ws)} open")
        except WmuxNotConfirmedError as exc:
            print("  wmux plugin:  AWAITING APPROVAL — approve 'pantheon' in the wmux window once,")
            print("                then re-run `pantheon session doctor`.")
            print(f"                ({exc})")
        except Exception as exc:
            print(f"  wmux plugin:  error: {exc}")


def register(subparsers: Any) -> None:
    session = subparsers.add_parser("session", help="マルチプレクサ上でエージェントセッションを駆動")
    session.add_argument("--repo", help="リポジトリルート（既定: カレント）")
    sub = session.add_subparsers(dest="session_command", required=True)

    start = sub.add_parser("start", help="セッションを開始（大タブ＝ワークスペース、エージェント＝小タブ）")
    start.add_argument("--name", help="セッション名（ワークスペース名）")
    start.add_argument("--demo", action="store_true", help="デモ用の最小エージェントで起動")
    start.add_argument("--agents-file", dest="agents_file", help="エージェント定義 JSON ファイル")
    start.add_argument("--prefer", choices=["wmux", "cmux", "headless"], help="使用するドライバを強制")
    start.add_argument("--watch", action="store_true", help="完了までステータスを監視")
    start.add_argument("--timeout", type=float, default=1800, help="--watch のタイムアウト秒")
    start.set_defaults(handler_name="cmd_session_start")

    listp = sub.add_parser("list", help="セッション一覧")
    listp.set_defaults(handler_name="cmd_session_list")

    show = sub.add_parser("show", help="セッション詳細")
    show.add_argument("id", help="セッションID")
    show.add_argument("--log", action="store_true", help="各エージェントのログ末尾を表示")
    show.set_defaults(handler_name="cmd_session_show")

    stop = sub.add_parser("stop", help="セッションのエージェントを停止")
    stop.add_argument("id", help="セッションID")
    stop.set_defaults(handler_name="cmd_session_stop")

    resume = sub.add_parser("resume", help="レート制限で止まったエージェントを再開")
    resume.add_argument("id", help="セッションID")
    resume.add_argument("--force", action="store_true", help="リセット時刻を待たず即再開")
    resume.set_defaults(handler_name="cmd_session_resume")

    doctor = sub.add_parser("doctor", help="claude / wmux 接続状態を診断")
    doctor.set_defaults(handler_name="cmd_session_doctor")
