"""Tests for the session orchestrator (session=workspace, agent=surface)."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import List

import pytest

from core.runtime.multiplexer.base import (
    AgentSpec,
    MultiplexerDriver,
    Surface,
    SurfaceStatus,
    Workspace,
)
from core.runtime.session_orchestrator import AgentTask, SessionOrchestrator, demo_tasks


class FakeDriver(MultiplexerDriver):
    """In-memory driver capturing what the orchestrator asks for."""

    name = "fake"

    def __init__(self):
        self.specs: List[AgentSpec] = []
        self.closed: List[str] = []
        self._counter = 0

    def is_available(self) -> bool:
        return True

    def ensure_running(self) -> None:
        return None

    def create_workspace(self, name: str) -> Workspace:
        return Workspace(id="ws-1", name=name)

    def open_surface(self, workspace: Workspace, spec: AgentSpec) -> Surface:
        self.specs.append(spec)
        self._counter += 1
        surface = Surface(
            id=f"{workspace.id}:s{self._counter}",
            title=spec.title,
            workspace_id=workspace.id,
            pty_id=str(1000 + self._counter),
            agent_id=spec.agent_id,
            cwd=spec.cwd,
            status=SurfaceStatus.RUNNING,
            log_path=spec.metadata.get("log_path"),
            metadata=dict(spec.metadata),
        )
        workspace.surfaces.append(surface)
        return surface

    def poll_surface(self, surface: Surface) -> Surface:
        surface.status = SurfaceStatus.DONE
        surface.exit_code = 0
        return surface

    def close_surface(self, surface: Surface) -> None:
        self.closed.append(surface.id)
        surface.status = SurfaceStatus.CLOSED

    def list_workspaces(self) -> List[Workspace]:
        return []


@pytest.fixture
def orch(tmp_path) -> SessionOrchestrator:
    return SessionOrchestrator(repo_root=tmp_path, driver=FakeDriver())


def test_start_session_persists_state_and_prompts(orch, tmp_path):
    tasks = [
        AgentTask(agent_id="agent:a", title="Alpha", prompt="do A", system_prompt="be terse"),
        AgentTask(agent_id="agent:b", title="Beta", prompt="do B"),
    ]
    rec = orch.start_session("My Session", tasks)

    session_dir = tmp_path / ".pantheon" / "sessions" / rec.id
    assert (session_dir / "session.json").exists()
    # prompts are written inside the repo for full management
    assert (session_dir / "agents" / "agent-a.prompt").read_text(encoding="utf-8") == "do A"
    assert (session_dir / "agents" / "agent-a.system").read_text(encoding="utf-8") == "be terse"
    assert not (session_dir / "agents" / "agent-b.system").exists()

    assert rec.driver == "fake"
    assert len(rec.surfaces) == 2
    assert {s["agent_id"] for s in rec.surfaces} == {"agent:a", "agent:b"}


def test_spec_has_both_argv_and_shell_command(orch):
    tasks = [AgentTask(agent_id="agent:a", title="Alpha", prompt="hello", model="claude-x")]
    orch.start_session("S", tasks)
    spec = orch._driver.specs[0]
    # argv for headless
    assert spec.command[0].lower().endswith("claude") or spec.command[0] == "claude"
    assert "--model" in spec.command and "claude-x" in spec.command
    # pwsh shell line for GUI drivers reads the prompt from a file and tees a log
    assert spec.shell_command is not None
    assert "Get-Content -Raw" in spec.shell_command
    assert "Tee-Object" in spec.shell_command


def test_get_and_list_sessions(orch):
    rec = orch.start_session("S", [AgentTask(agent_id="agent:a", title="A", prompt="p")])
    again = orch.get_session(rec.id)
    assert again is not None and again.id == rec.id
    listed = orch.list_sessions()
    assert [r.id for r in listed] == [rec.id]


def test_poll_marks_completed(orch):
    rec = orch.start_session("S", [AgentTask(agent_id="agent:a", title="A", prompt="p")])
    polled = orch.poll_session(rec.id)
    assert polled is not None
    assert polled.status == "completed"
    assert polled.surfaces[0]["status"] == SurfaceStatus.DONE
    assert polled.surfaces[0]["exit_code"] == 0


def test_stop_session_closes_surfaces(orch):
    rec = orch.start_session("S", [AgentTask(agent_id="agent:a", title="A", prompt="p")])
    stopped = orch.stop_session(rec.id)
    assert stopped is not None and stopped.status == "stopped"
    assert orch._driver.closed  # close_surface was called


def test_demo_tasks_shape():
    tasks = demo_tasks()
    assert len(tasks) >= 2
    assert all(t.prompt for t in tasks)


def test_rate_limit_detection_and_resume(tmp_path):
    """A failed agent whose log shows a usage limit is marked rate_limited and
    can be resumed (re-launched) once forced."""

    class RateLimitedDriver(FakeDriver):
        def poll_surface(self, surface: Surface) -> Surface:
            surface.status = SurfaceStatus.FAILED
            surface.exit_code = 1
            return surface

    driver = RateLimitedDriver()
    orch = SessionOrchestrator(repo_root=tmp_path, driver=driver)
    rec = orch.start_session("S", [AgentTask(agent_id="agent:a", title="A", prompt="hi")])

    log_path = Path(rec.surfaces[0]["log_path"])
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("Claude usage limit reached. Try again in 30 minutes.", encoding="utf-8")

    polled = orch.poll_session(rec.id)
    assert polled is not None
    assert polled.status == "rate_limited"
    assert polled.surfaces[0]["status"] == SurfaceStatus.RATE_LIMITED
    assert polled.surfaces[0]["retry_at"]

    resumed = orch.resume_session(rec.id, force=True)
    assert resumed is not None
    assert resumed.surfaces[0]["status"] == SurfaceStatus.RUNNING
    assert len(driver.specs) == 2  # initial launch + resume


def test_poll_done_surface_with_stats_429_stays_completed(orch):
    """完了済み agent の 1 行 JSON ログに数値由来の '429' が含まれても
    RATE_LIMITED に誤反転しない（完了済み仕事の再実行＝トークン二重消費を防ぐ）。"""
    rec = orch.start_session("S", [AgentTask(agent_id="agent:a", title="A", prompt="p")])
    log_path = Path(rec.surfaces[0]["log_path"])
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        json.dumps(
            {
                "type": "result",
                "result": "完了。3件の提案を生成しました。",
                "is_error": False,
                "duration_ms": 14290,
                "total_cost_usd": 0.0429,
                "session_id": "a4290b1c-9e7f-4a2d-8c3e-5f6a7b8c9d0e",
            }
        ),
        encoding="utf-8",
    )

    polled = orch.poll_session(rec.id)
    assert polled is not None
    assert polled.status == "completed"
    assert polled.surfaces[0]["status"] == SurfaceStatus.DONE


def test_poll_done_surface_with_limit_result_marked_rate_limited(orch):
    """CLI が exit 0 で制限を返すケース（is_error=true の result）は検知して
    RATE_LIMITED（自動 resume 対象）に倒す。"""
    rec = orch.start_session("S", [AgentTask(agent_id="agent:a", title="A", prompt="p")])
    log_path = Path(rec.surfaces[0]["log_path"])
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        json.dumps(
            {
                "type": "result",
                "is_error": True,
                "result": "You've hit your session limit · resets 3:20am (Asia/Tokyo)",
            }
        ),
        encoding="utf-8",
    )

    polled = orch.poll_session(rec.id)
    assert polled is not None
    assert polled.status == "rate_limited"
    assert polled.surfaces[0]["status"] == SurfaceStatus.RATE_LIMITED
    assert polled.surfaces[0]["retry_at"]


def test_headless_real_subprocess(tmp_path):
    """End-to-end with the real HeadlessDriver running a trivial process."""
    from core.runtime.multiplexer.headless_driver import HeadlessDriver

    driver = HeadlessDriver(log_root=tmp_path)
    ws = driver.create_workspace("hs")
    spec = AgentSpec(
        agent_id="agent:echo",
        title="echo",
        command=[sys.executable, "-c", "print('pantheon-ok')"],
        cwd=str(tmp_path),
        metadata={"log_dir": str(tmp_path)},
    )
    surface = driver.open_surface(ws, spec)
    assert surface.status == SurfaceStatus.RUNNING

    proc = driver._procs[surface.id]
    proc.wait(timeout=30)
    driver.poll_surface(surface)
    assert surface.status == SurfaceStatus.DONE
    assert surface.exit_code == 0
    log = Path(surface.log_path).read_text(encoding="utf-8")
    assert "pantheon-ok" in log


def _run_headless_to_exit(driver, ws, tmp_path, agent_id, exit_code):
    """Open a surface that exits with ``exit_code`` and wait for it (owning proc)."""
    spec = AgentSpec(
        agent_id=agent_id,
        title=agent_id,
        command=[sys.executable, "-c", f"import sys; sys.exit({exit_code})"],
        cwd=str(tmp_path),
        metadata={"log_dir": str(tmp_path)},
    )
    surface = driver.open_surface(ws, spec)
    driver._procs[surface.id].wait(timeout=30)
    return surface


def _cross_process_view(surface) -> Surface:
    """A RUNNING surface as a *fresh* process would reload it (no Popen handle)."""
    return Surface(
        id=surface.id,
        title=surface.title,
        workspace_id=surface.workspace_id,
        pty_id=surface.pty_id,
        agent_id=surface.agent_id,
        cwd=surface.cwd,
        status=SurfaceStatus.RUNNING,
        log_path=surface.log_path,
    )


def test_headless_owning_poll_writes_exit_sidecar(tmp_path):
    """When the owning process reaps the child, it records the real exit code."""
    from core.runtime.multiplexer.headless_driver import HeadlessDriver

    driver = HeadlessDriver(log_root=tmp_path)
    ws = driver.create_workspace("hs")
    surface = _run_headless_to_exit(driver, ws, tmp_path, "agent:ok", 0)
    driver.poll_surface(surface)
    assert surface.status == SurfaceStatus.DONE
    sidecar = Path(surface.log_path + ".exit")
    assert sidecar.exists() and sidecar.read_text(encoding="utf-8").strip() == "0"


def test_headless_cross_process_poll_reads_sidecar(tmp_path):
    """A fresh driver (no Popen handle) must read the true outcome from the
    sidecar — DONE for exit 0, FAILED for a non-zero exit — never guess."""
    from core.runtime.multiplexer.headless_driver import HeadlessDriver

    owner = HeadlessDriver(log_root=tmp_path)
    ws = owner.create_workspace("hs")

    ok = _run_headless_to_exit(owner, ws, tmp_path, "agent:ok", 0)
    bad = _run_headless_to_exit(owner, ws, tmp_path, "agent:bad", 7)
    owner.poll_surface(ok)  # writes sidecar "0"
    owner.poll_surface(bad)  # writes sidecar "7"

    fresh = HeadlessDriver(log_root=tmp_path)  # empty _procs == another process
    ok_view = fresh.poll_surface(_cross_process_view(ok))
    bad_view = fresh.poll_surface(_cross_process_view(bad))
    assert ok_view.status == SurfaceStatus.DONE and ok_view.exit_code == 0
    assert bad_view.status == SurfaceStatus.FAILED and bad_view.exit_code == 7


def test_headless_cross_process_poll_no_sidecar_reports_failed(tmp_path, monkeypatch):
    """The honesty fix: a vanished process with NO recorded exit code must NOT
    be fabricated as a successful DONE — its outcome is unknowable, so report
    FAILED so callers surface it instead of trusting lost work as completed.

    ``_pid_alive`` is forced False to model "process gone" deterministically on
    every OS (Windows pid-reuse semantics differ from POSIX, so we don't rely on
    them to prove the honesty behaviour)."""
    from core.runtime.multiplexer import headless_driver as hd

    owner = hd.HeadlessDriver(log_root=tmp_path)
    ws = owner.create_workspace("hs")
    # Reap the child in the owning driver but never call poll_surface, so no
    # sidecar is ever written.
    surface = _run_headless_to_exit(owner, ws, tmp_path, "agent:lost", 0)
    assert not Path(surface.log_path + ".exit").exists()

    monkeypatch.setattr(hd, "_pid_alive", lambda pid: False)
    fresh = hd.HeadlessDriver(log_root=tmp_path)
    view = fresh.poll_surface(_cross_process_view(surface))
    assert view.status == SurfaceStatus.FAILED  # NOT fabricated as DONE
    assert view.exit_code is None  # genuinely unknown


def test_headless_cross_process_poll_pid_alive_stays_running(tmp_path, monkeypatch):
    """A still-running cross-process surface (no sidecar, pid alive) must remain
    RUNNING — the FAILED fallback only fires once the process is actually gone."""
    from core.runtime.multiplexer import headless_driver as hd

    owner = hd.HeadlessDriver(log_root=tmp_path)
    ws = owner.create_workspace("hs")
    surface = _run_headless_to_exit(owner, ws, tmp_path, "agent:live", 0)

    monkeypatch.setattr(hd, "_pid_alive", lambda pid: True)
    fresh = hd.HeadlessDriver(log_root=tmp_path)
    view = fresh.poll_surface(_cross_process_view(surface))
    assert view.status == SurfaceStatus.RUNNING


# --------------------------------------------------------------------------- #
# Cross-process stop (close_surface with no in-memory Popen handle)
#
# stop_session reached from a process that did not open the surface (e.g. the
# web server stopping a session a daemon launched) has no Popen to ``terminate``,
# so close_surface must fall back to the pid persisted as ``pty_id`` and kill it
# via the Windows-safe ``terminate_pid``. The cross-process *poll* path is well
# covered above; these pin the cross-process *stop* path it relies on.
# --------------------------------------------------------------------------- #
def _spawn_long_running(driver, ws, tmp_path, agent_id: str) -> Surface:
    """Open a surface running a process that sleeps long enough to be killed."""
    spec = AgentSpec(
        agent_id=agent_id,
        title=agent_id,
        command=[sys.executable, "-c", "import time; time.sleep(30)"],
        cwd=str(tmp_path),
        metadata={"log_dir": str(tmp_path)},
    )
    surface = driver.open_surface(ws, spec)
    assert surface.status == SurfaceStatus.RUNNING
    return surface


def pid_alive_check(pid: int) -> bool:
    """Thin test-side wrapper over the shared liveness probe (readability)."""
    from core.runtime.process_utils import pid_alive

    return pid_alive(pid)


def _wait_pid_dead(pid: int, timeout: float = 10.0) -> bool:
    """Poll until ``pid`` is no longer alive (or ``timeout`` elapses)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not pid_alive_check(pid):
            return True
        time.sleep(0.05)
    return not pid_alive_check(pid)


