from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _health_bar(score: float, width: int = 20) -> str:
    filled = int(score / 100 * width)
    return f"[{'█' * filled}{'░' * (width - filled)}]"


def _tail_file(path: Path, count: int) -> list[str]:
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    return lines[-count:] if count > 0 else lines


def _snapshot_platform_state(platform_home: Path, snapshot_dir: Path) -> None:
    if snapshot_dir.exists():
        shutil.rmtree(snapshot_dir)
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    for item in platform_home.iterdir():
        if item.name in {"backups", snapshot_dir.name}:
            continue
        destination = snapshot_dir / item.name
        if item.is_dir():
            shutil.copytree(item, destination)
        else:
            shutil.copy2(item, destination)


def _restore_snapshot_contents(platform_home: Path, snapshot_dir: Path) -> None:
    for item in snapshot_dir.iterdir():
        target = platform_home / item.name
        if target.name == "backups":
            continue
        if target.exists():
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
        if item.is_dir():
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)


async def cmd_platform_status(args: argparse.Namespace, *, get_psm: Any) -> None:
    """全 Organization 横断のプラットフォームダッシュボード（指標は実状態から計算）"""
    from core.metrics.live_metrics import compute_live_group_metrics, compute_live_org_metrics

    psm = get_psm()
    orgs = psm.load_organizations()

    if not orgs:
        print("\nOrganization が登録されていません。")
        print("   pantheon org add --name MyApp --repo /path/to/app")
        return

    # GUI（web/server.py）と同じ live_metrics を使い、CLI と GUI の数値を一致させる。
    metrics_list = []
    items = []
    for org in orgs:
        sm = psm.get_org_state_manager(org)
        live = compute_live_org_metrics(org, sm)
        metrics_list.append((org, live, live.pending_proposals))
        items.append((org, live))

    group = compute_live_group_metrics(items)

    print(f"\n{'═' * 60}")
    print("  Pantheon プラットフォーム")
    print(f"  Core: {psm.platform_home}")
    print(f"{'═' * 60}")
    print(f"  グループ健康度   : {group.group_health_score:5.1f} / 100")
    print(f"  バランススコア   : {group.balance_score:5.1f} / 100")
    print(f"  Organization 数  : {group.total_organizations} ({group.active_organizations} active)")
    print(f"  最も弱い Org     : {group.weakest_organization or '—'}")
    print(f"{'─' * 60}")
    print("  Organizations（子会社）\n")

    for org, metric, pending in sorted(
        metrics_list, key=lambda item: item[1].health_score, reverse=True
    ):
        bar = _health_bar(metric.health_score)
        badge = (
            "[HEALTHY]"
            if metric.health_score >= 70
            else "[WATCH]"
            if metric.health_score >= 50
            else "[CRITICAL]"
        )
        repo = org.target_repo_path or "(未設定)"
        print(f"  {badge} {org.name}")
        print(f"     リポジトリ : {repo}")
        print(f"     健康度     : {bar} {metric.health_score:.1f}")
        print(f"     未対応提案 : {pending} 件  |  Agent: {len(org.get_all_agents())} 個")
        print()

    print(f"{'═' * 60}")
    print("  pantheon platform run-all  で全 Org の改善サイクルを実行")
    print("  pantheon serve             で Web GUI を起動")
    print(f"{'═' * 60}\n")


