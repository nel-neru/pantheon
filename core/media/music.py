"""BGM 自動選定 — 利用者が用意したローカル音源ライブラリから mood に合う1曲を選ぶ（鍵不要）。

無言ストーリーに必須の BGM を、ブリーフの ``timeline_spec.music_mood`` に合わせて決定論的に選ぶ。
音源は利用者が権利処理済みのものを ``~/.pantheon/music_library/<mood>/*.mp3`` 等に置く前提
（Pantheon は音を生成・ダウンロードしない＝偽の/無断の音源を作らない）。ライブラリが空なら
``None`` を返し、動画は BGM 無しで進む（正直）。完全ローカル・決定論でテスト可能。
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

_AUDIO_EXTS = (".mp3", ".wav", ".m4a", ".ogg", ".aac", ".flac")

# mood フォルダ名 → それに寄せるキーワード（music_mood 文字列との部分一致で判定）。
_MOOD_KEYWORDS: Dict[str, Tuple[str, ...]] = {
    "tender": (
        "tender",
        "calm",
        "quiet",
        "gentle",
        "soft",
        "emotional",
        "warm",
        "sad",
        "穏",
        "静",
        "切",
    ),
    "tense": ("tense", "dark", "suspense", "mystery", "ominous", "dramatic", "緊張", "不穏", "謎"),
    "whimsical": (
        "whimsical",
        "playful",
        "light",
        "quirky",
        "fun",
        "curious",
        "軽",
        "楽し",
        "不思議",
    ),
    "neutral": ("neutral", "ambient", "minimal", "中立"),
}


def music_library_dir(platform_home: Optional[Path] = None) -> Path:
    if platform_home is None:
        from core.platform.state import get_platform_home

        platform_home = get_platform_home()
    return Path(platform_home) / "music_library"


def _tracks_in(folder: Path) -> List[Path]:
    if not folder.exists() or not folder.is_dir():
        return []
    return sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in _AUDIO_EXTS)


def _match_mood_folder(mood_text: str) -> Optional[str]:
    """music_mood 文字列に最も合う mood フォルダ名を返す（当たらなければ None）。"""
    low = str(mood_text or "").lower()
    for folder, keywords in _MOOD_KEYWORDS.items():
        if any(k.lower() in low for k in keywords):
            return folder
    return None


def select_music(
    mood_text: str,
    *,
    platform_home: Optional[Path] = None,
    episode_no: int = 0,
) -> Optional[str]:
    """mood に合う音源を1曲選んで返す。ライブラリが空/不在なら ``None``（BGM 無しで進む）。

    選曲は決定論: mood フォルダ内のトラックを ``episode_no`` で循環選択（話ごとに変化・再現可能）。
    mood フォルダが無ければ、他の mood フォルダ → ライブラリ直下 の順にフォールバックする。
    """
    lib = music_library_dir(platform_home)
    if not lib.exists():
        return None

    # 1) mood に一致するフォルダ
    candidates: List[Path] = []
    folder = _match_mood_folder(mood_text)
    if folder:
        candidates = _tracks_in(lib / folder)
    # 2) フォールバック: いずれかの mood フォルダ → 直下
    if not candidates:
        for sub in sorted(p for p in lib.iterdir() if p.is_dir()):
            candidates = _tracks_in(sub)
            if candidates:
                break
    if not candidates:
        candidates = _tracks_in(lib)
    if not candidates:
        return None

    idx = abs(int(episode_no)) % len(candidates)
    return str(candidates[idx])
