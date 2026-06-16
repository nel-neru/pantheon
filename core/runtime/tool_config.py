"""Per-agent tool / MCP configuration → ``claude`` CLI argv.

An agent declares the tools it may use in its YAML (``tools:`` for built-in CLI
tools, optional ``mcp:`` for MCP servers). :class:`ToolSpec` turns that into the
``--mcp-config`` / ``--allowedTools`` / ``--disallowedTools`` argv that
``core.runtime.claude_code`` injects. It is the inverse of ``_build_cli_args``'s
fast-path (which DISABLES MCP with ``--mcp-config {}``) and is pure/deterministic
so it is unit-tested without spawning the CLI.

Safety: tools are classified read-only vs gated. **Gated tools (write / execute /
external) are NEVER auto-allowed** for an autonomous run (``allow_gated=False``,
the default) — they are placed on ``--disallowedTools`` and must be granted only
through an explicit human-approved context. This keeps the 24/7 daemons incapable
of irreversible/external actions without a human in the loop.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

# Built-in claude tools that only READ — safe to auto-allow.
READ_ONLY_TOOLS = frozenset({"Read", "Grep", "Glob", "LS", "NotebookRead", "TodoRead", "WebSearch"})
# Built-in tools that WRITE / EXECUTE / reach EXTERNAL — gated (need human approval).
GATED_TOOLS = frozenset({"Write", "Edit", "MultiEdit", "NotebookEdit", "Bash", "WebFetch", "Task"})


def classify_tool(name: str, *, read_only_servers: Optional[dict] = None) -> str:
    """Return ``"read_only"`` or ``"gated"`` for a tool name.

    MCP tools are named ``mcp__<server>__<tool>``; one is read-only only if its
    server is declared ``read_only`` in the agent's ``mcp:`` block. Unknown
    built-ins default to ``gated`` (fail safe).
    """
    if name in READ_ONLY_TOOLS:
        return "read_only"
    if name in GATED_TOOLS:
        return "gated"
    if name.startswith("mcp__"):
        rest = name[len("mcp__") :]
        server = rest.split("__", 1)[0] if "__" in rest else rest
        if read_only_servers and read_only_servers.get(server):
            return "read_only"
        return "gated"
    return "gated"


def read_only_servers_of(mcp: Optional[dict]) -> dict:
    """Map of ``server_name -> bool(read_only)`` from an agent's ``mcp:`` block.

    Single source for the read-only classification used by both this module and the
    tool registry, so the rule can't drift between them.
    """
    servers = (mcp or {}).get("servers", {})
    if not isinstance(servers, dict):
        return {}
    return {
        name: bool(cfg.get("read_only")) for name, cfg in servers.items() if isinstance(cfg, dict)
    }


@dataclass
class ToolSpec:
    allowed: list[str] = field(default_factory=list)
    gated: list[str] = field(default_factory=list)  # declared but disallowed in autonomous mode
    mcp_servers: dict = field(default_factory=dict)

    @property
    def is_empty(self) -> bool:
        """True when there is nothing to enable (so the fast-path stays in effect)."""
        return not self.allowed and not self.mcp_servers

    def to_argv(self) -> list[str]:
        # ALWAYS pin MCP. This spec is only used when bypassing the fast-path, so we must still
        # suppress ambient .mcp.json servers (context7/playwright) — otherwise an agent declaring
        # only read-only CLI tools would silently re-expose them. Empty servers -> "{}", exactly
        # like the fast-path's own `--mcp-config {}`; `--strict-mcp-config` allows nothing ambient.
        config = {"mcpServers": self.mcp_servers} if self.mcp_servers else {}
        args: list[str] = [
            "--mcp-config",
            json.dumps(config, ensure_ascii=False),
            "--strict-mcp-config",
        ]
        if self.allowed:
            args += ["--allowedTools", ",".join(self.allowed)]
        if self.gated:
            args += ["--disallowedTools", ",".join(self.gated)]
        return args

    @classmethod
    def from_tools(
        cls,
        tools: Sequence[str],
        mcp: Optional[dict] = None,
        *,
        allow_gated: bool = False,
    ) -> "ToolSpec":
        mcp = mcp or {}
        raw_servers = mcp.get("servers", {})
        servers = raw_servers if isinstance(raw_servers, dict) else {}
        read_only_servers = read_only_servers_of(mcp)
        # Only SPAWN a server if it is read-only or gated access is explicitly allowed; a
        # non-read-only server in autonomous mode is omitted entirely (never launched), so its
        # tools can't run without a human-approved (allow_gated) context. Strip the control key.
        clean_servers = {
            name: {k: v for k, v in cfg.items() if k != "read_only"}
            for name, cfg in servers.items()
            if isinstance(cfg, dict) and (read_only_servers.get(name) or allow_gated)
        }
        allowed: list[str] = []
        gated: list[str] = []
        for tool in tools:
            kind = classify_tool(tool, read_only_servers=read_only_servers)
            if kind == "read_only" or allow_gated:
                allowed.append(tool)
            else:
                gated.append(tool)
        return cls(allowed=allowed, gated=gated, mcp_servers=clean_servers)

    @classmethod
    def from_definition(cls, definition: Any, *, allow_gated: bool = False) -> Optional["ToolSpec"]:
        """Build a spec from an ``AgentDefinition`` (``.tools`` + optional ``.mcp``).

        Returns ``None`` when the agent declares no tools/MCP (keeps the fast-path).
        """
        tools = list(getattr(definition, "tools", None) or [])
        mcp = dict(getattr(definition, "mcp", None) or {})
        if not tools and not mcp.get("servers"):
            return None
        return cls.from_tools(tools, mcp, allow_gated=allow_gated)
