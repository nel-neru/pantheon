"""
Headless multiplexer driver.

No GUI: each agent runs as a plain subprocess whose stdout/stderr stream into a
per-agent log file under the session directory. This is the always-available
execution substrate — used in CI, in tests, and whenever no terminal
multiplexer app (wmux/cmux) is running. It still honours the same
session=workspace / agent=surface model so the orchestrator and dashboard work
identically with or without a GUI.
"""

from __future__ import annotations

import logging
import os
import re
import signal
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

from core.runtime.multiplexer.base import (
    AgentSpec,
    MultiplexerDriver,
    Surface,
    SurfaceStatus,
    Workspace,
)

logger = logging.getLogger(__name__)


def _slug(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", text).strip("-").lower() or "session"


def _pid_alive(pid: int) -> bool:
    """Best-effort liveness check for a pid (used for cross-process polling)."""
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            if kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return code.value == STILL_ACTIVE
            return False
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def _kill_pid(pid: int) -> bool:
    """Best-effort terminate a pid (used for cross-process ``stop_session``)."""
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        PROCESS_TERMINATE = 0x0001
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(PROCESS_TERMINATE, False, pid)
        if not handle:
            return False
        try:
            return bool(kernel32.TerminateProcess(handle, 1))
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, signal.SIGTERM)
        return True
    except (OSError, ProcessLookupError):
        return False


class HeadlessDriver(MultiplexerDriver):
    name = "headless"

    def __init__(self, log_root: Optional[os.PathLike] = None):
        # log_root defaults to the session dir passed per-surface via metadata.
        self._log_root = Path(log_root) if log_root else None
        self._procs: Dict[str, subprocess.Popen] = {}
        self._logs: Dict[str, "object"] = {}
        self._workspaces: Dict[str, Workspace] = {}
        self._counter = 0

    # -- lifecycle ---------------------------------------------------------- #
    def is_available(self) -> bool:
        return True

    def ensure_running(self) -> None:
        return None

    def create_workspace(self, name: str) -> Workspace:
        ws_id = f"hl-{_slug(name)}-{len(self._workspaces) + 1}"
        ws = Workspace(id=ws_id, name=name)
        self._workspaces[ws_id] = ws
        return ws

    def open_surface(self, workspace: Workspace, spec: AgentSpec) -> Surface:
        self._counter += 1
        surface_id = f"{workspace.id}.s{self._counter}"

        log_dir = Path(spec.metadata.get("log_dir") or self._log_root or Path.cwd())
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / f"{_slug(spec.agent_id)}-{self._counter}.log"

        surface = Surface(
            id=surface_id,
            title=spec.title,
            workspace_id=workspace.id,
            agent_id=spec.agent_id,
            cwd=spec.cwd,
            status=SurfaceStatus.RUNNING,
            log_path=str(log_path),
            metadata=dict(spec.metadata),
        )

        try:
            log_fh = open(log_path, "w", encoding="utf-8", errors="replace")
            log_fh.write(f"$ {subprocess.list2cmdline(list(spec.command))}\n\n")
            log_fh.flush()
            proc = subprocess.Popen(
                list(spec.command),
                stdout=log_fh,
                stderr=subprocess.STDOUT,
                cwd=spec.cwd,
                env=os.environ.copy(),
            )
            self._procs[surface_id] = proc
            self._logs[surface_id] = log_fh
            surface.pty_id = str(proc.pid)
        except OSError as exc:
            logger.warning("HeadlessDriver: failed to start %s: %s", spec.agent_id, exc)
            surface.status = SurfaceStatus.FAILED
            surface.exit_code = -1

        workspace.surfaces.append(surface)
        return surface

    def poll_surface(self, surface: Surface) -> Surface:
        proc = self._procs.get(surface.id)
        if proc is None:
            # Cross-process polling: no Popen handle here, fall back to the pid
            # we recorded as ``pty_id`` when the surface was opened.
            if surface.status in (
                SurfaceStatus.DONE,
                SurfaceStatus.FAILED,
                SurfaceStatus.CLOSED,
            ):
                return surface
            pid = int(surface.pty_id) if (surface.pty_id or "").isdigit() else 0
            if pid and _pid_alive(pid):
                surface.status = SurfaceStatus.RUNNING
            elif pid:
                # process gone; exit code unknown from another process
                if surface.status == SurfaceStatus.RUNNING:
                    surface.status = SurfaceStatus.DONE
            return surface
        code = proc.poll()
        if code is None:
            surface.status = SurfaceStatus.RUNNING
        else:
            surface.exit_code = code
            surface.status = SurfaceStatus.DONE if code == 0 else SurfaceStatus.FAILED
            self._flush_log(surface.id)
        return surface

    def close_surface(self, surface: Surface) -> None:
        proc = self._procs.get(surface.id)
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        elif proc is None:
            # クロスプロセス停止: Popen ハンドルが無い（web など別プロセスで起動した）
            # 場合は、open_surface で pty_id に保存した pid を使って終了させる。
            pid = int(surface.pty_id) if (surface.pty_id or "").isdigit() else 0
            if pid and _pid_alive(pid):
                _kill_pid(pid)
        self._flush_log(surface.id)
        if surface.status == SurfaceStatus.RUNNING:
            surface.status = SurfaceStatus.CLOSED

    def list_workspaces(self) -> List[Workspace]:
        return list(self._workspaces.values())

    # -- internals ---------------------------------------------------------- #
    def _flush_log(self, surface_id: str) -> None:
        fh = self._logs.pop(surface_id, None)
        if fh is not None:
            try:
                fh.flush()
                fh.close()
            except OSError:
                pass
