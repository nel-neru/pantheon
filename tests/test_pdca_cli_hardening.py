from __future__ import annotations

import asyncio
import importlib
import json
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
        _run(cmd_query(SimpleNamespace(filter="WHERE priority='high'", limit=10, db_path=str(db_path))))

    out = capsys.readouterr().out
    assert "key=value" in out


def test_require_api_key_uses_gui_settings(monkeypatch, tmp_path):
    from main import _require_api_key

    settings_file = tmp_path / "gui_settings.json"
    settings_file.write_text(
        json.dumps({"llm_provider": "openai", "openai_api_key": "sk-test"}),
        encoding="utf-8",
    )
    monkeypatch.setattr("main.SETTINGS_FILE", settings_file)
    monkeypatch.delenv("REPOCORP_DEFAULT_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    _require_api_key("repocorp chat")


def test_require_api_key_prints_remediation(monkeypatch, tmp_path, capsys):
    from main import _require_api_key

    settings_file = tmp_path / "missing.json"
    monkeypatch.setattr("main.SETTINGS_FILE", settings_file)
    monkeypatch.delenv("REPOCORP_DEFAULT_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    with pytest.raises(SystemExit):
        _require_api_key("repocorp goal run")

    out = capsys.readouterr().out
    assert "ANTHROPIC_API_KEY" in out
    assert "repocorp serve" in out


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

    fake_org = SimpleNamespace(name="DemoOrg", target_repo_path=str(tmp_path))

    class FakePSM:
        def load_organization_by_name(self, name):
            return fake_org

        def get_org_state_manager(self, org):
            return FakeStateManager()

    monkeypatch.setattr("main._require_api_key", lambda _command: None)
    monkeypatch.setattr("main._get_psm", lambda: FakePSM())
    monkeypatch.setattr("main._get_orchestrator", lambda: (_ for _ in ()).throw(AssertionError("orchestrator should not run")))
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
        lambda: (_ for _ in ()).throw(AssertionError("new_event_loop should not be used at import time")),
    )

    importlib.reload(main)

    assert calls == []


def test_cmd_daemon_start_closes_log_handle(monkeypatch, tmp_path, capsys):
    from main import cmd_daemon_start
    import core.platform.state as platform_state_module
    import subprocess as subprocess_module

    captured: dict[str, object] = {}

    class DummyProc:
        pid = 4321

    def fake_popen(cmd, cwd, stdout, stderr, start_new_session):
        captured["cmd"] = cmd
        captured["stdout"] = stdout
        captured["cwd"] = cwd
        captured["stderr"] = stderr
        captured["start_new_session"] = start_new_session
        return DummyProc()

    monkeypatch.setattr(platform_state_module, "get_platform_home", lambda: tmp_path)
    monkeypatch.setattr(subprocess_module, "Popen", fake_popen)

    _run(cmd_daemon_start(SimpleNamespace(interval=60, max_files=5)))

    out = capsys.readouterr().out
    assert "[OK] デーモンを起動しました" in out
    assert captured["stdout"].closed is True
    assert (tmp_path / "daemon.pid").read_text(encoding="utf-8") == "4321"
