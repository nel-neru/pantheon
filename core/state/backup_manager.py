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

    def _source_key(self, source_path: Path | str) -> str:
        raw = str(source_path)
        if all(sep not in raw for sep in ("/", "\\")):
            return Path(raw).name

        source = Path(source_path).expanduser()
        try:
            relative = source.resolve().relative_to(self.platform_home.resolve())
        except ValueError:
            relative = source if not source.is_absolute() else Path(*source.parts[1:])
        parts = [part for part in relative.parts if part not in {"", "."}]
        return "__".join(parts) or Path(raw).name

    def backup_now(self, source_path: Path) -> Path:
        source = Path(source_path)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
        backup_path = self.backups_dir / f"{self._source_key(source)}_{timestamp}.bak"
        if source.is_dir():
            ignore = shutil.ignore_patterns(self.backups_dir.name) if source.resolve() == self.platform_home.resolve() else None
            shutil.copytree(source, backup_path, ignore=ignore)
        else:
            shutil.copy2(source, backup_path)
        return backup_path

    def list_backups(self, source_name: Path | str) -> list[Path]:
        backups = list(self.backups_dir.glob(f"{self._source_key(source_name)}_*.bak"))
        return sorted(backups, key=lambda path: path.stat().st_mtime, reverse=True)

    def restore_latest(self, source_path: Path) -> bool:
        source = Path(source_path)
        backups = self.list_backups(source)
        if not backups:
            return False
        latest = backups[0]
        source.parent.mkdir(parents=True, exist_ok=True)
        if latest.is_dir():
            latest_in_source = latest.resolve().is_relative_to(source.resolve())
            if source.exists() and latest_in_source:
                staging = source.parent / f".{source.name}.restore"
                if staging.exists():
                    if staging.is_dir():
                        shutil.rmtree(staging)
                    else:
                        staging.unlink()
                shutil.copytree(latest, staging)
                shutil.rmtree(source)
                shutil.move(str(staging), str(source))
            else:
                if source.exists():
                    shutil.rmtree(source)
                shutil.copytree(latest, source)
        else:
            shutil.copy2(latest, source)
        return True

    def cleanup_old_backups(self, source_name: Path | str, keep: int = 5) -> int:
        backups = self.list_backups(source_name)
        deleted = 0
        for backup in backups[keep:]:
            if backup.is_dir():
                shutil.rmtree(backup)
            else:
                backup.unlink(missing_ok=True)
            deleted += 1
        return deleted
