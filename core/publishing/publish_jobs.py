"""PublishJob — 承認済みコンテンツを「いつ・どこへ投稿するか」を表す永続ジョブ。

``~/.pantheon/publish_jobs.json`` に JSON で保存する（``ContentJobStore`` と同じパターン）。
ジョブは content_asset 提案が **人間に承認された後** に enqueue され、予約時刻（``scheduled_at``）
に達すると ``runner`` が適切なアダプタで実行する。承認の無いジョブは決して作られない。
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.persistence import atomic_write_text
from core.publishing.base import (
    PUBLISH_MODE_ASSISTED,
    SUPPORTED_PLATFORMS,
)

# ジョブのライフサイクル。handed_off は「assisted の下書き流し込みまで完了し、
# 最終公開を人間に引き渡した」状態（published とは区別し、成果指標にも数えない）。
PUBLISH_JOB_STATUSES = ("queued", "publishing", "published", "handed_off", "failed", "cancelled")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


@dataclass
class PublishJob:
    """1 件の投稿ジョブ。本文は enqueue 時点のスナップショットを保持する。"""

    org_name: str
    platform: str
    title: str = ""
    body: str = ""
    account: str = ""
    scheduled_at: Optional[str] = None
    mode: str = PUBLISH_MODE_ASSISTED
    status: str = "queued"
    result_url: str = ""
    error: str = ""
    attempts: int = 0
    # トレーサビリティ: どの提案・どのワークスペースファイル由来か。
    source_proposal_id: str = ""
    file_path: str = ""
    job_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: str = field(default_factory=lambda: _iso(_now()))
    updated_at: str = field(default_factory=lambda: _iso(_now()))

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PublishJob":
        known = {f for f in cls.__dataclass_fields__}  # noqa: C416
        return cls(**{k: v for k, v in data.items() if k in known})

    def is_due(self, now: Optional[datetime] = None) -> bool:
        """予約時刻に達し、まだ未実行（queued）かを判定する。"""
        if self.status != "queued":
            return False
        if not self.scheduled_at:
            return True  # 予約なし = 即時投稿可
        now = now or _now()
        try:
            return datetime.fromisoformat(self.scheduled_at) <= now
        except (ValueError, TypeError):  # naive/不正な scheduled_at で全 due スキャンを落とさない
            return True


class PublishJobStore:
    """PublishJob の永続ストア（``~/.pantheon/publish_jobs.json``）。"""

    def __init__(self, platform_home: Optional[Path] = None):
        from core.platform.state import get_platform_home

        self.platform_home = Path(platform_home) if platform_home else get_platform_home()
        self.platform_home.mkdir(parents=True, exist_ok=True)
        self.path = self.platform_home / "publish_jobs.json"

    # ---- 低レベル read/write ----
    def _load_raw(self) -> List[Dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        return data if isinstance(data, list) else []

    def _save_raw(self, items: List[Dict[str, Any]]) -> None:
        atomic_write_text(self.path, json.dumps(items, ensure_ascii=False, indent=2))

    # ---- 公開 API ----
    def list_jobs(self) -> List[PublishJob]:
        jobs: List[PublishJob] = []
        for d in self._load_raw():
            try:
                jobs.append(PublishJob.from_dict(d))
            except (TypeError, ValueError):
                # 壊れた/不完全なレコードはスキップして 500 を避ける。
                continue
        return jobs

    def get_job(self, job_id: str) -> Optional[PublishJob]:
        for job in self.list_jobs():
            if job.job_id == job_id:
                return job
        return None

    def add_job(self, job: PublishJob) -> PublishJob:
        if job.platform not in SUPPORTED_PLATFORMS:
            raise ValueError(f"未対応のプラットフォーム: {job.platform}")
        if job.status not in PUBLISH_JOB_STATUSES:
            job.status = "queued"
        items = self._load_raw()
        items.append(job.to_dict())
        self._save_raw(items)
        return job

    def update_job(self, job: PublishJob) -> PublishJob:
        job.updated_at = _iso(_now())
        items = self._load_raw()
        for i, d in enumerate(items):
            if d.get("job_id") == job.job_id:
                items[i] = job.to_dict()
                break
        else:
            items.append(job.to_dict())
        self._save_raw(items)
        return job

    def delete_job(self, job_id: str) -> bool:
        items = self._load_raw()
        remaining = [d for d in items if d.get("job_id") != job_id]
        if len(remaining) == len(items):
            return False
        self._save_raw(remaining)
        return True

    def mark_status(
        self,
        job_id: str,
        *,
        status: str,
        result_url: str = "",
        error: str = "",
        bump_attempts: bool = False,
    ) -> Optional[PublishJob]:
        job = self.get_job(job_id)
        if job is None:
            return None
        if status in PUBLISH_JOB_STATUSES:
            job.status = status
        if result_url:
            job.result_url = result_url
        job.error = error
        if bump_attempts:
            job.attempts += 1
        return self.update_job(job)

    def due_jobs(self, now: Optional[datetime] = None) -> List[PublishJob]:
        now = now or _now()
        return [job for job in self.list_jobs() if job.is_due(now)]


def publish_request_from_proposal(proposal: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """提案の ``intervention_spec.publish`` ブロック（投稿指定）を取り出す。

    投稿対象でない（publish ブロックが無い）提案では None を返す。content_asset 提案に
    ``{"publish": {"platform": "note", "scheduled_at": ..., "mode": "assisted", "account": ...}}``
    を載せることで「承認したら投稿する」を表現する（モデル変更を避けるため spec に内包）。
    """
    spec = proposal.get("intervention_spec") or {}
    pub = spec.get("publish")
    return pub if isinstance(pub, dict) else None


def enqueue_from_proposal(
    proposal: Dict[str, Any],
    org_name: str,
    *,
    store: Optional["PublishJobStore"] = None,
    platform_home: Optional[Path] = None,
) -> Optional[PublishJob]:
    """承認済み content_asset 提案に投稿指定があれば PublishJob を enqueue する。

    投稿指定が無い / プラットフォームが未対応なら None を返す（承認フローを壊さない）。
    本文は提案の ``intervention_spec.content`` を、タイトルは提案 ``title`` をスナップショットする。
    """
    pub = publish_request_from_proposal(proposal)
    if not pub:
        return None
    platform = str(pub.get("platform") or "").strip().lower()
    if platform not in SUPPORTED_PLATFORMS:
        return None
    store = store or PublishJobStore(platform_home=platform_home)
    spec = proposal.get("intervention_spec") or {}
    scheduled_at = pub.get("scheduled_at")
    job = PublishJob(
        org_name=org_name,
        platform=platform,
        title=str(proposal.get("title") or ""),
        body=str(spec.get("content") or ""),
        account=str(pub.get("account") or ""),
        scheduled_at=str(scheduled_at) if scheduled_at else None,
        mode=str(pub.get("mode") or PUBLISH_MODE_ASSISTED),
        source_proposal_id=str(proposal.get("id") or ""),
        file_path=str(proposal.get("file_path") or ""),
    )
    return store.add_job(job)
