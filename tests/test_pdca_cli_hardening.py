from __future__ import annotations

import asyncio
import importlib
from types import SimpleNamespace

import pytest

from core.models.organization import ImprovementProposal
from core.state.sqlite_manager import SQLiteStateManager


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        loop.close()
        asyncio.set_event_loop(asyncio.new_event_loop())


def _proposal(title: str, priority: str = "medium") -> ImprovementProposal:
    from uuid import uuid4

    return ImprovementProposal(
        review_id=uuid4(),
        title=title,
        description="desc",
        file_path="src/app.py",
        priority=priority,
        category="general",
    )


def test_cmd_query_rejects_sql_like_filter(tmp_path, capsys):
    from main import cmd_query

    db_path = tmp_path / "state.db"
    manager = SQLiteStateManager(db_path)
    manager.save_improvement_proposal(_proposal("Unsafe filter target", priority="high"))
    manager.close()

    with pytest.raises(SystemExit):
        _run(
            cmd_query(
                SimpleNamespace(filter="WHERE priority='high'", limit=10, db_path=str(db_path))
            )
        )

    out = capsys.readouterr().out
    assert "key=value" in out


def test_require_api_key_passes_when_claude_available(monkeypatch):
    from main import _require_api_key

    # Pantheon uses no API keys; the gate now checks the local `claude` CLI backend.
    monkeypatch.setattr("core.runtime.claude_code.claude_available", lambda: True)

    _require_api_key("pantheon chat")  # must not raise when the backend is available


def test_require_api_key_prints_remediation(monkeypatch, capsys):
    from main import _require_api_key

    monkeypatch.setattr("core.runtime.claude_code.claude_available", lambda: False)

    with pytest.raises(SystemExit):
        _require_api_key("pantheon goal run")

    out = capsys.readouterr().out
    assert "claude" in out.lower()
    assert "pantheon serve" in out


def test_cmd_org_remove_requires_confirmation(monkeypatch, capsys):
    from main import cmd_org_remove

    removed: list[str] = []

    class FakePSM:
        def load_organization_by_name(self, name):
            return SimpleNamespace(id="org-1", name=name)

        def remove_organization(self, org_id):
            removed.append(org_id)

    monkeypatch.setattr("main._get_psm", lambda: FakePSM())
    monkeypatch.setattr("builtins.input", lambda _prompt: "no")

    _run(cmd_org_remove(SimpleNamespace(name="DemoOrg", yes=False)))

    out = capsys.readouterr().out
    assert removed == []
    assert "中止" in out


def test_cmd_approve_requires_confirmation(monkeypatch, tmp_path, capsys):
    from main import cmd_approve

    status_updates: list[tuple[str, str]] = []
    target = {
        "id": "abcd1234-0000-0000-0000-000000000000",
        "title": "Apply fix",
        "file_path": "src/app.py",
        "description": "desc",
    }

    class FakeStateManager:
        def get_pending_improvement_proposals(self, limit=100):
            return [target]

        def update_proposal_status(self, proposal_id, status):
            status_updates.append((proposal_id, status))

        def update_proposal_fields(self, proposal_id, **updates):
            return True

    fake_org = SimpleNamespace(name="DemoOrg", target_repo_path=str(tmp_path), github_repo=None)

    class FakePSM:
        platform_home = tmp_path

        def load_organization_by_name(self, name):
            return fake_org

        def get_org_state_manager(self, org):
            return FakeStateManager()

    monkeypatch.setattr("main._require_api_key", lambda _command: None)
    monkeypatch.setattr("main._get_psm", lambda: FakePSM())
    monkeypatch.setattr(
        "main._get_orchestrator",
        lambda: (_ for _ in ()).throw(AssertionError("orchestrator should not run")),
    )
    monkeypatch.setattr("builtins.input", lambda _prompt: "n")

    _run(
        cmd_approve(
            SimpleNamespace(
                proposal_id="abcd1234",
                org_name="DemoOrg",
                github_token=None,
                github_repo=None,
                yes=False,
            )
        )
    )

    out = capsys.readouterr().out
    assert status_updates == []
    assert "中止" in out


def test_main_import_does_not_create_event_loop(monkeypatch):
    import asyncio as asyncio_module

    import main

    calls: list[object] = []
    monkeypatch.setattr(asyncio_module, "set_event_loop", lambda loop: calls.append(loop))
    monkeypatch.setattr(
        asyncio_module,
        "new_event_loop",
        lambda: (_ for _ in ()).throw(
            AssertionError("new_event_loop should not be used at import time")
        ),
    )

    importlib.reload(main)

    assert calls == []


def test_cmd_daemon_start_closes_log_handle(monkeypatch, tmp_path, capsys):
    import subprocess as subprocess_module

    import core.platform.state as platform_state_module
    from main import cmd_daemon_start

    captured: dict[str, object] = {}

    class DummyProc:
        pid = 4321

    def fake_popen(cmd, cwd, stdout, stderr, **kwargs):
        captured["cmd"] = cmd
        captured["stdout"] = stdout
        captured["cwd"] = cwd
        captured["stderr"] = stderr
        captured["popen_kwargs"] = kwargs
        return DummyProc()

    monkeypatch.setattr(platform_state_module, "get_platform_home", lambda: tmp_path)
    monkeypatch.setattr(subprocess_module, "Popen", fake_popen)

    _run(cmd_daemon_start(SimpleNamespace(interval=60, max_files=5)))

    out = capsys.readouterr().out
    assert "[OK] デーモンを起動しました" in out
    assert captured["stdout"].closed is True
    assert (tmp_path / "daemon.pid").read_text(encoding="utf-8") == "4321"
    # CLI daemon start also detaches OS-correctly (Windows ignores start_new_session).
    import core.runtime.daemon_registry as registry

    for key, value in registry._detach_popen_kwargs().items():
        assert captured["popen_kwargs"][key] == value
    # daemons spawn in UTF-8 mode so print() of non-cp932 chars cannot crash them.
    assert captured["popen_kwargs"]["env"]["PYTHONUTF8"] == "1"
