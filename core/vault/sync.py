"""VaultSync — ストア ⇆ Vault の同期エンジン（Phase 1: export + status + doctor）。

Phase 1 は **export 専用**（store→vault）。各エントリを ``.md`` 化し、既存ファイルの
保存済みハッシュと比較して**内容が変わった時だけ** ``atomic_write_text`` で書き直す
（＝冪等: 変更が無ければ 2 回目の export は 0 バイト書き込み）。

import（vault→store）・競合解決（``.conflict.md``）は Phase 2 で配線する。本モジュールには
まだ実装しない（未実装を実装済みに見せない）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Sequence

from core.persistence import atomic_write_text
from core.vault.format import body_hash, emit_wikilink, meta_hash, parse_note, render_note
from core.vault.slug import note_filename
from core.vault.stores import StoreEntry, VaultStoreAdapter

_VALID_TYPES = {
    "insight",
    "playbook",
    "pattern",
    "agent_pattern",
    "failure_pattern",
    "capability",
    "org",
    "handoff",
    "outcome",
    "proposal",
    "decision",
    "review",
}

_PANTHEON_README = "_pantheon.md"


@dataclass
class ExportStats:
    written: int = 0
    skipped: int = 0
    by_type: Dict[str, int] = field(default_factory=dict)
    paths: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "written": self.written,
            "skipped": self.skipped,
            "by_type": dict(self.by_type),
            "paths": list(self.paths),
        }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class VaultSync:
    """登録アダプタ群を Vault ディレクトリへ同期する。"""

    def __init__(
        self,
        vault_dir: Path | str,
        adapters: Sequence[VaultStoreAdapter],
        *,
        now_iso: Callable[[], str] | None = None,
    ):
        self.vault_dir = Path(vault_dir)
        self.adapters: List[VaultStoreAdapter] = list(adapters)
        self._now_iso = now_iso or _now_iso

    # ---- export ----

    def export(self, *, dry_run: bool = False) -> ExportStats:
        """全アダプタのエントリを Vault へ書き出す（差分時のみ書き込み・冪等）。"""
        stats = ExportStats()
        if not dry_run:
            self.vault_dir.mkdir(parents=True, exist_ok=True)
            self._ensure_readme()
        for adapter in self.adapters:
            subdir = self.vault_dir / adapter.subdir
            for entry in adapter.iter_entries():
                self._export_entry(adapter, entry, subdir, stats, dry_run=dry_run)
        return stats

    def _compose_body(self, entry: StoreEntry) -> str:
        body = (entry.body or "").rstrip()
        if entry.wikilinks:
            lines = [body, "", "## Related", ""]
            seen: set[tuple[str, str]] = set()
            for link in entry.wikilinks:
                key = (link.type, link.target)
                if key in seen:
                    continue
                seen.add(key)
                lines.append(f"- {emit_wikilink(link.type, link.target, link.alias)}")
            body = "\n".join(lines)
        return body

    def _export_entry(
        self,
        adapter: VaultStoreAdapter,
        entry: StoreEntry,
        subdir: Path,
        stats: ExportStats,
        *,
        dry_run: bool,
    ) -> None:
        body = self._compose_body(entry)
        fm_core: Dict[str, Any] = {
            "pantheon_id": entry.id,
            "pantheon_type": adapter.pantheon_type,
            "pantheon_canonical": adapter.canonical,
            "pantheon_store": adapter.key,
        }
        fm_core.update(entry.fields)
        new_body_hash = body_hash(body)
        new_meta_hash = meta_hash(fm_core)

        path = subdir / note_filename(entry.title, entry.id)
        if path.exists():
            existing = parse_note(path.read_text(encoding="utf-8"))
            if (
                existing.frontmatter.get("pantheon_body_hash") == new_body_hash
                and existing.frontmatter.get("pantheon_meta_hash") == new_meta_hash
            ):
                stats.skipped += 1
                return

        if dry_run:
            stats.written += 1
            stats.by_type[adapter.pantheon_type] = stats.by_type.get(adapter.pantheon_type, 0) + 1
            stats.paths.append(path.relative_to(self.vault_dir).as_posix())
            return

        frontmatter = dict(fm_core)
        frontmatter["pantheon_synced_at"] = self._now_iso()
        frontmatter["pantheon_body_hash"] = new_body_hash
        frontmatter["pantheon_meta_hash"] = new_meta_hash
        atomic_write_text(path, render_note(frontmatter, body))
        stats.written += 1
        stats.by_type[adapter.pantheon_type] = stats.by_type.get(adapter.pantheon_type, 0) + 1
        stats.paths.append(path.relative_to(self.vault_dir).as_posix())

    def _ensure_readme(self) -> None:
        """Vault の運用ルール README を 1 度だけ書く（ユーザー編集を上書きしない）。"""
        readme = self.vault_dir / _PANTHEON_README
        if readme.exists():
            return
        lines = [
            "# Pantheon Vault",
            "",
            "このフォルダは Pantheon が管理する **Obsidian 互換ナレッジ Vault** です。",
            "本物の Obsidian アプリでこのフォルダを開くと、AI が蓄積した知見・施策・成果を",
            "`[[wikilink]]` / バックリンク / グラフで閲覧できます。",
            "",
            "## 正本（どちらの編集が勝つか）",
            "",
            "| 種別 | フォルダ | 正本 | 編集 |",
            "| --- | --- | --- | --- |",
            "| insight | `insights/` | vault | Obsidian で編集可（Phase 2 で書き戻し） |",
            "| playbook | `playbooks/` | vault | Obsidian で編集可（Phase 2 で書き戻し） |",
            "| outcome | `outcomes/` | json | **読み取り専用ミラー**（確定収益のみ・偽造禁止） |",
            "",
            "> Phase 1 は **export のみ**（AI が書き、あなたは読む）。Obsidian での編集の",
            "> 書き戻し（双方向同期）は Phase 2 で配線します。",
            "",
            "`pantheon_*` で始まる frontmatter は Pantheon の制御情報です（手編集しないでください）。",
        ]
        atomic_write_text(readme, "\n".join(lines) + "\n")

    # ---- status / doctor ----

    def status(self) -> Dict[str, Any]:
        """ストア件数・Vault 上のノート数・未反映（pending）件数を集計する（書き込みなし）。"""
        per_adapter: List[Dict[str, Any]] = []
        total_entries = 0
        total_pending = 0
        for adapter in self.adapters:
            entries = list(adapter.iter_entries())
            subdir = self.vault_dir / adapter.subdir
            on_disk = len(list(subdir.glob("*.md"))) if subdir.exists() else 0
            pending = 0
            for entry in entries:
                if self._needs_write(adapter, entry, subdir):
                    pending += 1
            per_adapter.append(
                {
                    "key": adapter.key,
                    "type": adapter.pantheon_type,
                    "canonical": adapter.canonical,
                    "subdir": adapter.subdir,
                    "store_entries": len(entries),
                    "on_disk": on_disk,
                    "pending_writes": pending,
                }
            )
            total_entries += len(entries)
            total_pending += pending
        return {
            "vault_dir": str(self.vault_dir),
            "exists": self.vault_dir.exists(),
            "total_entries": total_entries,
            "total_pending": total_pending,
            "adapters": per_adapter,
        }

    def _needs_write(self, adapter: VaultStoreAdapter, entry: StoreEntry, subdir: Path) -> bool:
        body = self._compose_body(entry)
        fm_core: Dict[str, Any] = {
            "pantheon_id": entry.id,
            "pantheon_type": adapter.pantheon_type,
            "pantheon_canonical": adapter.canonical,
            "pantheon_store": adapter.key,
        }
        fm_core.update(entry.fields)
        path = subdir / note_filename(entry.title, entry.id)
        if not path.exists():
            return True
        existing = parse_note(path.read_text(encoding="utf-8"))
        return not (
            existing.frontmatter.get("pantheon_body_hash") == body_hash(body)
            and existing.frontmatter.get("pantheon_meta_hash") == meta_hash(fm_core)
        )

    def doctor(self) -> Dict[str, Any]:
        """Vault 内の管理ノートの frontmatter を検証する（変更なし・読み取り専用）。"""
        issues: List[Dict[str, str]] = []
        checked = 0
        unmanaged = 0
        if self.vault_dir.exists():
            for path in sorted(self.vault_dir.rglob("*.md")):
                if not path.is_file():
                    continue
                rel = path.relative_to(self.vault_dir).as_posix()
                try:
                    note = parse_note(path.read_text(encoding="utf-8"))
                except OSError as exc:
                    issues.append({"path": rel, "problem": f"読み取り失敗: {exc}"})
                    continue
                fm = note.frontmatter
                pid = fm.get("pantheon_id")
                ptype = fm.get("pantheon_type")
                if not pid and not ptype:
                    # README / MOC / ユーザー自作ノートは管理対象外（エラーではない）。
                    unmanaged += 1
                    continue
                checked += 1
                if not pid:
                    issues.append({"path": rel, "problem": "pantheon_id がありません"})
                if not ptype:
                    issues.append({"path": rel, "problem": "pantheon_type がありません"})
                elif ptype not in _VALID_TYPES:
                    issues.append({"path": rel, "problem": f"未知の pantheon_type: {ptype}"})
                if fm.get("pantheon_canonical") not in ("vault", "json", None):
                    issues.append(
                        {
                            "path": rel,
                            "problem": f"不正な canonical: {fm.get('pantheon_canonical')}",
                        }
                    )
        return {
            "checked": checked,
            "unmanaged": unmanaged,
            "issues": issues,
            "ok": len(issues) == 0,
        }