def test_headless_cross_process_close_kills_real_process(tmp_path):
    """End-to-end: a fresh driver (no Popen handle) stopping a surface another
    process opened must actually terminate the real OS process via its pid, and
    flip a RUNNING surface to CLOSED."""
    from core.runtime.multiplexer import headless_driver as hd

    owner = hd.HeadlessDriver(log_root=tmp_path)
    ws = owner.create_workspace("hs")
    surface = _spawn_long_running(owner, ws, tmp_path, "agent:sleep")
    pid = int(surface.pty_id)
    assert pid_alive_check(pid)  # really running before the cross-process stop

    fresh = hd.HeadlessDriver(log_root=tmp_path)  # empty _procs == another process
    view = _cross_process_view(surface)
    fresh.close_surface(view)

    assert _wait_pid_dead(pid), "cross-process close_surface did not terminate the real process"
    assert view.status == SurfaceStatus.CLOSED
    # tidy the owning driver's still-open log/proc handles (process already gone).
    owner.close_surface(surface)


def test_headless_cross_process_close_issues_kill_when_alive(tmp_path, monkeypatch):
    """Deterministic branch pin: when the pid is alive, the cross-process close
    path issues exactly one ``terminate_pid`` for that pid (no Popen needed)."""
    from core.runtime.multiplexer import headless_driver as hd

    owner = hd.HeadlessDriver(log_root=tmp_path)
    ws = owner.create_workspace("hs")
    surface = _run_headless_to_exit(owner, ws, tmp_path, "agent:gone", 0)
    pid = int(surface.pty_id)

    killed: list[int] = []
    monkeypatch.setattr(hd, "_pid_alive", lambda p: True)
    monkeypatch.setattr(hd, "_kill_pid", lambda p: killed.append(p) or True)

    fresh = hd.HeadlessDriver(log_root=tmp_path)
    view = _cross_process_view(surface)
    fresh.close_surface(view)

    assert killed == [pid]  # killed exactly the persisted pid
    assert view.status == SurfaceStatus.CLOSED
    owner.close_surface(surface)  # close the owning driver's log handle (proc already reaped)


