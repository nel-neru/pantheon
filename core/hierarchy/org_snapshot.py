"""
OrgSnapshotManager — 組織スナップショット管理 (E-05)
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from core.platform.state import get_platform_home


@dataclass
class OrgSnapshot:
    snapshot_id: str
    org_name: str
    org_data: dict
    created_at: str
    label: str = ""


class OrgSnapshotManager:
    def __init__(self, platform_home: Optional[Path] = None):
        self.platform_home = Path(platform_home) if platform_home else get_platform_home()
        self.snapshots_dir = self.platform_home / "org_snapshots"
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)

    def take_snapshot(self, org, label: str = "") -> OrgSnapshot:
        org_data = self._dump_org(org)
        org_name = getattr(org, "name", "") or org_data.get("name", "organization")
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
        safe_name = self._sanitize_name(org_name)
        snapshot_id = f"{safe_name}_{timestamp}"
        snapshot = OrgSnapshot(
            snapshot_id=snapshot_id,
            org_name=org_name,
            org_data=org_data,
            created_at=datetime.now(timezone.utc).isoformat(),
            label=label,
        )
        path = self.snapshots_dir / f"{snapshot_id}.json"
        path.write_text(
            json.dumps(asdict(snapshot), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return snapshot

    def list_snapshots(self, org_name: str) -> list[OrgSnapshot]:
        prefix = f"{self._sanitize_name(org_name)}_"
        snapshots: list[OrgSnapshot] = []
        for path in sorted(self.snapshots_dir.glob(f"{prefix}*.json")):
            try:
                snapshots.append(OrgSnapshot(**json.loads(path.read_text(encoding="utf-8"))))
            except Exception:
                continue
        return snapshots

    def restore_snapshot(self, snapshot_id: str) -> dict:
        path = self.snapshots_dir / f"{snapshot_id}.json"
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
        return dict(payload.get("org_data", {}))

    def _dump_org(self, org) -> dict:
        if hasattr(org, "model_dump"):
            try:
                return org.model_dump(mode="json")
            except TypeError:
                return org.model_dump()
        return json.loads(json.dumps(getattr(org, "__dict__", {}), ensure_ascii=False, default=str))

    def _sanitize_name(self, org_name: str) -> str:
        return "_".join((org_name or "organization").split())
