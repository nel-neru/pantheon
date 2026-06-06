import sys, asyncio, tempfile, pathlib
import core.platform.state as ps
tmpdir = pathlib.Path(tempfile.mkdtemp())
ps.get_platform_home = lambda: tmpdir  # isolate

from core.intelligence.capability_registry import CapabilityRegistry
from core.orchestration.task_router import TaskRouter

reg = CapabilityRegistry(platform_home=tmpdir)
reg.scan_and_register_all()
router = TaskRouter(capability_registry=reg)
for tt in ["meta_improvement", "code_review", "organization_design", "improvement_execution"]:
    d = router.route(tt, max_agents=2)
    print(tt, "->", d.selected_agent_ids)
