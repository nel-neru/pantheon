"""定期実行スケジューラ（core/illustration_story/scheduler）と story schedule CLI の検証。

schtasks コマンド構築は純粋関数で検証。CLI は install/uninstall/status を注入差し替えして配線を
確認（実タスクスケジューラには触れない）。
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from core.illustration_story.scheduler import (
    build_create_command,
    build_delete_command,
    install_schedule,
    task_name_for,
)
from core.orchestration.company_plugins import install_company_plugin
from core.platform.state import PlatformStateManager


def test_build_create_command_runs_story_produce_daily():
    cmd = build_create_command(
        "RedThread", count=3, time="08:30", python_exe="py.exe", main_py="C:/repo/main.py"
    )
    assert cmd[0] == "schtasks" and "/Create" in cmd
    assert "/SC" in cmd and "DAILY" in cmd
    assert "08:30" in cmd
    tr = cmd[cmd.index("/TR") + 1]
    assert "main.py" in tr and "story produce" in tr
    assert '--org "RedThread"' in tr and "--count 3" in tr


def test_task_name_unique_for_non_ascii():
    a = task_name_for("赤い糸社")
    b = task_name_for("別の会社")
    assert a != b  # 非ASCII名でもハッシュで衝突しない
    assert task_name_for("RedThread") == "Pantheon Story Produce - RedThread"


def test_build_delete_command():
    cmd = build_delete_command("RedThread")
    assert cmd[:2] == ["schtasks", "/Delete"] and "/F" in cmd


def test_install_schedule_uses_injected_runner():
    """install は runner（schtasks 実行）を呼び、成功コードで True を返す（実登録しない）。"""
    captured = {}

    def fake_runner(cmd):
        captured["cmd"] = cmd
        return 0, "SUCCESS"

    ok, out = install_schedule(
        "RedThread", count=2, time="10:00", python_exe="py", main_py="m.py", runner=fake_runner
    )
    assert ok and out == "SUCCESS"
    assert captured["cmd"][0] == "schtasks" and "story produce" in " ".join(captured["cmd"])


def test_cli_schedule_install_wires_through(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("core.platform.state.get_platform_home", lambda: tmp_path)
    monkeypatch.setattr(
        "core.illustration_story.scheduler.install_schedule",
        lambda org, **kw: (True, "registered"),
    )
    psm = PlatformStateManager(platform_home=tmp_path)
    org_name = install_company_plugin("illustration_story_youtube", psm=psm)["org_name"]

    from commands.story import cmd_story_schedule

    asyncio.run(
        cmd_story_schedule(
            SimpleNamespace(org=org_name, schedule_action="install", count=2, time="09:00"),
            get_psm=lambda: psm,
        )
    )
    out = capsys.readouterr().out
    assert "登録しました" in out and "無人公開はしない" in out
