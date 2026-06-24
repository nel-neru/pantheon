"""`pantheon trends` — 外部トレンドの収集・一覧。

`collect` で config/trend_sources.yaml の RSS/Atom を横断取得→採点→重複排除保存。
`list` で保存済みトレンドをスコア順に表示する。X/YouTube は別 collector（B-2/B-3）。
"""

from __future__ import annotations

import argparse
from typing import Any


async def cmd_trends_collect(args: argparse.Namespace) -> None:
    """選択ソース（既定 web+youtube、--source grok で Grok）から収集して保存する。"""
    from core.trends.runner import collect_and_store

    source = getattr(args, "source", None)
    grok_query = getattr(args, "grok_query", None)
    sources: set[str] | None = None
    if grok_query:
        sources = {"grok"}
    elif source == "all":
        sources = {"web", "youtube", "grok"}
    elif source in {"web", "youtube", "grok"}:
        sources = {source}
    # source 無指定（None）→ collect_and_store の既定（web+youtube）に委ねる

    result = await collect_and_store(sources=sources, grok_query=grok_query)
    print(
        f"[trends] {result['sources']} ソースから {result['collected']} 件収集、"
        f"{result['added']} 件を新規保存（重複は除外）"
    )
    if result.get("grok"):
        print(f"        Grok: {result['grok']} 件")
    if result.get("grok_needs_reconnect"):
        print(
            "[warn]  Grok セッションが未接続/失効の可能性があります。"
            "`pantheon trends connect-grok` で再接続してください"
        )


async def cmd_trends_connect_grok(args: argparse.Namespace) -> None:
    """grok.com にヘッドフルブラウザで手動ログインし、セッション state を保存する（1回だけ）。"""
    from core.trends.grok_connect import connect_grok

    print(
        "[grok] ヘッドフルブラウザを起動します。開いたウィンドウで grok.com にログインしてください…"
    )
    print("       （注意: grok.com の自動操作は xAI の規約・bot 検知の対象になり得ます）")
    result = await connect_grok(timeout_s=float(getattr(args, "timeout", 300.0)))
    if result.ok:
        print(f"[OK]   {result.detail}")
        print(f"       state: {result.state_path}")
    else:
        print(f"[ERROR] {result.error}")


async def cmd_trends_grok_status(args: argparse.Namespace) -> None:
    """Grok の接続状態を表示する。"""
    from core.trends.grok_connect import grok_status

    st = grok_status()
    mark = "[OK]  " if st.status == "connected" else "[NONE]"
    suffix = f" connected_at={st.connected_at}" if st.connected_at else ""
    print(f"{mark} grok {st.status}{suffix}")
    if st.status != "connected":
        print("       接続: pantheon trends connect-grok")


async def cmd_trends_disconnect_grok(args: argparse.Namespace) -> None:
    """保存済み Grok セッション state を削除して切断する。"""
    from core.trends.grok_connect import disconnect_grok

    if disconnect_grok():
        print("[grok] 切断しました（セッション state を削除）")
    else:
        print("[grok] 保存済みセッションはありません")


async def cmd_trends_list(args: argparse.Namespace) -> None:
    """保存済みトレンドをスコア順に表示する。"""
    from core.trends.store import TrendStore

    items = TrendStore().list(
        limit=args.limit,
        source=args.source,
        genre=args.genre,
        min_score=args.min_score,
    )
    if not items:
        print("[trends] 保存済みトレンドはありません（pantheon trends collect で収集）")
        return
    for i in items:
        topics = f" [{', '.join(i.topics)}]" if i.topics else ""
        print(f"  {i.score:4.1f}  ({i.source}/{i.genre or '-'}) {i.title}{topics}")
        print(f"        {i.url}")


async def cmd_trends_business_scan(args: argparse.Namespace) -> None:
    """高スコアトレンドを新規会社候補提案へ変換し承認キューへ積む（WIRE-B・自動採用しない）。"""
    from core.trends.business_pipeline import scan_business_proposals

    result = scan_business_proposals(min_score=args.min_score, max_per_run=args.max_per_run)
    if result.get("reason") == "no_org":
        print("[trends] 受け手の Organization がありません（先に org を作成してください）")
        return
    print(
        f"[trends] 新規会社候補提案を {result.get('proposals', 0)} 件起票"
        f"（走査 {result.get('scanned', 0)} 件・承認キュー /inbox で確認）"
    )


async def cmd_trends_untapped(args: argparse.Namespace) -> None:
    """未開拓ジャンルを発見し新会社候補提案を承認キューへ起票する（P4.2・claude CLI 不要）。"""
    from core.trends.untapped_genre import (
        enumerate_genre_evidence,
        find_untapped_genres,
        scan_untapped_genre_proposals,
    )

    if getattr(args, "preview", False):
        from core.platform.state import PlatformStateManager, get_platform_home
        from core.trends.store import TrendStore
        from core.trends.untapped_genre import _covered_genres

        home = get_platform_home()
        evidence = enumerate_genre_evidence(TrendStore(home), min_score=args.min_score)
        covered = _covered_genres(PlatformStateManager(home))
        untapped = find_untapped_genres(
            evidence, covered, min_evidence=args.min_evidence, min_score=args.min_score
        )
        if not untapped:
            print("[trends] 未開拓ジャンルは見つかりませんでした")
            return
        print(f"[trends] 未開拓ジャンル {len(untapped)} 件（被覆 {len(covered)} 件を除外）:")
        for g in untapped:
            ev = evidence[g]
            print(f"  - {g}（証拠 {ev['count']} 件 / 最高スコア {ev['max_score']:.1f}）")
        print("（--preview のため起票していません）")
        return

    result = scan_untapped_genre_proposals(
        min_score=args.min_score, min_evidence=args.min_evidence, max_per_run=args.max_per_run
    )
    if result.get("reason") == "no_org":
        print("[trends] 受け手の Organization がありません（先に org を作成してください）")
        return
    print(
        f"[trends] 未開拓ジャンルの新会社候補を {result.get('proposals', 0)} 件起票"
        f"（検出 {result.get('scanned', 0)} 件・承認キュー /inbox で確認）"
    )


