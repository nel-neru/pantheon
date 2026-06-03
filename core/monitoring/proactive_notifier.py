"""
ProactiveNotifier — 組織からの能動的通知 (I-02)

健康スコア低下・重大問題検知時にCLI通知を出力する。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from core.platform.state import get_platform_home


@dataclass
class Notification:
    notification_id: str
    level: str
    message: str
    org_name: str
    created_at: str


class ProactiveNotifier:
    DEFAULT_THRESHOLDS = {
        "health_drop_threshold": 10.0,
        "min_health": 30.0,
        "critical_backlog": 20,
    }

    def __init__(self, platform_home: Path = None, thresholds: dict = None):
        self.platform_home = Path(platform_home) if platform_home else get_platform_home()
        self.platform_home.mkdir(parents=True, exist_ok=True)
        self.thresholds = {**self.DEFAULT_THRESHOLDS, **(thresholds or {})}
        self._notifications_file = self.platform_home / "notifications.jsonl"

    def check_org_health(
        self, org_name: str, current_score: float, previous_score: float
    ) -> list[Notification]:
        notifications: list[Notification] = []
        drop = previous_score - current_score

        if drop > float(self.thresholds["health_drop_threshold"]):
            notifications.append(
                self._make_notification(
                    level="warn",
                    org_name=org_name,
                    message=(
                        f"health score dropped by {drop:.1f} "
                        f"({previous_score:.1f} -> {current_score:.1f})"
                    ),
                )
            )

        if current_score < float(self.thresholds["min_health"]):
            notifications.append(
                self._make_notification(
                    level="critical",
                    org_name=org_name,
                    message=f"health score is critically low at {current_score:.1f}",
                )
            )

        return notifications

    def check_proposal_backlog(self, org_name: str, pending_count: int) -> list[Notification]:
        if pending_count > int(self.thresholds["critical_backlog"]):
            return [
                self._make_notification(
                    level="warn",
                    org_name=org_name,
                    message=f"proposal backlog has reached {pending_count} pending items",
                )
            ]
        return []

    def format_notification(self, notification: Notification) -> str:
        return f"[{notification.level.upper()}] {notification.org_name}: {notification.message}"

    def save_notification(self, notification: Notification) -> None:
        self._notifications_file.parent.mkdir(parents=True, exist_ok=True)
        with self._notifications_file.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(notification), ensure_ascii=False) + "\n")

    def get_recent_notifications(self, limit: int = 10) -> list[Notification]:
        if not self._notifications_file.exists():
            return []

        notifications: list[Notification] = []
        for line in self._notifications_file.read_text(encoding="utf-8").splitlines()[-limit:]:
            if not line.strip():
                continue
            try:
                notifications.append(Notification(**json.loads(line)))
            except Exception:
                continue
        return notifications

    def _make_notification(self, level: str, org_name: str, message: str) -> Notification:
        return Notification(
            notification_id=str(uuid4()),
            level=level,
            message=message,
            org_name=org_name,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
