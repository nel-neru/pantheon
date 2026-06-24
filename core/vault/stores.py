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
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterable, List, Protocol, runtime_checkable

from core.persistence import coerce_float, coerce_int
from core.vault.format import WikiLink, split_user_content


def _scalar(value: Any) -> Any:
    """frontmatter 用に YAML 安全な素のスカラへ coerce（None→""・datetime/UUID/enum→str）。

    重要: ``OrganizationStatus`` 等は ``str`` の**サブクラス Enum** なので、Enum を最優先で
    判定して ``.value`` の素の値に落とす（str 判定を先に通すと str サブクラス実体のまま渡り、
    YAML SafeDumper が ``cannot represent an object`` で落ちる）。
    """
    if value is None:
        return ""
    if isinstance(value, Enum):
        inner = value.value
        return inner if isinstance(inner, (str, int, float, bool)) else str(inner)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        return str(value)  # str サブクラス（enum 等）は素の str に正規化する
    return str(value)


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
    # ユーザーが Vault 上で編集可能な frontmatter フィールド（owned_hash 算出・書き戻し対象）。
    # 本文(content)は常に owned。json 正本ミラーは空（編集を取り込まない）。
    editable_keys: tuple[str, ...]

    def iter_entries(self) -> Iterable[StoreEntry]: ...

    def apply_import(
        self, entry_id: str, frontmatter: Dict[str, Any], body: str
    ) -> ImportResult: ...


class _BaseAdapter:
    """共通実装。既定の ``apply_import`` は read-only ミラー（reject）。"""

    key: str = ""
    pantheon_type: str = ""
    canonical: str = "vault"
    subdir: str = ""
    editable_keys: tuple[str, ...] = ()

    def iter_entries(self) -> Iterable[StoreEntry]:  # pragma: no cover - 抽象
        raise NotImplementedError

    def apply_import(self, entry_id: str, frontmatter: Dict[str, Any], body: str) -> ImportResult:
        # 既定は書き戻し未対応（読み取り専用ミラー）。vault 正本アダプタが override する。
        return ImportResult("rejected", "このストアは読み取り専用ミラー（書き戻し未対応）")


class KnowledgeAdapter(_BaseAdapter):
    """KnowledgeManager の insight を ``insights/`` へ写す（vault 正本）。"""

    key = "knowledge"
    pantheon_type = "insight"
    canonical = "vault"
    subdir = "insights"
    editable_keys = ("title", "tags", "importance")

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

    def apply_import(self, entry_id: str, frontmatter: Dict[str, Any], body: str) -> ImportResult:
        tags = frontmatter.get("tags")
        ok = self._km.update_insight(
            entry_id,
            title=str(frontmatter.get("title") or ""),
            content=split_user_content(body),
            tags=list(tags) if isinstance(tags, list) else None,
            importance=str(frontmatter.get("importance") or "medium"),
        )
        if ok:
            return ImportResult("accepted")
        return ImportResult("rejected", "ストアに該当 insight がありません")


class PlaybookAdapter(_BaseAdapter):
    """PlaybookStore の施策ノートを ``playbooks/`` へ写す（vault 正本）。"""

    key = "playbook"
    pantheon_type = "playbook"
    canonical = "vault"
    subdir = "playbooks"
    editable_keys = ("title", "category")

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

    def apply_import(self, entry_id: str, frontmatter: Dict[str, Any], body: str) -> ImportResult:
        updated = self._store.update(
            entry_id,
            title=str(frontmatter.get("title") or ""),
            content=split_user_content(body),
            category=str(frontmatter.get("category") or "general"),
        )
        if updated is not None:
            return ImportResult("accepted")
        return ImportResult("rejected", "ストアに該当 playbook がありません")


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


# ──────────────────────────────────────────────────────────────────────────────
# Phase 3: 残ストアの読み取り専用ミラー（json 正本・apply_import は既定で reject）。
# Vault を「全ナレッジの俯瞰・グラフ空間」にする。編集の書き戻しは未対応（正直にミラー）。
# ──────────────────────────────────────────────────────────────────────────────


class PatternAdapter(_BaseAdapter):
    """PatternLibrary（実装パターン）を ``patterns/`` へ写す（読み取り専用ミラー）。"""

    key = "pattern"
    pantheon_type = "pattern"
    canonical = "json"
    subdir = "patterns"

    def __init__(self, platform_home: Path | str):
        from core.intelligence.pattern_library import PatternLibrary

        self._lib = PatternLibrary(platform_home)

    def iter_entries(self) -> Iterable[StoreEntry]:
        for pattern in self._lib.search_patterns(""):  # 空クエリ＝全件
            body = (pattern.description or "").rstrip()
            if pattern.code_snippet:
                body = f"{body}\n\n```python\n{pattern.code_snippet}\n```"
            fields: Dict[str, Any] = {
                "title": pattern.name,
                "tags": list(pattern.tags or []),
                "use_count": coerce_int(pattern.use_count, 0),
                "created_at": _scalar(pattern.created_at),
            }
            yield StoreEntry(
                id=str(pattern.pattern_id), fields=fields, body=body, title=pattern.name
            )


