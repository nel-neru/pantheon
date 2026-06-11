"""DesignStyleLoader — config/design_styles/<id>.yaml の視覚スタイル指針を読む。

組織の ``design_style`` に応じてコンテンツ生成プロンプト（と将来の /studio
プレビュー）へトーン・配色・レイアウト指針を注入する。スタイル定義が無い場合は
空文字を返し、生成を一切妨げない。スタイルパック本体は C-2 で拡充する。
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

STYLE_DIRNAME = "design_styles"


def _styles_dir() -> Path:
    try:
        from core.paths import resource_path

        return resource_path("config", STYLE_DIRNAME)
    except Exception:  # noqa: BLE001
        return Path("config") / STYLE_DIRNAME


@lru_cache(maxsize=64)
def load_style(style_id: str) -> Optional[Dict[str, Any]]:
    """``config/design_styles/<id>.yaml`` を読み込む（欠落/不正時は None）。"""
    sid = (style_id or "").strip()
    if not sid:
        return None
    path = _styles_dir() / f"{sid}.yaml"
    try:
        import yaml

        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:  # noqa: BLE001
        return None
    return data if isinstance(data, dict) else None


def get_style_prompt_addon(style_id: str) -> str:
    """スタイルの prompt_addon（コンテンツ生成 system へ追記する指針）を返す。"""
    data = load_style(style_id)
    if not data:
        return ""
    addon = data.get("prompt_addon")
    return str(addon).strip() if addon else ""


def get_palette(style_id: str) -> Dict[str, str]:
    """スタイルの配色（primary/secondary/background/accent）を返す（欠落時空）。"""
    data = load_style(style_id)
    if not data:
        return {}
    palette = data.get("palette")
    return {str(k): str(v) for k, v in palette.items()} if isinstance(palette, dict) else {}


def list_styles() -> List[str]:
    d = _styles_dir()
    if not d.exists():
        return []
    return sorted({p.stem for p in d.glob("*.yaml")})


def list_style_summaries() -> List[Dict[str, Any]]:
    """全スタイルの id/name/description/palette を返す（/studio・API 用）。"""
    out: List[Dict[str, Any]] = []
    for sid in list_styles():
        data = load_style(sid) or {}
        out.append(
            {
                "id": sid,
                "name": str(data.get("name", sid)),
                "description": str(data.get("description", "")),
                "palette": get_palette(sid),
                "font_family": str(data.get("font_family", "")),
            }
        )
    return out
