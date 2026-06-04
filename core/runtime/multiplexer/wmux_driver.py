"""
wmux multiplexer driver (Windows).

Maps the Pantheon session model onto the wmux app control endpoint using
wmux's native **one-workspace-per-agent** model (the same model wmux's own
a2a/company features use):

* **session** -> a logical group (no single wmux workspace; the dashboard groups
  agents by the ``"<session> · <agent>"`` naming + ``pantheon.session`` metadata).
* **agent**   -> its **own wmux workspace** (a top tab) created with
  ``mcp.claimWorkspace``; the agent's ``claude`` command is typed into that
  workspace's shell with ``input.send``.
* **monitor**  via ``terminal.readEvents`` (exit codes) + ``workspace.list``.
* **tag**      via ``pane.setMetadata`` so the dashboard can see which Pantheon
  agent/session owns each workspace.

Why one workspace per agent: as an external plugin Pantheon can *create*
workspaces (``mcp.claimWorkspace``) and drive any terminal by ``ptyId``, but it
**cannot** add a pane to a specific non-active workspace — ``pane.split`` only
splits whatever workspace is globally active and ``workspace.focus`` is an
internal-only capability. One-workspace-per-agent is therefore both the reliable
and the wmux-idiomatic mapping (each agent is its own discoverable a2a tab).

Everything goes through :class:`~core.runtime.multiplexer.wmux_rpc.WmuxClient`,
which performs the one-time ``identify`` + ``declarePermissions`` handshake (the
user approves Pantheon once in the wmux GUI).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from core.runtime.multiplexer.base import (
    AgentSpec,
    MultiplexerDriver,
    MultiplexerUnavailableError,
    Surface,
    SurfaceStatus,
    Workspace,
)
from core.runtime.multiplexer.wmux_rpc import (
    WmuxClient,
    WmuxNotConfirmedError,
    WmuxRpcError,
    WmuxUnavailableError,
)

logger = logging.getLogger(__name__)


def _pwsh_quote(arg: str) -> str:
    """Single-quote an argument for PowerShell (the wmux default shell)."""
    return "'" + arg.replace("'", "''") + "'"


def shell_command_for(spec: AgentSpec) -> str:
    """Return the shell command line to type into a surface for ``spec``."""
    if spec.shell_command:
        return spec.shell_command
    return " ".join(_pwsh_quote(a) if (" " in a or "'" in a or '"' in a) else a
                     for a in spec.command)


class WmuxDriver(MultiplexerDriver):
    name = "wmux"

    def __init__(self, client: Optional[WmuxClient] = None):
        self._client = client or WmuxClient()

    # -- lifecycle ---------------------------------------------------------- #
    def is_available(self) -> bool:
        return self._client.available()

    def ensure_running(self) -> None:
        if not self._client.available():
            raise MultiplexerUnavailableError(
                "wmux app is not running. Launch wmux, then retry."
            )
        try:
            self._client.verify()
        except WmuxNotConfirmedError as exc:
            raise MultiplexerUnavailableError(
                "wmux has not approved Pantheon yet. Approve the 'pantheon' "
                "plugin in the wmux window (one-time), then retry. "
                f"({exc})"
            ) from exc
        except WmuxUnavailableError as exc:
            raise MultiplexerUnavailableError(str(exc)) from exc

    # -- session (logical group) -------------------------------------------- #
    def create_workspace(self, name: str) -> Workspace:
        """A Pantheon session is a logical group of per-agent workspaces, so this
        is a no-RPC container; each agent claims its own wmux workspace."""
        self.ensure_running()
        return Workspace(id=f"session:{name}", name=name)

    # -- agent = its own workspace (top tab) -------------------------------- #
    def open_surface(self, workspace: Workspace, spec: AgentSpec) -> Surface:
        self.ensure_running()
        tab_name = f"{workspace.name} · {spec.title}"
        res = self._client.call("mcp.claimWorkspace", {"name": tab_name})
        if not isinstance(res, dict) or not res.get("workspaceId"):
            raise MultiplexerUnavailableError(f"claimWorkspace failed: {res!r}")
        ws_id = res["workspaceId"]
        pty_id = res.get("ptyId")
        pane_id = self._active_pane(ws_id)

        surface = Surface(
            id=f"{ws_id}:{pty_id}",
            title=spec.title,
            workspace_id=ws_id,
            pty_id=pty_id,
            agent_id=spec.agent_id,
            cwd=spec.cwd,
            status=SurfaceStatus.RUNNING,
            metadata={**spec.metadata, "pane_id": pane_id or "", "tab_name": tab_name},
        )

        # Label the agent's workspace pane so the dashboard can group it.
        self._safe_set_metadata(
            ws_id, pane_id,
            label=spec.title[:64],
            role=spec.role[:64],
            status="running",
            custom={"pantheon.agentId": spec.agent_id,
                    "pantheon.session": workspace.name},
        )

        cmd = shell_command_for(spec)
        try:
            self._client.call("input.send", {
                "workspaceId": ws_id,
                "ptyId": pty_id,
                "text": cmd,
                "submit": True,
            })
        except WmuxRpcError as exc:
            logger.warning("wmux input.send failed for %s: %s", spec.agent_id, exc)
            surface.status = SurfaceStatus.FAILED
            surface.exit_code = -1

        workspace.surfaces.append(surface)
        return surface

    # -- monitoring --------------------------------------------------------- #
    def poll_surface(self, surface: Surface) -> Surface:
        if surface.status in (SurfaceStatus.DONE, SurfaceStatus.FAILED, SurfaceStatus.CLOSED):
            return surface
        if not surface.pty_id or not surface.workspace_id:
            return surface
        # If the agent's workspace/pty disappeared (user closed the tab), it's gone.
        if surface.pty_id not in self._pty_ids(surface.workspace_id):
            surface.status = SurfaceStatus.CLOSED
            return surface
        try:
            ev = self._client.call("terminal.readEvents", {
                "workspaceId": surface.workspace_id,
                "ptyId": surface.pty_id,
                "lastCommandOnly": True,
            })
        except WmuxRpcError as exc:
            logger.debug("readEvents failed for %s: %s", surface.id, exc)
            return surface
        rng = (ev or {}).get("lastCompletedRange") if isinstance(ev, dict) else None
        if rng and rng.get("exitCode") is not None:
            code = rng.get("exitCode")
            surface.exit_code = code
            surface.status = SurfaceStatus.DONE if code == 0 else SurfaceStatus.FAILED
            self._safe_set_metadata(
                surface.workspace_id, surface.metadata.get("pane_id"),
                status=("done" if code == 0 else f"failed({code})"),
            )
        return surface

    def read_output(self, surface: Surface, tail: int = 4000) -> str:
        if not surface.pty_id or not surface.workspace_id:
            return ""
        try:
            res = self._client.call("input.readScreen", {
                "workspaceId": surface.workspace_id,
                "ptyId": surface.pty_id,
            })
        except WmuxRpcError:
            return ""
        if isinstance(res, dict):
            text = res.get("text") or res.get("screen") or ""
        else:
            text = str(res or "")
        return text[-tail:]

    def close_surface(self, surface: Surface) -> None:
        # Plugins cannot close a workspace directly; ask the shell to exit, which
        # tears the agent's tab down (automatic tab removal).
        if surface.pty_id and surface.workspace_id:
            try:
                self._client.call("input.sendKey", {
                    "workspaceId": surface.workspace_id,
                    "ptyId": surface.pty_id, "key": "ctrl+c",
                })
            except WmuxRpcError:
                pass
            try:
                self._client.call("input.send", {
                    "workspaceId": surface.workspace_id,
                    "ptyId": surface.pty_id,
                    "text": "exit",
                    "submit": True,
                })
            except WmuxRpcError:
                pass
        if surface.status == SurfaceStatus.RUNNING:
            surface.status = SurfaceStatus.CLOSED

    def tag_surface(self, surface: Surface, **meta: Any) -> None:
        super().tag_surface(surface, **meta)
        self._safe_set_metadata(
            surface.workspace_id, surface.metadata.get("pane_id"),
            label=meta.get("label"),
            role=meta.get("role"),
            status=meta.get("status"),
            custom={k: str(v) for k, v in meta.items()
                    if k not in ("label", "role", "status") and v is not None} or None,
        )

    # -- listing ------------------------------------------------------------ #
    def list_workspaces(self) -> List[Workspace]:
        out: List[Workspace] = []
        for w in self._raw_workspaces():
            ws = Workspace(id=w.get("id"), name=w.get("name") or w.get("id"))
            for pty in w.get("ptyIds") or []:
                ws.surfaces.append(Surface(
                    id=f"{ws.id}:{pty}",
                    title=pty,
                    workspace_id=ws.id,
                    pty_id=pty,
                    cwd=(w.get("metadata") or {}).get("cwd"),
                    status=SurfaceStatus.RUNNING,
                ))
            out.append(ws)
        return out

    # -- internals ---------------------------------------------------------- #
    def _raw_workspaces(self) -> List[dict]:
        try:
            return self._client.call("workspace.list") or []
        except WmuxRpcError:
            return []

    def _pty_ids(self, ws_id: str) -> List[str]:
        for w in self._raw_workspaces():
            if w.get("id") == ws_id:
                return list(w.get("ptyIds") or [])
        return []

    def _active_pane(self, ws_id: str) -> Optional[str]:
        """Return the active leaf pane id of ``ws_id`` (for metadata)."""
        try:
            res = self._client.call("pane.list", {"workspaceId": ws_id})
        except WmuxRpcError:
            return None
        panes = res.get("panes") if isinstance(res, dict) else res
        for p in (panes or []):
            if p.get("active"):
                return p.get("id")
        if panes:
            return panes[0].get("id")
        return None

    def _safe_set_metadata(self, ws_id, pane_id, *, label=None, role=None,
                           status=None, custom=None) -> None:
        if not ws_id:
            return
        params: Dict[str, Any] = {"workspaceId": ws_id}
        if pane_id:
            params["paneId"] = pane_id
        if label is not None:
            params["label"] = label
        if role is not None:
            params["role"] = role
        if status is not None:
            params["status"] = status
        if custom:
            params["custom"] = custom
        if len(params) <= (2 if pane_id else 1):
            return
        try:
            self._client.call("pane.setMetadata", params)
        except WmuxRpcError as exc:
            logger.debug("pane.setMetadata failed: %s", exc)
