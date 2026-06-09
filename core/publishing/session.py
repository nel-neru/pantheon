"""ブラウザセッション state の管理（資格情報は保存しない）。

各プラットフォームについて、ユーザーが一度だけ手動ログインして作る Playwright の
storage_state を ``~/.pantheon/browser_sessions/<platform>/state.json`` に保持する。
パスワード/トークンは Pantheon が一切保持しない（``.env``/資格情報の編集を禁じる
PreToolUse ガードの方針と整合）。

本モジュールは Playwright を import しない（状態＝ファイルの有無で判定する）。実際の
ログイン用ブラウザ起動は接続フロー（Track E）が必要時に遅延 import で行う。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from core.publishing.base import SUPPORTED_PLATFORMS

# 接続状態。
STATUS_CONNECTED = "connected"
STATUS_DISCONNECTED = "disconnected"

_STATE_FILE = "state.json"


@dataclass
class ConnectionStatus:
    platform: str
    status: str
    connected_at: Optional[str] = None


class SessionStore:
    """プラットフォームごとのブラウザセッション state を管理する。"""

    def __init__(self, platform_home: Optional[Path] = None):
        from core.platform.state import get_platform_home

        self.platform_home = Path(platform_home) if platform_home else get_platform_home()
        self.root = self.platform_home / "browser_sessions"

    def session_dir(self, platform: str) -> Path:
        return self.root / platform

    def state_path(self, platform: str) -> Path:
        return self.session_dir(platform) / _STATE_FILE

    def is_connected(self, platform: str) -> bool:
        path = self.state_path(platform)
        return path.exists() and path.stat().st_size > 0

    def status(self, platform: str) -> ConnectionStatus:
        path = self.state_path(platform)
        if path.exists() and path.stat().st_size > 0:
            connected_at = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()
            return ConnectionStatus(
                platform=platform, status=STATUS_CONNECTED, connected_at=connected_at
            )
        return ConnectionStatus(platform=platform, status=STATUS_DISCONNECTED)

    def list_connections(self) -> List[ConnectionStatus]:
        return [self.status(p) for p in SUPPORTED_PLATFORMS]

    def clear(self, platform: str) -> bool:
        """セッション state を削除（切断）する。"""
        path = self.state_path(platform)
        if path.exists():
            path.unlink()
            return True
        return False

    def ensure_dir(self, platform: str) -> Path:
        """接続フローが storage_state を書き込めるようディレクトリを用意する。"""
        d = self.session_dir(platform)
        d.mkdir(parents=True, exist_ok=True)
        return d
