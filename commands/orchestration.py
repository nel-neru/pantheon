from __future__ import annotations

import argparse
import json
from collections import defaultdict
from typing import Any


async def cmd_orchestration_analyze(args: argparse.Namespace, *, get_orchestrator: Any) -> None:
    """タスクの最適実行計画を表示する (N-07)"""
    task_type = args.task_type
    agent = get_orchestrator()
    routing = agent.describe_routing(task_type, f"{task_type} の最適実行計画を分析")

    print(f"\n{'═' * 60}")
    print("  Pre-Task 実行計画分析")
    print(f"{'═' * 60}")
    print(f"  タスク種別     : {routing['task_type']}")
    print(f"  推奨パターン   : {routing['recommended_pattern']}")
    print(f"  推奨エージェント: {', '.join(routing['recommended_agents']) or '(なし — 動的作成)'}")
    print(f"  新エージェント : {'作成が必要' if routing['spawn_new_agent'] else '不要'}")
    print(f"  複雑度         : {routing['complexity']}")
    if routing.get("reasoning"):
        print("\n  判断根拠:")
        for line in routing["reasoning"].splitlines():
            print(f"     {line}")
    print(f"{'═' * 60}\n")


async def cmd_orchestration_history(args: argparse.Namespace) -> None:
    """過去のオーケストレーション実行履歴を表示する (N-07)"""
    from core.orchestration.orchestration_pattern_store import OrchestrationPatternStore

    store = OrchestrationPatternStore()
    records = list(store._records)

    if not records:
        print("\n[INFO] 実行履歴がまだありません。")
        print("   pantheon analyze --org-name <name> で分析を実行してください。")
        return

    stats: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"total": 0, "success": 0, "patterns": defaultdict(int)}
    )
    for record in records:
        item = stats[record.task_type]
        item["total"] += 1
        if record.success:
            item["success"] += 1
        item["patterns"][record.pattern] += 1

    print(f"\n{'═' * 60}")
    print(f"  オーケストレーション実行履歴  (合計 {len(records)} 件)")
    print(f"{'═' * 60}")
    for task_type, item in sorted(stats.items()):
        rate = item["success"] / item["total"] * 100 if item["total"] else 0
        top_pattern = max(item["patterns"], key=item["patterns"].get)
        print(f"  {task_type}")
        print(f"    実行数: {item['total']}  成功率: {rate:.0f}%  主パターン: {top_pattern}")
    print(f"{'═' * 60}\n")


