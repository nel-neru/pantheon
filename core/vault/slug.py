"""Vault ノートの決定論的・衝突安全なファイル名（slug）生成。

同じストアエントリは常に同じファイル名へ写像されること（冪等 export の前提）が肝心。
``human_slug`` は title を読みやすい slug に、``short_id`` は安定 id から短縮 id を作り、
``note_filename`` がその 2 つを連結して ``<slug>-<short_id>.md`` を返す。

title はユーザーが Obsidian 上で H1 を書き換えても**ファイル名の同一性は ``short_id``
（＝ストアの正本 id 由来）で保たれる**。真の同一性は frontmatter の ``pantheon_id``。
"""

from __future__ import annotations

import hashlib
import re

# Windows で禁止される文字（<>:"/\|?*）と制御文字を除去する。CJK 等の Unicode 文字は
# 近代 FS / Obsidian がそのまま扱えるので保持する（日本語 title をそのまま読めるようにする）。
_FORBIDDEN = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')
# 空白・ハイフン・アンダースコア・ドット連続を 1 本のハイフンへ畳み込む。
_SEPARATORS = re.compile(r"[\s\-_.]+")
_ID_ALNUM = re.compile(r"[^A-Za-z0-9]")


def human_slug(text: str, *, max_len: int = 60) -> str:
    """``text`` を安定したファイル名 slug に変換する。

    禁止文字を除去し、区切りを ``-`` に畳み込む。Unicode（日本語等）は保持する。
    空になる入力（全部禁止文字等）には ``"note"`` を返す（空ファイル名を作らない）。
    """
    raw = (text or "").strip()
    cleaned = _FORBIDDEN.sub("", raw)
    slug = _SEPARATORS.sub("-", cleaned).strip("-. ")
    if len(slug) > max_len:
        slug = slug[:max_len].rstrip("-. ")
    # 先頭ドットは隠しファイル化を招くので除去（strip 済みだが念のため）。
    slug = slug.lstrip(".")
    return slug or "note"


def short_id(entry_id: str, *, length: int = 8) -> str:
    """``entry_id`` から決定論的な短縮 id を作る。

    英数字が ``length`` 文字以上あれば末尾をそのまま使う（uuid の末尾は十分に一意）。
    そうでなければ id 全体の sha256 先頭を使う（記号のみ等の退化 id でも衝突を避ける）。
    """
    alnum = _ID_ALNUM.sub("", entry_id or "")
    if len(alnum) >= length:
        return alnum[-length:].lower()
    digest = hashlib.sha256((entry_id or "").encode("utf-8")).hexdigest()
    return digest[:length]


def note_filename(title: str, entry_id: str, *, max_len: int = 60) -> str:
    """``<human_slug(title)>-<short_id(entry_id)>.md`` を返す（決定論的・衝突安全）。"""
    return f"{human_slug(title, max_len=max_len)}-{short_id(entry_id)}.md"
