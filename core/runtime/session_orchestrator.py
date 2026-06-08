"""
Session orchestrator — "session = big tab, agent = small tab".

A Pantheon **session** is a unit of work (an org's improvement cycle, a goal, a
review) that maps to a multiplexer **workspace**. Each **agent** in the session
maps to a **surface** (small tab) running a headless ``claude`` invocation.

The orchestrator is driver-agnostic: it drives whatever
:class:`~core.runtime.multiplexer.base.MultiplexerDriver` the factory selects
(wmux on Windows, cmux on macOS, or the headless substrate), and falls back to
headless automatically when the GUI multiplexer is present but not yet usable
(e.g. wmux hasn't approved Pantheon). All session state lives **inside the
repository** under ``<repo>/.pantheon/sessions/<id>/`` so it is fully managed and
inspectable:

    .pantheon/sessions/<id>/
        session.json            # session + agent records (status, exit codes)
        agents/<agent>.prompt    # the prompt handed to that agent's claude
        agents/<agent>.system    # the appended system prompt (if any)
        agents/<agent>.log       # streamed stdout/stderr of the agent
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.runtime.claude_code import claude_binary
from core.runtime.multiplexer import (
    AgentSpec,
    MultiplexerUnavailableError,
    Surface,
    SurfaceStatus,
    Workspace,
    get_driver,
)
from core.runtime.multiplexer.headless_driver import HeadlessDriver
from core.runtime.rate_limit import detect_rate_limit

logger = logging.getLogger(__name__)

STATE_DIRNAME = ".pantheon"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _now_dt() -> datetime:
    return datetime.now(timezone.utc)


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _slug(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", text or "").strip("-").lower() or "session"


def _read_log(path: Path) -> str:
    """Read an agent log, tolerating UTF-8 (headless) or UTF-16 (PowerShell
    ``Tee-Object`` writes UTF-16LE by default in the wmux shell)."""
    try:
        raw = path.read_bytes()
    except OSError:
        return ""
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        return raw.decode("utf-16", errors="replace")
    # Heuristic: lots of interleaved NULs => UTF-16 without BOM.
    if raw[:2000].count(b"\x00") > len(raw[:2000]) // 4:
        return raw.decode("utf-16-le", errors="replace")
    return raw.decode("utf-8", errors="replace")


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #
@dataclass
class AgentTask:
    """One agent's work within a session."""

    agent_id: str
    title: str
    prompt: str
    system_prompt: Optional[str] = None
    model: Optional[str] = None
    role: str = "agent"
    cwd: Optional[str] = None
    stream_json: bool = True


@dataclass
class SessionRecord:
    """Persisted state of a session (serialised to ``session.json``)."""

    id: str
    name: str
    repo_root: str
    driver: str
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    status: str = "running"
    workspace: Dict[str, Any] = field(default_factory=dict)
    surfaces: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "repo_root": self.repo_root,
            "driver": self.driver,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "status": self.status,
            "workspace": self.workspace,
            "surfaces": self.surfaces,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SessionRecord":
        return cls(
            id=d["id"],
            name=d.get("name", d["id"]),
            repo_root=d.get("repo_root", ""),
            driver=d.get("driver", "headless"),
            created_at=d.get("created_at", _now()),
            updated_at=d.get("updated_at", _now()),
            status=d.get("status", "unknown"),
            workspace=d.get("workspace", {}),
            surfaces=d.get("surfaces", []),
        )


