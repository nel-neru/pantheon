"""
Knowledge Manager

Organization 間で共有できる知見を .pantheon/knowledge/ に永続化する。
学習したパターン・ベストプラクティス・改善ノウハウを蓄積し、
次回の改善サイクルで活用できるようにする。
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from core.persistence import coerce_float, coerce_int, coerce_sort_str


class KnowledgeManager:
    """
    .pantheon/knowledge/ に知見を保存・取得する。
    タグによる絞り込み・ソース Organization の記録が可能。
    """

    def __init__(self, repo_path: Path | str):
        self.knowledge_dir = Path(repo_path) / ".pantheon" / "knowledge"
        self.knowledge_dir.mkdir(parents=True, exist_ok=True)

    def save_insight(
        self,
        title: str,
        content: str,
        tags: Optional[List[str]] = None,
        source_org: str = "",
        importance: str = "medium",
        **metadata: Any,
    ) -> str:
        """
        知見を保存する。Returns: insight_id
        """
        insight_id = str(uuid4())
        record: Dict[str, Any] = {
            "id": insight_id,
            "title": title,
            "content": content,
            "tags": list(tags or []),
            "source_org": source_org,
            "importance": importance,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        if metadata:
            record.update(metadata)
        self._write_record(record)
        return insight_id

    def save_with_repo_tag(
        self,
        content: str,
        tags: List[str],
        repo_name: str,
        **kwargs: Any,
    ) -> None:
        repo_tag = f"repo:{repo_name}"
        merged_tags = list(tags or [])
        if repo_tag not in merged_tags:
            merged_tags.append(repo_tag)
        title = kwargs.pop("title", f"[{repo_name}] insight")
        self.save_insight(title=title, content=content, tags=merged_tags, **kwargs)

    def get_insights(
        self,
        limit: int = 20,
        tags: Optional[List[str]] = None,
        source_org: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        知見を取得する（作成日時の新しい順）。
        tags が指定された場合、少なくとも 1 つ一致する知見のみ返す。
        """
        results = self._load_all_entries()
        if source_org:
            results = [record for record in results if record.get("source_org") == source_org]
        if tags:
            tag_set = set(tags)
            results = [
                record for record in results if tag_set.intersection(set(record.get("tags", [])))
            ]
        return results[:limit]

    def record_knowledge_access(self, tags: List[str]) -> None:
        if not tags:
            return
        tag_set = set(tags)
        referenced_at = datetime.now(timezone.utc).isoformat()
        for record in self._load_all_entries():
            if not tag_set.intersection(set(record.get("tags", []))):
                continue
            record["usage_count"] = coerce_int(record.get("usage_count"), 0) + 1
            record["last_referenced"] = referenced_at
            self._write_record(record)

    def get_by_importance(self, limit: int = 10) -> List[Dict[str, Any]]:
        entries = self._load_all_entries()
        entries.sort(
            key=lambda record: (
                -coerce_int(record.get("usage_count"), 0),
                coerce_sort_str(record.get("created_at")),
            ),
        )
        return entries[:limit]

    def promote_to_best_practice(self, entry_id: str) -> bool:
        record = self._load_by_id(entry_id)
        if not record:
            return False
        quality_score = coerce_float(record.get("quality_score"), 0.0)
        if quality_score < 8 or record.get("importance") == "best_practice":
            return False
        record["importance"] = "best_practice"
        self._write_record(record)
        return True

    def get_best_practices(self, limit: int = 10) -> List[Dict[str, Any]]:
        entries = [
            record
            for record in self._load_all_entries()
            if record.get("importance") == "best_practice"
        ]
        entries.sort(
            key=lambda record: (
                -coerce_int(record.get("usage_count"), 0),
                coerce_sort_str(record.get("created_at")),
            ),
        )
        return entries[:limit]

    def auto_promote_high_quality(self, threshold: float = 8.0) -> int:
        promoted = 0
        for record in self._load_all_entries():
            if record.get("importance") == "best_practice":
                continue
            if coerce_float(record.get("quality_score"), 0.0) < threshold:
                continue
            record["importance"] = "best_practice"
            self._write_record(record)
            promoted += 1
        return promoted

    def archive_stale_entries(self, days_inactive: int = 30) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_inactive)
        archived = 0
        for record in self._load_all_entries():
            if record.get("archived") is True:
                continue
            last_referenced = record.get("last_referenced")
            if not last_referenced:
                continue
            try:
                referenced_at = datetime.fromisoformat(last_referenced)
            except ValueError:
                continue
            # naive な legacy timestamp は UTC とみなして aware の cutoff と比較可能にする。
            # 未 coerce だと naive<aware 比較が TypeError で archive sweep 全体を落とす。
            if referenced_at.tzinfo is None:
                referenced_at = referenced_at.replace(tzinfo=timezone.utc)
            if referenced_at < cutoff:
                record["archived"] = True
                self._write_record(record)
                archived += 1
        return archived

    def get_active_entries(self, limit: int = 50) -> List[Dict[str, Any]]:
        entries = [
            record for record in self._load_all_entries() if record.get("archived") is not True
        ]
        return entries[:limit]

    def get_for_repo(self, repo_name: str, limit: int = 20) -> List[Dict[str, Any]]:
        repo_tag = f"repo:{repo_name}"
        entries = [
            record for record in self._load_all_entries() if repo_tag in record.get("tags", [])
        ]
        entries.sort(
            key=lambda record: (
                -coerce_int(record.get("usage_count"), 0),
                coerce_sort_str(record.get("created_at")),
            ),
        )
        return entries[:limit]

    def get_context_for_agent(self, tags: Optional[List[str]] = None, limit: int = 5) -> str:
        """
        エージェントのプロンプトに埋め込める形式でナレッジを返す。
        """
        insights = self.get_insights(limit=limit, tags=tags)
        if not insights:
            return ""
        lines = ["【過去の知見・ベストプラクティス】"]
        for ins in insights:
            lines.append(
                f"- [{ins.get('importance', 'medium').upper()}] {ins['title']}: {ins['content'][:150]}"
            )
        return "\n".join(lines)

    def count(self) -> int:
        return len(list(self.knowledge_dir.glob("*.json")))

    def _entry_path(self, entry_id: str) -> Path:
        return self.knowledge_dir / f"{entry_id}.json"

    def _load_by_id(self, entry_id: str) -> Optional[Dict[str, Any]]:
        path = self._entry_path(entry_id)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def _write_record(self, record: Dict[str, Any]) -> None:
        path = self._entry_path(str(record["id"]))
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

    def _load_all_entries(self) -> List[Dict[str, Any]]:
        entries: List[Dict[str, Any]] = []
        for path in self.knowledge_dir.glob("*.json"):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if isinstance(record, dict):  # 非 dict の壊れたファイルは読み取り全体を壊さない
                entries.append(record)
        # 生 JSON の created_at は null/非 str になりうる（``None < str`` のソート TypeError 防止）。
        entries.sort(key=lambda record: coerce_sort_str(record.get("created_at")), reverse=True)
        return entries
