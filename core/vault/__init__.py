"""Pantheon Vault — Obsidian 互換のナレッジ Vault 基盤。

``~/.pantheon/vault/`` をディスク上の本物の Obsidian Vault（Markdown + YAML frontmatter +
``[[wikilink]]`` + バックリンク）として実体化し、Pantheon の各ナレッジストアと同期する。

公開 API:
- ``get_vault_dir(platform_home=None)`` — Vault ルート（``<platform_home>/vault``）を返す。
- ``build_default_adapters(platform_home=None)`` — 既定アダプタ群（Phase 1: insight/playbook/outcome）。
- ``build_default_sync(platform_home=None)`` — 既定アダプタを積んだ ``VaultSync``。
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from core.vault.format import (
    VaultNote,
    WikiLink,
    body_hash,
    emit_wikilink,
    meta_hash,
    parse_note,
    parse_wikilinks,
    render_note,
)
from core.vault.links import LinkIndex, NoteRef, backlinks_for, build_link_index
from core.vault.slug import human_slug, note_filename, short_id
from core.vault.stores import (
    ImportResult,
    KnowledgeAdapter,
    OutcomeAdapter,
    PlaybookAdapter,
    StoreEntry,
    VaultStoreAdapter,
)
from core.vault.sync import ExportStats, VaultSync

__all__ = [
    "VaultNote",
    "WikiLink",
    "body_hash",
    "emit_wikilink",
    "meta_hash",
    "parse_note",
    "parse_wikilinks",
    "render_note",
    "LinkIndex",
    "NoteRef",
    "backlinks_for",
    "build_link_index",
    "human_slug",
    "note_filename",
    "short_id",
    "ImportResult",
    "KnowledgeAdapter",
    "OutcomeAdapter",
    "PlaybookAdapter",
    "StoreEntry",
    "VaultStoreAdapter",
    "ExportStats",
    "VaultSync",
    "get_vault_dir",
    "build_default_adapters",
    "build_default_sync",
]


def _resolve_home(platform_home: Optional[Path | str]) -> Path:
    if platform_home is not None:
        return Path(platform_home)
    from core.platform.state import get_platform_home

    return get_platform_home()


def get_vault_dir(platform_home: Optional[Path | str] = None) -> Path:
    """Vault ルートディレクトリ（``<platform_home>/vault``）を返す。"""
    return _resolve_home(platform_home) / "vault"


def build_default_adapters(
    platform_home: Optional[Path | str] = None,
) -> List[VaultStoreAdapter]:
    """Phase 1 の既定アダプタ群を構築する（insight / playbook / outcome）。"""
    home = _resolve_home(platform_home)
    return [
        KnowledgeAdapter(home),
        PlaybookAdapter(home),
        OutcomeAdapter(home),
    ]


def build_default_sync(platform_home: Optional[Path | str] = None) -> VaultSync:
    """既定アダプタを積んだ ``VaultSync`` を返す。"""
    home = _resolve_home(platform_home)
    return VaultSync(get_vault_dir(home), build_default_adapters(home))
