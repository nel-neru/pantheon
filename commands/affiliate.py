"""`pantheon affiliate` — AI 短尺動画アフィリエイト運用 CLI。

商材レジストリ・投稿カレンダー・成果記録を人間の運用導線として束ねる。
投稿は人間が 1 日 1 本（``affiliate next`` が /inbox に HumanTask を積む）。
ロードマップ: ``docs/plans/shortvideo-affiliate-monetization-roadmap.md``。
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

# 成果(Outcome)は単一の収益 Organization 名で集計する。
AFFILIATE_ORG = "ShortVideoAffiliate"
VALID_METRICS = ("impressions", "clicks", "conversions", "revenue")


def _program_store():
    from core.affiliate.programs import AffiliateProgramStore

    return AffiliateProgramStore()


def _calendar_store():
    from core.affiliate.short_video import ShortVideoCalendarStore

    return ShortVideoCalendarStore()


async def cmd_affiliate_seed(args: argparse.Namespace, *, get_psm: Any) -> None:
    """config/affiliate_programs/ai_tools.yaml を商材レジストリへ取り込む（冪等）。"""
    store = _program_store()
    count = store.seed_from_config()
    if count == 0:
        print(
            "[WARN] シードできる案件が見つかりませんでした（config/affiliate_programs/ai_tools.yaml を確認）。"
        )
        return
    print(
        f"[OK] {count} 件の商材をレジストリへ取り込みました（~/.pantheon/affiliate_programs.json）。"
    )
    print("一覧: pantheon affiliate programs")


async def cmd_affiliate_programs(args: argparse.Namespace, *, get_psm: Any) -> None:
    """商材レジストリを一覧表示する（空ならconfigから自動シード）。"""
    store = _program_store()
    programs = store.list_programs()
    if not programs:
        seeded = store.seed_from_config()
        programs = store.list_programs()
        if seeded:
            print(f"（レジストリが空だったため config から {seeded} 件シードしました）\n")
    if not programs:
        print("商材がありません。pantheon affiliate seed を実行してください。")
        return
    order = {"a": 0, "b": 1, "c": 2}
    programs.sort(key=lambda p: (order.get(p.tier, 3), p.name))
    print(f"\nアフィリエイト商材レジストリ（{len(programs)} 件）\n")
    print(f"{'tier':4} {'aff':4} {'rec':4} {'category':10} name")
    print("-" * 60)
    for p in programs:
        aff = "○" if p.has_affiliate else "-"
        rec = "○" if p.recurring else "-"
        print(f"{p.tier:4} {aff:4} {rec:4} {p.category:10} {p.name}")
    enabled = [p for p in programs if p.has_affiliate]
    print(
        f"\n収益源(has_affiliate)= {len(enabled)} 件 / 集客ネタ= {len(programs) - len(enabled)} 件"
    )
    print("tier a=主力 / b=補完 / c=集客ネタ、rec=継続報酬。料率・参加可否は各自要確認。")


async def cmd_affiliate_calendar(args: argparse.Namespace, *, get_psm: Any) -> None:
    """投稿カレンダーの予定を表示する（既定は直近 limit 件）。"""
    store = _calendar_store()
    store.ensure_seeded()  # 空なら同梱の半年分カレンダーを取り込む
    posts = store.list_posts()
    if not posts:
        print(
            "カレンダーが空です。`pantheon affiliate generate`（または量産Workflow）で生成してください。"
        )
        return
    limit = max(1, int(getattr(args, "limit", 14) or 14))
    upcoming = store.upcoming(limit=limit)
    shown = upcoming or posts[:limit]
    posted = sum(1 for p in posts if p.status == "posted")
    print(f"\n投稿カレンダー: 全 {len(posts)} 本（投稿済 {posted} / 残 {len(posts) - posted}）\n")
    for p in shown:
        mark = "* " if p.status == "posted" else "  "
        print(
            f"{mark} Day{p.day_index:>3} {p.date}  [{p.hook_type:7}] {p.program_name:14} {p.title}"
        )
    print("\n今日の1本: pantheon affiliate next")


async def cmd_affiliate_next(args: argparse.Namespace, *, get_psm: Any) -> None:
    """投稿すべき次の 1 本を全文表示し、人間タスク(/inbox)へ積む。"""
    store = _calendar_store()
    store.ensure_seeded()  # 空なら同梱の半年分カレンダーを取り込む
    post = store.next_unposted()
    if post is None:
        print("未投稿の下書きがありません（全て投稿済み、またはカレンダー未生成）。")
        return
    tags = " ".join(post.hashtags)
    print(f"\n=== 今日の投稿 Day {post.day_index} / {post.date} / {post.program_name} ===\n")
    print(f"タイトル: {post.title}")
    print(f"フック  : {post.hook}")
    print("\n--- 台本 ---")
    print(post.script)
    if post.onscreen_text:
        print(f"\nテロップ: {' / '.join(post.onscreen_text)}")
    print(f"\nCTA     : {post.cta}")
    print("\n--- 概要欄 ---")
    print(post.caption)
    print(f"\n{tags}")
    print(f"\nリンクslug: {post.affiliate_url_slug}（概要欄に計測付きアフィリリンクを差し込む）")

    # /inbox に「今日の投稿」確認タスクを積む（dedupe で二重登録なし）。
    try:
        from core.humans.human_tasks import HumanTaskStore

        HumanTaskStore().add(
            f"今日のShort投稿 Day{post.day_index}: {post.title}",
            description=f"{post.program_name} / {post.date}。台本は `pantheon affiliate next` 参照。投稿後 `pantheon affiliate done --post-id {post.post_id}`。",
            kind="publish_confirm",
            org_name=AFFILIATE_ORG,
            ref=post.post_id,
            dedupe_key=f"sv-post:{post.post_id}",
        )
        print(f"\n[OK] /inbox に投稿タスクを積みました（post_id={post.post_id}）。")
    except Exception as exc:  # noqa: BLE001 — タスク積みの失敗は表示を妨げない
        print(f"\n[WARN] 人間タスクの登録に失敗: {exc}")
    print(f"投稿が終わったら: pantheon affiliate done --post-id {post.post_id}")


async def cmd_affiliate_done(args: argparse.Namespace, *, get_psm: Any) -> None:
    """投稿済みにマークする。"""
    store = _calendar_store()
    post = store.mark_posted(args.post_id)
    if post is None:
        print(f"[ERROR] post_id '{args.post_id}' が見つかりません。")
        sys.exit(1)
    print(f"[OK] Day{post.day_index}（{post.title}）を投稿済みにしました。")
    nxt = store.next_unposted()
    if nxt:
        print(
            f"次の1本: Day{nxt.day_index} {nxt.date} {nxt.program_name}（pantheon affiliate next）"
        )


async def cmd_affiliate_record(args: argparse.Namespace, *, get_psm: Any) -> None:
    """成果（クリック/成約/収益等）を記録する（OutcomeStore）。"""
    metric = str(args.metric).strip().lower()
    if metric not in VALID_METRICS:
        print(f"[ERROR] --metric は {', '.join(VALID_METRICS)} のいずれか。")
        sys.exit(1)
    from core.metrics.outcomes import OutcomeStore

    program = getattr(args, "program", "") or "all"
    source = f"affiliate:{program}"
    OutcomeStore().record(
        AFFILIATE_ORG,
        metric,
        float(args.value),
        source=source,
        note=getattr(args, "note", "") or "",
    )
    print(f"[OK] 記録: {metric}={args.value}（program={program}）")
    print("集計: pantheon affiliate stats")


async def cmd_affiliate_stats(args: argparse.Namespace, *, get_psm: Any) -> None:
    """成果サマリ（収益・リーチ）を表示する。"""
    from core.metrics.outcomes import OutcomeStore

    summary = OutcomeStore().summary_for_org(AFFILIATE_ORG)
    print(f"\n成果サマリ - {AFFILIATE_ORG}（{summary.event_count} イベント）\n")
    if not summary.by_metric:
        print(
            "記録なし。`pantheon affiliate record --metric clicks --value 10 --program ElevenLabs` で記録できます。"
        )
        return
    for metric, stats in sorted(summary.by_metric.items()):
        print(f"  {metric:12} 合計 {stats.get('sum', 0):.1f} / 件数 {int(stats.get('count', 0))}")
    print(f"\n  収益計: {summary.total_revenue:.0f} / リーチ計: {summary.total_reach:.0f}")


def register(subparsers: Any) -> None:
    parser = subparsers.add_parser(
        "affiliate", help="AI短尺動画アフィリエイト運用（商材/カレンダー/成果）"
    )
    sub = parser.add_subparsers(dest="affiliate_command", required=True)

    seed_p = sub.add_parser("seed", help="商材レジストリを config から取り込む（冪等）")
    seed_p.set_defaults(handler_name="cmd_affiliate_seed")

    prog_p = sub.add_parser("programs", help="商材レジストリを一覧表示")
    prog_p.set_defaults(handler_name="cmd_affiliate_programs")

    cal_p = sub.add_parser("calendar", help="投稿カレンダーの予定を表示")
    cal_p.add_argument("--limit", type=int, default=14, help="表示件数（既定14）")
    cal_p.set_defaults(handler_name="cmd_affiliate_calendar")

    next_p = sub.add_parser("next", help="次に投稿する1本を全文表示し /inbox に積む")
    next_p.set_defaults(handler_name="cmd_affiliate_next")

    done_p = sub.add_parser("done", help="投稿済みにマーク")
    done_p.add_argument(
        "--post-id", required=True, dest="post_id", help="ShortVideoPost の post_id"
    )
    done_p.set_defaults(handler_name="cmd_affiliate_done")

    rec_p = sub.add_parser("record", help="成果（クリック/成約/収益）を記録")
    rec_p.add_argument("--metric", required=True, help="impressions/clicks/conversions/revenue")
    rec_p.add_argument("--value", required=True, type=float, help="数値")
    rec_p.add_argument("--program", default="", help="対象案件名（任意）")
    rec_p.add_argument("--note", default="", help="メモ（任意）")
    rec_p.set_defaults(handler_name="cmd_affiliate_record")

    stats_p = sub.add_parser("stats", help="成果サマリを表示")
    stats_p.set_defaults(handler_name="cmd_affiliate_stats")