async def cmd_platform_run_all(args: argparse.Namespace, *, get_psm: Any) -> None:
    """全 Organization の改善サイクルを優先度順に実行する"""
    from core.metrics.balanced_growth import (
        calculate_organization_metrics,
        get_improvement_priority_score,
    )
    from core.quality.self_improvement_loop import SelfImprovementLoop

    psm = get_psm()
    orgs = psm.load_organizations()

    if not orgs:
        print("Organization が登録されていません。")
        return

    if getattr(args, "from_atlas", False):
        from core.atlas import build_atlas, generate_atlas_proposals
        from core.bootstrap import META_ORG_NAME

        meta_org = next((o for o in orgs if o.name == META_ORG_NAME), None)
        if meta_org is not None:
            meta_sm = psm.get_org_state_manager(meta_org)
            result = generate_atlas_proposals(build_atlas(), meta_sm)
            print(
                f"[Atlas] known_issues から meta 提案を生成: "
                f"新規 {len(result['created'])} / 対象 {result['total']} 件"
            )
        else:
            print("[Atlas] Meta-Improvement Organization が無いため --from-atlas をスキップします")

    scored = []
    for org in orgs:
        sm = psm.get_org_state_manager(org)
        pending = len(sm.get_pending_improvement_proposals(limit=100))
        metric = calculate_organization_metrics(org, pending_proposals_count=pending)
        scored.append((org, sm, get_improvement_priority_score(metric)))

    scored.sort(key=lambda item: item[2], reverse=True)
    target = scored[: args.max_orgs]

    print(f"\n改善サイクルを実行します ({len(target)} / {len(orgs)} Organization)\n")
    successes = 0
    failures: list[tuple[str, str]] = []
    for org, sm, score in target:
        print(f"  → {org.name} (優先度: {score:.1f}) [{org.target_repo_path or '(未設定)'}]")
        loop = SelfImprovementLoop(org, sm)
        try:
            await loop.run_improvement_cycle()
            successes += 1
        except Exception as exc:  # noqa: BLE001
            logger.exception("platform run-all failed for organization %s", org.name)
            failures.append((org.name, str(exc)))
            print(f"    [ERROR] {org.name}: {exc}")
            continue

    print(f"\n[OK] 完了。成功: {successes} / {len(target)}")
    if failures:
        print("[WARN] 失敗した Organization:")
        for org_name, message in failures:
            print(f"  - {org_name}: {message}")
    print("pantheon platform status で結果を確認できます。")


async def cmd_platform_config(args: argparse.Namespace, *, get_psm: Any) -> None:
    psm = get_psm()
    config = psm.load_platform_config()

    print(f"\nPlatform Config — {psm.platform_home}\n")
    if not config:
        print("  (設定がありません)")
        return

    for key in sorted(config):
        print(f"  {key:24}: {config[key]}")


async def cmd_platform_config_set(args: argparse.Namespace, *, get_psm: Any) -> None:
    psm = get_psm()
    config = psm.load_platform_config()
    raw_value = args.value
    try:
        value = json.loads(raw_value)
    except Exception:
        value = raw_value
    config[args.key] = value
    psm.save_platform_config(config)
    print(f"[OK] {args.key} を更新しました。")


async def cmd_platform_logs(args: argparse.Namespace, *, get_psm: Any) -> None:
    psm = get_psm()
    platform_home = psm.platform_home
    daemon_log = platform_home / "daemon.log"
    scheduler_log = platform_home / "scheduler_log.jsonl"

    print(f"\nPlatform Logs — {platform_home}\n")
    any_lines = False
    for label, path in (("daemon", daemon_log), ("scheduler", scheduler_log)):
        lines = _tail_file(path, args.tail)
        if not lines:
            continue
        any_lines = True
        print(f"[{label}] {path}")
        for line in lines:
            print(f"  {line}")
        print()
    if not any_lines:
        print("  ログがありません。")


async def cmd_platform_backup(args: argparse.Namespace, *, get_psm: Any) -> None:
    from core.state.backup_manager import BackupManager

    psm = get_psm()
    snapshot_dir = psm.platform_home / ".platform_snapshot"
    _snapshot_platform_state(psm.platform_home, snapshot_dir)
    backup_manager = BackupManager(psm.platform_home)
    backup_path = backup_manager.backup_now(snapshot_dir)
    shutil.rmtree(snapshot_dir, ignore_errors=True)
    print(f"[OK] プラットフォームをバックアップしました: {backup_path}")


