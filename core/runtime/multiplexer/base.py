"""
Multiplexer driver contract.

The orchestrator speaks only to :class:`MultiplexerDriver`; concrete drivers
(wmux / cmux / headless) implement how a session-workspace and per-agent
surfaces are actually created, run, monitored and torn down.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence


class MultiplexerUnavailableError(RuntimeError):
    """Raised when a requested multiplexer backend cannot be used."""


class SurfaceStatus:
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CLOSED = "closed"
    RATE_LIMITED = "rate_limited"   # hit a Claude usage limit; awaiting auto-resume


@dataclass
class AgentSpec:
    """One agent to run inside a session as its own surface (small tab)."""

    agent_id: str               # e.g. "agent:code_reviewer"
    title: str                  # short human label for the tab
    command: Sequence[str]      # argv to run (typically a `claude -p ...` invocation)
    cwd: Optional[str] = None
    role: str = "agent"
    metadata: Dict[str, str] = field(default_factory=dict)
    #: Optional pre-quoted shell command line. GUI drivers (wmux/cmux) type this
    #: into the surface's shell; if absent they quote ``command`` themselves.
    #: Headless always uses ``command``.
    shell_command: Optional[str] = None


@dataclass
class Surface:
    """A running agent's terminal (the "small tab")."""

    id: str
    title: str
    workspace_id: Optional[str] = None
    pty_id: Optional[str] = None
    agent_id: Optional[str] = None
    cwd: Optional[str] = None
    status: str = SurfaceStatus.PENDING
    exit_code: Optional[int] = None
    log_path: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "workspace_id": self.workspace_id,
            "pty_id": self.pty_id,
            "agent_id": self.agent_id,
            "cwd": self.cwd,
            "status": self.status,
            "exit_code": self.exit_code,
            "log_path": self.log_path,
            "metadata": self.metadata,
        }


@dataclass
class Workspace:
    """A session's container (the "big tab")."""

    id: str
    name: str
    surfaces: List[Surface] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "surfaces": [s.to_dict() for s in self.surfaces],
        }


class MultiplexerDriver(ABC):
    """Abstract terminal-multiplexer backend."""

    #: short identifier, e.g. "wmux", "cmux", "headless"
    name: str = "abstract"

    @abstractmethod
    def is_available(self) -> bool:
        """True when this backend can actually be driven right now."""

    @abstractmethod
    def ensure_running(self) -> None:
        """Start the backend if needed (no-op for headless)."""

    @abstractmethod
    def create_workspace(self, name: str) -> Workspace:
        """Create (or claim) the workspace that represents a session."""

    @abstractmethod
    def open_surface(self, workspace: Workspace, spec: AgentSpec) -> Surface:
        """Open a surface for an agent and start its command."""

    @abstractmethod
    def poll_surface(self, surface: Surface) -> Surface:
        """Refresh ``surface.status``/``exit_code`` from the backend."""

    @abstractmethod
    def close_surface(self, surface: Surface) -> None:
        """Close/terminate a finished agent's surface (auto tab removal)."""

    @abstractmethod
    def list_workspaces(self) -> List[Workspace]:
        """Return all live workspaces (for the dashboard)."""

    # -- optional helpers (drivers may override) ---------------------------- #
    def read_output(self, surface: Surface, tail: int = 4000) -> str:
        """Return recent output captured from the surface (best effort)."""
        if surface.log_path:
            try:
                with open(surface.log_path, "r", encoding="utf-8", errors="replace") as fh:
                    return fh.read()[-tail:]
            except OSError:
                return ""
        return ""

    def tag_surface(self, surface: Surface, **meta: Any) -> None:
        """Attach metadata to a surface (best effort)."""
        surface.metadata.update({k: v for k, v in meta.items() if v is not None})
