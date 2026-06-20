"""エピソードブリーフ生成 — 永続カノンから1話分の制作パッケージを組み立てる（決定論・LLM 非依存）。

会社プラグイン install で org ワークスペースに展開されたカノン（style_bible / character_registry /
series_canon）を読み、1 エピソード分の **制作ブリーフ**を組み立てる:

- 2 ビート（kind setup → twist）の構成と決定論的なショットリスト
- 各ショットの**画像生成プロンプト**（style_suffix・キャラ参照と固定 seed・negative bank・aspect を
  カノンから必ず注入 ＝ 独自性と連続性を prompt 層で固定）
- タイトル/概要（アフィリ表記＋CTA）/タグ/サムネ指示
- 動画タイムライン JSON 仕様（Ken Burns・尺・音楽ムード）
- TikTok/Reels/X 向けクロス投稿文
- **外部・人手ハンドオフのチェックリスト**（画像生成/動画組立/楽曲/アップロードは Pantheon では
  やらない＝見かけ自動にしない正直な境界をブリーフ自体に明記）

ここは Pantheon が「テキスト AI として確実にできる」範囲だけを担う。画像ピクセル・動画レンダ・
YouTube 投稿は生成しない（それらは external-tool / user）。LLM 非依存で決定論（テスト可能・
トークン消費ゼロ）。creative な文面の claude 強化は将来の opt-in（Phase 2）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

CANON_FILES = ("style_bible", "character_registry", "series_canon")


def load_canon(workspace: Any) -> Dict[str, Any]:
    """``<workspace>/canon/{style_bible,character_registry,series_canon}.yaml`` を読み込む。

    壊れた/欠落ファイルはそのキーを ``{}`` にフォールバックして全体を止めない（観測可能な堅牢性）。
    """
    canon_dir = Path(workspace) / "canon"
    out: Dict[str, Any] = {}
    for key in CANON_FILES:
        path = canon_dir / f"{key}.yaml"
        data: Any = {}
        if path.exists():
            try:
                data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            except (yaml.YAMLError, OSError):
                data = {}
        out[key] = data if isinstance(data, dict) else {}
    return out


def _resolve_act(series_canon: Dict[str, Any], episode_no: int) -> str:
    """arc.acts のうち episode_no を含む幕名を返す（範囲 "a-b"）。無ければ ""。"""
    arc = series_canon.get("arc") or {}
    for act in arc.get("acts") or []:
        rng = str(act.get("episodes") or "")
        if "-" in rng:
            try:
                lo, hi = (int(x) for x in rng.split("-", 1))
            except ValueError:
                continue
            if lo <= episode_no <= hi:
                return str(act.get("name") or "")
    return ""


def _resolve_cast(registry: Dict[str, Any], cast_ids: List[str]) -> List[Dict[str, Any]]:
    """character_registry から cast_ids に対応するキャラ block（name/base_seed/face/outfit）を返す。"""
    by_id = {str(c.get("id")): c for c in (registry.get("characters") or []) if c.get("id")}
    resolved: List[Dict[str, Any]] = []
    for cid in cast_ids:
        c = by_id.get(str(cid))
        if c is None:
            continue
        resolved.append(
            {
                "id": str(c.get("id")),
                "name": str(c.get("name") or c.get("id")),
                "base_seed": c.get("base_seed"),
                "face": str(c.get("face") or ""),
                "outfit": str(c.get("outfit") or ""),
            }
        )
    return resolved


# 2 ビート寓話の決定論ショット骨格（beat, 役割, カメラ, 既定尺秒）。
_SHOT_SKELETON = [
    ("setup", "establishing", "町の静かな全景。日常の優しい空気を確立する", "wide establishing", 4),
    ("setup", "subject", "主役の何気ない行動。観客が状況を素直に受け取る", "medium", 4),
    ("setup", "detail", "赤い糸がさりげなく画面に入る（伏線）", "insert close-up", 3),
    ("twist", "pivot", "視点が動く。さっきの場面の前提が揺らぐ", "slow push-in", 4),
    ("twist", "reveal", "一つの twist で全部の意味が反転する決定的カット", "reveal wide", 5),
    ("twist", "resonance", "反転後の余韻。赤い糸が意味を帯びて残る", "static hold", 4),
]


def _style_suffix(style_bible: Dict[str, Any]) -> str:
    return " ".join(str(style_bible.get("style_suffix") or "").split())


def _negative_prompt(style_bible: Dict[str, Any]) -> str:
    return ", ".join(str(x) for x in (style_bible.get("negative_prompt_bank") or []))


def _aspect(style_bible: Dict[str, Any], fmt: str) -> str:
    ar = style_bible.get("aspect_ratios") or {}
    return str(ar.get(fmt) or ar.get("long_form") or "16:9")


def build_episode_brief(
    canon: Dict[str, Any],
    *,
    episode_no: int,
    logline: str,
    cast_ids: Optional[List[str]] = None,
    advances_arc: bool = False,
    fmt: str = "long_form",
) -> Dict[str, Any]:
    """カノン＋エピソード前提から決定論で制作ブリーフを組み立てる。

    ``fmt`` は ``long_form`` か ``shorts``（aspect と尺の既定が変わる）。画像プロンプトには
    style_suffix・キャラ参照（固定 seed）・negative bank・aspect を必ず注入する（独自性・連続性の固定）。
    """
    style_bible = canon.get("style_bible") or {}
    registry = canon.get("character_registry") or {}
    series = canon.get("series_canon") or {}

    cast = _resolve_cast(registry, list(cast_ids or []))
    style_suffix = _style_suffix(style_bible)
    negative = _negative_prompt(style_bible)
    aspect = _aspect(style_bible, fmt)
    thread_red = (style_bible.get("palette") or {}).get("thread_red", "#D7263D")

    is_shorts = fmt == "shorts"
    char_refs = [{"id": c["id"], "base_seed": c["base_seed"]} for c in cast]
    char_desc = (
        "; ".join(f"{c['name']}（{c['face']} / {c['outfit']}）" for c in cast) or "（登場人物なし）"
    )

    shots: List[Dict[str, Any]] = []
    image_prompts: List[Dict[str, Any]] = []
    timeline_shots: List[Dict[str, Any]] = []
    # Shorts は twist 中心に短く（reveal/resonance を厚く）、long_form は全 6 ショット。
    skeleton = (
        _SHOT_SKELETON
        if not is_shorts
        else [s for s in _SHOT_SKELETON if s[0] == "twist" or s[1] in ("subject", "detail")]
    )
    for idx, (beat, role, desc, camera, dur) in enumerate(skeleton, start=1):
        shot_id = f"S{idx:02d}"
        thread_placement = (
            "twist の蝶番として赤い糸が機能する"
            if role == "reveal"
            else "画面の一辺に赤い糸を一本だけ配置"
        )
        positive = (
            f"{desc}. 登場: {char_desc}. {thread_placement}（{thread_red}）. シーン主旨: {logline}."
        )
        shots.append(
            {
                "id": shot_id,
                "beat": beat,
                "role": role,
                "description": desc,
                "camera": camera,
                "cast": [c["id"] for c in cast],
                "thread_placement": thread_placement,
                "duration_s": dur,
            }
        )
        image_prompts.append(
            {
                "shot_id": shot_id,
                "positive": positive,
                "style_suffix": style_suffix,  # カノン由来＝署名スタイル（独自性）
                "character_refs": char_refs,  # 固定 seed ＝ 連続性
                "negative_prompt": negative,
                "aspect": aspect,
            }
        )
        timeline_shots.append(
            {
                "shot_id": shot_id,
                "duration_s": dur,
                "motion": "ken_burns_in" if idx % 2 else "ken_burns_out",
                "transition": "hard_cut" if role == "reveal" else "dissolve",
            }
        )

    total_s = sum(s["duration_s"] for s in shots)
    act = _resolve_act(series, episode_no)
    title = f"RED THREAD #{episode_no} — {logline[:48]}"
    if is_shorts:
        title = f"[Shorts] {title}"

    description = (
        f"{logline}\n\n"
        "言葉のない、たった一つの twist の物語。毎話どこかに赤い糸が一本——見つけられますか？\n"
        "Full story / 他のエピソード → （チャンネルURL）\n\n"
        "— 使用画材/ツール（アフィリエイトリンクを含む場合があります #PR）: （リンク）\n"
        "#RedThread #wordlessstory #illustration #twistending #shortfilm"
    )
    tags = [
        "red thread",
        "wordless story",
        "illustration",
        "twist ending",
        "animated short",
        "赤い糸",
        "イラスト物語",
    ]
    thumbnail_brief = {
        "composition": f"twist の reveal カットを基に、{char_desc} を一人、赤い糸を強調",
        "style_suffix": style_suffix,
        "text_overlay": "なし（無言・グローバル）。必要なら普遍記号（?）のみ",
        "focal_color": thread_red,
        "aspect": "16:9",
    }

    return {
        "series": str(series.get("premise") and "RED THREAD" or "RED THREAD"),
        "episode_no": episode_no,
        "format": fmt,
        "act": act,
        "advances_arc": bool(advances_arc),
        "logline": logline,
        "beats": [
            {"beat": "setup", "intent": "優しく見える日常で観客の前提を作る"},
            {"beat": "twist", "intent": "一つの再文脈化で全部の意味を反転させる"},
        ],
        "cast": cast,
        "shot_list": shots,
        "image_prompts": image_prompts,
        "total_duration_s": total_s,
        "metadata": {
            "title": title,
            "description": description,
            "tags": tags,
            "thumbnail_brief": thumbnail_brief,
        },
        "timeline_spec": {
            "fps": 30,
            "aspect": aspect,
            "shots": timeline_shots,
            "music_mood": "minimal, tender, one quiet turn at the reveal; no lyrics",
        },
        "cross_post": {
            "tiktok": "言葉のない物語。赤い糸を見つけて。続きはYouTubeで。 #RedThread",
            "reels": "A wordless twist. Find the red thread. Full story on YouTube. #RedThread",
            "x": f"赤い糸はどこ？ 言葉のない twist 物語 #{episode_no}。フルはYouTubeで。 #RedThread #イラスト",
        },
        # 見かけ自動にしない正直な境界をブリーフ自体に明記する。
        "human_handoff": [
            f"画像生成: 上記 image_prompts {len(image_prompts)} 件を外部ツール（Nano Banana 等）で生成。"
            "character_refs の base_seed を固定し、初回は canonical_sheet を作って以後アンカーにする",
            "動画組立: timeline_spec を Shotstack/JSON2Video/Remotion/FFmpeg 等でレンダリング（Ken Burns・尺・トランジション）",
            "楽曲/効果音: music_mood に沿って権利処理済み音源を付与（アカウント紐付け）",
            "サムネ: thumbnail_brief を基に最終描画",
            "アップロード: YouTube へ最終投稿（チャンネル作成/OAuth/投稿は利用者）",
        ],
        "originality_continuity_lock": {
            "style_suffix_applied": bool(style_suffix),
            "negative_bank_applied": bool(negative),
            "character_seeds": {c["id"]: c["base_seed"] for c in cast},
            "note": "全カットに同一 style_suffix と固定 seed を注入＝独自性と連続性を prompt 層で固定",
        },
    }


def next_unproduced_episode(canon: Dict[str, Any], episodes_dir: Any) -> Optional[Dict[str, Any]]:
    """series_canon.backlog のうち、まだ ``episodes_dir/ep-<NN>.yaml`` が無い最小 ep を返す。

    繰り返し実行で backlog を順に消化する（自律運営の「次の一手」決定）。全て生成済みなら None。
    返り値: ``{episode_no, logline, cast_ids, advances_arc}``。
    """
    series = canon.get("series_canon") or {}
    backlog = series.get("backlog") or []
    edir = Path(episodes_dir)
    entries = []
    for b in backlog:
        try:
            ep = int(b.get("ep"))
        except (TypeError, ValueError):
            continue
        entries.append((ep, b))
    entries.sort(key=lambda t: t[0])
    for ep, b in entries:
        if (edir / f"ep-{ep:02d}.yaml").exists():
            continue
        return {
            "episode_no": ep,
            "logline": str(b.get("logline") or ""),
            "cast_ids": [str(x) for x in (b.get("cast") or [])],
            "advances_arc": bool(b.get("advances_arc")),
        }
    return None