async def cmd_platform_restore(args: argparse.Namespace, *, get_psm: Any) -> None:
    from core.state.backup_manager import BackupManager

    psm = get_psm()
    snapshot_dir = psm.platform_home / ".platform_snapshot"
    backup_manager = BackupManager(psm.platform_home)
    backups = backup_manager.list_backups(snapshot_dir)
    if not backups:
        print("[ERROR] 復元できるバックアップがありません。")
        sys.exit(1)
    if not backup_manager.restore_latest(snapshot_dir):
        print("[ERROR] バックアップの復元に失敗しました。")
        sys.exit(1)
    _restore_snapshot_contents(psm.platform_home, snapshot_dir)
    shutil.rmtree(snapshot_dir, ignore_errors=True)
    print(f"[OK] バックアップを復元しました: {backups[0]}")


def cmd_serve(args: argparse.Namespace) -> None:
    """Web GUI サーバーを起動する"""
    try:
        from web.server import run_server
    except ImportError:
        print("[ERROR] Web GUI には fastapi と uvicorn が必要です。")
        print("   pip install 'pantheon[web]' でインストールしてください。")
        sys.exit(1)

    run_server(
        host=args.host,
        port=args.port,
        open_browser=not getattr(args, "no_browser", False),
    )


async def cmd_daemon_start(
    args: argparse.Namespace,
    *,
    get_platform_home: Any,
    project_root: Path,
) -> None:
    """自律改善デーモンをバックグラウンドで起動する"""
    import subprocess

    platform_home = get_platform_home()
    pid_file = platform_home / "daemon.pid"

    if pid_file.exists():
        pid = int(pid_file.read_text().strip())
        try:
            import os as _os

            _os.kill(pid, 0)
            print(f"[WARN] デーモンはすでに起動中です (PID: {pid})")
            return
        except OSError:
            pid_file.unlink(missing_ok=True)

    log_file = platform_home / "daemon.log"
    if getattr(sys, "frozen", False):
        # exe 化時は `-m core._daemon_runner` が使えないので、自分自身を
        # `Pantheon.exe --daemon-run ...` として再実行する（main.py 側で捕捉）。
        cmd = [
            sys.executable,
            "--daemon-run",
            f"--interval={args.interval}",
            f"--max-files={args.max_files}",
        ]
    else:
        cmd = [
            sys.executable,
            "-m",
            "core._daemon_runner",
            f"--interval={args.interval}",
            f"--max-files={args.max_files}",
        ]

    with open(log_file, "a", encoding="utf-8") as log_handle:
        proc = subprocess.Popen(
            cmd,
            cwd=project_root,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    pid_file.write_text(str(proc.pid), encoding="utf-8")
    print(f"[OK] デーモンを起動しました (PID: {proc.pid})")
    print(f"   ログ  : {log_file}")
    print(f"   間隔  : {args.interval} 秒ごと")
    print("\n停止: pantheon daemon stop")
    print("状態: pantheon daemon status")


def cmd_daemon_stop(args: argparse.Namespace, *, get_platform_home: Any) -> None:
    """自律改善デーモンを停止する"""
    import signal as _signal

    pid_file = get_platform_home() / "daemon.pid"
    if not pid_file.exists():
        print("[INFO] デーモンは起動していません。")
        return

    pid = int(pid_file.read_text().strip())
    try:
        import os as _os

        _os.kill(pid, _signal.SIGTERM)
        pid_file.unlink(missing_ok=True)
        print(f"[OK] デーモンを停止しました (PID: {pid})")
    except OSError:
        pid_file.unlink(missing_ok=True)
        print(f"[INFO] デーモン (PID: {pid}) はすでに停止しています。")


def cmd_daemon_status(args: argparse.Namespace, *, get_platform_home: Any) -> None:
    """デーモンの稼働状態とログを表示する"""
    platform_home = get_platform_home()
    pid_file = platform_home / "daemon.pid"
    scheduler_log = platform_home / "scheduler_log.jsonl"

    if pid_file.exists():
        pid = int(pid_file.read_text().strip())
        try:
            import os as _os

            _os.kill(pid, 0)
            print(f"[OK] デーモン稼働中 (PID: {pid})")
        except OSError:
            print(f"デーモン停止中（PID ファイルが残存: {pid}）")
    else:
        print("デーモンは起動していません。")

    if scheduler_log.exists():
        lines = scheduler_log.read_text(encoding="utf-8").strip().splitlines()
        recent = lines[-5:]
        if recent:
            print(f"\n直近の実行ログ ({len(lines)} サイクル合計):")
            for line in recent:
                try:
                    data = json.loads(line)
                    ts = data.get("started_at", "")[:19].replace("T", " ")
                    triggered = data.get("triggered_orgs", 0)
                    cycle = data.get("cycle", "?")
                    print(f"  #{cycle:3}  {ts}  triggered={triggered}")
                except Exception:
                    pass

    print("\n起動: pantheon daemon start [--interval=3600]")


def register(subparsers: Any) -> None:
    platform_parser = subparsers.add_parser("platform", help="プラットフォーム全体の操作")
    platform_sub = platform_parser.add_subparsers(dest="platform_command", required=True)

    status_parser = platform_sub.add_parser("status", help="全 Organization 横断ダッシュボード")
    status_parser.set_defaults(handler_name="cmd_platform_status")

    run_all_parser = platform_sub.add_parser("run-all", help="全 Organization の改善サイクルを実行")
    run_all_parser.add_argument(
        "--max-orgs", type=int, default=5, help="最大実行 Org 数（default: 5）"
    )
    run_all_parser.add_argument(
        "--from-atlas",
        action="store_true",
        help="実行前に Atlas の known_issues から meta 提案を生成し Meta-Improvement Org に投入する",
    )
    run_all_parser.set_defaults(handler_name="cmd_platform_run_all")

    config_parser = platform_sub.add_parser("config", help="プラットフォーム設定を表示・更新")
    config_parser.set_defaults(handler_name="cmd_platform_config")
    config_sub = config_parser.add_subparsers(dest="platform_config_command")

    config_set = config_sub.add_parser("set", help="設定値を更新")
    config_set.add_argument("key", help="設定キー")
    config_set.add_argument("value", help="設定値")
    config_set.set_defaults(handler_name="cmd_platform_config_set")

    logs_parser = platform_sub.add_parser("logs", help="プラットフォームログを表示")
    logs_parser.add_argument("--tail", type=int, default=20, help="末尾から表示する行数")
    logs_parser.set_defaults(handler_name="cmd_platform_logs")

    backup_parser = platform_sub.add_parser("backup", help="プラットフォーム状態をバックアップ")
    backup_parser.set_defaults(handler_name="cmd_platform_backup")

    restore_parser = platform_sub.add_parser("restore", help="最新バックアップを復元")
    restore_parser.set_defaults(handler_name="cmd_platform_restore")

    serve_parser = subparsers.add_parser("serve", help="Web GUI を起動する")
    serve_parser.add_argument("--host", default="0.0.0.0", help="バインドホスト (default: 0.0.0.0)")
    serve_parser.add_argument("--port", type=int, default=7860, help="ポート番号 (default: 7860)")
    serve_parser.add_argument(
        "--no-browser",
        action="store_true",
        help="起動時にブラウザを自動で開かない（既定は自動で開く）",
    )
    serve_parser.set_defaults(handler_name="cmd_serve")

    daemon_parser = subparsers.add_parser("daemon", help="自律改善デーモンの管理")
    daemon_sub = daemon_parser.add_subparsers(dest="daemon_command", required=True)

    start_parser = daemon_sub.add_parser("start", help="デーモンをバックグラウンドで起動")
    start_parser.add_argument(
        "--interval", type=int, default=3600, help="実行間隔（秒, default: 3600）"
    )
    start_parser.add_argument(
        "--max-files", type=int, default=10, help="1 Org あたり最大分析ファイル数"
    )
    start_parser.set_defaults(handler_name="cmd_daemon_start")

    stop_parser = daemon_sub.add_parser("stop", help="デーモンを停止")
    stop_parser.set_defaults(handler_name="cmd_daemon_stop")

    daemon_status = daemon_sub.add_parser("status", help="デーモンの稼働状態・ログを表示")
    daemon_status.set_defaults(handler_name="cmd_daemon_status")
