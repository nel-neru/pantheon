"""
Pantheon - Event Detector

Organization の担当リポジトリを監視してイベントを検知する。
検知したイベントがスケジューラーに渡され、自律的な改善サイクルのトリガーとなる。

検知するイベント:
  - NEW_COMMIT    : 対象リポジトリに新しいコミットがある
  - HEALTH_DROP   : Organization の健康スコアが閾値を下回った
  - PENDING_SPIKE : 未対応提案が上限を超えた
  - SCHEDULED     : 定期実行タイマー
"""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    NEW_COMMIT = "new_commit"
    HEALTH_DROP = "health_drop"
    PENDING_SPIKE = "pending_spike"
    SCHEDULED = "scheduled"


@dataclass
class DetectedEvent:
    event_type: EventType
    org_name: str
    org_id: str
    details: Dict[str, Any] = field(default_factory=dict)
    detected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_type": self.event_type.value,
            "org_name": self.org_name,
            "org_id": self.org_id,
            "details": self.details,
            "detected_at": self.detected_at.isoformat(),
        }


class EventDetector:
    """
    全 Organization を走査してイベントを検知する。
    スケジューラーが定期的に呼び出す。
    """

    def __init__(
        self,
        platform_home: Optional[Path] = None,
        health_drop_threshold: float = 40.0,
        pending_spike_limit: int = 10,
    ):
        from core.platform.state import get_platform_home

        self._platform_home = platform_home or get_platform_home()
        self._health_threshold = health_drop_threshold
        self._pending_limit = pending_spike_limit
        self._last_commits: Dict[str, str] = self._load_commit_cache()

    # ---- キャッシュ（最後に確認したコミットSHA） ----

    def _cache_path(self) -> Path:
        return self._platform_home / "event_cache.json"

    def _load_commit_cache(self) -> Dict[str, str]:
        p = self._cache_path()
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.warning("Failed to load commit cache from %s: %s", p, exc)
        return {}

    def _save_commit_cache(self) -> None:
        cache_file = self._cache_path()
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(
            json.dumps(self._last_commits, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ---- イベント検知 ----

    def detect_all(self) -> List[DetectedEvent]:
        """全 Organization を走査してイベント一覧を返す"""
        from core.metrics.balanced_growth import calculate_organization_metrics
        from core.platform.state import PlatformStateManager

        psm = PlatformStateManager(self._platform_home)
        orgs = psm.load_organizations()
        events: List[DetectedEvent] = []

        for org in orgs:
            sm = psm.get_org_state_manager(org)
            pending = sm.get_pending_improvement_proposals(limit=100)
            pending_count = len(pending)

            # 1. 新規コミット検知
            if org.target_repo_path:
                new_sha = self._get_latest_commit(org.target_repo_path)
                old_sha = self._last_commits.get(str(org.id))
                if new_sha and new_sha != old_sha:
                    events.append(
                        DetectedEvent(
                            event_type=EventType.NEW_COMMIT,
                            org_name=org.name,
                            org_id=str(org.id),
                            details={"old_sha": old_sha, "new_sha": new_sha},
                        )
                    )
                    self._last_commits[str(org.id)] = new_sha

            # 2. 健康スコア低下検知
            m = calculate_organization_metrics(org, pending_proposals_count=pending_count)
            if m.health_score < self._health_threshold:
                events.append(
                    DetectedEvent(
                        event_type=EventType.HEALTH_DROP,
                        org_name=org.name,
                        org_id=str(org.id),
                        details={
                            "health_score": m.health_score,
                            "threshold": self._health_threshold,
                        },
                    )
                )

            # 3. 未対応提案急増検知
            if pending_count >= self._pending_limit:
                events.append(
                    DetectedEvent(
                        event_type=EventType.PENDING_SPIKE,
                        org_name=org.name,
                        org_id=str(org.id),
                        details={"pending_count": pending_count, "limit": self._pending_limit},
                    )
                )

        self._save_commit_cache()
        return events

    def detect_for_org(self, org_name: str) -> List[DetectedEvent]:
        """特定 Organization のイベントのみ検知"""
        return [e for e in self.detect_all() if e.org_name == org_name]

    # ---- ユーティリティ ----

    @staticmethod
    def _get_latest_commit(repo_path: str) -> Optional[str]:
        """git log から最新コミット SHA を取得する"""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception as e:
            logger.debug("git rev-parse failed for %s: %s", repo_path, e)
        return None
