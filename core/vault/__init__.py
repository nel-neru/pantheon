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
    compose_related,
    emit_wikilink,
    meta_hash,
    owned_hash,
    parse_note,
    parse_wikilinks,
    render_note,
    split_user_content,
)
from core.vault.graph import build_vault_graph, to_dot
from core.vault.links import LinkIndex, NoteRef, backlinks_for, build_link_index
from core.vault.slug import human_slug, note_filename, short_id
from core.vault.stores import (
    AgentPatternAdapter,
    CapabilityAdapter,
    DecisionAdapter,
    FailurePatternAdapter,
    HandoffAdapter,
    ImportResult,
    KnowledgeAdapter,
    OrgAdapter,
    OutcomeAdapter,
    PatternAdapter,
    PlaybookAdapter,
    ProposalAdapter,
    StoreEntry,
    VaultStoreAdapter,
)
from core.vault.sync import ExportStats, ImportStats, VaultSync

__all__ = [
    "VaultNote",
    "WikiLink",
    "body_hash",
    "compose_related",
    "emit_wikilink",
    "meta_hash",
    "owned_hash",
    "parse_note",
    "parse_wikilinks",
    "render_note",
    "split_user_content",
    "LinkIndex",
    "NoteRef",
    "backlinks_for",
    "build_link_index",
    "build_vault_graph",
    "to_dot",
    "human_slug",
    "note_filename",
    "short_id",
    "ImportResult",
    "KnowledgeAdapter",
    "OutcomeAdapter",
    "PlaybookAdapter",
    "PatternAdapter",
    "AgentPatternAdapter",
    "FailurePatternAdapter",
    "CapabilityAdapter",
    "OrgAdapter",
    "HandoffAdapter",
    "ProposalAdapter",
    "DecisionAdapter",
    "StoreEntry",
    "VaultStoreAdapter",
    "ExportStats",
    "ImportStats",
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


def _repo_scoped_adapters(home: Path) -> List[VaultStoreAdapter]:
    """各 Organization の repo 内 state（提案・意思決定）を ``repos/<org>/`` に写すアダプタ群。

    data_location が実在する org のみ対象（存在しない repo へ ``.pantheon`` を作らない）。
    org 列挙や 1 org の不整合で Vault 全体を壊さないよう防御的に握りつぶす（収集できた分だけ返す）。
    """
    adapters: List[VaultStoreAdapter] = []
    try:
        from core.platform.state import PlatformStateManager

        psm = PlatformStateManager(home)
        organizations = psm.load_organizations()
    except Exception:
        return adapters
    for org in organizations:
        try:
            location = org.data_location
            if not location or not Path(location).exists():
                continue
            rsm = psm.get_org_state_manager(org)
            slug = f"{human_slug(org.name)}-{short_id(str(org.id))}"
            adapters.append(ProposalAdapter(rsm, slug))
            adapters.append(DecisionAdapter(rsm, slug))
        except Exception:
            continue
    return adapters


def build_default_adapters(
    platform_home: Optional[Path | str] = None,
) -> List[VaultStoreAdapter]:
    """既定アダプタ群を構築する。

    プラットフォーム全体の知識（insight/playbook=vault 正本、outcome/pattern/agent/failure/
    capability/org/handoff=読み取り専用ミラー）＋ 各 org の repo state（proposal/decision ミラー）。
    """
    home = _resolve_home(platform_home)
    adapters: List[VaultStoreAdapter] = [
        KnowledgeAdapter(home),
        PlaybookAdapter(home),
        OutcomeAdapter(home),
        PatternAdapter(home),
        AgentPatternAdapter(home),
        FailurePatternAdapter(home),
        CapabilityAdapter(home),
        OrgAdapter(home),
        HandoffAdapter(home),
    ]
    adapters.extend(_repo_scoped_adapters(home))
    return adapters


def build_default_sync(platform_home: Optional[Path | str] = None) -> VaultSync:
    """既定アダプタを積んだ ``VaultSync`` を返す。"""
    home = _resolve_home(platform_home)
    return VaultSync(get_vault_dir(home), build_default_adapters(home))