class AgentPatternAdapter(_BaseAdapter):
    """AgentKnowledgeAccumulator の成功パターンを ``agent-patterns/`` へ写す（読み取り専用）。"""

    key = "agent_pattern"
    pantheon_type = "agent_pattern"
    canonical = "json"
    subdir = "agent-patterns"

    def __init__(self, platform_home: Path | str):
        from core.intelligence.agent_knowledge import AgentKnowledgeAccumulator

        self._acc = AgentKnowledgeAccumulator(platform_home=platform_home)

    def iter_entries(self) -> Iterable[StoreEntry]:
        for sp in self._acc.list_patterns():
            title = f"[{sp.agent_id}] {sp.task_type}"
            fields: Dict[str, Any] = {
                "title": title,
                "agent_id": sp.agent_id,
                "skill_name": sp.skill_name,
                "task_type": sp.task_type,
                "success_score": coerce_float(sp.success_score, 0.0),
                "created_at": _scalar(sp.created_at),
            }
            links = [WikiLink(type="org", target=sp.agent_id)] if sp.agent_id else []
            yield StoreEntry(
                id=str(sp.pattern_id),
                fields=fields,
                body=str(sp.pattern_summary or ""),
                wikilinks=links,
                title=title,
            )


class FailurePatternAdapter(_BaseAdapter):
    """FailurePatternRegistry を ``failure-patterns/`` へ写す（読み取り専用ミラー）。"""

    key = "failure_pattern"
    pantheon_type = "failure_pattern"
    canonical = "json"
    subdir = "failure-patterns"

    def __init__(self, platform_home: Path | str):
        from core.knowledge.failure_patterns import FailurePatternRegistry

        self._reg = FailurePatternRegistry(platform_home)

    def iter_entries(self) -> Iterable[StoreEntry]:
        for fp in self._reg.get_patterns(limit=1_000_000):
            title = f"{fp.category}: {fp.file_pattern}"
            fields: Dict[str, Any] = {
                "title": title,
                "category": fp.category,
                "file_pattern": fp.file_pattern,
                "occurrence_count": coerce_int(fp.occurrence_count, 0),
                "first_seen": _scalar(fp.first_seen),
                "last_seen": _scalar(fp.last_seen),
            }
            yield StoreEntry(
                id=str(fp.pattern_id), fields=fields, body=str(fp.reason or ""), title=title
            )


class CapabilityAdapter(_BaseAdapter):
    """CapabilityRegistry を ``capabilities/`` へ写す（読み取り専用ミラー）。"""

    key = "capability"
    pantheon_type = "capability"
    canonical = "json"
    subdir = "capabilities"

    def __init__(self, platform_home: Path | str):
        from core.intelligence.capability_registry import CapabilityRegistry

        self._reg = CapabilityRegistry(platform_home=platform_home)

    def iter_entries(self) -> Iterable[StoreEntry]:
        for cap in self._reg.list_all():
            fields: Dict[str, Any] = {
                "title": cap.name,
                "capability_type": cap.capability_type,
                "source_file": cap.source_file,
                "skills": list(cap.skills or []),
                "usage_count": coerce_int(cap.usage_count, 0),
                "last_used": _scalar(cap.last_used),
                "is_active": bool(cap.is_active),
                "added_at": _scalar(cap.added_at),
            }
            yield StoreEntry(
                id=str(cap.id), fields=fields, body=str(cap.description or ""), title=cap.name
            )


class OrgAdapter(_BaseAdapter):
    """Organization を ``orgs/`` へ写す（読み取り専用ミラー＝リンクハブ）。

    ``[[org:<name>]]`` を解決させるため pantheon_id に **org 名**を使う（insight/playbook/handoff の
    リンクと一致）。組織構造の変更は専用フロー経由なので Vault からは編集しない。
    """

    key = "org"
    pantheon_type = "org"
    canonical = "json"
    subdir = "orgs"

    def __init__(self, platform_home: Path | str):
        from core.platform.state import PlatformStateManager

        self._psm = PlatformStateManager(platform_home)

    def iter_entries(self) -> Iterable[StoreEntry]:
        for org in self._psm.load_organizations():
            try:
                loc = org.data_location
            except Exception:
                loc = None
            div_count = len(getattr(org, "divisions", []) or [])
            body_lines = [
                str(getattr(org, "purpose", "") or "").rstrip(),
                "",
                "## 構成",
                "",
                f"- Division 数: {div_count}",
            ]
            if loc:
                body_lines.append(f"- データ位置: `{loc}`")
            fields: Dict[str, Any] = {
                "title": org.name,
                "status": _scalar(getattr(org, "status", "")),
                "management_mode": _scalar(getattr(org, "management_mode", "")),
                "industry_genre": _scalar(getattr(org, "industry_genre", "")),
                "autonomy_score": coerce_float(getattr(org, "autonomy_score", 0.0), 0.0),
                "improvement_velocity": coerce_float(
                    getattr(org, "improvement_velocity", 0.0), 0.0
                ),
                "created_at": _scalar(getattr(org, "created_at", "")),
                "data_location": _scalar(loc),
            }
            yield StoreEntry(id=org.name, fields=fields, body="\n".join(body_lines), title=org.name)


