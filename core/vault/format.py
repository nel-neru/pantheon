"""Vault ノートの Markdown フォーマット（frontmatter + body + wikilink）。

- ``parse_note`` / ``render_note``: YAML frontmatter と本文の相互変換。``render_note`` は
  **バイト決定論的**（既知キー順）にし「内容が変わらなければ再 export で 0 バイト書き込み」を
  保証する（[[atomic-write]] と対の冪等性）。parse は壊れた frontmatter にも寛容で例外を出さない。
- ``parse_wikilinks`` / ``emit_wikilink``: ``[[type:target|alias]]`` 記法の解析/生成。
  ``type`` が Vault サブフォルダに 1:1 対応するので解決が決定論的（title 改名に強い）。
- ``body_hash`` / ``meta_hash``: 競合検出・差分判定用のハッシュ（同期時の base 値）。

PyYAML（requirements.txt 既存）に依存。``yaml.safe_load`` / ``yaml.safe_dump`` のみ使う。
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List

import yaml

# frontmatter の制御キー（pantheon_ 名前空間でユーザー追加キーと衝突しない）。
PANTHEON_VOLATILE_KEYS = ("pantheon_synced_at", "pantheon_body_hash", "pantheon_meta_hash")
_CONTROL_ORDER = (
    "pantheon_id",
    "pantheon_type",
    "pantheon_canonical",
    "pantheon_store",
    "pantheon_repo",
    "pantheon_synced_at",
    "pantheon_body_hash",
    "pantheon_meta_hash",
)

_FRONTMATTER_RE = re.compile(r"^---\r?\n(.*?)\r?\n---\r?\n?(.*)$", re.DOTALL)
_WIKILINK_RE = re.compile(r"\[\[([^\[\]]+?)\]\]")


@dataclass
class WikiLink:
    """``[[type:target|alias]]`` 1 件。``type`` 空は素のタイトルリンク。"""

    type: str
    target: str
    alias: str = ""
    raw: str = ""
    resolved: bool = False

    @property
    def node_id(self) -> str:
        """グラフ/バックリンク照合用のノード id（``type:target`` 形）。"""
        return f"{self.type}:{self.target}" if self.type else self.target


@dataclass
class VaultNote:
    """1 つの Vault ノート（frontmatter + body）。"""

    frontmatter: Dict[str, Any] = field(default_factory=dict)
    body: str = ""

    @property
    def wikilinks(self) -> List[WikiLink]:
        return parse_wikilinks(self.body)


def parse_note(text: str) -> VaultNote:
    """Markdown テキストを frontmatter(dict) と body(str) に分解する（寛容・例外なし）。

    frontmatter が無い／YAML が壊れている／非 dict の場合は ``frontmatter={}`` で本文だけ返す
    （ユーザーが自由に書いたノートや破損ファイルでも読み手を壊さない）。
    """
    if text is None:
        return VaultNote()
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return VaultNote(frontmatter={}, body=text)
    raw_yaml, body = match.group(1), match.group(2)
    try:
        loaded = yaml.safe_load(raw_yaml)
    except yaml.YAMLError:
        loaded = None
    frontmatter = loaded if isinstance(loaded, dict) else {}
    return VaultNote(frontmatter=frontmatter, body=body)


def _ordered_frontmatter(frontmatter: Dict[str, Any]) -> Dict[str, Any]:
    """制御キーを既定順に、残りをアルファベット順に並べた dict を返す（決定論的出力）。"""
    ordered: Dict[str, Any] = {}
    for key in _CONTROL_ORDER:
        if key in frontmatter:
            ordered[key] = frontmatter[key]
    for key in sorted(frontmatter):
        if key not in ordered:
            ordered[key] = frontmatter[key]
    return ordered


def render_note(frontmatter: Dict[str, Any], body: str) -> str:
    """frontmatter(dict) と body(str) を 1 本の Markdown テキストへ決定論的に描画する。

    キー順を固定し ``sort_keys=False`` で dump するので、同じ入力は必ず同じバイト列になる。
    """
    ordered = _ordered_frontmatter(frontmatter or {})
    dumped = yaml.safe_dump(
        ordered,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
        width=10_000,
    )
    return f"---\n{dumped}---\n\n{(body or '').rstrip()}\n"


def parse_wikilinks(body: str) -> List[WikiLink]:
    """本文中の ``[[type:target|alias]]`` を順に解析して返す（重複もそのまま）。"""
    links: List[WikiLink] = []
    for match in _WIKILINK_RE.finditer(body or ""):
        inner = match.group(1).strip()
        alias = ""
        if "|" in inner:
            inner, alias = inner.split("|", 1)
            inner, alias = inner.strip(), alias.strip()
        if ":" in inner:
            ltype, target = inner.split(":", 1)
            ltype, target = ltype.strip(), target.strip()
        else:
            ltype, target = "", inner
        links.append(WikiLink(type=ltype, target=target, alias=alias, raw=match.group(0)))
    return links


def emit_wikilink(link_type: str, target: str, alias: str = "") -> str:
    """``[[type:target]]`` / ``[[type:target|alias]]`` を生成する（``type`` 空は素のリンク）。"""
    inner = f"{link_type}:{target}" if link_type else f"{target}"
    if alias:
        return f"[[{inner}|{alias}]]"
    return f"[[{inner}]]"


def _normalize_body(body: str) -> str:
    """ハッシュ用に本文を正規化する（改行統一・各行末空白除去・前後 strip）。"""
    text = (body or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in text.split("\n")]
    return "\n".join(lines).strip()


def body_hash(body: str) -> str:
    """正規化した本文の sha256（``sha256:...``）。export 差分判定・競合検出の base。"""
    digest = hashlib.sha256(_normalize_body(body).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def meta_hash(frontmatter: Dict[str, Any]) -> str:
    """managed メタの sha256（volatile 制御キーを除外した正準 JSON のハッシュ）。"""
    managed = {
        key: value
        for key, value in (frontmatter or {}).items()
        if key not in PANTHEON_VOLATILE_KEYS
    }
    canonical = json.dumps(managed, sort_keys=True, ensure_ascii=False, default=str)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"
