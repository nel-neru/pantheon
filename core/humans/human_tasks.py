"""Human Member タスク管理 — 人間にしかできない作業をキューに積む。

Master Plan §10「人間は組織の優秀な社員」を実体化する。Pantheon は AI で出来ることを
すべて進め、**人間専用のタスク**（初回アカウント作成・高リスク承認・実投稿の最終確認など）は
握り潰さず ``~/.pantheon/human_tasks.json`` のキューへ積み、GUI で一覧・完了報告できるようにする。

JSON を正準とする（収益サブストレート＝`OutcomeStore` と同じ方針）。冪等追加（``dedupe_key``）で
自動化経路（publishing の handed_off 等）から二重登録しない。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional
from uuid import uuid4

STATUS_OPEN = "open"
STATUS_DONE = "done"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class HumanTask:
    """人間専用タスク 1 件。"""

    title: str
    description: str = ""
    kind: str = "general"  # account_setup / approval / publish_confirm / general など
    org_name: str = ""
    status: str = STATUS_OPEN
    ref: str = ""  # 紐づく対象（publish job id / proposal id など）
    dedupe_key: str = ""  # 同一 key の open タスクは二重登録しない
    task_id: str = ""
    created_at: str = ""
    done_at: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.task_id:
            self.task_id = f"human:{uuid4()}"
        if not self.created_at:
            self.created_at = _now_iso()


class HumanTaskStore:
    """人間タスクの永続ストア（``~/.pantheon/human_tasks.json``）。"""

    def __init__(self, platform_home: Optional[Path] = None):
        if platform_home is None:
            from core.platform.state import get_platform_home

            platform_home = get_platform_home()
        self.platform_home = Path(platform_home)
        self.platform_home.mkdir(parents=True, exist_ok=True)
        self.path = self.platform_home / "human_tasks.json"

    def add(
        self,
        title: str,
        *,
        description: str = "",
        kind: str = "general",
        org_name: str = "",
        ref: str = "",
        dedupe_key: str = "",
    ) -> HumanTask:
        """タスクを 1 件積む。``dedupe_key`` 指定時、同 key の open タスクがあれば既存を返す。"""
        tasks = self._load()
        if dedupe_key:
            for t in tasks:
                if t.dedupe_key == dedupe_key and t.status == STATUS_OPEN:
                    return t
        task = HumanTask(
            title=title,
            description=description,
            kind=kind,
            org_name=org_name,
            ref=ref,
            dedupe_key=dedupe_key,
        )
        tasks.append(task)
        self._save(tasks)
        return task

    def list_tasks(self, status: Optional[str] = None) -> List[HumanTask]:
        tasks = self._load()
        if status is None:
            return tasks
        return [t for t in tasks if t.status == status]

    def complete(self, task_id: str) -> Optional[HumanTask]:
        """タスクを完了にする。見つからなければ None。"""
        tasks = self._load()
        changed: Optional[HumanTask] = None
        for t in tasks:
            if t.task_id == task_id and t.status != STATUS_DONE:
                t.status = STATUS_DONE
                t.done_at = _now_iso()
                changed = t
                break
        if changed is not None:
            self._save(tasks)
        return changed

    # ---- 内部 ----

    def _load(self) -> List[HumanTask]:
        if not self.path.exists():
            return []
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return []
        out: List[HumanTask] = []
        for item in payload:
            try:
                out.append(HumanTask(**item))
            except (TypeError, ValueError):
                continue  # 不正レコードはスキップして全体を壊さない
        return out

    def _save(self, tasks: List[HumanTask]) -> None:
        self.path.write_text(
            json.dumps([asdict(t) for t in tasks], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def enqueue_human_task(
    title: str,
    *,
    platform_home: Optional[Path] = None,
    description: str = "",
    kind: str = "general",
    org_name: str = "",
    ref: str = "",
    dedupe_key: str = "",
) -> Optional[HumanTask]:
    """自動化経路から人間タスクを積む薄いヘルパ（失敗してもフローを壊さない）。"""
    try:
        return HumanTaskStore(platform_home=platform_home).add(
            title,
            description=description,
            kind=kind,
            org_name=org_name,
            ref=ref,
            dedupe_key=dedupe_key,
        )
    except (OSError, ValueError, TypeError):
        return None
