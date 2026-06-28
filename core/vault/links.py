"""Vault 全 .md を走査して wikilink の前方/後方（backlink）索引を構築する。

backlink は frontmatter に保存しない（書き込み増幅と競合チャーンを避ける）。読み取り時に
全ノートを 1 度走査して前方リンクを反転して算出する（Obsidian は同じ ``[[...]]`` から native に
backlink を描くので、この索引は Pantheon GUI / API 用）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

from core.vault.format import WikiLink, parse_note, parse_wikilinks


@dataclass
class NoteRef:
    """1 つの管理ノート（pantheon_* 制御ブロックを持つ）の参照情報。"""

    path: str  # vault ルートからの POSIX 相対パス
    node_id: str  # "type:id"
    title: str
    pantheon_type: str
    wikilinks: List[WikiLink] = field(default_factory=list)


@dataclass
class LinkIndex:
    notes: List[NoteRef] = field(default_factory=list)
    by_node: Dict[str, NoteRef] = field(default_factory=dict)  # node_id -> NoteRef
    by_path: Dict[str, NoteRef] = field(default_factory=dict)  # rel path -> NoteRef
    # node_id -> その node を指している（backlink 元）ノートの相対パス一覧
    backlinks: Dict[str, List[str]] = field(default_factory=dict)


def _iter_markdown(vault_dir: Path):
    if not vault_dir.exists():
        return
    for path in sorted(vault_dir.rglob("*.md")):
        if path.is_file():
            yield path


def build_link_index(vault_dir: Path | str) -> LinkIndex:
    """Vault 内の全管理ノートを走査し、node 索引と backlink 索引を構築する。"""
    vault_dir = Path(vault_dir)
    index = LinkIndex()

    # --- 第 1 パス: 管理ノートを列挙し node_id を確定する ---
    for path in _iter_markdown(vault_dir):
        try:
            note = parse_note(path.read_text(encoding="utf-8"))
        except OSError:
            continue
        fm = note.frontmatter
        pid = fm.get("pantheon_id")
        ptype = fm.get("pantheon_type")
        if not pid or not ptype:
            # 管理ブロックの無いノート（README/MOC/ユーザー自作）は索引対象外。
            continue
        rel = path.relative_to(vault_dir).as_posix()
        ref = NoteRef(
            path=rel,
            node_id=f"{ptype}:{pid}",
            title=str(fm.get("title") or path.stem),
            pantheon_type=str(ptype),
            wikilinks=parse_wikilinks(note.body),
        )
        index.notes.append(ref)
        index.by_node[ref.node_id] = ref
        index.by_path[rel] = ref

    # --- 第 2 パス: 前方リンクを反転して backlink を作る ---
    for ref in index.notes:
        for link in ref.wikilinks:
            target_node = link.node_id
            link.resolved = target_node in index.by_node
            index.backlinks.setdefault(target_node, [])
            if ref.path not in index.backlinks[target_node]:
                index.backlinks[target_node].append(ref.path)

    return index


def backlinks_for(index: LinkIndex, node_id: str) -> List[Dict[str, str]]:
    """``node_id`` を指すノート（backlink 元）を ``{path,title}`` のリストで返す。"""
    out: List[Dict[str, str]] = []
    for rel in index.backlinks.get(node_id, []):
        ref = index.by_path.get(rel)
        out.append({"path": rel, "title": ref.title if ref else rel})
    return out
