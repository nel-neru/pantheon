"""dev/prod 環境のデータ完全分離（PANTHEON_HOME によるプラットフォームホーム切替）。

PANTHEON_HOME を切り替えると、収益・組織・タスクキュー等の正準ストアが別領域に分離され、
互いに混ざらないことを検証する。ハードコード ~/.pantheon を排し get_platform_home() に集約した回帰防止。
"""

from __future__ import annotations

from core.metrics.outcomes import OutcomeStore
from core.orchestration.task_queue import TaskQueue
from core.org_factory import create_default_organization
from core.platform.state import (
    PlatformStateManager,
    get_platform_home,
    resolve_environment,
)


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


def test_resolve_environment_explicit_env(monkeypatch):
    """PANTHEON_ENV の明示指定が最優先される。"""
    monkeypatch.setenv("PANTHEON_ENV", "development")
    info = resolve_environment()
    assert info["environment"] == "development"
    assert info["env_label"] == "DEV"
    assert info["friendly_host"] == "dev.pantheon.localhost"

    monkeypatch.setenv("PANTHEON_ENV", "production")
    info = resolve_environment()
    assert info["environment"] == "production"
    assert info["env_label"] == "PROD"
    assert info["friendly_host"] == "pantheon.localhost"


def test_resolve_environment_from_home_name(tmp_path, monkeypatch):
    """PANTHEON_ENV 未指定なら PANTHEON_HOME のディレクトリ名（-dev）で判定する。"""
    monkeypatch.delenv("PANTHEON_ENV", raising=False)
    monkeypatch.setenv("PANTHEON_HOME", str(tmp_path / ".pantheon-dev"))
    assert resolve_environment()["environment"] == "development"

    monkeypatch.setenv("PANTHEON_HOME", str(tmp_path / ".pantheon"))
    assert resolve_environment()["environment"] == "production"


def test_platform_status_reports_environment(tmp_path, monkeypatch):
    """/api/platform/status が environment / env_label を返す（GUI バッジ用）。"""
    from fastapi.testclient import TestClient

    monkeypatch.delenv("PANTHEON_ENV", raising=False)
    # PANTHEON_HOME 環境変数が正準の redirect 手段（PlatformStateManager も resolve_environment も
    # core.platform.state.get_platform_home 経由で読む）。tmp の隔離 dev ホームを指す。
    monkeypatch.setenv("PANTHEON_HOME", str(tmp_path / ".pantheon-dev"))

    import web.server as server

    with TestClient(server.app) as client:
        data = client.get("/api/platform/status").json()
    assert data["environment"] == "development"
    assert data["env_label"] == "DEV"


def test_settings_and_chat_paths_derive_from_home():
    """web.server / chat_agent の設定・チャット保存先が get_platform_home() 由来であること。"""
    import agents.chat_agent as chat_agent
    import web.server as server

    base = get_platform_home()
    # 既定（PANTHEON_HOME 未設定）では ~/.pantheon 配下に揃う＝ハードコードではなく home 由来
    assert server.SETTINGS_FILE == base / "gui_settings.json"
    assert server.CHAT_SESSIONS_DIR == base / "chat_sessions"
    assert chat_agent.SETTINGS_FILE == base / "gui_settings.json"


def test_settings_paths_track_home_changes_not_frozen(tmp_path, monkeypatch):
    """設定・チャット保存先は import 時に凍結されず、後続の PANTHEON_HOME 変更へ追随する。

    旧実装は SETTINGS_FILE / CHAT_SESSIONS_DIR を module 定数として import 時に凍結していたため、
    web.server を tmp の PANTHEON_HOME 下で初回 import する別テストが先に走ると、その後 home が
    戻っても凍結値が古い領域を指し続け、単体/小グループ実行で test_settings_and_chat_paths_
    derive_from_home が落ちた（実行順依存フラジリティ）。遅延解決へ移したことの回帰防止 teeth。
    """
    import agents.chat_agent as chat_agent
    import web.server as server

    home_a = tmp_path / "A"
    monkeypatch.setenv("PANTHEON_HOME", str(home_a))
    assert server.SETTINGS_FILE == home_a.resolve() / "gui_settings.json"
    assert server.CHAT_SESSIONS_DIR == home_a.resolve() / "chat_sessions"
    assert chat_agent.SETTINGS_FILE == home_a.resolve() / "gui_settings.json"

    # 凍結していれば home_a を指し続けて落ちる。遅延解決なら home_b へ追随する。
    home_b = tmp_path / "B"
    monkeypatch.setenv("PANTHEON_HOME", str(home_b))
    assert server.SETTINGS_FILE == home_b.resolve() / "gui_settings.json"
    assert server.CHAT_SESSIONS_DIR == home_b.resolve() / "chat_sessions"
    assert chat_agent.SETTINGS_FILE == home_b.resolve() / "gui_settings.json"
