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


async def cmd_story_render(args: argparse.Namespace, *, get_psm: Any) -> None:
    """ブリーフ（ep-NN.yaml）から画像を生成し、FFmpeg で動画(mp4)を組み立てる。

    画像生成は provider の鍵が要る（無ければ正直にスキップ）。動画組立は FFmpeg ローカル完結。
    どちらも偽の成果物は作らない。
    """
    from pathlib import Path

    import yaml

    from core.media.credentials import MediaProviderNotConfigured
    from core.media.image_gen import generate_images
    from core.media.video_assembly import assemble_video

    psm = get_psm()
    org = psm.load_organization_by_name(args.org)
    if org is None:
        print(f"[ERROR] Organization '{args.org}' が見つかりません")
        sys.exit(1)
    ws = getattr(org, "workspace_path", None)
    if not ws:
        print(f"[ERROR] '{args.org}' にワークスペースがありません")
        sys.exit(1)

    episodes_dir = Path(ws) / "episodes"
    ep = getattr(args, "ep", None)
    if ep is None:
        briefs = sorted(episodes_dir.glob("ep-*.yaml"))
        if not briefs:
            print("[ERROR] ブリーフがありません。先に `pantheon story brief` を実行してください")
            sys.exit(1)
        ep_path = briefs[-1]
    else:
        ep_path = episodes_dir / f"ep-{int(ep):02d}.yaml"
    if not ep_path.exists():
        print(f"[ERROR] ブリーフが見つかりません: {ep_path}")
        sys.exit(1)

    brief = yaml.safe_load(ep_path.read_text(encoding="utf-8")) or {}
    ep_no = int(brief.get("episode_no") or 0)
    work = episodes_dir / f"ep-{ep_no:02d}"
    images_dir = work / "images"
    provider = getattr(args, "provider", "gemini") or "gemini"

    print(f"\nエピソード #{ep_no} をレンダリングします（{ep_path.name}）")
    if not getattr(args, "no_images", False):
        try:
            results = generate_images(
                brief.get("image_prompts") or [],
                out_dir=images_dir,
                provider=provider,
                platform_home=psm.platform_home,
            )
            ok = sum(1 for r in results if r.ok)
            print(f"  画像生成: {ok} 成功 / {len(results) - ok} 失敗（{images_dir}）")
            for r in results:
                if not r.ok:
                    print(f"    [画像失敗] {r.shot_id}: {r.error}")
        except MediaProviderNotConfigured as exc:
            print(f"  画像生成スキップ（未設定）: {exc}")
    else:
        print("  画像生成スキップ（--no-images）。既存画像を使います")

    timeline = brief.get("timeline_spec") or {}
    image_paths: dict[str, str] = {}
    for shot in timeline.get("shots") or []:
        sid = str(shot.get("shot_id") or "")
        p = images_dir / f"{sid}.png"
        if p.exists():
            image_paths[sid] = str(p)

    out_mp4 = work / f"ep-{ep_no:02d}.mp4"
    result = assemble_video(
        timeline, image_paths, out_path=out_mp4, audio_path=getattr(args, "audio", None)
    )
    if not result.ok:
        print(f"\n[ERROR] 動画組立に失敗: {result.error}")
        print("  画像が揃っているか確認してください（画像生成には provider の鍵が必要です）")
        sys.exit(1)
    print(f"\n[OK] 動画を生成しました: {result.path}")
    print(
        "  残りの人手/外部: サムネ最終描画 / 楽曲（--audio 未指定なら）/ "
        "YouTube 投稿（pantheon publish youtube ＝ 後続フェーズ）"
    )


