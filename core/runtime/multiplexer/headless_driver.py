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
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

from core.persistence import atomic_write_text
from core.runtime.multiplexer.base import (
    AgentSpec,
    MultiplexerDriver,
    Surface,
    SurfaceStatus,
    Workspace,
)
from core.runtime.process_utils import pid_alive, terminate_pid

logger = logging.getLogger(__name__)


def _slug(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", text).strip("-").lower() or "session"


def _exit_sidecar_path(surface: Surface) -> Optional[Path]:
    """Path of the exit-code sidecar colocated with the surface's log.

    Cross-process polling (``poll_surface`` reached from a process that did not
    open the surface) has no in-memory ``Popen`` to ``poll()``, so the only way
    to learn the *real* outcome is a file written by the owning process when it
    reaped the child. We key it off ``log_path`` because that is persisted in
    ``Surface.to_dict()`` and therefore reconstructable from another process.
    Returns ``None`` when the surface has no log path (no anchor to derive from).
    """
    if not surface.log_path:
        return None
    return Path(str(surface.log_path) + ".exit")


def _write_exit_sidecar(surface: Surface, code: int) -> None:
    """Record ``code`` so a different process can read the true exit status.

    Best effort: a failure here must never crash polling/closing — the worst
    case is falling back to the conservative "outcome unknown → FAILED" branch.
    """
    path = _exit_sidecar_path(surface)
    if path is None:
        return
    try:
        atomic_write_text(path, str(int(code)))
    except OSError as exc:  # pragma: no cover - defensive
        logger.debug("HeadlessDriver: could not write exit sidecar %s: %s", path, exc)


def _read_exit_sidecar(surface: Surface) -> Optional[int]:
    """Return the recorded exit code, or ``None`` if absent/unparseable."""
    path = _exit_sidecar_path(surface)
    if path is None:
        return None
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _pid_alive(pid: int) -> bool:
    """Best-effort liveness check for a pid (used for cross-process polling).

    Thin wrapper over the shared, Windows-safe implementation. Kept as a
    module-level name so tests can monkeypatch it deterministically.
    """
    return pid_alive(pid)


def _kill_pid(pid: int) -> bool:
    """Best-effort terminate a pid (used for cross-process ``stop_session``)."""
    return terminate_pid(pid)


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
            _write_exit_sidecar(surface, -1)

        workspace.surfaces.append(surface)
        return surface

    def poll_surface(self, surface: Surface) -> Surface:
        proc = self._procs.get(surface.id)
        if proc is None:
            # Cross-process polling: no Popen handle here. We cannot ``poll()`` a
            # child we did not spawn, so we never reaped its exit code. The only
            # trustworthy outcome source is the exit-code sidecar the owning
            # process wrote when it reaped the child.
            if surface.status in (
                SurfaceStatus.DONE,
                SurfaceStatus.FAILED,
                SurfaceStatus.CLOSED,
            ):
                return surface
            # Prefer the sidecar (authoritative terminal signal). Checking it
            # before pid liveness also avoids a pid-reuse false "running".
            recorded = _read_exit_sidecar(surface)
            if recorded is not None:
                surface.exit_code = recorded
                surface.status = SurfaceStatus.DONE if recorded == 0 else SurfaceStatus.FAILED
                return surface
            pid = int(surface.pty_id) if (surface.pty_id or "").isdigit() else 0
            if pid and _pid_alive(pid):
                surface.status = SurfaceStatus.RUNNING
            elif pid:
                # Process is gone but no exit code was ever recorded — its real
                # outcome is genuinely unknowable from here. Do NOT fabricate a
                # successful DONE (that silently hides crashes/non-zero exits);
                # fall to the safe side and report FAILED so the caller surfaces
                # it instead of treating the lost agent as completed work.
                if surface.status == SurfaceStatus.RUNNING:
                    logger.warning(
                        "HeadlessDriver: surface %s (pid %s) vanished with no exit "
                        "sidecar — reporting FAILED (outcome unknown)",
                        surface.id,
                        pid,
                    )
                    surface.status = SurfaceStatus.FAILED
            return surface
        code = proc.poll()
        if code is None:
            surface.status = SurfaceStatus.RUNNING
        else:
            surface.exit_code = code
            surface.status = SurfaceStatus.DONE if code == 0 else SurfaceStatus.FAILED
            # Persist the reaped exit code so a *different* process polling this
            # same surface later reads the true outcome instead of guessing.
            _write_exit_sidecar(surface, code)
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
            if proc.returncode is not None:
                # Record the reaped exit so a cross-process poll reads a definite
                # terminal outcome rather than the conservative FAILED fallback.
                _write_exit_sidecar(surface, proc.returncode)
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
