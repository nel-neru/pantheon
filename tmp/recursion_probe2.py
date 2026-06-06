import asyncio, tempfile, pathlib
import core.platform.state as ps
tmpdir = pathlib.Path(tempfile.mkdtemp())
ps.get_platform_home = lambda: tmpdir

from core.intelligence.capability_registry import CapabilityRegistry
from core.orchestration.pre_task_orchestrator import PreTaskOrchestrator, TASK_ORCHESTRATION_PROFILES

reg = CapabilityRegistry(platform_home=tmpdir)
reg.scan_and_register_all()
orch = PreTaskOrchestrator(capability_registry=reg)
for tt in list(TASK_ORCHESTRATION_PROFILES.keys()):
    a = orch.analyze(tt, "x")
    has_orch = "agent:orchestrator" in a.recommended_agent_ids
    flag = "  <<< ORCHESTRATOR SELECTED" if has_orch else ""
    print(f"{tt:24} pattern={a.recommended_pattern:18} agents={a.recommended_agent_ids}{flag}")
