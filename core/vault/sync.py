"""VaultSync — ストア ⇆ Vault の双方向同期エンジン（Phase 2）。

- ``export``（store→vault）: 各エントリを ``.md`` 化し、保存済みハッシュと比較して**内容が
  変わった時だけ** ``atomic_write_text`` で書き直す（冪等）。ストアを正として書き出す一方向。
  ストア未変更なら既存ファイル（ユーザー編集を含む）は触らない。
- ``import_vault``（vault→store）: Obsidian で編集された ``.md`` を解析し、3-way 比較
  （base=frontmatter の owned_hash / 現 Vault / 現ストア）でユーザー編集を検出して書き戻す。
  両者が衝突したら ``<slug>.conflict.md`` サイドカーへ両版を保全し、元ノートは触らない。
- ``sync`` = import_vault → export（双方向 1 往復）。``edit_note`` = GUI からの単一ノート編集。

設計の肝: ``export`` はストア勝ち（バックアップ/初期化）、``sync`` はユーザー編集を先に取り込む。
**ユーザー編集もストアのデータも決して黙って失わない**（衝突は ``.conflict.md`` に保全して可視化）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from core.persistence import atomic_write_text
from core.vault.format import (
    body_hash,
    compose_related,
    meta_hash,
    owned_hash,
    parse_note,
    render_note,
    split_user_content,
)
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
    "conflict",
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


@dataclass
class ImportStats:
    imported: int = 0
    conflicts: int = 0
    rejected: int = 0
    orphan: int = 0
    skipped: int = 0
    conflict_paths: List[str] = field(default_factory=list)
    imported_paths: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "imported": self.imported,
            "conflicts": self.conflicts,
            "rejected": self.rejected,
            "orphan": self.orphan,
            "skipped": self.skipped,
            "conflict_paths": list(self.conflict_paths),
            "imported_paths": list(self.imported_paths),
        }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _editable_fields(adapter: VaultStoreAdapter, source: Dict[str, Any]) -> Dict[str, Any]:
    return {key: source.get(key) for key in getattr(adapter, "editable_keys", ())}


class VaultSync:
    """登録アダプタ群と Vault ディレクトリを同期する。"""

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

    # ---- 共通ヘルパ ----

    def _fm_core(self, adapter: VaultStoreAdapter, entry: StoreEntry) -> Dict[str, Any]:
        fm_core: Dict[str, Any] = {
            "pantheon_id": entry.id,
            "pantheon_type": adapter.pantheon_type,
            "pantheon_canonical": adapter.canonical,
            "pantheon_store": adapter.key,
        }
        fm_core.update(entry.fields)
        return fm_core

    def _compose(
        self, adapter: VaultStoreAdapter, entry: StoreEntry
    ) -> Tuple[str, Dict[str, Any], str, str, str]:
        """(body, fm_core, body_hash, meta_hash, owned_hash) を返す。"""
        body = compose_related(entry.body, entry.wikilinks)
        fm_core = self._fm_core(adapter, entry)
        new_body_hash = body_hash(body)
        new_meta_hash = meta_hash(fm_core)
        new_owned_hash = owned_hash(_editable_fields(adapter, entry.fields), entry.body)
        return body, fm_core, new_body_hash, new_meta_hash, new_owned_hash

    def _note_path(self, adapter: VaultStoreAdapter, entry: StoreEntry) -> Path:
        return self.vault_dir / adapter.subdir / note_filename(entry.title, entry.id)

    def _write_note(self, adapter: VaultStoreAdapter, entry: StoreEntry) -> Path:
        """エントリを Vault ノートとして（無条件に）書く。ストアの真値を反映する。"""
        body, fm_core, bh, mh, oh = self._compose(adapter, entry)
        frontmatter = dict(fm_core)
        frontmatter["pantheon_synced_at"] = self._now_iso()
        frontmatter["pantheon_body_hash"] = bh
        frontmatter["pantheon_meta_hash"] = mh
        frontmatter["pantheon_owned_hash"] = oh
        path = self._note_path(adapter, entry)
        atomic_write_text(path, render_note(frontmatter, body))
        return path

    def _conflict_path_for(self, note_path: Path) -> Path:
        return note_path.with_name(note_path.stem + ".conflict.md")

    # ---- export（store→vault・一方向） ----

    def export(self, *, dry_run: bool = False) -> ExportStats:
        """全アダプタのエントリを Vault へ書き出す（差分時のみ・冪等・ストア勝ち）。"""
        stats = ExportStats()
        if not dry_run:
            self.vault_dir.mkdir(parents=True, exist_ok=True)
            self._ensure_readme()
        for adapter in self.adapters:
            for entry in adapter.iter_entries():
                self._export_entry(adapter, entry, stats, dry_run=dry_run)
        return stats

    def _export_entry(
        self,
        adapter: VaultStoreAdapter,
        entry: StoreEntry,
        stats: ExportStats,
        *,
        dry_run: bool,
    ) -> None:
        body, fm_core, new_body_hash, new_meta_hash, _ = self._compose(adapter, entry)
        path = self._note_path(adapter, entry)

        if path.exists():
            existing = parse_note(path.read_text(encoding="utf-8"))
            # 未変更ならスキップ（ユーザー編集を含む既存ファイルを触らない＝非破壊）。
            if (
                existing.frontmatter.get("pantheon_body_hash") == new_body_hash
                and existing.frontmatter.get("pantheon_meta_hash") == new_meta_hash
            ):
                stats.skipped += 1
                return
            # vault 正本は競合解決中（.conflict.md 在中）なら上書きしない（両版を守る）。
            if adapter.canonical == "vault" and self._conflict_path_for(path).exists():
                stats.skipped += 1
                return

        if dry_run:
            stats.written += 1
            stats.by_type[adapter.pantheon_type] = stats.by_type.get(adapter.pantheon_type, 0) + 1
            stats.paths.append(path.relative_to(self.vault_dir).as_posix())
            return

        self._write_note(adapter, entry)
        stats.written += 1
        stats.by_type[adapter.pantheon_type] = stats.by_type.get(adapter.pantheon_type, 0) + 1
        stats.paths.append(path.relative_to(self.vault_dir).as_posix())

    # ---- import（vault→store・双方向の核） ----

    def import_vault(self) -> ImportStats:
        """Obsidian で編集されたノートをストアへ書き戻す（3-way 競合判定付き）。"""
        stats = ImportStats()
        self._stamp_owned_hashes()
        for adapter in self.adapters:
            subdir = self.vault_dir / adapter.subdir
            if not subdir.exists():
                continue
            store_index = {entry.id: entry for entry in adapter.iter_entries()}
            for path in sorted(subdir.glob("*.md")):
                if path.name.endswith(".conflict.md"):
                    continue
                self._import_file(adapter, path, store_index, stats)
        return stats

    def _stamp_owned_hashes(self) -> None:
        """owned_hash 未保有の管理ノートに、**ファイル内容から**算出した base を刻む（移行）。

        Phase 1 で書かれた owned_hash の無いノートに 3-way の base を与える。ファイル本文を
        regenerate せずそのまま保つので、既存のユーザー編集を base 化して取りこぼさない。
        """
        for adapter in self.adapters:
            subdir = self.vault_dir / adapter.subdir
            if not subdir.exists():
                continue
            for path in sorted(subdir.glob("*.md")):
                if path.name.endswith(".conflict.md"):
                    continue
                note = parse_note(path.read_text(encoding="utf-8"))
                fm = note.frontmatter
                if not fm.get("pantheon_id") or fm.get("pantheon_store") != adapter.key:
                    continue
                if fm.get("pantheon_owned_hash"):
                    continue
                content = split_user_content(note.body)
                new_fm = dict(fm)
                new_fm["pantheon_owned_hash"] = owned_hash(_editable_fields(adapter, fm), content)
                atomic_write_text(path, render_note(new_fm, note.body))

    def _import_file(
        self,
        adapter: VaultStoreAdapter,
        path: Path,
        store_index: Dict[str, StoreEntry],
        stats: ImportStats,
    ) -> None:
        note = parse_note(path.read_text(encoding="utf-8"))
        fm = note.frontmatter
        pid = fm.get("pantheon_id")
        if not pid or fm.get("pantheon_store") != adapter.key:
            return  # 非管理 / 別ストア
        base_owned = fm.get("pantheon_owned_hash")
        file_content = split_user_content(note.body)
        file_owned = owned_hash(_editable_fields(adapter, fm), file_content)
        store_entry = store_index.get(pid)

        # 競合解決中（.conflict.md 在中）は import を保留（ユーザーの解決待ち）。
        if self._conflict_path_for(path).exists():
            stats.skipped += 1
            return

        # json 正本（読み取り専用ミラー）: ユーザー編集は適用せず、両版を保全して真値を復元する。
        if adapter.canonical == "json":
            if base_owned is not None and file_owned != base_owned:
                self._write_conflict(
                    path, fm, note.body, store_entry, adapter, "読み取り専用ミラー"
                )
                if store_entry is not None:
                    self._write_note(adapter, store_entry)  # 真値を即時復元（上書き）
                stats.rejected += 1
                stats.conflict_paths.append(self._rel(self._conflict_path_for(path)))
            else:
                stats.skipped += 1
            return

        # vault 正本
        if store_entry is None:
            stats.orphan += 1  # ストアから消えた id。勝手に復活させない。
            return
        store_owned = owned_hash(_editable_fields(adapter, store_entry.fields), store_entry.body)
        user_changed = base_owned is not None and file_owned != base_owned
        store_changed = base_owned is not None and store_owned != base_owned

        if not user_changed:
            stats.skipped += 1
            return
        if not store_changed:
            self._apply_and_refresh(adapter, pid, fm, note.body, store_entry, stats)
            return
        if file_owned == store_owned:
            # 両者が同じ内容に収束 → 取り込み不要（export が hash を整える）。
            stats.skipped += 1
            return
        # 双方が別内容に分岐 → 競合。元ノートは触らず両版を保全して可視化する。
        self._write_conflict(
            path, fm, note.body, store_entry, adapter, "ユーザーとストアの両方が編集"
        )
        stats.conflicts += 1
        stats.conflict_paths.append(self._rel(self._conflict_path_for(path)))

    def _apply_and_refresh(
        self,
        adapter: VaultStoreAdapter,
        pid: str,
        fm: Dict[str, Any],
        body: str,
        store_entry: StoreEntry,
        stats: ImportStats,
    ) -> None:
        result = adapter.apply_import(pid, fm, body)
        if result.status == "accepted":
            stats.imported += 1
            stats.imported_paths.append(self._rel(self._note_path(adapter, store_entry)))
        else:
            stats.rejected += 1

    def _write_conflict(
        self,
        note_path: Path,
        file_fm: Dict[str, Any],
        file_body: str,
        store_entry: Optional[StoreEntry],
        adapter: VaultStoreAdapter,
        reason: str,
    ) -> None:
        conflict_path = self._conflict_path_for(note_path)
        if store_entry is not None:
            store_body = compose_related(store_entry.body, store_entry.wikilinks)
        else:
            store_body = "(ストアに対応するエントリがありません)"
        fm = {
            "pantheon_type": "conflict",
            "pantheon_conflict_for": note_path.name,
            "pantheon_resolves": file_fm.get("pantheon_id", ""),
            "pantheon_reason": reason,
        }
        lines = [
            f"# ⚠ コンフリクト: {file_fm.get('title', '')}",
            "",
            f"理由: **{reason}**。あなたの編集とストア(AI)側の内容が衝突しています。",
            "",
            "どちらかに内容を整え、**この `.conflict.md` を削除**してから再度 "
            "`pantheon vault sync` を実行してください。",
            "（この `.conflict.md` がある間、元ノートは上書きされず import も保留されます。）",
            "",
            "## あなたの版（Vault）",
            "",
            split_user_content(file_body),
            "",
            "## ストア（AI）の版",
            "",
            split_user_content(store_body),
        ]
        atomic_write_text(conflict_path, render_note(fm, "\n".join(lines)))

    def _rel(self, path: Path) -> str:
        return path.relative_to(self.vault_dir).as_posix()

    # ---- sync / 単一ノート編集 ----

    def sync(self) -> Dict[str, Any]:
        """双方向 1 往復（import → export）。"""
        self.vault_dir.mkdir(parents=True, exist_ok=True)
        imported = self.import_vault()
        exported = self.export()
        return {
            "import": imported.as_dict(),
            "export": exported.as_dict(),
            "conflicts": imported.conflicts + imported.rejected,
        }

    def edit_note(self, rel_path: str, content: str) -> Dict[str, Any]:
        """GUI からの単一ノート編集を書き戻す（vault 正本のみ・json はラベル付き reject）。"""
        path = self.vault_dir / rel_path
        if not path.exists() or not path.is_file():
            return {"status": "not_found"}
        note = parse_note(path.read_text(encoding="utf-8"))
        fm = note.frontmatter
        pid = fm.get("pantheon_id")
        store_key = fm.get("pantheon_store")
        adapter = next((a for a in self.adapters if a.key == store_key), None)
        if not pid or adapter is None:
            return {"status": "unmanaged"}
        if adapter.canonical != "vault":
            return {"status": "rejected", "reason": "読み取り専用ミラー（編集は反映されません）"}
        # content はユーザー本文。frontmatter を引き継いで apply_import→export で正本化する。
        merged_fm = dict(fm)
        result = adapter.apply_import(pid, merged_fm, content)
        if result.status != "accepted":
            return {"status": result.status, "reason": result.reason}
        self.export()
        return {"status": "accepted"}

    # ---- README ----

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
            "| insight | `insights/` | vault | Obsidian で編集可（`vault sync` で書き戻し） |",
            "| playbook | `playbooks/` | vault | Obsidian で編集可（`vault sync` で書き戻し） |",
            "| その他 | 各フォルダ | json | **読み取り専用ミラー**（編集は反映されません） |",
            "| outcome | `outcomes/` | json | 読み取り専用ミラー（確定収益のみ・偽造禁止） |",
            "",
            "> `pantheon vault sync` で双方向同期します（Obsidian の編集を取り込み→最新を書き出し）。",
            "> 編集が AI 側と衝突した場合は `<ノート名>.conflict.md` に両版を保全します"
            "（整えてその .conflict.md を削除→再 sync）。",
            "",
            "`pantheon_*` で始まる frontmatter は Pantheon の制御情報です（手編集しないでください）。",
        ]
        atomic_write_text(readme, "\n".join(lines) + "\n")

    # ---- status / doctor ----

    def _count_conflicts(self) -> List[str]:
        if not self.vault_dir.exists():
            return []
        return [self._rel(p) for p in sorted(self.vault_dir.rglob("*.conflict.md")) if p.is_file()]

    def status(self) -> Dict[str, Any]:
        """ストア件数・Vault 上のノート数・未反映（pending）件数・競合を集計する（書き込みなし）。"""
        per_adapter: List[Dict[str, Any]] = []
        total_entries = 0
        total_pending = 0
        for adapter in self.adapters:
            entries = list(adapter.iter_entries())
            subdir = self.vault_dir / adapter.subdir
            on_disk = (
                len([p for p in subdir.glob("*.md") if not p.name.endswith(".conflict.md")])
                if subdir.exists()
                else 0
            )
            pending = sum(1 for entry in entries if self._needs_write(adapter, entry))
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
        conflicts = self._count_conflicts()
        return {
            "vault_dir": str(self.vault_dir),
            "exists": self.vault_dir.exists(),
            "total_entries": total_entries,
            "total_pending": total_pending,
            "conflicts": conflicts,
            "conflict_count": len(conflicts),
            "adapters": per_adapter,
        }

    def _needs_write(self, adapter: VaultStoreAdapter, entry: StoreEntry) -> bool:
        _, _, new_body_hash, new_meta_hash, _ = self._compose(adapter, entry)
        path = self._note_path(adapter, entry)
        if not path.exists():
            return True
        existing = parse_note(path.read_text(encoding="utf-8"))
        return not (
            existing.frontmatter.get("pantheon_body_hash") == new_body_hash
            and existing.frontmatter.get("pantheon_meta_hash") == new_meta_hash
        )

    def doctor(self) -> Dict[str, Any]:
        """Vault 内の管理ノートの frontmatter を検証する（変更なし・読み取り専用）。"""
        issues: List[Dict[str, str]] = []
        checked = 0
        unmanaged = 0
        conflicts = 0
        if self.vault_dir.exists():
            for path in sorted(self.vault_dir.rglob("*.md")):
                if not path.is_file():
                    continue
                rel = self._rel(path)
                if path.name.endswith(".conflict.md"):
                    conflicts += 1
                    continue
                try:
                    note = parse_note(path.read_text(encoding="utf-8"))
                except OSError as exc:
                    issues.append({"path": rel, "problem": f"読み取り失敗: {exc}"})
                    continue
                fm = note.frontmatter
                pid = fm.get("pantheon_id")
                ptype = fm.get("pantheon_type")
                if not pid and not ptype:
                    unmanaged += 1  # README / MOC / ユーザー自作ノート
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
            "conflicts": conflicts,
            "issues": issues,
            "ok": len(issues) == 0,
        }