def test_headless_cross_process_close_skips_kill_when_pid_dead(tmp_path, monkeypatch):
    """Deterministic branch pin: when the pid is already gone, the close path must
    NOT issue a kill — guarding against terminating an unrelated, pid-reused
    process (mirrors the pid-reuse caution on the poll path)."""
    from core.runtime.multiplexer import headless_driver as hd

    owner = hd.HeadlessDriver(log_root=tmp_path)
    ws = owner.create_workspace("hs")
    surface = _run_headless_to_exit(owner, ws, tmp_path, "agent:dead", 0)

    killed: list[int] = []
    monkeypatch.setattr(hd, "_pid_alive", lambda p: False)
    monkeypatch.setattr(hd, "_kill_pid", lambda p: killed.append(p) or True)

    fresh = hd.HeadlessDriver(log_root=tmp_path)
    view = _cross_process_view(surface)
    fresh.close_surface(view)

    assert killed == []  # no needless kill of a vanished/pid-reused process
    assert view.status == SurfaceStatus.CLOSED
    owner.close_surface(surface)  # close the owning driver's log handle (proc already reaped)


def test_stop_session_cross_process_terminates_real_subprocess(tmp_path):
    """Realistic flow: orchestrator A starts a session backed by a real
    subprocess; a *separate* orchestrator B (driver=None, so it reattaches a
    fresh HeadlessDriver) stops it. The OS process must die and the persisted
    session must record status=stopped with the surface CLOSED."""
    from core.runtime.multiplexer.headless_driver import HeadlessDriver

    owner_driver = HeadlessDriver(log_root=tmp_path)
    orch_a = SessionOrchestrator(repo_root=tmp_path, driver=owner_driver)
    rec = orch_a.start_command_session(
        "cross-stop",
        [sys.executable, "-c", "import time; time.sleep(30)"],
        agent_id="work:sleeper",
    )
    pid = int(rec.surfaces[0]["pty_id"])
    assert pid_alive_check(pid)
    assert rec.driver == "headless"  # B will reattach a headless driver from this

    # Fresh orchestrator standing in for another process: no injected driver, so
    # stop_session goes through _reattach_driver -> a brand-new HeadlessDriver.
    orch_b = SessionOrchestrator(repo_root=tmp_path)
    stopped = orch_b.stop_session(rec.id)

    assert stopped is not None and stopped.status == "stopped"
    assert stopped.surfaces[0]["status"] == SurfaceStatus.CLOSED
    assert _wait_pid_dead(pid), "stop_session did not terminate the cross-process subprocess"
    # persisted state on disk reflects the stop (a third process would read this).
    reloaded = SessionOrchestrator(repo_root=tmp_path).get_session(rec.id)
    assert reloaded is not None and reloaded.status == "stopped"
    # tidy the owning driver's still-open handles (process already terminated).
    for proc in list(owner_driver._procs.values()):
        try:
            proc.wait(timeout=5)
        except Exception:  # noqa: BLE001
            pass
    for surface_id in list(owner_driver._logs):
        owner_driver._flush_log(surface_id)
