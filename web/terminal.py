"""
terminal — 埋め込みターミナル(PTY)のセッション管理（cmux 風ワークスペースの中核）

実シェル/外部CLIを PTY 上で起動し、WebSocket 経由でブラウザの xterm.js と双方向接続する。
ワークスペース(タブ)ごとに 1 セッション。git ブランチ/cwd/状態/通知(エージェント待ちの青リング)を
メタとして提供する。

セキュリティ: localhost 限定（呼び出し側でクライアントホストを検証する想定）。Unix(PTY)前提。
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import shlex
import signal
import struct
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

try:  # PTY は POSIX 専用。Windows では未対応（C5）。
    import fcntl
    import termios

    _PTY_AVAILABLE = os.name != "nt"
except ImportError:  # pragma: no cover - Windows 環境
    fcntl = None  # type: ignore[assignment]
    termios = None  # type: ignore[assignment]
    _PTY_AVAILABLE = False

_SCROLLBACK_CAP = 200_000  # 1セッションあたりの保持出力(バイト)
_DEFAULT_IDLE_TTL = 3600.0  # 購読者ゼロの running セッションをこの秒数で回収（C1）
_DEFAULT_EXITED_TTL = 300.0  # exited セッションをこの秒数で回収（C1）


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if raw:
        try:
            return float(raw)
        except ValueError:
            pass
    return default
# "testclient" は Starlette TestClient のセンチネルホスト（ネットワーク到達不可）。
_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient", ""}


def is_loopback_host(host: Optional[str]) -> bool:
    """クライアントホストがループバックか（ターミナルは localhost 限定）。"""
    if host is None:
        return True
    return host in _LOOPBACK_HOSTS or host.startswith("127.")


def is_allowed_origin(origin: Optional[str]) -> bool:
    """WebSocket の Origin ヘッダがループバック由来か（DNS リバインディング対策）。

    Origin が無い（非ブラウザクライアント）場合は許可し、別途クライアントホストで判定する。
    """
    if not origin:
        return True
    from urllib.parse import urlparse

    try:
        host = urlparse(origin).hostname
    except ValueError:
        return False
    return is_loopback_host(host)


class TerminalSession:
    """1つの PTY セッション（= cmux のワークスペース1つ）。"""

    def __init__(self, session_id: str, name: str, command: List[str], cwd: Path):
        self.id = session_id
        self.name = name
        self.command = command
        self.cwd = cwd
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.last_activity = time.monotonic()  # 最終活動時刻（アイドルGC用, C1）
        self.status = "running"
        self.exit_code: Optional[int] = None
        self.notification = False  # エージェント待ち等の通知(青リング)
        self.scrollback = bytearray()
        self._subscribers: set[asyncio.Queue] = set()
        self._reader_added = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None

        env = dict(os.environ)
        env.setdefault("TERM", "xterm-256color")
        env["REPOCORP_TERMINAL"] = "1"

        self.master_fd, slave_fd = pty_openpty()
        self.proc = subprocess.Popen(  # noqa: S603 — ローカル開発用の実シェル(設計上の意図)
            command,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            cwd=str(cwd),
            env=env,
            start_new_session=True,
            close_fds=True,
        )
        os.close(slave_fd)
        os.set_blocking(self.master_fd, False)

    # --- 出力リーダー（イベントループに登録） --- #

    def start_reader(self, loop: asyncio.AbstractEventLoop) -> None:
        if self._reader_added:
            return
        with contextlib.suppress(Exception):
            loop.add_reader(self.master_fd, self._on_readable)
            self._loop = loop
            self._reader_added = True

    def touch(self) -> None:
        """最終活動時刻を更新する（アイドルGC用, C1）。"""
        self.last_activity = time.monotonic()

    def has_subscribers(self) -> bool:
        return bool(self._subscribers)

    def _on_readable(self) -> None:
        try:
            data = os.read(self.master_fd, 65536)
        except BlockingIOError:
            return
        except OSError:
            data = b""
        if not data:
            self._handle_exit()
            return
        self.touch()
        self.scrollback += data
        if len(self.scrollback) > _SCROLLBACK_CAP:
            del self.scrollback[: len(self.scrollback) - _SCROLLBACK_CAP]
        if b"\x07" in data:  # BEL = エージェントの注意喚起 → 通知
            self.notification = True
        for queue in list(self._subscribers):
            queue.put_nowait(("data", data))

    def _handle_exit(self) -> None:
        if self.status == "exited":
            return
        self.status = "exited"
        self.exit_code = self.proc.poll()
        self.notification = True
        if self._loop is not None:
            with contextlib.suppress(Exception):
                self._loop.remove_reader(self.master_fd)
        self._reader_added = False
        for queue in list(self._subscribers):
            queue.put_nowait(("exit", self.exit_code))

    # --- 購読(WebSocket attach) --- #

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers.add(queue)
        self.notification = False  # タブを開いたら通知を消す
        self.touch()
        return queue

    def rename(self, name: str) -> None:
        """ワークスペース名を変更する（C11）。空文字は無視。"""
        name = (name or "").strip()
        if name:
            self.name = name

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.discard(queue)

    # --- 入出力 --- #

    def write(self, data: str) -> None:
        if self.status != "running":
            return
        self.touch()
        try:
            os.write(self.master_fd, data.encode("utf-8"))
        except OSError:
            self._handle_exit()

    def resize(self, rows: int, cols: int) -> None:
        if not _PTY_AVAILABLE:
            return
        self.touch()
        with contextlib.suppress(OSError, ValueError):
            fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))

    def kill(self) -> None:
        with contextlib.suppress(ProcessLookupError, OSError):
            os.killpg(os.getpgid(self.proc.pid), signal.SIGTERM)
        self._handle_exit()
        with contextlib.suppress(OSError):
            os.close(self.master_fd)

    # --- メタ --- #

    def alive(self) -> bool:
        return self.proc.poll() is None

    def git_branch(self) -> Optional[str]:
        head = self.cwd / ".git" / "HEAD"
        try:
            text = head.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        if text.startswith("ref:"):
            return text.rsplit("/", 1)[-1]
        return text[:8] or None

    def meta(self) -> Dict[str, Any]:
        if self.status == "running" and not self.alive():
            self._handle_exit()
        return {
            "id": self.id,
            "name": self.name,
            "cwd": str(self.cwd),
            "command": self.command,
            "status": self.status,
            "exit_code": self.exit_code,
            "git_branch": self.git_branch(),
            "created_at": self.created_at,
            "waiting": bool(self.notification),
        }


def pty_openpty():
    """pty.openpty() の薄いラッパ（テストでのモック差し替え用）。"""
    import pty

    return pty.openpty()


class TerminalManager:
    """PTY セッションのコレクション。"""

    def __init__(self, default_cwd: Optional[Path] = None, max_sessions: int = 20):
        self._sessions: Dict[str, TerminalSession] = {}
        self._default_cwd = Path(default_cwd) if default_cwd else Path.cwd()
        self._max_sessions = max_sessions

    def _resolve_command(
        self,
        command: Optional[str],
        cli_tool: Optional[str],
        settings: Optional[Dict[str, Any]],
    ) -> List[str]:
        if cli_tool:
            from core.execution.cli_registry import resolve_cli_command

            resolved = resolve_cli_command(cli_tool, settings)
            if not resolved:
                raise ValueError(f"未知の CLI ツール: {cli_tool}")
            return [resolved]
        if command and command.strip():
            return shlex.split(command)
        shell = os.environ.get("SHELL") or "/bin/bash"
        return [shell, "-i"]

    def create(
        self,
        name: Optional[str] = None,
        cwd: Optional[str] = None,
        command: Optional[str] = None,
        cli_tool: Optional[str] = None,
        settings: Optional[Dict[str, Any]] = None,
    ) -> TerminalSession:
        if not _PTY_AVAILABLE:
            raise ValueError("埋め込みターミナルは Windows 未対応です（PTY/POSIX が必要, C5）。")
        self.gc()  # 残留セッションを機会的に回収（C1）
        if len([s for s in self._sessions.values() if s.status == "running"]) >= self._max_sessions:
            raise ValueError(f"同時セッション数の上限({self._max_sessions})に達しています。")
        work_dir = Path(cwd).expanduser() if cwd else self._default_cwd
        if not work_dir.is_dir():
            raise ValueError(f"cwd が存在しません: {work_dir}")
        argv = self._resolve_command(command, cli_tool, settings)
        session_id = uuid4().hex[:12]
        display_name = name or (cli_tool or argv[0])
        session = TerminalSession(session_id, display_name, argv, work_dir)
        self._sessions[session_id] = session
        return session

    def get(self, session_id: str) -> Optional[TerminalSession]:
        return self._sessions.get(session_id)

    def list(self) -> List[Dict[str, Any]]:
        self.gc()  # ポーリングのたびに残留を機会的に回収（C1）
        return [s.meta() for s in self._sessions.values()]

    def rename(self, session_id: str, name: str) -> bool:
        """セッション名を変更する（C11）。存在しなければ False。"""
        session = self._sessions.get(session_id)
        if session is None:
            return False
        session.rename(name)
        return True

    def gc(self, idle_ttl: Optional[float] = None, exited_ttl: Optional[float] = None) -> int:
        """残留セッションを回収する（C1）。

        - exited セッション: 最終活動から `exited_ttl` 秒経過で削除（プロセスは既に終了）。
        - running セッション: 購読者ゼロかつ `idle_ttl` 秒アイドルなら kill して削除。
        環境変数 `REPOCORP_TERMINAL_IDLE_TTL` / `REPOCORP_TERMINAL_EXITED_TTL` で上書き可。
        回収したセッション数を返す。
        """
        idle_ttl = idle_ttl if idle_ttl is not None else _env_float("REPOCORP_TERMINAL_IDLE_TTL", _DEFAULT_IDLE_TTL)
        exited_ttl = exited_ttl if exited_ttl is not None else _env_float("REPOCORP_TERMINAL_EXITED_TTL", _DEFAULT_EXITED_TTL)
        now = time.monotonic()
        removed = 0
        for session_id, session in list(self._sessions.items()):
            if session.status == "running" and not session.alive():
                session._handle_exit()
            idle = now - session.last_activity
            if session.status == "exited" and idle > exited_ttl:
                self._sessions.pop(session_id, None)
                removed += 1
            elif (
                session.status == "running"
                and not session.has_subscribers()
                and idle > idle_ttl
            ):
                session.kill()
                self._sessions.pop(session_id, None)
                removed += 1
        return removed

    def kill(self, session_id: str) -> bool:
        session = self._sessions.pop(session_id, None)
        if session is None:
            return False
        session.kill()
        return True

    def shutdown(self) -> None:
        for session in list(self._sessions.values()):
            session.kill()
        self._sessions.clear()