class HandoffAdapter(_BaseAdapter):
    """OrgHandoff（org 間引き渡し）を ``handoffs/`` へ写す（読み取り専用ミラー）。"""

    key = "handoff"
    pantheon_type = "handoff"
    canonical = "json"
    subdir = "handoffs"

    def __init__(self, platform_home: Path | str):
        from core.hierarchy.org_handoff import OrgHandoffStore

        self._store = OrgHandoffStore(platform_home)

    def iter_entries(self) -> Iterable[StoreEntry]:
        for ho in self._store.list_handoffs():
            title = ho.title or f"{ho.source_org}→{ho.target_org}"
            body_lines = [
                str(ho.note or "").rstrip(),
                "",
                f"- 種別: {ho.kind}",
                f"- 状態: {ho.status}",
            ]
            if ho.payload:
                keys = ", ".join(str(k) for k in ho.payload.keys())
                body_lines.append(f"- payload キー: {keys}")
            fields: Dict[str, Any] = {
                "title": title,
                "source_org": ho.source_org,
                "target_org": ho.target_org,
                "kind": ho.kind,
                "status": ho.status,
                "priority": ho.priority,
                "created_at": _scalar(ho.created_at),
            }
            links: List[WikiLink] = []
            if ho.source_org:
                links.append(WikiLink(type="org", target=ho.source_org))
            if ho.target_org:
                links.append(WikiLink(type="org", target=ho.target_org))
            yield StoreEntry(
                id=str(ho.handoff_id or f"handoff:{ho.source_org}-{ho.target_org}"),
                fields=fields,
                body="\n".join(body_lines),
                wikilinks=links,
                title=title,
            )


class ProposalAdapter(_BaseAdapter):
    """RepoStateManager の改善提案を ``repos/<org>/proposals/`` へ写す（読み取り専用ミラー）。

    status は analyze→approve→apply のステートマシン（真値は JSON）。Vault からは編集しない。
    """

    key = "proposal"
    pantheon_type = "proposal"
    canonical = "json"

    def __init__(self, repo_state_manager: Any, org_slug: str):
        self._rsm = repo_state_manager
        self.subdir = f"repos/{org_slug}/proposals"

    def iter_entries(self) -> Iterable[StoreEntry]:
        for prop in self._rsm.get_all_improvement_proposals(limit=1_000_000):
            pid = str(prop.get("id") or "")
            if not pid:
                continue
            title = str(prop.get("title") or "")
            body = str(prop.get("description") or "").rstrip()
            code = prop.get("generated_code") or prop.get("code_preview")
            if code:
                body = f"{body}\n\n```\n{code}\n```"
            fields: Dict[str, Any] = {
                "title": title,
                "status": _scalar(prop.get("status")),
                "priority": _scalar(prop.get("priority")),
                "category": _scalar(prop.get("category")),
                "file_path": str(prop.get("file_path") or ""),
                "created_at": _scalar(prop.get("created_at")),
            }
            links = (
                [WikiLink(type="file", target=str(prop["file_path"]))]
                if prop.get("file_path")
                else []
            )
            yield StoreEntry(id=pid, fields=fields, body=body, wikilinks=links, title=title)


class DecisionAdapter(_BaseAdapter):
    """RepoStateManager の意思決定記録を ``repos/<org>/decisions/`` へ写す（読み取り専用ミラー）。"""

    key = "decision"
    pantheon_type = "decision"
    canonical = "json"

    def __init__(self, repo_state_manager: Any, org_slug: str):
        self._rsm = repo_state_manager
        self.subdir = f"repos/{org_slug}/decisions"

    def iter_entries(self) -> Iterable[StoreEntry]:
        for dec in self._rsm.get_recent_decisions(limit=1_000_000):
            did = str(dec.get("id") or "")
            if not did:
                continue
            title = str(dec.get("title") or "")
            fields: Dict[str, Any] = {
                "title": title,
                "made_by": str(dec.get("made_by") or ""),
                "tags": list(dec.get("tags") or []),
                "timestamp": _scalar(dec.get("timestamp")),
            }
            yield StoreEntry(id=did, fields=fields, body=str(dec.get("content") or ""), title=title)
