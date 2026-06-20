"""`pantheon inbox` — 統合承認インボックス（提案＋handoff＋投稿待ち＋人間タスク）を CLI で見る。

GUI の唯一の承認ハブ ``/inbox``（``/api/inbox``）と同じ集約・並び（収益インパクト→優先度）を
CLI・自律パスへ開く。これまで CLI は「/inbox で確認」と促すだけで統合キューを列挙できず、
承認は種別ごと（proposal / handoff / human-task / publish）に別コマンドが必要だった。

本コマンドは **読み取り（list）**を提供する。承認アクションは種別ごとの既存コマンドで行う:
proposal → ``pantheon approve`` / ``proposal apply|reject``、handoff → ``pantheon handoff approve``、
publish → ``pantheon publish jobs run|confirm``（list の各行に種別と id を出すので辿れる）。
"""

from __future__ import annotations

import argparse
from typing import Any, Dict, List

_PRIORITY_RANK = {"high": 3, "medium": 2, "low": 1}


def _collect_inbox(platform_home: Any) -> List[Dict[str, Any]]:
    """提案/handoff/publish/human-task を 1 つの優先度付きキューへ集約する（/api/inbox と同じ）。"""
    from core.hierarchy.org_handoff import OrgHandoffStore
    from core.humans.human_tasks import HumanTaskStore
    from core.metrics.revenue_intelligence import revenue_impact_rank
    from core.platform.state import PlatformStateManager
    from core.publishing.publish_jobs import PublishJobStore

    psm = PlatformStateManager(platform_home=platform_home)
    home = psm.platform_home
    items: List[Dict[str, Any]] = []

    for org in psm.load_organizations():
        try:
            sm = psm.get_org_state_manager(org)
            for p in sm.get_pending_improvement_proposals(limit=50):
                items.append(
                    {
                        "kind": "proposal",
                        "id": str(p.get("id", "")),
                        "org_name": org.name,
                        "title": p.get("title", ""),
                        "priority": p.get("priority", "medium"),
                        "revenue_impact": revenue_impact_rank(p),
                    }
                )
        except Exception:  # noqa: BLE001 — 1 組織の読み取り失敗で全体を落とさない
            continue

    for h in OrgHandoffStore(platform_home=home).list_handoffs(status="pending"):
        items.append(
            {
                "kind": "handoff",
                "id": getattr(h, "handoff_id", ""),
                "org_name": getattr(h, "target_org", ""),
                "title": getattr(h, "title", ""),
                "priority": getattr(h, "priority", "medium"),
                "revenue_impact": 1,
            }
        )

    for j in PublishJobStore(platform_home=home).list_jobs():
        if j.status not in ("queued", "handed_off"):
            continue
        items.append(
            {
                "kind": "publish",
                "id": j.job_id,
                "org_name": j.org_name,
                "title": j.title or j.platform,
                "priority": "high",
                "revenue_impact": 1,
            }
        )

    for t in HumanTaskStore(platform_home=home).list_tasks("open"):
        items.append(
            {
                "kind": "human_task",
                "id": t.task_id,
                "org_name": t.org_name,
                "title": t.title,
                "priority": "high",
                "revenue_impact": 1,
            }
        )

    items.sort(
        key=lambda i: (
            i.get("revenue_impact", 0),
            _PRIORITY_RANK.get(str(i.get("priority", "medium")), 2),
        ),
        reverse=True,
    )
    return items


async def cmd_inbox_list(args: argparse.Namespace) -> None:
    """統合承認インボックスを一覧表示する（収益インパクト→優先度の順）。"""
    from core.platform.state import get_platform_home

    items = _collect_inbox(get_platform_home())
    kind_filter = getattr(args, "kind", None)
    if kind_filter:
        items = [i for i in items if i["kind"] == kind_filter]
    if not items:
        print("承認待ちはありません（インボックスは空です）。")
        return

    counts: Dict[str, int] = {}
    for i in items:
        counts[i["kind"]] = counts.get(i["kind"], 0) + 1
    summary = " / ".join(f"{k}:{v}" for k, v in sorted(counts.items()))
    print(f"\n承認インボックス（{len(items)} 件 — {summary}）\n")
    _hint = {
        "proposal": "proposal apply",
        "handoff": "handoff approve",
        "publish": "publish jobs run/confirm",
        "human_task": "人手対応",
    }
    for i in items:
        print(
            f"  [{i['kind']:<10}] ★{i['revenue_impact']} ({i['priority']:<6}) "
            f"{i['title']}  ({i['org_name']})  id={i['id']}"
        )
    print("\n承認: 種別ごとに pantheon approve / handoff approve / publish jobs run … で実行")


def register(subparsers: Any) -> None:
    parser = subparsers.add_parser("inbox", help="統合承認インボックスを一覧（GUI /inbox と同等）")
    sub = parser.add_subparsers(dest="inbox_command", required=True)

    list_p = sub.add_parser("list", help="承認待ち（提案/handoff/投稿/人間タスク）を一覧")
    list_p.add_argument(
        "--kind",
        default=None,
        choices=["proposal", "handoff", "publish", "human_task"],
        help="種別で絞り込み",
    )
    list_p.set_defaults(handler_name="cmd_inbox_list")