# --------------------------------------------------------------------------- #
# Orchestrator
# --------------------------------------------------------------------------- #
class SessionOrchestrator:
    def __init__(
        self,
        repo_root: Optional[os.PathLike] = None,
        *,
        driver=None,
        prefer: Optional[str] = None,
    ):
        self.repo_root = Path(repo_root or Path.cwd()).resolve()
        self.sessions_dir = self.repo_root / STATE_DIRNAME / "sessions"
        self._driver = driver
        self._prefer = prefer

    # -- driver ------------------------------------------------------------- #
    def _driver_for(self, log_root: Path):
        if self._driver is not None:
            return self._driver
        return get_driver(self._prefer, log_root=log_root)

    # -- public API --------------------------------------------------------- #
    def start_session(self, name: str, tasks: List[AgentTask]) -> SessionRecord:
        """Create the session workspace and launch every agent as a surface."""
        sid = f"{_slug(name)}-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
        session_dir = self.sessions_dir / sid
        agents_dir = session_dir / "agents"
        agents_dir.mkdir(parents=True, exist_ok=True)

        driver = self._driver_for(agents_dir)

        # Create the session workspace (big tab); fall back to headless if the
        # GUI multiplexer is present but not usable yet.
        try:
            driver.ensure_running()
            workspace = driver.create_workspace(name)
        except MultiplexerUnavailableError as exc:
            logger.warning("multiplexer unavailable (%s) — using headless", exc)
            driver = HeadlessDriver(log_root=agents_dir)
            self._driver = driver
            workspace = driver.create_workspace(name)

        record = SessionRecord(
            id=sid,
            name=name,
            repo_root=str(self.repo_root),
            driver=driver.name,
            workspace=workspace.to_dict(),
        )

        for task in tasks:
            spec = self._build_spec(task, agents_dir)
            surface = driver.open_surface(workspace, spec)
            record.surfaces.append(self._surface_record(task, surface))

        self._persist(record)
        return record

    def open_command_surface(
        self,
        group: str,
        title: str,
        command: List[str],
        *,
        agent_id: Optional[str] = None,
        role: str = "interactive",
        cwd: Optional[str] = None,
        require_gui: bool = True,
    ) -> Surface:
        """Open an arbitrary **interactive** command (e.g. a chat REPL) as a surface.

        Unlike :meth:`start_session` — which runs headless ``claude`` one-shots and
        persists a session — this types ``command`` into a fresh GUI multiplexer tab
        (``"<group> · <title>"``) so the user can interact with it: a REPL needs a
        real TTY. When only the headless substrate is available there is no
        interactive terminal, so this raises
        :class:`~core.runtime.multiplexer.MultiplexerUnavailableError` and the caller
        should tell the user to run ``command`` in their own terminal.
        """
        driver = self._driver_for(self.sessions_dir / "_interactive")
        if require_gui and isinstance(driver, HeadlessDriver):
            raise MultiplexerUnavailableError(
                "対話タブには GUI マルチプレクサ（wmux）が必要です。"
            )
        driver.ensure_running()
        workspace = driver.create_workspace(group)
        spec = AgentSpec(
            agent_id=agent_id or f"cmd:{_slug(title)}",
            title=title,
            command=list(command),
            cwd=cwd or str(self.repo_root),
            role=role,
        )
        return driver.open_surface(workspace, spec)

    def poll_session(self, sid: str) -> Optional[SessionRecord]:
        """Refresh agent statuses from the driver and re-persist."""
        record = self.get_session(sid)
        if record is None:
            return None
        driver = self._reattach_driver(record)
        all_done = True
        rate_limited = False
        for sr in record.surfaces:
            if sr.get("status") == SurfaceStatus.RATE_LIMITED:
                rate_limited = True
                all_done = False
                continue
            surface = self._surface_from_record(sr)
            try:
                driver.poll_surface(surface)
            except Exception as exc:  # pragma: no cover - defensive
                logger.debug("poll_surface failed: %s", exc)
            sr["status"] = surface.status
            sr["exit_code"] = surface.exit_code
            # A failed agent may have simply hit a usage limit — mark it for
            # automatic resume rather than treating it as a hard failure.
            if surface.status == SurfaceStatus.FAILED:
                info = detect_rate_limit(self._read_surface_log(sr))
                if info.limited:
                    sr["status"] = SurfaceStatus.RATE_LIMITED
                    sr["retry_at"] = info.reset_at.isoformat() if info.reset_at else None
                    sr["rate_limit_scope"] = info.scope
                    rate_limited = True
            if sr["status"] not in (
                SurfaceStatus.DONE, SurfaceStatus.FAILED, SurfaceStatus.CLOSED,
            ):
                all_done = False
        if rate_limited:
            record.status = "rate_limited"
        elif all_done:
            record.status = "completed"
        else:
            record.status = "running"
        record.updated_at = _now()
        self._persist(record)
        return record

    def resume_session(self, sid: str, *, force: bool = False) -> Optional[SessionRecord]:
        """Re-launch agents that hit a usage limit once their reset time passes.

        With ``force`` the reset time is ignored. Prompts are reconstructed from
        the per-agent files persisted under the session directory.
        """
        record = self.get_session(sid)
        if record is None:
            return None
        agents_dir = self.sessions_dir / sid / "agents"
        driver = self._driver_for(agents_dir)
        workspace = Workspace(
            id=(record.workspace or {}).get("id") or f"session:{record.name}",
            name=record.name,
        )
        now = _now_dt()
        resumed = 0
        for sr in record.surfaces:
            if sr.get("status") != SurfaceStatus.RATE_LIMITED:
                continue
            retry_at = _parse_dt(sr.get("retry_at"))
            if not force and retry_at and retry_at > now:
                continue
            task = self._task_from_record(sr, agents_dir)
            if task is None:
                continue
            try:
                driver.ensure_running()
            except MultiplexerUnavailableError:
                driver = HeadlessDriver(log_root=agents_dir)
                self._driver = driver
            spec = self._build_spec(task, agents_dir)
            surface = driver.open_surface(workspace, spec)
            sr.update(self._surface_record(task, surface))
            sr["status"] = surface.status
            sr.pop("retry_at", None)
            resumed += 1
        record.driver = driver.name
        if resumed:
            record.status = "running"
        record.updated_at = _now()
        self._persist(record)
        return record

    def due_for_resume(self, sid: str) -> int:
        """How many of the session's agents are rate-limited and past their reset."""
        record = self.get_session(sid)
        if record is None:
            return 0
        now = _now_dt()
        count = 0
        for sr in record.surfaces:
            if sr.get("status") != SurfaceStatus.RATE_LIMITED:
                continue
            retry_at = _parse_dt(sr.get("retry_at"))
            if retry_at is None or retry_at <= now:
                count += 1
        return count

    def stop_session(self, sid: str) -> Optional[SessionRecord]:
        record = self.get_session(sid)
        if record is None:
            return None
        driver = self._reattach_driver(record)
        for sr in record.surfaces:
            surface = self._surface_from_record(sr)
            try:
                driver.close_surface(surface)
            except Exception as exc:  # pragma: no cover - defensive
                logger.debug("close_surface failed: %s", exc)
            sr["status"] = surface.status
        record.status = "stopped"
        record.updated_at = _now()
        self._persist(record)
        return record

    def list_sessions(self) -> List[SessionRecord]:
        out: List[SessionRecord] = []
        if not self.sessions_dir.exists():
            return out
        for child in sorted(self.sessions_dir.iterdir()):
            rec = self.get_session(child.name)
            if rec is not None:
                out.append(rec)
        return out

    def get_session(self, sid: str) -> Optional[SessionRecord]:
        path = self.sessions_dir / sid / "session.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return SessionRecord.from_dict(data)

    def agent_log(self, sid: str, agent_id: str, tail: int = 8000) -> str:
        rec = self.get_session(sid)
        if rec is None:
            return ""
        for sr in rec.surfaces:
            if sr.get("agent_id") == agent_id:
                log_path = sr.get("log_path")
                if log_path and Path(log_path).exists():
                    return _read_log(Path(log_path))[-tail:]
        return ""

    # -- internals ---------------------------------------------------------- #
    def _build_spec(self, task: AgentTask, agents_dir: Path) -> AgentSpec:
        slug = _slug(task.agent_id)
        prompt_file = agents_dir / f"{slug}.prompt"
        prompt_file.write_text(task.prompt, encoding="utf-8")
        sys_file: Optional[Path] = None
        if task.system_prompt:
            sys_file = agents_dir / f"{slug}.system"
            sys_file.write_text(task.system_prompt, encoding="utf-8")
        log_file = agents_dir / f"{slug}.log"

        binary = claude_binary() or "claude"
        out_fmt = "stream-json" if task.stream_json else "json"
        model = task.model or os.getenv("PANTHEON_DEFAULT_MODEL")

        # argv for the headless driver (it captures stdout to the log itself).
        argv: List[str] = [binary, "-p", task.prompt, "--output-format", out_fmt]
        if task.stream_json:
            argv += ["--verbose"]
        if task.system_prompt:
            argv += ["--append-system-prompt", task.system_prompt]
        if model:
            argv += ["--model", model]

        # pwsh command line for GUI drivers: read prompt/system from files (avoids
        # quoting a huge prompt) and tee the stream to the per-agent log.
        shell_command = self._pwsh_command(
            binary, prompt_file, sys_file, model, out_fmt, log_file,
        )

        return AgentSpec(
            agent_id=task.agent_id,
            title=task.title,
            command=argv,
            cwd=task.cwd or str(self.repo_root),
            role=task.role,
            shell_command=shell_command,
            metadata={"log_dir": str(agents_dir), "log_path": str(log_file)},
        )

    @staticmethod
    def _pwsh_command(binary, prompt_file, sys_file, model, out_fmt, log_file) -> str:
        def q(p) -> str:
            return "'" + str(p).replace("'", "''") + "'"

        parts = [
            f"& {q(binary)} -p (Get-Content -Raw {q(prompt_file)})",
            f"--output-format {out_fmt}",
        ]
        if out_fmt == "stream-json":
            parts.append("--verbose")
        if sys_file is not None:
            parts.append(f"--append-system-prompt (Get-Content -Raw {q(sys_file)})")
        if model:
            parts.append(f"--model {q(model)}")
        parts.append(f"2>&1 | Tee-Object -FilePath {q(log_file)}")
        return " ".join(parts)

    def _surface_record(self, task: AgentTask, surface: Surface) -> Dict[str, Any]:
        d = surface.to_dict()
        d["agent_id"] = task.agent_id
        d["title"] = task.title
        d["role"] = task.role
        d["model"] = task.model
        d["stream_json"] = task.stream_json
        d["log_path"] = surface.log_path or surface.metadata.get("log_path")
        return d

    @staticmethod
    def _surface_from_record(sr: Dict[str, Any]) -> Surface:
        return Surface(
            id=sr.get("id"),
            title=sr.get("title", ""),
            workspace_id=sr.get("workspace_id"),
            pty_id=sr.get("pty_id"),
            agent_id=sr.get("agent_id"),
            cwd=sr.get("cwd"),
            status=sr.get("status", SurfaceStatus.PENDING),
            exit_code=sr.get("exit_code"),
            log_path=sr.get("log_path"),
            metadata=sr.get("metadata", {}),
        )

    def _reattach_driver(self, record: SessionRecord):
        """Return a driver capable of polling ``record`` from a fresh process."""
        if self._driver is not None:
            return self._driver
        if record.driver in ("wmux", "cmux"):
            # GUI drivers are stateless across processes (state lives in the app).
            try:
                drv = get_driver(record.driver)
                if drv.name == record.driver:
                    return drv
            except Exception:  # pragma: no cover - defensive
                pass
        # headless: polling reconstructs liveness from the pid stored as pty_id.
        return HeadlessDriver(log_root=self.sessions_dir / record.id / "agents")

    def _read_surface_log(self, sr: Dict[str, Any]) -> str:
        log_path = sr.get("log_path") or (sr.get("metadata") or {}).get("log_path")
        if log_path and Path(log_path).exists():
            return _read_log(Path(log_path))
        return ""

    def _task_from_record(self, sr: Dict[str, Any], agents_dir: Path) -> Optional[AgentTask]:
        agent_id = sr.get("agent_id")
        if not agent_id:
            return None
        slug = _slug(agent_id)
        prompt_file = agents_dir / f"{slug}.prompt"
        if not prompt_file.exists():
            return None
        try:
            prompt = prompt_file.read_text(encoding="utf-8")
        except OSError:
            return None
        sys_file = agents_dir / f"{slug}.system"
        system = None
        if sys_file.exists():
            try:
                system = sys_file.read_text(encoding="utf-8")
            except OSError:
                system = None
        return AgentTask(
            agent_id=agent_id,
            title=sr.get("title", agent_id),
            prompt=prompt,
            system_prompt=system,
            model=sr.get("model"),
            role=sr.get("role", "agent"),
            cwd=sr.get("cwd"),
            stream_json=sr.get("stream_json", True),
        )

    def _persist(self, record: SessionRecord) -> None:
        session_dir = self.sessions_dir / record.id
        session_dir.mkdir(parents=True, exist_ok=True)
        (session_dir / "session.json").write_text(
            json.dumps(record.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


# --------------------------------------------------------------------------- #
# Demo / convenience builders
# --------------------------------------------------------------------------- #
def demo_tasks() -> List[AgentTask]:
    """A tiny, dependency-free session for verifying orchestration end-to-end."""
    return [
        AgentTask(
            agent_id="agent:greeter",
            title="Greeter",
            prompt="Say hello as the Pantheon greeter agent in one short sentence.",
            role="demo",
            stream_json=False,
        ),
        AgentTask(
            agent_id="agent:summarizer",
            title="Summarizer",
            prompt="In one sentence, describe what an AI agent orchestrator does.",
            role="demo",
            stream_json=False,
        ),
    ]
