"""グローバルタスクキュー - 複数組織のタスクをJSONで永続管理する。"""

from __future__ import annotations

import json
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Iterator

from core.platform.state import get_platform_home

# 注: キューの保存先は TaskQueue.__init__ が get_platform_home()（PANTHEON_HOME を尊重）から
# 解決する。旧 module 定数 QUEUE_FILE はハードコード ~/.pantheon で環境分離を破る dead code
# だったため削除（2026-06-14 dev/prod 環境分離）。
_FILE_LOCK = threading.RLock()


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskType(str, Enum):
    ANALYZE = "analyze"
    GOAL = "goal"
    IMPROVE = "improve"
    REVIEW = "review"
    CUSTOM = "custom"


class TaskQueue:
    """JSON ファイルベースのグローバルタスクキュー。"""

    def __init__(self, queue_file: Path | None = None):
        self.queue_file = (
            Path(queue_file) if queue_file is not None else get_platform_home() / "task_queue.json"
        )
        self.queue_file.parent.mkdir(parents=True, exist_ok=True)
        self.lock_file = self.queue_file.with_suffix(f"{self.queue_file.suffix}.lock")

    @contextmanager
    def _locked(self) -> Iterator[None]:
        self.lock_file.parent.mkdir(parents=True, exist_ok=True)
        with _FILE_LOCK:
            with self.lock_file.open("a", encoding="utf-8") as lock_handle:
                try:
                    import fcntl

                    fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
                except (ImportError, OSError):
                    pass
                try:
                    yield
                finally:
                    try:
                        import fcntl

                        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
                    except (ImportError, OSError):
                        pass

    def _load(self) -> dict[str, Any]:
        if self.queue_file.exists():
            try:
                with self.queue_file.open(encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict) and isinstance(data.get("tasks"), list):
                    data.setdefault("version", 1)
                    return data
            except Exception:
                pass
        return {"tasks": [], "version": 1}

    def _save(self, data: dict[str, Any]) -> None:
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        temp_file = self.queue_file.with_suffix(f"{self.queue_file.suffix}.tmp")
        temp_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_file.replace(self.queue_file)

    @staticmethod
    def _normalize_task_type(task_type: str | TaskType) -> str:
        raw = task_type.value if isinstance(task_type, TaskType) else str(task_type)
        try:
            return TaskType(raw).value
        except ValueError:
            return raw

    @staticmethod
    def _normalize_status(status: str | TaskStatus) -> str:
        return status.value if isinstance(status, TaskStatus) else TaskStatus(status).value

    @staticmethod
    def _parse_timestamp(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None

    def add_task(
        self,
        task_type: str,
        org_name: str,
        description: str,
        payload: dict[str, Any] | None = None,
        priority: int = 5,
    ) -> dict[str, Any]:
        """タスクをキューに追加する。返値はタスク dict。"""
        with self._locked():
            data = self._load()
            task = {
                "id": str(uuid.uuid4()),
                "type": self._normalize_task_type(task_type),
                "org_name": org_name,
                "description": description,
                "payload": payload or {},
                "status": TaskStatus.PENDING.value,
                "priority": priority,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "started_at": None,
                "completed_at": None,
                "result": None,
                "error": None,
            }
            data["tasks"].append(task)
            self._save(data)
            return dict(task)

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        with self._locked():
            data = self._load()
            task = next((t for t in data["tasks"] if t["id"] == task_id), None)
            return dict(task) if task else None

    def list_tasks(
        self,
        org_name: str | None = None,
        status: str | None = None,
        limit: int | None = 50,
    ) -> list[dict[str, Any]]:
        with self._locked():
            data = self._load()
            tasks = list(data["tasks"])

        if org_name:
            tasks = [t for t in tasks if t.get("org_name") == org_name]
        if status:
            tasks = [t for t in tasks if t.get("status") == status]
        tasks = sorted(tasks, key=lambda t: t.get("created_at", ""), reverse=True)
        if limit is None:
            return tasks
        return tasks[:limit]

    def update_status(
        self,
        task_id: str,
        status: str,
        result: Any = None,
        error: str | None = None,
    ) -> dict[str, Any] | None:
        normalized_status = self._normalize_status(status)
        with self._locked():
            data = self._load()
            for task in data["tasks"]:
                if task["id"] == task_id:
                    task["status"] = normalized_status
                    now = datetime.now(timezone.utc).isoformat()
                    if normalized_status == TaskStatus.RUNNING.value:
                        task["started_at"] = now
                    elif normalized_status in {
                        TaskStatus.DONE.value,
                        TaskStatus.FAILED.value,
                        TaskStatus.CANCELLED.value,
                    }:
                        task["completed_at"] = now
                    if result is not None:
                        task["result"] = result
                    if error is not None:
                        task["error"] = error
                    self._save(data)
                    return dict(task)
        return None

    def cancel_task(self, task_id: str) -> bool:
        with self._locked():
            data = self._load()
            for task in data["tasks"]:
                if task["id"] == task_id and task["status"] == TaskStatus.PENDING.value:
                    task["status"] = TaskStatus.CANCELLED.value
                    task["completed_at"] = datetime.now(timezone.utc).isoformat()
                    self._save(data)
                    return True
        return False

    def get_pending_tasks(self, limit: int | None = 10) -> list[dict[str, Any]]:
        """優先度順にPENDINGタスクを返す。"""
        with self._locked():
            data = self._load()
            tasks = [t for t in data["tasks"] if t["status"] == TaskStatus.PENDING.value]

        tasks = sorted(
            tasks,
            key=lambda t: (-int(t.get("priority", 5)), t.get("created_at", "")),
        )
        if limit is None:
            return tasks
        return tasks[:limit]

    def cleanup_old_tasks(self, keep_days: int = 7) -> int:
        """完了済みタスクのうち keep_days 日以上前のものを削除する。"""
        cutoff = datetime.now(timezone.utc) - timedelta(days=keep_days)
        with self._locked():
            data = self._load()
            before = len(data["tasks"])
            data["tasks"] = [
                t
                for t in data["tasks"]
                if t["status"] in (TaskStatus.PENDING.value, TaskStatus.RUNNING.value)
                or (
                    (completed_at := self._parse_timestamp(t.get("completed_at"))) is not None
                    and completed_at > cutoff
                )
            ]
            removed = before - len(data["tasks"])
            if removed:
                self._save(data)
            return removed