async def cmd_orchestration_capabilities(args: argparse.Namespace) -> None:
    """現在のエージェント能力一覧と未充足ギャップを表示する (N-07)"""
    from core.intelligence.capability_gap_analyzer import CapabilityGapAnalyzer
    from core.intelligence.capability_registry import CapabilityRegistry

    registry = CapabilityRegistry()
    entries = registry.list_all()

    print(f"\n{'═' * 60}")
    print(f"  Capability Registry  ({len(entries)} エントリ)")
    print(f"{'═' * 60}")

    agents = [entry for entry in entries if entry.capability_type == "agent"]
    skills = [entry for entry in entries if entry.capability_type == "skill"]

    if agents:
        print("  【Agents】")
        for entry in agents:
            status = "active" if getattr(entry, "is_active", True) else "unavailable"
            print(f"    {entry.name}  {status}")
    if skills:
        print("\n  【Skills】")
        for entry in skills:
            print(f"    {entry.name}")

    gap_analyzer = CapabilityGapAnalyzer(capability_registry=registry)
    gaps = gap_analyzer.get_all_gaps()
    if gaps:
        print(f"\n  {'─' * 56}")
        print(f"  検出された能力ギャップ ({len(gaps)} 件)")
        _priority_rank = {"high": 0, "medium": 1, "low": 2}
        for gap in sorted(gaps, key=lambda item: _priority_rank.get(item.priority, 99)):
            print(f"    [{gap.priority.upper()}] {gap.suggested_name} ({gap.suggested_type})")
            print(f"      → {gap.description}")
    else:
        print("\n  能力ギャップなし")

    # --unused: 最終アクティビティが閾値より古い能力を非推奨候補として一覧（既定オフ・read-only）。
    unused_days = getattr(args, "unused", None)
    if unused_days is not None:
        unused = registry.get_unused_capabilities(days_threshold=unused_days)
        print(f"\n  {'─' * 56}")
        print(f"  非推奨候補（最終アクティビティから {unused_days} 日以上） {len(unused)} 件")
        if unused:
            for cap in sorted(unused, key=lambda c: c.get("last_used") or c.get("added_at") or ""):
                last_activity = cap.get("last_used") or cap.get("added_at") or "不明"
                # id を併記して `--deprecate <id>` でそのまま非推奨化できるようにする。
                print(
                    f"    {cap.get('name')} ({cap.get('capability_type')})"
                    f"  使用 {cap.get('usage_count', 0)} 回  最終 {last_activity}"
                    f"  [id: {cap.get('id')}]"
                )
        else:
            print("    なし（全能力が閾値内にアクティブ）")

    # --deprecate: 指定能力を非推奨化（is_active=False を永続化）。明示コマンド＝HITL。
    deprecate_target = getattr(args, "deprecate", None)
    if deprecate_target:
        entry = registry.get(deprecate_target) or registry.find_by_name(deprecate_target)
        print(f"\n  {'─' * 56}")
        if entry is None:
            print(f"  [WARN] 能力 '{deprecate_target}' が見つかりません（id・表示名で指定）。")
        elif registry.mark_for_deprecation(entry.id):
            print(
                f"  ✓ '{entry.name}' ({entry.id}) を非推奨にしました（is_active=False）。"
                "\n    以後 --unused 候補・エージェント能力一覧から除外されます。"
            )
        else:  # pragma: no cover - get/find で解決済みなら通常到達しない
            print(f"  [WARN] '{deprecate_target}' の非推奨化に失敗しました。")

    # --resolve: 検出ギャップを CapabilityGapResolver で解消する（既定オフ）。
    # agent/skill → registry へ永続 spawn、team/division → PolicyEngine 評価（HITL ゲート）。
    if getattr(args, "resolve", False):
        _resolve_capability_gaps(gaps, registry, getattr(args, "org_name", None))
    print(f"{'═' * 60}\n")


def _resolve_capability_gaps(gaps: list, registry: Any, org_name: str | None) -> None:
    """検出ギャップを解消し結果サマリーを表示する（capabilities --resolve の本番ドライバ）。

    解消側 :class:`CapabilityGapResolver` は従来テストのみで本番から呼ばれていなかった。
    agent/skill ギャップは registry へ永続 spawn（実効果あり）、team/division ギャップは
    PolicyEngine 経由で既定 HITL ゲート（自動適用しない）に倒す。
    """
    from core.orchestration.capability_gap_loop import resolve_gaps_for_org
    from core.platform.state import PlatformStateManager

    if not gaps:
        print("\n  解消すべき能力ギャップはありません。")
        return

    psm = PlatformStateManager()
    if org_name:
        org = psm.load_organization_by_name(org_name)
        if org is None:
            print(
                f"\n  [WARN] Organization '{org_name}' が見つかりません。ギャップ解消をスキップします。"
            )
            return
    else:
        orgs = psm.load_organizations()
        if not orgs:
            print("\n  [WARN] Organization が未登録のため、ギャップ解消をスキップします。")
            return
        org = orgs[0]

    # state_manager を渡すと team/division 構造ギャップが ImprovementProposal として
    # org の .pantheon/improvements/ に永続化される（書込先 = API `_pending_proposals_for`
    # の読取先）。既定 HITL では status="pending"（active）で /inbox 承認ハブに出る。
    # これで「検出 → PolicyEngine → 永続化 → GUI → 人間承認」のループが閉じる。
    sm = psm.get_org_state_manager(org)
    summary = resolve_gaps_for_org(gaps, org, capability_registry=registry, state_manager=sm)
    # 構造ギャップが（policy.yaml の明示設定で）auto-apply された場合のみ org は
    # in-memory で変異する。その時だけ永続化して `auto-applied` の報告を正直にする
    # （既定の HITL 経路では構造は提案止まりで org は不変＝save 不要）。spawn は registry
    # 側で既に永続済みで org を変えないため、ここでの save 対象ではない。
    structure_applied = any(
        record["auto_applied"] and record["action"] in ("proposed_team", "proposed_division")
        for record in summary["results"]
    )
    if structure_applied:
        psm.save_organization(org)
    print(f"\n  {'─' * 56}")
    print(f"  能力ギャップ解消結果  (対象 org: {org.name})")
    print(f"    spawned agents : {summary['spawned_agents']}")
    print(f"    proposed teams : {summary['proposed_teams']}")
    print(f"    proposed divs  : {summary['proposed_divisions']}")
    print(f"    auto-applied   : {summary['auto_applied']}")
    for record in summary["results"]:
        print(f"      - {record['action']}: {record['detail']}")