async def cmd_story_publish(args: argparse.Namespace, *, get_psm: Any) -> None:
    """レンダリング済み mp4 を YouTube へアップロードする（既定ドライラン・--yes で実行）。

    外部公開アクションなので既定はドライプレビュー。認証情報が無ければ正直に停止（偽公開しない）。
    """
    from pathlib import Path

    import yaml

    from core.media.credentials import MediaProviderNotConfigured
    from core.media.youtube_upload import load_youtube_credentials, upload_video

    psm = get_psm()
    org = psm.load_organization_by_name(args.org)
    if org is None:
        print(f"[ERROR] Organization '{args.org}' が見つかりません")
        sys.exit(1)
    ws = getattr(org, "workspace_path", None)
    if not ws:
        print(f"[ERROR] '{args.org}' にワークスペースがありません")
        sys.exit(1)

    ep = int(args.ep)
    episodes_dir = Path(ws) / "episodes"
    mp4 = episodes_dir / f"ep-{ep:02d}" / f"ep-{ep:02d}.mp4"
    if not mp4.exists():
        print(f"[ERROR] 動画がありません: {mp4}（先に `pantheon story render` を実行）")
        sys.exit(1)

    brief_path = episodes_dir / f"ep-{ep:02d}.yaml"
    brief = yaml.safe_load(brief_path.read_text(encoding="utf-8")) if brief_path.exists() else {}
    md = (brief or {}).get("metadata") or {}
    title = str(md.get("title") or f"RED THREAD #{ep}")
    description = str(md.get("description") or "")
    tags = list(md.get("tags") or [])
    privacy = getattr(args, "privacy", "private")

    if not getattr(args, "yes", False):
        creds = load_youtube_credentials(psm.platform_home)
        print("（ドライラン）以下を YouTube にアップロードします。実行は --yes を付けてください:")
        print(f"  動画      : {mp4}")
        print(f"  タイトル  : {title}")
        print(f"  公開範囲  : {privacy}")
        print(f"  タグ      : {', '.join(tags)}")
        print(f"  認証情報  : {'あり' if creds else 'なし（OAuth 未設定ではアップロード不可）'}")
        return

    try:
        result = upload_video(
            mp4,
            title=title,
            description=description,
            tags=tags,
            privacy=privacy,
            platform_home=psm.platform_home,
        )
    except MediaProviderNotConfigured as exc:
        print(f"[ERROR] {exc}")
        sys.exit(1)
    if not result.ok:
        print(f"[ERROR] アップロード失敗: {result.error}")
        sys.exit(1)

    # 公開記録を残す（insights が episode→video_id を辿るため）。
    import json
    from datetime import datetime, timezone

    from core.persistence import atomic_write_text

    published = {
        "episode_no": ep,
        "video_id": result.video_id,
        "url": result.url,
        "privacy": privacy,
        "logline": str((brief or {}).get("logline") or ""),
        "published_at": datetime.now(timezone.utc).isoformat(),
    }
    atomic_write_text(
        episodes_dir / f"ep-{ep:02d}" / "published.json",
        json.dumps(published, ensure_ascii=False, indent=2),
    )
    print(f"\n[OK] YouTube にアップロードしました: {result.url}（公開範囲: {privacy}）")


async def cmd_story_produce(args: argparse.Namespace, *, get_psm: Any) -> None:
    """次の未制作 N 話を brief→render まで一括自動化する（外部公開は story publish --yes に残す）。

    ブリーフ生成（テキスト）は常に実行。動画化は画像鍵があれば実行し、失敗（鍵未設定など）は
    そのエピソードだけ skip して次へ進む（ブリーフは残る）。これが「自動運用」の一括コマンド。
    """
    from pathlib import Path

    from core.illustration_story.episode_brief import load_canon, next_unproduced_episode

    psm = get_psm()
    org = psm.load_organization_by_name(args.org)
    if org is None:
        print(f"[ERROR] Organization '{args.org}' が見つかりません")
        sys.exit(1)
    ws = getattr(org, "workspace_path", None)
    if not ws:
        print(f"[ERROR] '{args.org}' にワークスペースがありません")
        sys.exit(1)

    canon = load_canon(ws)
    if not canon.get("series_canon"):
        print("[ERROR] カノンがありません（illustration_story_youtube プラグインで作成されます）")
        sys.exit(1)

    episodes_dir = Path(ws) / "episodes"
    count = max(1, int(getattr(args, "count", 1)))
    fmt = getattr(args, "format", "long_form") or "long_form"
    produced = 0
    rendered = 0
    for _ in range(count):
        nxt = next_unproduced_episode(canon, episodes_dir)
        if nxt is None:
            print("backlog のエピソードは全て生成済みです（series_canon.yaml に追加できます）")
            break
        ep = nxt["episode_no"]
        await cmd_story_brief(argparse.Namespace(org=args.org, ep=ep, format=fmt), get_psm=get_psm)
        produced += 1
        try:
            await cmd_story_render(
                argparse.Namespace(
                    org=args.org,
                    ep=ep,
                    provider=getattr(args, "provider", "gemini"),
                    no_images=getattr(args, "no_images", False),
                    audio=None,
                ),
                get_psm=get_psm,
            )
            rendered += 1
        except SystemExit:
            print(
                f"  ep{ep}: 動画化はスキップ（画像鍵未設定/画像不足など）。ブリーフは生成済みです"
            )

    print(f"\n[完了] ブリーフ {produced} 本 / 動画 {rendered} 本を生成しました。")
    print("  公開（外部アクション）は人間の確認付き: pantheon story publish --org ... --ep N --yes")


