"""dev/prod 環境のデータ完全分離（PANTHEON_HOME によるプラットフォームホーム切替）。

PANTHEON_HOME を切り替えると、収益・組織・タスクキュー等の正準ストアが別領域に分離され、
互いに混ざらないことを検証する。ハードコード ~/.pantheon を排し get_platform_home() に集約した回帰防止。
"""

from __future__ import annotations

from core.metrics.outcomes import OutcomeStore
from core.orchestration.task_queue import TaskQueue
from core.org_factory import create_default_organization
from core.platform.state import PlatformStateManager, get_platform_home


def test_get_platform_home_honors_env(tmp_path, monkeypatch):
    home = tmp_path / "envhome"
    monkeypatch.setenv("PANTHEON_HOME", str(home))
    assert get_platform_home() == home.resolve()


def test_outcomes_are_isolated_between_two_homes(tmp_path, monkeypatch):
    """PANTHEON_HOME=A で記録した収益は B からは一切見えない（完全分離）。"""
    home_a = tmp_path / "A"
    home_b = tmp_path / "B"

    monkeypatch.setenv("PANTHEON_HOME", str(home_a))
    OutcomeStore().record("Reachy", "revenue", 5000)  # 既定ホーム=A へ
    assert OutcomeStore().summary_for_org("Reachy").total_revenue == 5000

    monkeypatch.setenv("PANTHEON_HOME", str(home_b))
    # B は別領域 — A のデータは存在しない
    assert OutcomeStore().summary_for_org("Reachy").total_revenue == 0


def test_orgs_are_isolated_between_two_homes(tmp_path, monkeypatch):
    """PANTHEON_HOME=A で作った Organization は B からは見えない。"""
    home_a = tmp_path / "A"
    home_b = tmp_path / "B"

    monkeypatch.setenv("PANTHEON_HOME", str(home_a))
    PlatformStateManager().save_organization(create_default_organization("DevCo", "dev"))
    assert PlatformStateManager().load_organization_by_name("DevCo") is not None

    monkeypatch.setenv("PANTHEON_HOME", str(home_b))
    assert PlatformStateManager().load_organization_by_name("DevCo") is None


def test_task_queue_honors_home(tmp_path, monkeypatch):
    """タスクキューの保存先も PANTHEON_HOME 配下（旧ハードコード QUEUE_FILE 回帰防止）。"""
    home = tmp_path / "home"
    monkeypatch.setenv("PANTHEON_HOME", str(home))
    queue = TaskQueue()
    # キューファイルは get_platform_home() 配下に解決される
    assert str(queue.queue_file).startswith(str(home.resolve()))


def test_settings_and_chat_paths_derive_from_home():
    """web.server / chat_agent の設定・チャット保存先が get_platform_home() 由来であること。"""
    import agents.chat_agent as chat_agent
    import web.server as server

    base = get_platform_home()
    # 既定（PANTHEON_HOME 未設定）では ~/.pantheon 配下に揃う＝ハードコードではなく home 由来
    assert server.SETTINGS_FILE == base / "gui_settings.json"
    assert server.CHAT_SESSIONS_DIR == base / "chat_sessions"
    assert chat_agent.SETTINGS_FILE == base / "gui_settings.json"
