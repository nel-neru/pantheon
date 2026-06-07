from __future__ import annotations

import argparse

import main
from core.org_factory import create_default_organization


class _FakeStateManager:
    def get_pending_improvement_proposals(self, limit: int = 100):
        return []


class _FakePSM:
    def __init__(self, orgs):
        self._orgs = orgs

    def load_organizations(self):
        return self._orgs

    def get_org_state_manager(self, _org):
        return _FakeStateManager()


def test_platform_run_all_continues_after_org_failure(monkeypatch, capsys):
    healthy = create_default_organization("Healthy Org", "happy path")
    broken = create_default_organization("Broken Org", "failing path")
    psm = _FakePSM([healthy, broken])
    calls: list[str] = []

    class FakeLoop:
        def __init__(self, org, state_manager):
            self.org = org
            self.state_manager = state_manager

        async def run_improvement_cycle(self):
            calls.append(self.org.name)
            if self.org.name == "Broken Org":
                raise RuntimeError("cycle exploded")

    monkeypatch.setattr(main, "_get_psm", lambda: psm)
    monkeypatch.setattr("core.quality.self_improvement_loop.SelfImprovementLoop", FakeLoop)

    args = argparse.Namespace(max_orgs=5)
    main.asyncio.run(main.cmd_platform_run_all(args))

    out = capsys.readouterr().out
    assert calls == [healthy.name, broken.name]
    assert "[ERROR] Broken Org: cycle exploded" in out
    assert "成功: 1 / 2" in out
    assert "Healthy Org" not in out.split("[WARN] 失敗した Organization:")[-1]
