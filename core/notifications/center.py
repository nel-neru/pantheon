"""NotificationCenter — 通知の集約・既読管理・設定（P3.3 / 計画 §Phase3）。

既存の append-only ``notifications.jsonl``（``ProactiveNotifier`` が書く正準ログ）を
読み、**別ファイルの既読 id 集合**（``notifications_read.json``）を重ねることで、
append-only ログを書き換えずに既読/未読を表現する（非破壊・冪等）。

設定（``notification_settings.json``）は通知の「能動的なプッシュ可否」を決める:
- ``min_level``: これ未満のレベルはプッシュしない（一覧・カウントには出る）。
- ``quiet_hours_start`` / ``quiet_hours_end``: 静音時間帯（0..23 時・両端含む範囲）。
  start==end なら静音なし扱い。start>end は日跨ぎ（例: 22→7）。

すべて I/O はローカル JSON/JSONL のみ、LLM 非依存。``add`` は ``ProactiveNotifier`` と
同じスキーマ（``notification_id`` / ``level`` / ``message`` / ``org_name`` / ``created_at``）で
追記し、両者が同じログを共有する。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from core.persistence import atomic_write_text

logger = logging.getLogger(__name__)

# レベルの強さ順（プッシュ可否・最小レベル比較に使う）。
LEVEL_ORDER: Dict[str, int] = {"info": 0, "warn": 1, "critical": 2}

NOTIFICATIONS_FILE = "notifications.jsonl"
READ_STATE_FILE = "notifications_read.json"
SETTINGS_FILE = "notification_settings.json"

DEFAULT_NOTIFICATION_SETTINGS: Dict[str, Any] = {
    "min_level": "info",
    "quiet_hours_start": 0,
    "quiet_hours_end": 0,  # start==end → 静音なし
}


def _level_rank(level: str) -> int:
    """レベル文字列を強さ順位へ（未知は info 扱い）。"""
    return LEVEL_ORDER.get(str(level or "").lower(), 0)


class NotificationCenter:
    def __init__(self, platform_home: Optional[Path] = None):
        if platform_home is None:
            from core.platform.state import get_platform_home

            platform_home = get_platform_home()
        self.platform_home = Path(platform_home)
        self._log = self.platform_home / NOTIFICATIONS_FILE
        self._read_path = self.platform_home / READ_STATE_FILE
        self._settings_path = self.platform_home / SETTINGS_FILE

    # ---- ログ読み取り ----

    def _iter_raw(self) -> List[Dict[str, Any]]:
        try:
            lines = self._log.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        out: List[Dict[str, Any]] = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if isinstance(rec, dict):
                out.append(rec)
        return out

    def _normalize(self, rec: Dict[str, Any], read_ids: set[str]) -> Dict[str, Any]:
        nid = str(rec.get("notification_id") or rec.get("id") or "")
        return {
            "id": nid,
            "level": str(rec.get("level") or "info"),
            "message": str(rec.get("message") or ""),
            "org_name": str(rec.get("org_name") or ""),
            "created_at": str(rec.get("created_at") or ""),
            "read": nid in read_ids,
        }

    # ---- 既読状態 ----

    def read_ids(self) -> set[str]:
        try:
            data = json.loads(self._read_path.read_text(encoding="utf-8"))
            return set(str(x) for x in data) if isinstance(data, list) else set()
        except (OSError, ValueError):
            return set()

    def _save_read_ids(self, ids: set[str]) -> None:
        try:
            # atomic: クラッシュ/並行書き込みで既読集合が壊れない（torn write 防止）
            atomic_write_text(self._read_path, json.dumps(sorted(ids), ensure_ascii=False))
        except OSError as exc:  # pragma: no cover
            logger.warning("failed to persist read state: %s", exc)

    # ---- public API ----

    def list(self, *, limit: int = 50, unread_only: bool = False) -> List[Dict[str, Any]]:
        """通知を新しい順に返す（``unread_only`` で未読のみ）。"""
        read_ids = self.read_ids()
        items = [self._normalize(r, read_ids) for r in self._iter_raw()]
        # created_at の ISO 文字列は辞書順 = 時系列順。新しい順に。
        items.sort(key=lambda i: i["created_at"], reverse=True)
        if unread_only:
            items = [i for i in items if not i["read"]]
        return items[:limit]

    def unread_count(self) -> int:
        read_ids = self.read_ids()
        return sum(
            1
            for r in self._iter_raw()
            if (nid := self._normalize(r, read_ids)["id"]) and nid not in read_ids
        )

    def mark_read(self, notification_id: str) -> bool:
        """1 件を既読にする。存在する未読を既読化したら True。"""
        nid = str(notification_id)
        existing_ids = {self._normalize(r, set())["id"] for r in self._iter_raw()}
        if nid not in existing_ids:
            return False
        ids = self.read_ids()
        if nid in ids:
            return False  # すでに既読（冪等で no-op）
        ids.add(nid)
        self._save_read_ids(ids)
        return True

    def mark_all_read(self) -> int:
        """全通知を既読にする。新たに既読化した件数を返す。"""
        all_ids = {self._normalize(r, set())["id"] for r in self._iter_raw()}
        all_ids.discard("")
        before = self.read_ids()
        newly = all_ids - before
        if newly:
            self._save_read_ids(before | all_ids)
        return len(newly)

    def add(self, *, level: str, message: str, org_name: str = "") -> Dict[str, Any]:
        """通知を 1 件追記する（ProactiveNotifier と同一スキーマ・未読として記録）。"""
        from datetime import datetime, timezone

        rec = {
            "notification_id": str(uuid4()),
            "level": str(level or "info"),
            "message": str(message),
            "org_name": str(org_name),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            self.platform_home.mkdir(parents=True, exist_ok=True)
            with self._log.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except OSError as exc:  # pragma: no cover
            logger.warning("failed to persist notification: %s", exc)
        return self._normalize(rec, set())

    # ---- 設定 ----

    def get_settings(self) -> Dict[str, Any]:
        try:
            data = json.loads(self._settings_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        merged = {**DEFAULT_NOTIFICATION_SETTINGS, **(data if isinstance(data, dict) else {})}
        # 値域を安全側へ正規化。
        merged["min_level"] = merged["min_level"] if merged["min_level"] in LEVEL_ORDER else "info"
        merged["quiet_hours_start"] = _clamp_hour(merged.get("quiet_hours_start"))
        merged["quiet_hours_end"] = _clamp_hour(merged.get("quiet_hours_end"))
        return merged

    def update_settings(self, patch: Dict[str, Any]) -> Dict[str, Any]:
        current = self.get_settings()
        if "min_level" in patch and patch["min_level"] in LEVEL_ORDER:
            current["min_level"] = patch["min_level"]
        if "quiet_hours_start" in patch:
            current["quiet_hours_start"] = _clamp_hour(patch["quiet_hours_start"])
        if "quiet_hours_end" in patch:
            current["quiet_hours_end"] = _clamp_hour(patch["quiet_hours_end"])
        try:
            atomic_write_text(
                self._settings_path, json.dumps(current, ensure_ascii=False, indent=2)
            )
        except OSError as exc:  # pragma: no cover
            logger.warning("failed to persist notification settings: %s", exc)
        return current

    def should_push(self, level: str, *, hour: int) -> bool:
        """設定に照らし、能動的にプッシュしてよいか（最小レベル＋静音時間帯）を判定する。

        一覧・未読カウントには影響しない（記録は常に残す）。Always-On 通知の送出ゲート。
        """
        settings = self.get_settings()
        if _level_rank(level) < _level_rank(settings["min_level"]):
            return False
        return not _in_quiet_hours(
            _clamp_hour(hour), settings["quiet_hours_start"], settings["quiet_hours_end"]
        )


def _clamp_hour(value: Any) -> int:
    """時刻を 0..23 の int へ正規化する（不正は 0）。"""
    try:
        h = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, min(23, h))


def _in_quiet_hours(hour: int, start: int, end: int) -> bool:
    """hour が静音時間帯 [start, end] に入るか（start==end は静音なし、start>end は日跨ぎ）。"""
    if start == end:
        return False
    if start < end:
        return start <= hour <= end
    # 日跨ぎ（例: 22→7）: hour>=start または hour<=end
    return hour >= start or hour <= end
