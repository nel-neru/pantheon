"""サムネ・キャラ設定画の画像プロンプト構築（純粋・カノン由来の独自性を固定）。

エピソード制作の image_prompts と同じ思想で、サムネとキャラ設定画にも style_suffix／
negative_prompt をカノンから注入する（署名スタイルの一貫性＝独自性）。生成自体は
``core.media.image_gen.generate_images`` が担い、ここはプロンプト dict を作るだけ（テスト可能）。
"""

from __future__ import annotations

from typing import Any, Dict, List


def _style_and_negative(canon: Dict[str, Any]) -> tuple[str, str]:
    sb = canon.get("style_bible") or {}
    style = " ".join(str(sb.get("style_suffix") or "").split())
    negative = ", ".join(str(x) for x in (sb.get("negative_prompt_bank") or []))
    return style, negative


def thumbnail_prompt(brief: Dict[str, Any], canon: Dict[str, Any]) -> Dict[str, Any]:
    """ブリーフの thumbnail_brief ＋カノンから、サムネ1枚分の画像プロンプトを作る。"""
    style, negative = _style_and_negative(canon)
    tb = (brief.get("metadata") or {}).get("thumbnail_brief") or {}
    style = " ".join(str(tb.get("style_suffix") or style).split())
    focal = str(tb.get("focal_color") or "#D7263D")
    composition = str(tb.get("composition") or f"thumbnail for: {brief.get('logline', '')}")
    positive = (
        f"{composition}. focal color {focal}. high-contrast, eye-catching, single clear focal "
        "subject, strong silhouette, leaves room for the red thread"
    )
    return {
        "shot_id": "thumbnail",
        "positive": positive,
        "style_suffix": style,
        "negative_prompt": negative,
        "aspect": str(tb.get("aspect") or "16:9"),
    }


def character_prompts(canon: Dict[str, Any]) -> List[Dict[str, Any]]:
    """character_registry の各キャラ → 設定画（model sheet）1枚分の画像プロンプト。

    shot_id はキャラ id（保存名に使う）。base_seed は記録として載せる（provider が seed を
    受ける場合の再現用。現状の provider は seed を送らないため、一貫性は style_suffix と
    設定画アンカーの再利用で担保する＝偽の seed-lock を主張しない）。
    """
    registry = canon.get("character_registry") or {}
    style, negative = _style_and_negative(canon)
    out: List[Dict[str, Any]] = []
    for c in registry.get("characters") or []:
        cid = str(c.get("id") or "").strip()
        if not cid:
            continue
        positive = (
            f"character model sheet (turnaround): {c.get('name', cid)}. "
            "front, three-quarter and side views, plus three facial expressions. "
            f"{c.get('face', '')}. wearing {c.get('outfit', '')}. "
            "full body, plain neutral background, consistent character design"
        )
        out.append(
            {
                "shot_id": cid,
                "positive": positive,
                "style_suffix": style,
                "negative_prompt": negative,
                "aspect": "16:9",
                "base_seed": c.get("base_seed"),
            }
        )
    return out
