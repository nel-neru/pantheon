"""Tests for the session orchestrator (session=workspace, agent=surface)."""

from __future__ import annotations

import sys
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
