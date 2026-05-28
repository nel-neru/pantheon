"""
BackupManager — 自動バックアップ (G-05)
"""

from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path

from core.platform.state import get_platform_home


class BackupManager:
    def __init__(self, platform_home=None):
        self.platform_home = Path(platform_home) if platform_home else get_platform_home()
        self.backups_dir = self.platform_home / "backups"
        self.backups_dir.mkdir(parents=True, exist_ok=True)

    def backup_now(self, source_path: Path) -> Path:
        source = Path(source_path)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
        backup_path = self.backups_dir / f"{source.name}_{timestamp}.bak"
        if source.is_dir():
            shutil.copytree(source, backup_path)
        else:
            shutil.copy2(source, backup_path)
        return backup_path

    def list_backups(self, source_name: str) -> list[Path]:
        backups = list(self.backups_dir.glob(f"{source_name}_*.bak"))
        return sorted(backups, key=lambda path: path.stat().st_mtime, reverse=True)

    def restore_latest(self, source_path: Path) -> bool:
        source = Path(source_path)
        backups = self.list_backups(source.name)
        if not backups:
            return False
        latest = backups[0]
        source.parent.mkdir(parents=True, exist_ok=True)
        if latest.is_dir():
            if source.exists():
                shutil.rmtree(source)
            shutil.copytree(latest, source)
        else:
            shutil.copy2(latest, source)
        return True

    def cleanup_old_backups(self, source_name: str, keep: int = 5) -> int:
        backups = self.list_backups(source_name)
        deleted = 0
        for backup in backups[keep:]:
            if backup.is_dir():
                shutil.rmtree(backup)
            else:
                backup.unlink(missing_ok=True)
            deleted += 1
        return deleted
