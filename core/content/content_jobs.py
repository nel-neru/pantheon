"""ContentJob — 定期的に「投稿（content_asset 提案）」を生成するジョブの永続ストア。

``~/.pantheon/content_jobs.json`` に JSON で保存する。1 ジョブ = 1 ワークスペース org に対する
「どんなコンテンツを・どの間隔で生成するか」のレシピ。実行（生成）は content_runner が担う。
外部公開は一切行わない（生成物は content_asset 提案として人間承認待ちで repo に残る）。
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# 生成するコンテンツの種類（org_handoff の kind と対応）。
CONTENT_JOB_KINDS = ("content_brief", "audience_signal", "monetization_lead", "generic")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


@dataclass
class ContentJob:
    """定期コンテンツ生成ジョブ。"""

    org_name: str
    kind: str = "content_brief"
    theme: str = ""
    interval_seconds: int = 86400
    enabled: bool = True
    # 投稿先（任意）。空なら投稿指定なし＝従来どおり下書きのみ。値があれば生成物の
    # content_asset 提案に publish 指定が載り、承認時に PublishJob が enqueue される。
    publish_platform: str = ""
    publish_mode: str = "assisted"
    job_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: str = field(default_factory=lambda: _iso(_now()))
    last_run_at: Optional[str] = None
    next_run_at: Optional[str] = None
    last_status: str = "scheduled"
    last_detail: str = ""
    run_count: int = 0
    # 由来トレンドの hash（トレンド→ジョブ変換の重複排除に使う。空=トレンド由来でない）。
    source_trend_hash: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ContentJob":
        known = {f for f in cls.__dataclass_fields__}  # noqa: C416
        return cls(**{k: v for k, v in data.items() if k in known})

    def is_due(self, now: Optional[datetime] = None) -> bool:
        if not self.enabled:
            return False
        if not self.next_run_at:
            return True
        now = now or _now()
        try:
            return datetime.fromisoformat(self.next_run_at) <= now
        except (ValueError, TypeError):  # naive/不正な next_run_at で cycle 全体を落とさない
            return True


class ContentJobStore:
    """ContentJob の永続ストア（``~/.pantheon/content_jobs.json``）。"""

    def __init__(self, platform_home: Optional[Path] = None):
        from core.platform.state import get_platform_home

        self.platform_home = Path(platform_home) if platform_home else get_platform_home()
        self.platform_home.mkdir(parents=True, exist_ok=True)
        self.path = self.platform_home / "content_jobs.json"

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
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    # ---- 公開 API ----
    def list_jobs(self) -> List[ContentJob]:
        jobs = []
        for d in self._load_raw():
            try:
                jobs.append(ContentJob.from_dict(d))
            except (TypeError, ValueError):
                # 壊れた/不完全なレコード（手編集・移行など）はスキップして 500 を避ける。
                continue
        return jobs

    def get_job(self, job_id: str) -> Optional[ContentJob]:
        for job in self.list_jobs():
            if job.job_id == job_id:
                return job
        return None

    def add_job(self, job: ContentJob) -> ContentJob:
        if job.kind not in CONTENT_JOB_KINDS:
            job.kind = "generic"
        # 初回 next_run_at は即時実行可能に（None のまま is_due=True）。
        items = self._load_raw()
        items.append(job.to_dict())
        self._save_raw(items)
        return job

    def update_job(self, job: ContentJob) -> ContentJob:
        if job.kind not in CONTENT_JOB_KINDS:
            job.kind = "generic"  # add_job と同様に許可リスト外は generic へ寄せる
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

    def set_enabled(self, job_id: str, enabled: bool) -> Optional[ContentJob]:
        job = self.get_job(job_id)
        if job is None:
            return None
        job.enabled = enabled
        return self.update_job(job)

    def mark_run(
        self, job_id: str, *, status: str, detail: str = "", now: Optional[datetime] = None
    ) -> Optional[ContentJob]:
        """実行結果を記録し、次回実行時刻を interval 後に進める。"""
        job = self.get_job(job_id)
        if job is None:
            return None
        now = now or _now()
        job.last_run_at = _iso(now)
        job.next_run_at = _iso(now + timedelta(seconds=max(1, job.interval_seconds)))
        job.last_status = status
        job.last_detail = detail
        job.run_count += 1
        return self.update_job(job)

    def due_jobs(self, now: Optional[datetime] = None) -> List[ContentJob]:
        now = now or _now()
        return [job for job in self.list_jobs() if job.is_due(now)]