async def cmd_trends_business_proposals(args: argparse.Namespace) -> None:
    """承認待ちの新規会社候補提案（category=new_business）を一覧する（GUI の Card 2 と同等）。"""
    from core.platform.state import PlatformStateManager, get_platform_home

    psm = PlatformStateManager(platform_home=get_platform_home())
    rows: list[tuple[str, str, str, str]] = []
    for org in psm.load_organizations():
        try:
            sm = psm.get_org_state_manager(org)
            for p in sm.get_pending_improvement_proposals(limit=50):
                if p.get("category") != "new_business":
                    continue
                rows.append(
                    (
                        org.name,
                        str(p.get("id", "")),
                        str(p.get("title", "")),
                        str(p.get("priority") or "medium"),
                    )
                )
        except Exception:  # noqa: BLE001 — 1 組織の読み取り失敗で全体を落とさない
            continue
    if not rows:
        print(
            "[trends] 承認待ちの新規会社候補提案はありません"
            "（pantheon trends business-scan / untapped で起票）"
        )
        return
    print(f"\n承認待ちの新規会社候補（{len(rows)} 件）\n")
    for org_name, pid, title, priority in rows:
        print(f"  - [{priority}] {title}  ({org_name})  id={pid}")
    print("\n承認: pantheon approve / proposal apply（または GUI /inbox）")


def register(subparsers: Any) -> None:
    parser = subparsers.add_parser("trends", help="外部トレンドの収集・一覧")
    sub = parser.add_subparsers(dest="trends_command", required=True)

    sp = sub.add_parser(
        "collect", help="収集・採点・保存（既定 web+youtube、--source grok で Grok）"
    )
    sp.add_argument(
        "--source",
        choices=["all", "web", "youtube", "grok"],
        default=None,
        help="収集する collector（無指定=web+youtube / all=全て / grok=Grokのみ）",
    )
    sp.add_argument(
        "--grok-query",
        default=None,
        dest="grok_query",
        help="Grok にその場で投げるアドホックなリサーチ指示（config を無視しこの1件のみ）",
    )
    sp.set_defaults(handler_name="cmd_trends_collect")

    sp = sub.add_parser("connect-grok", help="grok.com に手動ログインしセッションを保存（1回だけ）")
    sp.add_argument("--timeout", type=float, default=300.0, help="ログイン検知のタイムアウト秒")
    sp.set_defaults(handler_name="cmd_trends_connect_grok")

    sp = sub.add_parser("grok-status", help="Grok の接続状態を表示")
    sp.set_defaults(handler_name="cmd_trends_grok_status")

    sp = sub.add_parser("disconnect-grok", help="保存済み Grok セッションを削除して切断")
    sp.set_defaults(handler_name="cmd_trends_disconnect_grok")

    sp = sub.add_parser("list", help="保存済みトレンドをスコア順に表示")
    sp.add_argument("--limit", type=int, default=30, help="表示件数")
    sp.add_argument("--source", default=None, help="source で絞り込み（web/youtube/x）")
    sp.add_argument("--genre", default=None, help="ジャンルで絞り込み")
    sp.add_argument("--min-score", type=float, default=0.0, dest="min_score", help="最低スコア")
    sp.set_defaults(handler_name="cmd_trends_list")

    sp = sub.add_parser("business-scan", help="高スコアトレンド→新規会社候補提案を承認キューへ起票")
    sp.add_argument(
        "--min-score", type=float, default=7.0, dest="min_score", help="最低スコア(0..10)"
    )
    sp.add_argument(
        "--max-per-run", type=int, default=5, dest="max_per_run", help="1回の最大起票数"
    )
    sp.set_defaults(handler_name="cmd_trends_business_scan")

    sp = sub.add_parser("untapped", help="未開拓ジャンルを発見し新会社候補提案を起票（P4.2）")
    sp.add_argument(
        "--min-score", type=float, default=7.0, dest="min_score", help="最低スコア(0..10)"
    )
    sp.add_argument(
        "--min-evidence", type=int, default=1, dest="min_evidence", help="ジャンル最小証拠件数"
    )
    sp.add_argument(
        "--max-per-run", type=int, default=5, dest="max_per_run", help="1回の最大起票数"
    )
    sp.add_argument("--preview", action="store_true", help="起票せず未開拓ジャンルを表示のみ")
    sp.set_defaults(handler_name="cmd_trends_untapped")

    sp = sub.add_parser(
        "business-proposals", help="承認待ちの新規会社候補提案を一覧（GUI Card 2 と同等）"
    )
    sp.set_defaults(handler_name="cmd_trends_business_proposals")
