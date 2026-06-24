"""Vault ⇆ 各ナレッジストアの橋渡しアダプタ。

``VaultStoreAdapter`` プロトコルが各ストアの bespoke API を隠蔽し、``VaultSync`` エンジンは
登録アダプタを回すだけ（ストアを増やす＝アダプタを 1 つ足すだけでエンジンは無改修）。

正本（canonical）の方針:
- ``vault`` 正本（insight / playbook …）= 人間が Obsidian で自由に編集でき、import で書き戻す
  （Phase 2）。Phase 1 は export のみ。
- ``json`` 正本（outcome …）= 型付き JSON が実行時の正本。Vault は**読み取り専用ミラー**で、
  編集は適用しない（``apply_import`` が reject）。OutcomeStore は収益インテグリティ上、
  確定収益（記録済みイベント）のみを表示する窓であり、ここからの偽造を許さない。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Protocol, runtime_checkable

from core.persistence import coerce_float, coerce_int
from core.vault.format import WikiLink


@dataclass
class StoreEntry:
    """1 ストアエントリを Vault ノートへ写すための中間表現。"""

    id: str
    fields: Dict[str, Any] = field(default_factory=dict)  # 型固有 frontmatter フィールド
    body: str = ""
    wikilinks: List[WikiLink] = field(default_factory=list)
    title: str = ""

    def __post_init__(self) -> None:
        if not self.title:
            self.title = str(self.fields.get("title") or self.id)


@dataclass
class ImportResult:
    """vault→store の書き戻し結果。"""

    status: str  # "accepted" | "rejected" | "unchanged"
    reason: str = ""


@runtime_checkable
class VaultStoreAdapter(Protocol):
    key: str
    pantheon_type: str
    canonical: str  # "vault" | "json"
    subdir: str

    def iter_entries(self) -> Iterable[StoreEntry]: ...

    def apply_import(
        self, entry_id: str, frontmatter: Dict[str, Any], body: str
    ) -> ImportResult: ...


class _BaseAdapter:
    """共通実装。既定の ``apply_import`` は Phase 2 まで未配線（正直に reject）。"""

    key: str = ""
    pantheon_type: str = ""
    canonical: str = "vault"
    subdir: str = ""

    def iter_entries(self) -> Iterable[StoreEntry]:  # pragma: no cover - 抽象
        raise NotImplementedError

    def apply_import(self, entry_id: str, frontmatter: Dict[str, Any], body: str) -> ImportResult:
        # Phase 1 は export のみ。書き戻し（import）は Phase 2 で配線する。
        return ImportResult("rejected", "import は Phase 2 で配線予定（未実装）")


class KnowledgeAdapter(_BaseAdapter):
    """KnowledgeManager の insight を ``insights/`` へ写す（vault 正本）。"""

    key = "knowledge"
    pantheon_type = "insight"
    canonical = "vault"
    subdir = "insights"

    def __init__(self, platform_home: Path | str):
        from core.knowledge.manager import KnowledgeManager

        # platform 共有 insight は KnowledgeManager(get_platform_home()) 経由で保存される。
        self._km = KnowledgeManager(platform_home)

    def iter_entries(self) -> Iterable[StoreEntry]:
        # archived も含めて全件ミラーする（知識は消さず archived フラグで表す）。
        for rec in self._km.get_insights(limit=1_000_000):
            entry_id = str(rec.get("id") or "")
            if not entry_id:
                continue
            title = str(rec.get("title") or "")
            fields: Dict[str, Any] = {
                "title": title,
                "tags": list(rec.get("tags") or []),
                "source_org": str(rec.get("source_org") or ""),
                "importance": str(rec.get("importance") or "medium"),
                "usage_count": coerce_int(rec.get("usage_count"), 0),
                "quality_score": coerce_float(rec.get("quality_score"), 0.0),
                "archived": bool(rec.get("archived") is True),
                "created_at": str(rec.get("created_at") or ""),
            }
            links: List[WikiLink] = []
            source_org = fields["source_org"]
            if source_org:
                links.append(WikiLink(type="org", target=source_org))
            yield StoreEntry(
                id=entry_id,
                fields=fields,
                body=str(rec.get("content") or ""),
                wikilinks=links,
                title=title,
            )


class PlaybookAdapter(_BaseAdapter):
    """PlaybookStore の施策ノートを ``playbooks/`` へ写す（vault 正本）。"""

    key = "playbook"
    pantheon_type = "playbook"
    canonical = "vault"
    subdir = "playbooks"

    def __init__(self, platform_home: Path | str):
        from core.intelligence.playbook import PlaybookStore

        self._store = PlaybookStore(platform_home)

    def iter_entries(self) -> Iterable[StoreEntry]:
        for entry in self._store.list_entries():
            fields: Dict[str, Any] = {
                "title": entry.title,
                "category": entry.category,
                "usefulness_score": float(entry.usefulness_score),
                "usage_count": int(entry.usage_count),
                "org_name": entry.org_name,
                "created_at": entry.created_at,
                "updated_at": entry.updated_at,
            }
            links: List[WikiLink] = []
            if entry.org_name:
                links.append(WikiLink(type="org", target=entry.org_name))
            yield StoreEntry(
                id=str(entry.entry_id),
                fields=fields,
                body=str(entry.content or ""),
                wikilinks=links,
                title=entry.title,
            )


# 収益インテグリティ: ここは「確定収益（記録済みイベントの合計）」の表示専用。
# このノートを編集しても記録収益は変わらない（import はハード reject）。
_OUTCOME_READONLY_CALLOUT = (
    "> [!warning] 読み取り専用ミラー\n"
    "> これは **確定収益（記録済み OutcomeStore イベントの合計）** を表示する窓です。\n"
    "> このノートを編集しても記録された収益・成果は一切変わりません"
    "（収益インテグリティ: 偽造禁止）。"
)


class OutcomeAdapter(_BaseAdapter):
    """OutcomeStore の成果を org 単位で ``outcomes/`` へ写す（json 正本＝読み取り専用ミラー）。"""

    key = "outcome"
    pantheon_type = "outcome"
    canonical = "json"
    subdir = "outcomes"

    def __init__(self, platform_home: Path | str):
        from core.metrics.outcomes import OutcomeStore

        self._store = OutcomeStore(platform_home)

    def iter_entries(self) -> Iterable[StoreEntry]:
        events = self._store.list_events()
        org_names = sorted({event.org_name for event in events})
        for org in org_names:
            summary = self._store.summary_for_org(org)
            body_lines = [
                _OUTCOME_READONLY_CALLOUT,
                "",
                f"## 成果サマリ — {org}",
                "",
                f"- 記録イベント数: **{summary.event_count}**",
                f"- 確定収益（revenue 系合計）: **{summary.total_revenue:g}**",
                f"- リーチ（reach 系合計）: **{summary.total_reach:g}**",
                "",
                "### メトリクス別内訳",
                "",
                "| metric | sum | count | last |",
                "| --- | ---: | ---: | ---: |",
            ]
            for metric in sorted(summary.by_metric):
                stats = summary.by_metric[metric]
                body_lines.append(
                    f"| {metric} | {stats.get('sum', 0.0):g} | "
                    f"{int(stats.get('count', 0))} | {stats.get('last', 0.0):g} |"
                )
            fields: Dict[str, Any] = {
                "title": f"成果: {org}",
                "org_name": org,
                "event_count": int(summary.event_count),
                "total_revenue": float(summary.total_revenue),
                "total_reach": float(summary.total_reach),
            }
            yield StoreEntry(
                id=f"outcome:{org}",
                fields=fields,
                body="\n".join(body_lines),
                wikilinks=[WikiLink(type="org", target=org)],
                title=fields["title"],
            )

    def apply_import(self, entry_id: str, frontmatter: Dict[str, Any], body: str) -> ImportResult:
        # 収益インテグリティ: 読み取り専用ミラー。Vault 側の編集は決して記録収益へ反映しない。
        return ImportResult("rejected", "読み取り専用ミラー（収益インテグリティ・偽造禁止）")