def _load_org_ws(get_psm: Any, org_name: str):
    """org とワークスペースパスを取り出す（無ければ正直に終了）。"""
    psm = get_psm()
    org = psm.load_organization_by_name(org_name)
    if org is None:
        print(f"[ERROR] Organization '{org_name}' が見つかりません")
        sys.exit(1)
    ws = getattr(org, "workspace_path", None)
    if not ws:
        print(f"[ERROR] '{org_name}' にワークスペースがありません")
        sys.exit(1)
    return psm, org, ws


async def cmd_story_thumbnail(args: argparse.Namespace, *, get_psm: Any) -> None:
    """ブリーフの thumbnail_brief ＋カノンからサムネ画像を1枚生成する（CTR の最大レバー）。"""
    from pathlib import Path

    import yaml

    from core.illustration_story.asset_prompts import thumbnail_prompt
    from core.illustration_story.episode_brief import load_canon
    from core.media.credentials import MediaProviderNotConfigured
    from core.media.image_gen import generate_images

    psm, _org, ws = _load_org_ws(get_psm, args.org)
    ep = int(args.ep)
    brief_path = Path(ws) / "episodes" / f"ep-{ep:02d}.yaml"
    if not brief_path.exists():
        print(f"[ERROR] ブリーフがありません: {brief_path}（先に story brief）")
        sys.exit(1)
    brief = yaml.safe_load(brief_path.read_text(encoding="utf-8")) or {}
    prompt = thumbnail_prompt(brief, load_canon(ws))
    out_dir = Path(ws) / "episodes" / f"ep-{ep:02d}"
    try:
        results = generate_images(
            [prompt], out_dir=out_dir, provider=args.provider, platform_home=psm.platform_home
        )
    except MediaProviderNotConfigured as exc:
        print(f"[ERROR] {exc}")
        sys.exit(1)
    r = results[0]
    if not r.ok:
        print(f"[ERROR] サムネ生成失敗: {r.error}")
        sys.exit(1)
    print(f"\n[OK] サムネを生成しました: {r.path}")


async def cmd_story_characters(args: argparse.Namespace, *, get_psm: Any) -> None:
    """カノンのキャラ登録簿から設定画（model sheet）を生成し canonical_sheet を登録する。

    連続性の要（不変アンカー）の一括ブートストラップ。生成済み画像のパスを registry へ書き戻す。
    """
    from pathlib import Path

    import yaml

    from core.illustration_story.asset_prompts import character_prompts
    from core.illustration_story.episode_brief import load_canon
    from core.media.credentials import MediaProviderNotConfigured
    from core.media.image_gen import generate_images
    from core.persistence import atomic_write_text

    psm, _org, ws = _load_org_ws(get_psm, args.org)
    prompts = character_prompts(load_canon(ws))
    if not prompts:
        print("[ERROR] character_registry にキャラがいません")
        sys.exit(1)
    out_dir = Path(ws) / "canon" / "characters"
    try:
        results = generate_images(
            prompts, out_dir=out_dir, provider=args.provider, platform_home=psm.platform_home
        )
    except MediaProviderNotConfigured as exc:
        print(f"[ERROR] {exc}")
        sys.exit(1)

    ok = [r for r in results if r.ok]
    reg_path = Path(ws) / "canon" / "character_registry.yaml"
    if ok and reg_path.exists():
        reg = yaml.safe_load(reg_path.read_text(encoding="utf-8")) or {}
        by_id = {r.shot_id: r.path for r in ok}
        for c in reg.get("characters") or []:
            if str(c.get("id")) in by_id:
                c["canonical_sheet"] = by_id[str(c.get("id"))]  # 不変アンカーを登録
        atomic_write_text(reg_path, yaml.safe_dump(reg, allow_unicode=True, sort_keys=False))

    print(f"\n[OK] キャラ設定画 {len(ok)}/{len(results)} 枚を生成（{out_dir}）")
    if ok:
        print("  canonical_sheet を character_registry.yaml に登録しました（以後の連続性アンカー）")
    for r in results:
        if not r.ok:
            print(f"  [失敗] {r.shot_id}: {r.error}")


