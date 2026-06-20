"""
Playbook — 再利用可能な施策ノート（学び）を蓄積・採点・参照する統一レイヤー（P2.3）。

組織やエージェントが得た「うまくいった/いかなかった施策」を軽量な JSON エントリとして
``~/.pantheon/playbooks.json`` に蓄積し、使用実績（成功/失敗）で usefulness_score を
更新する。本社(HQ)や各 Organization が「次に何を再利用すべきか」を判断する材料にする。

OutcomeStore（core/metrics/outcomes.py）と同方式: JSON を正準とし、外部 API には依存しない。
決定論的・冪等で、LLM 呼び出しを持たない（採点は単純な加減算ルール）。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional
from uuid import uuid4


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class PlaybookEntry:
    """再利用可能な施策ノート 1 件。

    外部（他プロセス/手書き）が書いた playbooks.json も安全に読めるよう、
    id/時刻/数値の補完・正規化は __post_init__ で行う（型ヒント任せにしない）。
    """

    title: str
    content: str
    category: str = "general"
    usefulness_score: float = 0.0
    usage_count: int = 0
    org_name: str = ""
    entry_id: str = ""
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        self.usefulness_score = float(self.usefulness_score)
        self.usage_count = int(self.usage_count)
        self.category = str(self.category).strip() or "general"
        if not self.entry_id:
            self.entry_id = f"pb:{uuid4()}"
        if not self.created_at:
            self.created_at = _now_iso()
        if not self.updated_at:
            self.updated_at = self.created_at


class PlaybookStore:
    """施策ノートの永続ストア（~/.pantheon/playbooks.json）。"""

    def __init__(self, platform_home: Optional[Path] = None):
        if platform_home is None:
            from core.platform.state import get_platform_home

            platform_home = get_platform_home()
        self.platform_home = Path(platform_home)
        self.platform_home.mkdir(parents=True, exist_ok=True)
        self.playbooks_path = self.platform_home / "playbooks.json"

    def add(
        self,
        title: str,
        content: str,
        *,
        category: str = "general",
        org_name: str = "",
    ) -> PlaybookEntry:
        """施策ノートを 1 件追加して保存し、作成したエントリを返す。"""
        entry = PlaybookEntry(
            title=str(title),
            content=str(content),
            category=str(category),
            org_name=str(org_name),
        )
        entries = self._load()
        entries.append(entry)
        self._save(entries)
        return entry

    def list_entries(self, category: Optional[str] = None) -> List[PlaybookEntry]:
        """全エントリ（``category`` 指定時はそのカテゴリのみ）を保存順で返す。"""
        entries = self._load()
        if category is None:
            return entries
        wanted = str(category).strip()
        return [e for e in entries if e.category == wanted]

    def record_use(self, entry_id: str, *, success: bool) -> Optional[PlaybookEntry]:
        """エントリの使用実績を 1 件記録する。

        ``usage_count`` を 1 増やし、成功なら ``usefulness_score`` を +1.0、失敗なら -0.5
        して ``updated_at`` を更新する。未知の ``entry_id`` は ``None`` を返す（何も書かない）。
        """
        entries = self._load()
        target: Optional[PlaybookEntry] = None
        for entry in entries:
            if entry.entry_id == entry_id:
                target = entry
                break
        if target is None:
            return None
        target.usage_count += 1
        target.usefulness_score += 1.0 if success else -0.5
        target.updated_at = _now_iso()
        self._save(entries)
        return target

    def top(self, limit: int = 5) -> List[PlaybookEntry]:
        """``usefulness_score`` 降順で上位 ``limit`` 件を返す（同点は保存順を保つ安定ソート）。"""
        entries = self._load()
        ranked = sorted(entries, key=lambda e: e.usefulness_score, reverse=True)
        if limit < 0:
            limit = 0
        return ranked[:limit]

    # ---- 内部 ----

    def _load(self) -> List[PlaybookEntry]:
        if not self.playbooks_path.exists():
            return []
        try:
            payload = json.loads(self.playbooks_path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return []
        entries: List[PlaybookEntry] = []
        for item in payload:
            try:
                entries.append(PlaybookEntry(**item))
            except (TypeError, ValueError):
                # 不正な item（未知キー/数値化できない値等）はスキップして全体を壊さない
                continue
        return entries

    def _save(self, entries: List[PlaybookEntry]) -> None:
        from core.persistence import atomic_write_text

        # 原子的に書く（Playbook カタログの partial write による学び消失を防ぐ）。
        atomic_write_text(
            self.playbooks_path,
            json.dumps([asdict(e) for e in entries], ensure_ascii=False, indent=2),
        )
