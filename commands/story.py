"""`pantheon story` — イラストストーリー（RED THREAD）の自律制作。

会社プラグイン ``illustration_story_youtube`` で立ち上げた Organization のワークスペースに
展開されたカノン（style_bible / character_registry / series_canon）を読み、1 エピソード分の
制作ブリーフ（2 ビート台本・ショット・スタイル固定の画像プロンプト・メタデータ・タイムライン
JSON・クロス投稿文・外部/人手ハンドオフ）を生成して ``<ws>/episodes/ep-<NN>.yaml`` に保存する。

Pantheon が「テキスト AI として確実にできる」範囲だけを担う。画像ピクセル・動画レンダ・
YouTube 投稿はブリーフの human_handoff として外部ツール/利用者へ正直に渡す（見かけ自動にしない）。
"""

from __future__ import annotations

import argparse
import sys
from typing import Any


async def cmd_story_brief(args: argparse.Namespace, *, get_psm: Any) -> None:
    """カノンから次（または指定）エピソードの制作ブリーフを生成し workspace に保存する。"""
    from pathlib import Path

    import yaml

    from core.illustration_story.episode_brief import (
        build_episode_brief,
        load_canon,
        next_unproduced_episode,
    )
    from core.persistence import atomic_write_text

    psm = get_psm()
    org = psm.load_organization_by_name(args.org)
    if org is None:
        print(f"[ERROR] Organization '{args.org}' が見つかりません")
        sys.exit(1)
    ws = getattr(org, "workspace_path", None)
    if not ws:
        print(
            f"[ERROR] '{args.org}' にワークスペースがありません（会社プラグインで作成してください）"
        )
        sys.exit(1)

    canon = load_canon(ws)
    if not canon.get("series_canon"):
        print(
            "[ERROR] カノン（series_canon.yaml）が見つかりません。"
            "illustration_story_youtube 会社プラグインの install で展開されます"
        )
        sys.exit(1)

    episodes_dir = Path(ws) / "episodes"
    fmt = getattr(args, "format", "long_form") or "long_form"

    if getattr(args, "ep", None):
        ep_no = int(args.ep)
        backlog = {
            int(b["ep"]): b
            for b in (canon["series_canon"].get("backlog") or [])
            if b.get("ep") is not None
        }
        b = backlog.get(ep_no)
        if b is None:
            print(
                f"[ERROR] ep {ep_no} は backlog にありません。"
                "series_canon.yaml の backlog に追加してください"
            )
            sys.exit(1)
        resolved = {
            "episode_no": ep_no,
            "logline": str(b.get("logline") or ""),
            "cast_ids": [str(x) for x in (b.get("cast") or [])],
            "advances_arc": bool(b.get("advances_arc")),
        }
    else:
        resolved = next_unproduced_episode(canon, episodes_dir)
        if resolved is None:
            print(
                "[OK] backlog のエピソードは全て生成済みです。"
                "series_canon.yaml の backlog に新エピソードを追加してください"
            )
            return

    brief = build_episode_brief(
        canon,
        episode_no=resolved["episode_no"],
        logline=resolved["logline"],
        cast_ids=resolved["cast_ids"],
        advances_arc=resolved["advances_arc"],
        fmt=fmt,
    )

    episodes_dir.mkdir(parents=True, exist_ok=True)
    out_path = episodes_dir / f"ep-{resolved['episode_no']:02d}.yaml"
    atomic_write_text(out_path, yaml.safe_dump(brief, allow_unicode=True, sort_keys=False))

    md = brief["metadata"]
    print(f"\n[OK] エピソードブリーフを生成しました: {out_path}")
    print(f"  #{brief['episode_no']} [{brief['format']}] {md['title']}")
    print(
        f"  ショット {len(brief['shot_list'])} / 画像プロンプト {len(brief['image_prompts'])} / "
        f"尺 {brief['total_duration_s']}s"
    )
    print(
        f"  幕: {brief['act'] or '(未設定)'}  /  arc進行: {'はい' if brief['advances_arc'] else 'いいえ'}"
    )
    print(
        "  次の人手/外部（briefの human_handoff 参照）: 画像生成→動画組立→楽曲→サムネ→YouTube投稿"
    )


def register(subparsers: Any) -> None:
    parser = subparsers.add_parser("story", help="イラストストーリー（RED THREAD）の自律制作")
    sub = parser.add_subparsers(dest="story_command", required=True)

    b = sub.add_parser(
        "brief",
        help="カノンから次エピソードの制作ブリーフ（台本/画像プロンプト/タイムライン/ハンドオフ）を生成",
    )
    b.add_argument(
        "--org", required=True, help="illustration_story_youtube で作成した Organization 名"
    )
    b.add_argument(
        "--ep",
        type=int,
        default=None,
        help="生成するエピソード番号（省略時は backlog の未生成の最小話）",
    )
    b.add_argument(
        "--format",
        choices=["long_form", "shorts"],
        default="long_form",
        help="長尺アンソロジー or Shorts（aspect と尺が変わる）",
    )
    b.set_defaults(handler_name="cmd_story_brief")
