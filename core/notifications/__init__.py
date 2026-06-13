"""通知センター（P3.3）。

既存の append-only ``notifications.jsonl``（``core.monitoring.proactive_notifier`` が書く）を
正準ログとして読み、既読状態・設定（時間帯/最小レベル）を非破壊で重ねる集約レイヤ。
"""

from __future__ import annotations

from core.notifications.center import (
    DEFAULT_NOTIFICATION_SETTINGS,
    LEVEL_ORDER,
    NotificationCenter,
)

__all__ = ["NotificationCenter", "DEFAULT_NOTIFICATION_SETTINGS", "LEVEL_ORDER"]