async def cmd_orchestration_self_review(args: argparse.Namespace) -> None:
    """PreTaskOrchestrator の判断精度を振り返り、改善提案を生成する (N-10)"""
    from core.orchestration.orchestration_pattern_store import OrchestrationPatternStore

    store = OrchestrationPatternStore()
    records = list(store._records)

    if not records:
        print("[INFO] 振り返りに十分な実行履歴がありません（0件）。")
        return

    pattern_stats: dict[str, dict[str, float]] = defaultdict(
        lambda: {"total": 0, "failed": 0, "quality_sum": 0.0}
    )
    for record in records:
        key = f"{record.task_type}:{record.pattern}"
        item = pattern_stats[key]
        item["total"] += 1
        if not record.success:
            item["failed"] += 1
        item["quality_sum"] += record.quality_score

    issues = []
    for key, item in pattern_stats.items():
        if item["total"] < 3:
            continue
        fail_rate = item["failed"] / item["total"]
        avg_quality = item["quality_sum"] / item["total"]
        if fail_rate > 0.4 or avg_quality < 5.0:
            issues.append(
                {
                    "key": key,
                    "fail_rate": fail_rate,
                    "avg_quality": avg_quality,
                    "total": item["total"],
                }
            )

    if not issues:
        print("[OK] 振り返り完了: 問題のあるオーケストレーションパターンは見つかりませんでした。")
        return

    print(f"\n{'═' * 60}")
    print("  Orchestrator Self-Review 振り返り結果")
    print(f"{'═' * 60}")
    print(f"  改善が必要なパターン ({len(issues)} 件)")
    for issue in issues:
        print(f"\n  {issue['key']}")
        print(f"     失敗率: {issue['fail_rate'] * 100:.0f}%  平均品質: {issue['avg_quality']:.1f}")
        print(f"     実行数: {issue['total']}")
        print("     → このパターンの見直しを推奨します")

    print("\n  次のアクション:")
    print("     pantheon orchestration analyze <task_type> で計画を再確認してください")
    print(f"{'═' * 60}\n")


async def cmd_agent_status(
    args: argparse.Namespace,
    *,
    filter_proficiency_data_by_org: Any,
    get_platform_home: Any,
) -> None:
    from core.intelligence.skill_proficiency import SkillProficiencyManager

    store_file = get_platform_home() / SkillProficiencyManager.STORE_FILE
    if not store_file.exists():
        print("エージェントの実績データがありません。改善サイクルを実行してください。")
        return

    try:
        raw_data = json.loads(store_file.read_text(encoding="utf-8"))
    except Exception:
        raw_data = {}
    if not raw_data:
        print("エージェントの実績データがありません。改善サイクルを実行してください。")
        return

    data = filter_proficiency_data_by_org(raw_data, args.org_name)
    if not data:
        print(f"Organization '{args.org_name}' のエージェント実績データがありません。")
        return

    print(f"\n{'═' * 72}")
    print(f"  Agent Status — {args.org_name}")
    print(f"{'═' * 72}")
    print(f"{'agent_id':20} | {'skills':22} | proficiency scores")
    print(f"{'─' * 72}")
    for agent_id, skills in sorted(data.items()):
        skill_names = ", ".join(sorted(skills))
        proficiencies = ", ".join(
            f"{skill}={record.get('proficiency', 1.0):.1f}/100"
            for skill, record in sorted(skills.items())
            if isinstance(record, dict)
        )
        print(f"{agent_id[:20]:20} | {skill_names[:22]:22} | {proficiencies}")
    print(f"{'═' * 72}\n")