async def cmd_story_insights(args: argparse.Namespace, *, get_psm: Any) -> None:
    """公開済みエピソードの YouTube 統計を取得し、再生数降順でランキング表示・保存する。

    フィードバックループの計測側。episode→video_id は publish 時の published.json から辿る。
    認証情報が無ければ正直に停止（偽の数値は出さない）。
    """
    import json
    from pathlib import Path

    from core.media.credentials import MediaProviderNotConfigured
    from core.media.youtube_analytics import fetch_video_stats, rank_episodes
    from core.persistence import atomic_write_text

    psm, _org, ws = _load_org_ws(get_psm, args.org)
    episodes_dir = Path(ws) / "episodes"
    published: list[dict] = []
    for pub_file in sorted(episodes_dir.glob("ep-*/published.json")):
        try:
            published.append(json.loads(pub_file.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    if not published:
        print("公開済みの動画がありません（pantheon story publish --yes で公開すると記録されます）")
        return

    video_ids = [str(p.get("video_id") or "") for p in published if p.get("video_id")]
    try:
        stats = fetch_video_stats(video_ids, platform_home=psm.platform_home)
    except MediaProviderNotConfigured as exc:
        print(f"[ERROR] {exc}")
        sys.exit(1)

    report = rank_episodes(published, stats)
    atomic_write_text(
        Path(ws) / "insights.json",
        json.dumps(
            {"total_views": report.total_views, "ranked": report.ranked, "note": report.note},
            ensure_ascii=False,
            indent=2,
        ),
    )
    print(
        f"\n━━ RED THREAD インサイト（公開 {len(published)} 本・総再生 {report.total_views:,}）━━"
    )
    for i, row in enumerate(report.ranked[:10], start=1):
        print(
            f"  {i:>2}. #{row['episode_no']} 再生 {row['views']:,} / 高評価 {row['likes']:,}"
            f" — {str(row['logline'])[:36]}"
        )
    print(f"\n  保存: {Path(ws) / 'insights.json'}")
    print(f"  注: {report.note}")
    print("  次サイクルは上位の twist/型に制作枠を寄せると効率的（series_canon.backlog を更新）")


async def cmd_story_schedule(args: argparse.Namespace, *, get_psm: Any) -> None:
    """story produce を Windows タスクスケジューラで毎日自動実行する（公開は手動のまま）。"""
    from core.illustration_story.scheduler import (
        install_schedule,
        schedule_status,
        task_name_for,
        uninstall_schedule,
    )

    _load_org_ws(get_psm, args.org)  # org の存在確認
    action = getattr(args, "schedule_action", None)
    if action == "install":
        ok, out = install_schedule(
            args.org, count=getattr(args, "count", 1), time=getattr(args, "time", "09:00")
        )
        if not ok:
            print(f"[ERROR] タスク登録に失敗: {out}")
            sys.exit(1)
        print(
            f"\n[OK] 毎日 {getattr(args, 'time', '09:00')} に '{task_name_for(args.org)}' を登録しました"
            f"（story produce --count {getattr(args, 'count', 1)}）"
        )
        print(
            "  自動生成: ブリーフ＋動画（画像鍵があれば）。公開は story publish --yes（無人公開はしない）"
        )
    elif action == "uninstall":
        ok, out = uninstall_schedule(args.org)
        print("[OK] タスクを削除しました" if ok else f"[INFO] 削除できませんでした: {out}")
    elif action == "status":
        ok, out = schedule_status(args.org)
        print(out if ok else f"[INFO] タスク未登録か照会失敗: {out}")
    else:
        print("[ERROR] schedule のサブコマンド（install/uninstall/status）を指定してください")
        sys.exit(1)


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

    r = sub.add_parser("render", help="ブリーフから画像生成→FFmpegで動画(mp4)を組み立てる")
    r.add_argument("--org", required=True, help="Organization 名")
    r.add_argument(
        "--ep",
        type=int,
        default=None,
        help="レンダリングするエピソード番号（省略時は最新ブリーフ）",
    )
    r.add_argument(
        "--provider",
        choices=["gemini", "fal"],
        default="gemini",
        help="画像生成プロバイダ（鍵が要る）",
    )
    r.add_argument("--no-images", action="store_true", help="画像生成をスキップし既存画像で動画化")
    r.add_argument(
        "--audio", default=None, help="BGM/効果音ファイルのパス（権利処理済を利用者が用意）"
    )
    r.set_defaults(handler_name="cmd_story_render")

    p = sub.add_parser(
        "publish",
        help="レンダリング済み動画を YouTube にアップロード（Data API v3・既定ドライラン・--yesで実行）",
    )
    p.add_argument("--org", required=True, help="Organization 名")
    p.add_argument("--ep", type=int, required=True, help="公開するエピソード番号")
    p.add_argument(
        "--privacy",
        choices=["private", "unlisted", "public"],
        default="private",
        help="公開範囲（既定 private＝誤公開防止）",
    )
    p.add_argument("--yes", action="store_true", help="実アップロードを実行（未指定はドライラン）")
    p.set_defaults(handler_name="cmd_story_publish")

    pr = sub.add_parser(
        "produce",
        help="次の未制作 N 話を brief→render まで一括自動化（公開は publish --yes に残す）",
    )
    pr.add_argument("--org", required=True, help="Organization 名")
    pr.add_argument("--count", type=int, default=1, help="一括制作する話数（既定 1）")
    pr.add_argument(
        "--format", choices=["long_form", "shorts"], default="long_form", help="長尺 or Shorts"
    )
    pr.add_argument(
        "--provider", choices=["gemini", "fal"], default="gemini", help="画像プロバイダ"
    )
    pr.add_argument(
        "--no-images", action="store_true", help="画像生成をスキップ（既存画像で動画化）"
    )
    pr.set_defaults(handler_name="cmd_story_produce")

    t = sub.add_parser("thumbnail", help="ブリーフ＋カノンからサムネ画像を生成（CTRの最大レバー）")
    t.add_argument("--org", required=True, help="Organization 名")
    t.add_argument("--ep", type=int, required=True, help="サムネを作るエピソード番号")
    t.add_argument("--provider", choices=["gemini", "fal"], default="gemini", help="画像プロバイダ")
    t.set_defaults(handler_name="cmd_story_thumbnail")

    c = sub.add_parser(
        "characters", help="カノンのキャラ設定画（連続性アンカー）を一括生成し登録する"
    )
    c.add_argument("--org", required=True, help="Organization 名")
    c.add_argument("--provider", choices=["gemini", "fal"], default="gemini", help="画像プロバイダ")
    c.set_defaults(handler_name="cmd_story_characters")

    ins = sub.add_parser(
        "insights",
        help="公開済み動画の YouTube 統計を取得し再生数でランキング（フィードバック計測）",
    )
    ins.add_argument("--org", required=True, help="Organization 名")
    ins.set_defaults(handler_name="cmd_story_insights")

    sch = sub.add_parser(
        "schedule", help="story produce を毎日自動実行（Windows タスク・公開は手動のまま）"
    )
    sch_sub = sch.add_subparsers(dest="schedule_action", required=True)
    si = sch_sub.add_parser("install", help="毎日 produce を実行するタスクを登録")
    si.add_argument("--org", required=True, help="Organization 名")
    si.add_argument("--count", type=int, default=1, help="1回あたりの制作話数")
    si.add_argument("--time", default="09:00", help="実行時刻 HH:mm（既定 09:00）")
    si.set_defaults(handler_name="cmd_story_schedule")
    su = sch_sub.add_parser("uninstall", help="タスクを削除")
    su.add_argument("--org", required=True, help="Organization 名")
    su.set_defaults(handler_name="cmd_story_schedule")
    st = sch_sub.add_parser("status", help="タスクの状態を表示")
    st.add_argument("--org", required=True, help="Organization 名")
    st.set_defaults(handler_name="cmd_story_schedule")
