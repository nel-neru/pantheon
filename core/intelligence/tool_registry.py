"""Register agent-declared tools/MCP into the CapabilityRegistry.

Agent YAML ``tools:`` entries were parsed (``AgentDefinition.tools``) but never
surfaced as capabilities. This scans definitions and registers each declared tool
as a ``capability_type="mcp_tool"`` entry (the previously-unused slot in
``CapabilityEntry``), tagging it read-only vs gated so gap analysis / the UI can
see which tools the org actually wields.
"""

from __future__ import annotations

import logging
from typing import Any, Iterable, Optional

from core.intelligence.capability_registry import CapabilityEntry, CapabilityRegistry
from core.runtime.tool_config import ToolSpec, classify_tool, read_only_servers_of

logger = logging.getLogger(__name__)


def _capability_id(tool: str) -> str:
    return f"mcp_tool:{tool}" if tool.startswith("mcp__") else f"tool:{tool}"


def scan_and_register_tools(definitions: Iterable[Any], registry: CapabilityRegistry) -> int:
    """Register every tool declared by any agent definition. Returns the count
    of distinct tools registered. Pure w.r.t. its inputs (testable with fakes)."""
    seen: set[str] = set()
    count = 0
    for defn in definitions:
        spec = ToolSpec.from_definition(defn)
        if spec is None:
            continue
        # classification uses the agent's own mcp read_only declarations (shared helper)
        read_only_servers = read_only_servers_of(getattr(defn, "mcp", None))
        for tool in list(getattr(defn, "tools", None) or []):
            cap_id = _capability_id(tool)
            if cap_id in seen:
                continue
            seen.add(cap_id)
            kind = classify_tool(tool, read_only_servers=read_only_servers)
            gate = "read-only" if kind == "read_only" else "gated (human-approval)"
            registry.register(
                CapabilityEntry(
                    id=cap_id,
                    name=tool,
                    capability_type="mcp_tool",
                    description=f"{gate} tool declared by agent definitions",
                )
            )
            count += 1
    return count


def scan_from_loader(
    loader: Optional[Any] = None, registry: Optional[CapabilityRegistry] = None
) -> int:
    """Convenience: scan the default agent loader into the default registry. Best-effort."""
    try:
        if loader is None:
            from core.loaders.agent_loader import AgentLoader

            loader = AgentLoader()
            for method in ("discover", "load", "load_all", "scan"):
                fn = getattr(loader, method, None)
                if callable(fn):
                    try:
                        fn()
                    except Exception:
                        pass
                    break
        if registry is None:
            registry = CapabilityRegistry()
        return scan_and_register_tools(loader.all(), registry)
    except Exception as exc:  # pragma: no cover - best-effort convenience
        logger.debug("scan_from_loader failed: %s", exc)
        return 0