async def cmd_agent_list(args: argparse.Namespace, *, get_psm: Any) -> None:
    psm = get_psm()
    orgs = psm.load_organizations()
    if not orgs:
        print("Organization が登録されていません。")
        return

    print(f"\n{'═' * 72}")
    print("  Agent List")
    print(f"{'═' * 72}")
    for org in orgs:
        agents = org.get_all_agents()
        print(f"{org.name} ({len(agents)} agents)")
        for agent in agents:
            skills = ", ".join(getattr(skill, "value", skill) for skill in agent.skills)
            print(f"  - {agent.name}: {skills}")
    print(f"{'═' * 72}\n")


def register(subparsers: Any) -> None:
    agent_parser = subparsers.add_parser("agent", help="エージェントの状態・実績を表示")
    agent_sub = agent_parser.add_subparsers(dest="agent_command", required=True)
    agent_list = agent_sub.add_parser("list", help="登録済みエージェントの一覧を表示")
    agent_list.set_defaults(handler_name="cmd_agent_list")
    agent_status = agent_sub.add_parser("status", help="エージェントのスキル習熟度を表示")
    agent_status.add_argument("--org-name", required=True, help="対象 Organization 名")
    agent_status.set_defaults(handler_name="cmd_agent_status")

    orch_parser = subparsers.add_parser(
        "orchestration", help="Pre-Task Orchestration の管理・分析 (Theme N)"
    )
    orch_sub = orch_parser.add_subparsers(dest="orch_command", required=True)

    analyze = orch_sub.add_parser("analyze", help="タスクの最適実行計画を表示")
    analyze.add_argument(
        "task_type", help="タスク種別 (例: code_review, meta_improvement, security_audit)"
    )
    analyze.set_defaults(handler_name="cmd_orchestration_analyze")

    history = orch_sub.add_parser("history", help="過去のオーケストレーション実行履歴を表示")
    history.set_defaults(handler_name="cmd_orchestration_history")

    capabilities = orch_sub.add_parser(
        "capabilities", help="現在のエージェント能力一覧と未充足ギャップを表示"
    )
    capabilities.add_argument(
        "--resolve",
        action="store_true",
        help="検出した能力ギャップを解消する（agent/skill は registry へ spawn、"
        "team/division は HITL ゲート提案）",
    )
    capabilities.add_argument(
        "--org-name",
        default=None,
        help="--resolve の対象 Organization 名（省略時は登録済みの先頭を使用）",
    )
    capabilities.add_argument(
        "--unused",
        nargs="?",
        type=int,
        const=90,
        default=None,
        metavar="DAYS",
        help="最終利用（未使用なら追加日）から DAYS 日以上経過した能力を非推奨候補として"
        "一覧する（DAYS 省略時は 90）。既定オフ・読み取り専用",
    )
    capabilities.add_argument(
        "--deprecate",
        default=None,
        metavar="ID_OR_NAME",
        help="指定した能力（id または表示名）を非推奨にする（is_active=False を永続化）。"
        "明示コマンド＝HITL。以後 --unused 候補とエージェント能力一覧から除外される",
    )
    capabilities.set_defaults(handler_name="cmd_orchestration_capabilities")

    self_review = orch_sub.add_parser(
        "self-review", help="Orchestrator の判断精度を振り返り改善提案を生成 (N-10)"
    )
    self_review.set_defaults(handler_name="cmd_orchestration_self_review")
