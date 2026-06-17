"""Regression: HeadlessDriver must not leak the log file handle on spawn failure.

`open_surface` opens the per-agent log file *before* it spawns the subprocess.
If `subprocess.Popen` raises (bad command, missing executable, resource
exhaustion), the handle was never stored in ``self._logs`` and is therefore
unreachable by ``_flush_log`` — so unless ``open_surface`` closes it on the
error path, every failed spawn leaks a file descriptor. In a 24/7 daemon that
retries failing commands this eventually exhausts the OS FD table.
"""

from __future__ import annotations

from core.runtime.multiplexer import headless_driver as hd
from core.runtime.multiplexer.base import AgentSpec, SurfaceStatus


def test_open_surface_closes_log_when_spawn_fails(tmp_path, monkeypatch):
    opened = []
    real_open = open  # builtin; hd.open is patched below, this stays unpatched

    def spy_open(*args, **kwargs):
        fh = real_open(*args, **kwargs)
        opened.append(fh)
        return fh

    # Only the log_fh in open_surface goes through the module's bare ``open``;
    # the exit sidecar uses atomic_write_text in a different module, so it is
    # not captured here.
    monkeypatch.setattr(hd, "open", spy_open, raising=False)

    def boom(*args, **kwargs):
        raise OSError("exec failed")

    monkeypatch.setattr(hd.subprocess, "Popen", boom)

    driver = hd.HeadlessDriver(log_root=tmp_path)
    ws = driver.create_workspace("t")
    spec = AgentSpec(agent_id="a", title="A", command=["nonexistent-command-xyz"])

    surface = driver.open_surface(ws, spec)

    assert surface.status == SurfaceStatus.FAILED
    assert surface.exit_code == -1
    assert opened, "expected the log file to be opened before the spawn attempt"
    assert all(fh.closed for fh in opened), "log handle leaked on spawn failure"
    # And the failed surface must not register a dangling log handle for cleanup.
    assert surface.id not in driver._logs
