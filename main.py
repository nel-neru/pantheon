"""
RepoCorp AI CLI

使用例:
  repocorp init                                       # グローバルプラットフォーム初期化
  repocorp org add --name "MyApp" --repo /path/to/app # 子会社を登録
  repocorp org list                                   # 子会社一覧
  repocorp analyze --org-name "MyApp"                 # 分析して改善提案を生成
  repocorp proposals --org-name "MyApp"               # 提案一覧
  repocorp approve <id> --org-name "MyApp"            # 提案を承認・適用
  repocorp platform status                            # 全子会社横断ダッシュボード
  repocorp platform run-all                           # 全 Org の改善サイクルを実行
  repocorp serve                                      # Web GUI 起動（http://localhost:7860）
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from uuid import uuid4

from core.models.organization import AgentSkill, ImprovementProposal, SpecialistAgent
from core.platform.state import PlatformStateManager, get_platform_home

try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())


def _get_psm() -> PlatformStateManager:
    return PlatformStateManager()


def _get_orchestrator():
    """
    OrchestratorAgent を返す。
    CLI はすべてのタスクをこのエージェント経由で実行する。
    OrchestratorAgent が PreTaskOrchestrator で分析し、最適な専門エージェントに委任する。
    """
    from agents.orchestrator_agent import OrchestratorAgent
    return OrchestratorAgent.create()


# ============================================================
# Commands
# ============================================================

async def cmd_init(args: argparse.Namespace) -> None:
    """グローバルプラットフォームを初期化する"""
    from core.bootstrap import bootstrap_platform

    psm = _get_psm()
    if psm.is_initialized():
        orgs = psm.load_organizations()
        print(f"[OK] プラットフォームはすでに初期化されています")
        print(f"   場所    : {psm.platform_home}")
        print(f"   子会社数 : {len(orgs)} 個")
        print(f"\n次のステップ: repocorp org add --name \"MyApp\" --repo /path/to/app")
        return

    bootstrap_platform()
    print(f"\n[OK] RepoCorp AI プラットフォームを初期化しました")
    print(f"   場所: {get_platform_home()}")
    print(f"\n次のステップ: repocorp org add --name \"MyApp\" --repo /path/to/app")


async def cmd_org_add(args: argparse.Namespace) -> None:
    """新しい Organization（子会社）を担当リポジトリ付きで登録する"""
    from core.bootstrap import bootstrap_platform
    from core.org_factory import create_default_organization, create_organization_from_template

    psm = bootstrap_platform()

    existing = psm.load_organization_by_name(args.name)
    if existing:
        print(f"[WARN] Organization '{args.name}' はすでに存在します (ID: {existing.id})")
        return

    repo_path = Path(args.repo).resolve() if args.repo else Path()
    if args.repo and not repo_path.exists():
        print(f"[ERROR] リポジトリパスが存在しません: {repo_path}")
        sys.exit(1)

    if args.template:
        template_path = Path(__file__).parent / "config" / "departments" / f"{args.template}.yaml"
        org = create_organization_from_template(args.name, args.purpose or "", template_path)
    else:
        org = create_default_organization(args.name, args.purpose or "")

    org.target_repo_path = str(repo_path)
    psm.save_organization(org)

    agents = org.get_all_agents()
    print(f"\n[OK] Organization を登録しました\n")
    print(f"  名前      : {org.name}")
    print(f"  目的      : {org.purpose}")
    print(f"  リポジトリ: {org.target_repo_path}")
    print(f"  ID        : {org.id}")
    print(f"  Division  : {len(org.divisions)} 個 / Agent: {len(agents)} 個")
    for a in agents:
        skills = " / ".join(s.value for s in a.skills)
        print(f"    • {a.name} [{skills}]")
    print(f"\n次のステップ: repocorp analyze --org-name \"{org.name}\"")


async def cmd_org_list(args: argparse.Namespace) -> None:
    """登録済み Organization を一覧表示する"""
    psm = _get_psm()
    orgs = psm.load_organizations()

    if not orgs:
        print("Organization が登録されていません。")
        print("\nヒント: repocorp org add --name MyApp --repo /path/to/app")
        return

    print(f"\nOrganization 一覧 ({len(orgs)} 件)\n")
    for org in orgs:
        sm = psm.get_org_state_manager(org)
        pending = len(sm.get_pending_improvement_proposals(limit=100))
        print(f"  {org.name}")
        print(f"    リポジトリ : {org.target_repo_path or '(未設定)'}")
        print(f"    目的       : {org.purpose[:60]}")
        print(f"    ステータス : {org.status.value}")
        print(f"    Agent数    : {len(org.get_all_agents())} 個")
        print(f"    未対応提案 : {pending} 件")
        print()


async def cmd_org_remove(args: argparse.Namespace) -> None:
    """Organization を削除する"""
    psm = _get_psm()
    org = psm.load_organization_by_name(args.name)
    if not org:
        print(f"[ERROR] Organization '{args.name}' が見つかりません。")
        sys.exit(1)
    psm.remove_organization(str(org.id))
    print(f"[OK] Organization '{args.name}' を削除しました。")


async def cmd_analyze(args: argparse.Namespace) -> None:
    """Organization の担当リポジトリを分析して改善提案を生成する"""
    from agents.base import AgentTask
    from core.state.manager import RepoStateManager

    psm = _get_psm()
    org = psm.load_organization_by_name(args.org_name)
    if not org:
        print(f"[ERROR] Organization '{args.org_name}' が見つかりません。")
        print("   repocorp org list で登録済みの一覧を確認してください。")
        sys.exit(1)

    repo_path = Path(org.target_repo_path) if org.target_repo_path else Path(".")
    print(f"\n{org.name} のコード分析を開始します...")
    print(f"   リポジトリ: {repo_path}\n")

    sm = RepoStateManager(repo_path, org.name)
    agent = _get_orchestrator()
    task = AgentTask(
        task_type="code_review",
        description=f"{org.name} のコードレビューと改善提案生成",
        input={
            "repo_path": str(repo_path),
            "max_files": args.max_files,
        },
    )

    result = await agent.run(task)
    if not result.success:
        print(f"[ERROR] 分析失敗: {result.error}")
        sys.exit(1)

    suggestions = result.output.get("suggestions", [])
    files = result.output.get("files_reviewed", 0)
    print(f"[OK] {files} ファイルを分析し、{len(suggestions)} 件の改善提案を生成しました。\n")

    for s in suggestions:
        proposal = ImprovementProposal(
            review_id=uuid4(),
            priority=s.get("priority", "medium"),
            category=s.get("category", "general"),
            title=s.get("title", "改善提案"),
            description=s.get("description", ""),
            file_path=s.get("file_path", ""),
            expected_impact=s.get("expected_impact", ""),
        )
        sm.save_improvement_proposal(proposal)
        badge = "[HIGH]" if proposal.priority == "high" else "[MEDIUM]" if proposal.priority == "medium" else "[LOW]"
        print(f"  {badge} [{proposal.priority.upper():6}] {proposal.title}")
        if proposal.file_path:
            print(f"           ファイル: {proposal.file_path}")
        print(f"           {proposal.description[:80]}...")
        print()

    print(f"[OK] {len(suggestions)} 件を保存しました。")
    print(f"\n次のステップ: repocorp proposals --org-name \"{org.name}\"")


async def cmd_proposals(args: argparse.Namespace) -> None:
    """未対応の改善提案を一覧表示する"""
    psm = _get_psm()
    org = psm.load_organization_by_name(args.org_name)
    if not org:
        print(f"[ERROR] Organization '{args.org_name}' が見つかりません。")
        sys.exit(1)

    sm = psm.get_org_state_manager(org)
    proposals = sm.get_pending_improvement_proposals(limit=50)

    if not proposals:
        print("未対応の改善提案はありません。")
        print(f"\nヒント: repocorp analyze --org-name \"{org.name}\"")
        return

    executable = [p for p in proposals if p.get("file_path")]
    meta = [p for p in proposals if not p.get("file_path")]

    print(f"\n未対応の改善提案 ({len(proposals)} 件) — {org.name}\n")
    if executable:
        print(f"【実行可能】 ({len(executable)} 件)")
        for p in executable:
            _print_proposal(p)
    if meta:
        print(f"【Meta-level（手動対応）】 ({len(meta)} 件)")
        for p in meta:
            _print_proposal(p)

    print(f"承認: repocorp approve <ID の最初の8文字> --org-name \"{org.name}\"")


async def cmd_query(args: argparse.Namespace) -> None:
    """SQLite proposals table を簡易検索する"""
    from core.state.sqlite_manager import SQLiteStateManager

    db_path = Path(args.db_path).expanduser().resolve() if getattr(args, "db_path", None) else get_platform_home() / "state.db"
    manager = SQLiteStateManager(db_path)
    try:
        rows = manager.query_proposals(sql_filter=getattr(args, "filter", ""), limit=getattr(args, "limit", 50))
    except ValueError as exc:
        print(f"[ERROR] {exc}")
        sys.exit(1)
    finally:
        manager.close()

    if not rows:
        print("条件に一致する提案はありません。")
        return

    print(f"\nQuery Results ({len(rows)} 件)\n")
    for row in rows:
        print(f"  ID       : {row.get('id')}")
        print(f"  タイトル : {row.get('title')}")
        print(f"  優先度   : {row.get('priority')}")
        print(f"  ステータス: {row.get('status')}")
        if row.get("file_path"):
            print(f"  ファイル : {row.get('file_path')}")
        print()


def _print_proposal(p: dict) -> None:
    print(f"  ID       : {p.get('id')}")
    print(f"  タイトル : {p.get('title')}")
    print(f"  優先度   : {p.get('priority')}")
    if p.get("file_path"):
        print(f"  ファイル : {p.get('file_path')}")
    print(f"  説明     : {str(p.get('description', ''))[:100]}...")
    print()


async def cmd_approve(args: argparse.Namespace) -> None:
    """改善提案を承認してコードに適用し PR またはローカルブランチを作成する"""
    from agents.base import AgentTask

    psm = _get_psm()
    org = psm.load_organization_by_name(args.org_name)
    if not org:
        print(f"[ERROR] Organization '{args.org_name}' が見つかりません。")
        sys.exit(1)

    sm = psm.get_org_state_manager(org)
    proposals = sm.get_pending_improvement_proposals(limit=100)
    target = next(
        (p for p in proposals if str(p.get("id", "")).startswith(args.proposal_id)),
        None,
    )
    if not target:
        print(f"[ERROR] ID '{args.proposal_id}' に一致する未対応提案が見つかりません。")
        sys.exit(1)

    file_path = target.get("file_path", "")
    if not file_path:
        print(f"[ERROR] この提案は file_path がありません（meta-level 提案）。")
        sm.update_proposal_status(str(target.get("id", "")), "rejected")
        sys.exit(1)

    repo_path = Path(org.target_repo_path) if org.target_repo_path else Path(".")
    print(f"\n改善提案を適用します: {target.get('title')}")
    print(f"   ファイル   : {file_path}")
    print(f"   リポジトリ : {repo_path}\n")

    sm.update_proposal_status(str(target.get("id", "")), "in_progress")
    github_token = args.github_token or os.getenv("GITHUB_TOKEN")

    executor = _get_orchestrator()
    task = AgentTask(
        task_type="improvement_execution",
        description=f"改善提案の適用: {target.get('title')}",
        input={
            "repo_path": str(repo_path),
            "suggestion": target,
            "github_token": github_token,
            "github_repo": args.github_repo,
        },
    )

    result = await executor.run(task)
    if not result.success:
        print(f"[ERROR] 適用失敗: {result.error}")
        sm.update_proposal_status(str(target.get("id", "")), "failed")
        sys.exit(1)

    if "pr_url" in result.output:
        sm.update_proposal_status(str(target.get("id", "")), "done")
        print(f"[OK] PR を作成しました: {result.output['pr_url']}")
    elif "branch" in result.output:
        sm.update_proposal_status(str(target.get("id", "")), "done")
        print(f"[OK] ローカルブランチを作成しました: {result.output['branch']}")
        print(f"   変更内容: {result.output.get('change_summary')}")
    else:
        sm.update_proposal_status(str(target.get("id", "")), "done")
        print(f"[OK] 完了: {result.output}")


async def cmd_platform_status(args: argparse.Namespace) -> None:
    """全 Organization 横断のプラットフォームダッシュボード"""
    from core.metrics.balanced_growth import calculate_group_metrics, calculate_organization_metrics
    from core.models.organization import GroupHQState

    psm = _get_psm()
    orgs = psm.load_organizations()

    if not orgs:
        print("\nOrganization が登録されていません。")
        print("   repocorp org add --name MyApp --repo /path/to/app")
        return

    hq = GroupHQState()
    metrics_list = []
    for org in orgs:
        hq.add_organization(org)
        sm = psm.get_org_state_manager(org)
        pending = len(sm.get_pending_improvement_proposals(limit=100))
        m = calculate_organization_metrics(org, pending_proposals_count=pending)
        metrics_list.append((org, m, pending))

    group = calculate_group_metrics(hq, [m for _, m, _ in metrics_list])

    print(f"\n{'═' * 60}")
    print(f"  RepoCorp AI プラットフォーム")
    print(f"  Core: {psm.platform_home}")
    print(f"{'═' * 60}")
    print(f"  グループ健康度   : {group.group_health_score:5.1f} / 100")
    print(f"  バランススコア   : {group.balance_score:5.1f} / 100")
    print(f"  Organization 数  : {group.total_organizations} ({group.active_organizations} active)")
    print(f"  最も弱い Org     : {group.weakest_organization or '—'}")
    print(f"{'─' * 60}")
    print(f"  Organizations（子会社）\n")

    for org, m, pending in sorted(metrics_list, key=lambda x: x[1].health_score, reverse=True):
        bar = _health_bar(m.health_score)
        badge = "[HEALTHY]" if m.health_score >= 70 else "[WATCH]" if m.health_score >= 50 else "[CRITICAL]"
        repo = org.target_repo_path or "(未設定)"
        print(f"  {badge} {org.name}")
        print(f"     リポジトリ : {repo}")
        print(f"     健康度     : {bar} {m.health_score:.1f}")
        print(f"     未対応提案 : {pending} 件  |  Agent: {len(org.get_all_agents())} 個")
        print()

    print(f"{'═' * 60}")
    print(f"  repocorp platform run-all  で全 Org の改善サイクルを実行")
    print(f"  repocorp serve             で Web GUI を起動")
    print(f"{'═' * 60}\n")


def _health_bar(score: float, width: int = 20) -> str:
    filled = int(score / 100 * width)
    return f"[{'█' * filled}{'░' * (width - filled)}]"


async def cmd_platform_run_all(args: argparse.Namespace) -> None:
    """全 Organization の改善サイクルを優先度順に実行する"""
    from core.quality.self_improvement_loop import SelfImprovementLoop
    from core.metrics.balanced_growth import calculate_organization_metrics, get_improvement_priority_score

    psm = _get_psm()
    orgs = psm.load_organizations()

    if not orgs:
        print("Organization が登録されていません。")
        return

    # 優先度でソート
    scored = []
    for org in orgs:
        sm = psm.get_org_state_manager(org)
        pending = len(sm.get_pending_improvement_proposals(limit=100))
        m = calculate_organization_metrics(org, pending_proposals_count=pending)
        scored.append((org, sm, get_improvement_priority_score(m)))

    scored.sort(key=lambda x: x[2], reverse=True)
    target = scored[:args.max_orgs]

    print(f"\n改善サイクルを実行します ({len(target)} / {len(orgs)} Organization)\n")
    for org, sm, score in target:
        print(f"  → {org.name} (優先度: {score:.1f}) [{org.target_repo_path or '(未設定)'}]")
        loop = SelfImprovementLoop(org, sm)
        await loop.run_improvement_cycle()

    print(f"\n[OK] 完了。repocorp platform status で結果を確認できます。")


def cmd_serve(args: argparse.Namespace) -> None:
    """Web GUI サーバーを起動する"""
    try:
        from web.server import run_server
    except ImportError:
        print("[ERROR] Web GUI には fastapi と uvicorn が必要です。")
        print("   pip install 'repocorp-ai[web]' でインストールしてください。")
        sys.exit(1)

    run_server(host=args.host, port=args.port)


async def cmd_daemon_start(args: argparse.Namespace) -> None:
    """自律改善デーモンをバックグラウンドで起動する"""
    import subprocess
    from core.platform.state import get_platform_home

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
    cmd = [
        sys.executable, "-m", "core._daemon_runner",
        f"--interval={args.interval}",
        f"--max-files={args.max_files}",
    ]

    proc = subprocess.Popen(
        cmd,
        cwd=Path(__file__).parent,
        stdout=open(log_file, "a"),
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    pid_file.write_text(str(proc.pid))
    print(f"[OK] デーモンを起動しました (PID: {proc.pid})")
    print(f"   ログ  : {log_file}")
    print(f"   間隔  : {args.interval} 秒ごと")
    print("\n停止: repocorp daemon stop")
    print("状態: repocorp daemon status")


def cmd_daemon_stop(args: argparse.Namespace) -> None:
    """自律改善デーモンを停止する"""
    import signal as _signal
    from core.platform.state import get_platform_home

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


def cmd_daemon_status(args: argparse.Namespace) -> None:
    """デーモンの稼働状態とログを表示する"""
    from core.platform.state import get_platform_home

    platform_home = get_platform_home()
    pid_file = platform_home / "daemon.pid"
    log_file = platform_home / "daemon.log"
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
            import json
            print(f"\n直近の実行ログ ({len(lines)} サイクル合計):")
            for line in recent:
                try:
                    d = json.loads(line)
                    ts = d.get("started_at", "")[:19].replace("T", " ")
                    n = d.get("triggered_orgs", 0)
                    c = d.get("cycle", "?")
                    print(f"  #{c:3}  {ts}  triggered={n}")
                except Exception:
                    pass

    print("\n起動: repocorp daemon start [--interval=3600]")


# ============================================================
# chat: 自然言語対話エージェント
# ============================================================

def cmd_chat(args: argparse.Namespace) -> None:
    """自然言語対話エージェントを起動する"""
    from agents.chat_agent import run_chat
    initial = getattr(args, "message", None)
    asyncio.run(run_chat(initial_message=initial))

async def cmd_orchestration_analyze(args: argparse.Namespace) -> None:
    """タスクの最適実行計画を表示する (N-07)"""
    task_type = args.task_type
    agent = _get_orchestrator()
    routing = agent.describe_routing(task_type, f"{task_type} の最適実行計画を分析")

    print(f"\n{'═' * 60}")
    print(f"  Pre-Task 実行計画分析")
    print(f"{'═' * 60}")
    print(f"  タスク種別     : {routing['task_type']}")
    print(f"  推奨パターン   : {routing['recommended_pattern']}")
    print(f"  推奨エージェント: {', '.join(routing['recommended_agents']) or '(なし — 動的作成)'}")
    print(f"  新エージェント : {'作成が必要' if routing['spawn_new_agent'] else '不要'}")
    print(f"  複雑度         : {routing['complexity']}")
    if routing.get('reasoning'):
        print(f"\n  判断根拠:")
        for line in routing['reasoning'].splitlines():
            print(f"     {line}")
    print(f"{'═' * 60}\n")


async def cmd_orchestration_history(args: argparse.Namespace) -> None:
    """過去のオーケストレーション実行履歴を表示する (N-07)"""
    from core.orchestration.orchestration_pattern_store import OrchestrationPatternStore

    store = OrchestrationPatternStore()
    records = list(store._records)

    if not records:
        print("\n[INFO] 実行履歴がまだありません。")
        print("   repocorp analyze --org-name <name> で分析を実行してください。")
        return

    # 種別ごとの集計
    from collections import defaultdict
    stats: dict = defaultdict(lambda: {"total": 0, "success": 0, "patterns": defaultdict(int)})
    for r in records:
        s = stats[r.task_type]
        s["total"] += 1
        if r.success:
            s["success"] += 1
        s["patterns"][r.pattern] += 1

    print(f"\n{'═' * 60}")
    print(f"  オーケストレーション実行履歴  (合計 {len(records)} 件)")
    print(f"{'═' * 60}")
    for task_type, s in sorted(stats.items()):
        rate = s["success"] / s["total"] * 100 if s["total"] else 0
        top_pattern = max(s["patterns"], key=s["patterns"].get)
        print(f"  {task_type}")
        print(f"    実行数: {s['total']}  成功率: {rate:.0f}%  主パターン: {top_pattern}")
    print(f"{'═' * 60}\n")


async def cmd_orchestration_capabilities(args: argparse.Namespace) -> None:
    """現在のエージェント能力一覧と未充足ギャップを表示する (N-07)"""
    from core.intelligence.capability_registry import CapabilityRegistry
    from core.intelligence.capability_gap_analyzer import CapabilityGapAnalyzer

    registry = CapabilityRegistry()
    entries = registry.list_all()

    print(f"\n{'═' * 60}")
    print(f"  Capability Registry  ({len(entries)} エントリ)")
    print(f"{'═' * 60}")

    agents = [e for e in entries if e.capability_type == "agent"]
    skills = [e for e in entries if e.capability_type == "skill"]

    if agents:
        print(f"  【Agents】")
        for e in agents:
            status = "active" if getattr(e, "is_active", True) else "unavailable"
            print(f"    {e.name}  {status}")
    if skills:
        print(f"\n  【Skills】")
        for e in skills:
            print(f"    {e.name}")

    gap_analyzer = CapabilityGapAnalyzer(capability_registry=registry)
    gaps = gap_analyzer.get_all_gaps()
    if gaps:
        print(f"\n  {'─' * 56}")
        print(f"  検出された能力ギャップ ({len(gaps)} 件)")
        for gap in sorted(gaps, key=lambda g: g.priority):
            print(f"    [{gap.priority.upper()}] {gap.suggested_name} ({gap.suggested_type})")
            print(f"      → {gap.description}")
    else:
        print(f"\n  能力ギャップなし")
    print(f"{'═' * 60}\n")


# ============================================================
# N-10: OrchestratorSelfReview — 振り返りループ
# ============================================================

async def cmd_orchestration_self_review(args: argparse.Namespace) -> None:
    """
    PreTaskOrchestrator の判断精度を振り返り、改善提案を生成する (N-10)

    週次の振り返りを想定。失敗率の高いパターンを検出して
    ImprovementProposal として登録する。
    """
    import json
    from collections import defaultdict
    from core.orchestration.orchestration_pattern_store import OrchestrationPatternStore

    store = OrchestrationPatternStore()
    records = list(store._records)

    if not records:
        print("[INFO] 振り返りに十分な実行履歴がありません（0件）。")
        return

    # 失敗率分析
    pattern_stats: dict = defaultdict(lambda: {"total": 0, "failed": 0, "quality_sum": 0.0})
    for r in records:
        key = f"{r.task_type}:{r.pattern}"
        s = pattern_stats[key]
        s["total"] += 1
        if not r.success:
            s["failed"] += 1
        s["quality_sum"] += r.quality_score

    issues = []
    for key, s in pattern_stats.items():
        if s["total"] < 3:
            continue
        fail_rate = s["failed"] / s["total"]
        avg_quality = s["quality_sum"] / s["total"]
        if fail_rate > 0.4 or avg_quality < 5.0:
            issues.append({
                "key": key,
                "fail_rate": fail_rate,
                "avg_quality": avg_quality,
                "total": s["total"],
            })

    if not issues:
        print("[OK] 振り返り完了: 問題のあるオーケストレーションパターンは見つかりませんでした。")
        return

    print(f"\n{'═' * 60}")
    print(f"  Orchestrator Self-Review 振り返り結果")
    print(f"{'═' * 60}")
    print(f"  改善が必要なパターン ({len(issues)} 件)")
    for issue in issues:
        print(f"\n  {issue['key']}")
        print(f"     失敗率: {issue['fail_rate']*100:.0f}%  平均品質: {issue['avg_quality']:.1f}")
        print(f"     実行数: {issue['total']}")
        print(f"     → このパターンの見直しを推奨します")

    print(f"\n  次のアクション:")
    print(f"     repocorp orchestration analyze <task_type> で計画を再確認してください")
    print(f"{'═' * 60}\n")


# ============================================================
# A-12: Agent status CLI
# ============================================================

async def cmd_agent_status(args: argparse.Namespace) -> None:
    from core.intelligence.skill_proficiency import SkillProficiencyManager

    pm = SkillProficiencyManager()
    data = pm._load()
    if not data:
        print("エージェントの実績データがありません。改善サイクルを実行してください。")
        return

    print(f"\n{'═' * 72}")
    print(f"  Agent Status — {args.org_name}")
    print(f"{'═' * 72}")
    print(f"{'agent_id':20} | {'skills':22} | proficiency scores")
    print(f"{'─' * 72}")
    for agent_id, skills in sorted(data.items()):
        skill_names = ", ".join(sorted(skills))
        proficiencies = ", ".join(
            f"{skill}={rec.get('proficiency', 1.0):.1f}/100"
            for skill, rec in sorted(skills.items())
        )
        print(f"{agent_id[:20]:20} | {skill_names[:22]:22} | {proficiencies}")
    print(f"{'═' * 72}\n")


# ============================================================
# Goal CLI (M-07)
# ============================================================

async def cmd_goal_status(args: argparse.Namespace) -> None:
    """repocorp goal status"""
    from core.goals.goal_library import GoalLibrary

    lib = GoalLibrary(platform_home=get_platform_home())
    templates = lib._load_all()
    if not templates:
        print("ゴールの実行履歴がありません。repocorp goal run <goal_text> を試してください。")
        return
    print(f"ゴールライブラリ: {len(templates)}件")
    for template in templates[:10]:
        print(f"  [{template.goal_type}] {template.description[:50]} (使用:{template.use_count}回)")


async def cmd_goal_run(args: argparse.Namespace) -> None:
    """repocorp goal run <goal_text>"""
    from core.goals.abstract_goal_pipeline import AbstractGoalPipeline

    pipeline = AbstractGoalPipeline()
    result = await pipeline.run(args.goal_text)
    summary = result.summary() if callable(getattr(result, "summary", None)) else str(result)
    print(summary)


# ============================================================
# CLI Parser
# ============================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description="RepoCorp AI — 自己成長型 AI Organization プラットフォーム",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 使い方ガイド
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

【クイックスタート（推奨: chatコマンド）】
  export ANTHROPIC_API_KEY=sk-ant-...   # Claude API キー（初回のみ）
  repocorp init                          # 初回セットアップ（1回だけ）
  repocorp chat                          # あとは自然言語で話しかけるだけ！

  チャット例:
    > ECサイトを作りたい
    > MyApp のコードをレビューして
    > セキュリティの提案を全部承認して

【スラッシュコマンド（APIキー不要）】
  repocorp chat → /help でコマンド一覧を表示
""",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init", help="グローバルプラットフォームを初期化する")

    p_org = subparsers.add_parser("org", help="Organization（子会社）の管理")
    org_sub = p_org.add_subparsers(dest="org_command", required=True)
    p_add = org_sub.add_parser("add", help="新しい Organization を登録する")
    p_add.add_argument("--name", required=True, help="Organization 名")
    p_add.add_argument("--repo", default=None, help="担当リポジトリの絶対パス")
    p_add.add_argument("--purpose", default="", help="Organization の目的・ゴール")
    p_add.add_argument("--template", default=None, help="テンプレート名（例: meta_improvement）")
    org_sub.add_parser("list", help="Organization の一覧を表示する")
    p_remove = org_sub.add_parser("remove", help="Organization を削除する")
    p_remove.add_argument("--name", required=True, help="削除する Organization 名")

    p_analyze = subparsers.add_parser("analyze", help="担当リポジトリを分析して改善提案を生成")
    p_analyze.add_argument("--org-name", required=True, help="対象 Organization 名")
    p_analyze.add_argument("--max-files", type=int, default=15, help="分析する最大ファイル数")

    p_proposals = subparsers.add_parser("proposals", help="未対応の改善提案を一覧表示")
    p_proposals.add_argument("--org-name", required=True, help="対象 Organization 名")

    p_approve = subparsers.add_parser("approve", help="改善提案を承認してコードに適用")
    p_approve.add_argument("proposal_id", help="承認する提案の ID（先頭 8 文字以上）")
    p_approve.add_argument("--org-name", required=True, help="対象 Organization 名")
    p_approve.add_argument("--github-repo", default=None, help="GitHub リポジトリ (owner/repo)")
    p_approve.add_argument("--github-token", default=None, help="GitHub トークン")

    p_query = subparsers.add_parser("query", help="SQLite proposals を条件付きで検索")
    p_query.add_argument("--filter", default="", help="SQL filter clause (例: WHERE priority='high')")
    p_query.add_argument("--limit", type=int, default=50, help="最大件数")
    p_query.add_argument("--db-path", default=None, help="対象 SQLite DB パス")

    p_platform = subparsers.add_parser("platform", help="プラットフォーム全体の操作")
    plat_sub = p_platform.add_subparsers(dest="platform_command", required=True)
    plat_sub.add_parser("status", help="全 Organization 横断ダッシュボード")
    p_run_all = plat_sub.add_parser("run-all", help="全 Organization の改善サイクルを実行")
    p_run_all.add_argument("--max-orgs", type=int, default=5, help="最大実行 Org 数（default: 5）")

    p_goal = subparsers.add_parser("goal", help="抽象ゴールの実行と履歴表示")
    goal_sub = p_goal.add_subparsers(dest="goal_command", required=True)
    goal_sub.add_parser("status", help="達成済みゴールの履歴を表示")
    p_goal_run = goal_sub.add_parser("run", help="抽象ゴールを自律実行する（ANTHROPIC_API_KEY が必要）")
    p_goal_run.add_argument("goal_text", help="実行するゴール文（例: 'ECサイトを作りたい'）")

    p_serve = subparsers.add_parser("serve", help="Web GUI を起動する")
    p_serve.add_argument("--host", default="0.0.0.0", help="バインドホスト (default: 0.0.0.0)")
    p_serve.add_argument("--port", type=int, default=7860, help="ポート番号 (default: 7860)")

    p_daemon = subparsers.add_parser("daemon", help="自律改善デーモンの管理")
    daemon_sub = p_daemon.add_subparsers(dest="daemon_command", required=True)
    p_daemon_start = daemon_sub.add_parser("start", help="デーモンをバックグラウンドで起動")
    p_daemon_start.add_argument("--interval", type=int, default=3600, help="実行間隔（秒, default: 3600）")
    p_daemon_start.add_argument("--max-files", type=int, default=10, help="1 Org あたり最大分析ファイル数")
    daemon_sub.add_parser("stop", help="デーモンを停止")
    daemon_sub.add_parser("status", help="デーモンの稼働状態・ログを表示")

    p_agent = subparsers.add_parser("agent", help="エージェントの状態・実績を表示")
    agent_sub = p_agent.add_subparsers(dest="agent_command", required=True)
    p_agent_status = agent_sub.add_parser("status", help="エージェントのスキル習熟度を表示")
    p_agent_status.add_argument("--org-name", required=True, help="対象 Organization 名")

    p_orch = subparsers.add_parser("orchestration", help="Pre-Task Orchestration の管理・分析 (Theme N)")
    orch_sub = p_orch.add_subparsers(dest="orch_command", required=True)
    p_orch_analyze = orch_sub.add_parser("analyze", help="タスクの最適実行計画を表示")
    p_orch_analyze.add_argument("task_type", help="タスク種別 (例: code_review, meta_improvement, security_audit)")
    orch_sub.add_parser("history", help="過去のオーケストレーション実行履歴を表示")
    orch_sub.add_parser("capabilities", help="現在のエージェント能力一覧と未充足ギャップを表示")
    orch_sub.add_parser("self-review", help="Orchestrator の判断精度を振り返り改善提案を生成 (N-10)")

    p_chat = subparsers.add_parser(
        "chat",
        help="自然言語でエージェントに依頼する（推奨）",
    )
    p_chat.add_argument(
        "message",
        nargs="?",
        default=None,
        help="最初のメッセージ（省略時は対話モードで起動）",
    )

    args = parser.parse_args()

    dispatch = {
        "init": lambda: asyncio.run(cmd_init(args)),
        "analyze": lambda: asyncio.run(cmd_analyze(args)),
        "proposals": lambda: asyncio.run(cmd_proposals(args)),
        "approve": lambda: asyncio.run(cmd_approve(args)),
        "query": lambda: asyncio.run(cmd_query(args)),
        "serve": lambda: cmd_serve(args),
        "chat": lambda: cmd_chat(args),
    }

    if args.command in dispatch:
        dispatch[args.command]()
    elif args.command == "org":
        if args.org_command == "add":
            asyncio.run(cmd_org_add(args))
        elif args.org_command == "list":
            asyncio.run(cmd_org_list(args))
        elif args.org_command == "remove":
            asyncio.run(cmd_org_remove(args))
    elif args.command == "platform":
        if args.platform_command == "status":
            asyncio.run(cmd_platform_status(args))
        elif args.platform_command == "run-all":
            asyncio.run(cmd_platform_run_all(args))
    elif args.command == "goal":
        if args.goal_command == "status":
            asyncio.run(cmd_goal_status(args))
        elif args.goal_command == "run":
            asyncio.run(cmd_goal_run(args))
    elif args.command == "daemon":
        if args.daemon_command == "start":
            asyncio.run(cmd_daemon_start(args))
        elif args.daemon_command == "stop":
            cmd_daemon_stop(args)
        elif args.daemon_command == "status":
            cmd_daemon_status(args)
    elif args.command == "agent":
        if args.agent_command == "status":
            asyncio.run(cmd_agent_status(args))
    elif args.command == "orchestration":
        if args.orch_command == "analyze":
            asyncio.run(cmd_orchestration_analyze(args))
        elif args.orch_command == "history":
            asyncio.run(cmd_orchestration_history(args))
        elif args.orch_command == "capabilities":
            asyncio.run(cmd_orchestration_capabilities(args))
        elif args.orch_command == "self-review":
            asyncio.run(cmd_orchestration_self_review(args))


if __name__ == "__main__":
    main()
