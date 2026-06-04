"""
MultiUserManager — マルチユーザー対応 (D-10)
PANTHEON_USER環境変数でプロファイルを切り替える
"""

from __future__ import annotations

import os
from pathlib import Path


class MultiUserManager:
    def get_current_user(self) -> str:
        return os.environ.get("PANTHEON_USER", "default")

    def get_profile_path(self, platform_home: Path, user: str = None) -> Path:
        target_user = user or self.get_current_user()
        return Path(platform_home) / "profiles" / target_user / "developer_profile.json"

    def list_users(self, platform_home: Path) -> list[str]:
        profiles_dir = Path(platform_home) / "profiles"
        if not profiles_dir.exists():
            return []
        return sorted(path.name for path in profiles_dir.iterdir() if path.is_dir())
