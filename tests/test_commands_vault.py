"""commands/vault.py — サブコマンド（export/status/open/doctor）と CLI 配線。"""

from __future__ import annotations

from types import SimpleNamespace

from core.intelligence.playbook import PlaybookStore
from core.knowledge.manager import KnowledgeManager
from core.metrics.outcomes import OutcomeStore


def _seed(tmp_path):
    KnowledgeManager(tmp_path).save_insight("Insight A", "本文", tags=["t"], source_org="Foo")
    PlaybookStore(tmp_path).add("Play A", "施策", category="general", org_name="Foo")
    OutcomeStore(tmp_path).record("Foo", "revenue", 100, source="note")


def _patch_home(monkeypatch, tmp_path):
    monkeypatch.setattr("core.platform.state.get_platform_home", lambda: tmp_path)


def test_vault_export_creates_vault(monkeypatch, tmp_path, capsys):
    _seed(tmp_path)
    _patch_home(monkeypatch, tmp_path)
    from commands.vault import cmd_vault

    cmd_vault(SimpleNamespace(vault_command="export"))
    out = capsys.readouterr().out

    assert "Vault export 完了" in out
    assert (tmp_path / "vault" / "insights").exists()
    assert list((tmp_path / "vault" / "playbooks").glob("*.md"))


def test_vault_status_runs(monkeypatch, tmp_path, capsys):
    _seed(tmp_path)
    _patch_home(monkeypatch, tmp_path)
    from commands.vault import cmd_vault

    cmd_vault(SimpleNamespace(vault_command="status"))
    out = capsys.readouterr().out
    assert "Vault status" in out
    assert "ストア総件数: 3" in out


def test_vault_open_prints_path(monkeypatch, tmp_path, capsys):
    _patch_home(monkeypatch, tmp_path)
    from commands.vault import cmd_vault

    cmd_vault(SimpleNamespace(vault_command="open"))
    out = capsys.readouterr().out
    assert str(tmp_path / "vault") in out


def test_vault_doctor_clean(monkeypatch, tmp_path, capsys):
    _seed(tmp_path)
    _patch_home(monkeypatch, tmp_path)
    from commands.vault import cmd_vault

    cmd_vault(SimpleNamespace(vault_command="export"))
    capsys.readouterr()
    cmd_vault(SimpleNamespace(vault_command="doctor"))
    out = capsys.readouterr().out
    assert "問題は見つかりませんでした" in out


def test_vault_command_is_wired_into_cli():
    from commands import build_parser

    parser = build_parser()
    args = parser.parse_args(["vault", "export"])
    assert args.handler_name == "cmd_vault"
    assert args.vault_command == "export"


def test_vault_handler_registered_in_main():
    from main import HANDLERS

    assert "cmd_vault" in HANDLERS
