"""evolve_resume_launcher.py（窓なし起動ランチャ）の契約検証。

このランチャの存在意義は「pythonw から powershell を CREATE_NO_WINDOW で起動して
毎時タスクの窓フラッシュ＝フォーカス奪取を断つ」こと。よってここでは
**窓なしフラグ・コマンド構築・戻り値伝播**という壊れたら無音で回帰する不変条件を固定する。

注意: launcher は `import subprocess` した共有モジュールの `run` を呼ぶため、差し替えは
必ず monkeypatch 経由で行う（直接代入はプロセス全体の subprocess.run を汚染し、他テストを壊す）。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_launcher():
    spec = importlib.util.spec_from_file_location(
        "evolve_resume_launcher", _REPO_ROOT / "scripts" / "evolve_resume_launcher.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_create_no_window_constant():
    """CREATE_NO_WINDOW は CreateProcess の dwCreationFlags（窓フラッシュ抑止の要）。"""
    module = _load_launcher()
    assert module.CREATE_NO_WINDOW == 0x08000000


def test_main_spawns_powershell_windowless(monkeypatch):
    """powershell を -File evolve_resume.ps1 で、必ず CREATE_NO_WINDOW で起動する。"""
    module = _load_launcher()
    captured: dict = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    rc = module.main(["launcher", "120"])

    assert rc == 0
    cmd = captured["cmd"]
    # powershell 本体 + 非対話で ps1 を -File 実行 + StaleMinutes を伝搬
    assert cmd[0].lower().endswith("powershell.exe") or cmd[0].lower().endswith("powershell")
    assert "-NoProfile" in cmd
    assert "-ExecutionPolicy" in cmd and "Bypass" in cmd
    assert "-File" in cmd
    ps1 = cmd[cmd.index("-File") + 1]
    assert Path(ps1).name == "evolve_resume.ps1"
    assert "-StaleMinutes" in cmd
    assert cmd[cmd.index("-StaleMinutes") + 1] == "120"
    # 窓なし契約: 必ずこのフラグで起動する
    assert captured["kwargs"].get("creationflags") == module.CREATE_NO_WINDOW
    # cwd=repo 契約: タスクスケジューラ下で ps1 の相対パス解決が System32 から
    # 走って無音で壊れないよう、必ずリポジトリルートを cwd にする。
    assert Path(captured["kwargs"].get("cwd")).resolve() == _REPO_ROOT


def test_main_defaults_stale_to_90(monkeypatch):
    """引数なし起動時の StaleMinutes 既定は 90（install スクリプトの既定と一致）。"""
    module = _load_launcher()
    captured: dict = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    module.main(["launcher"])
    cmd = captured["cmd"]
    assert cmd[cmd.index("-StaleMinutes") + 1] == "90"


def test_main_propagates_returncode(monkeypatch):
    """powershell の終了コードを Task Scheduler の Last Run Result へ正しく伝える。"""
    module = _load_launcher()

    monkeypatch.setattr(module.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=7))
    assert module.main(["launcher"]) == 7


def test_main_returns_1_when_ps1_missing(monkeypatch, tmp_path):
    """ps1 が無ければ subprocess を起動せず 1 を返し、観測可能にログへ残す。"""
    module = _load_launcher()
    # __file__ を ps1 の隣に無い場所へ向けることで「ps1 不在」を再現する。
    fake_file = tmp_path / "evolve_resume_launcher.py"
    fake_file.write_text("# placeholder", encoding="utf-8")
    monkeypatch.setattr(module, "__file__", str(fake_file))

    logged: list[str] = []
    monkeypatch.setattr(module, "_log", lambda msg: logged.append(msg))

    def fail_run(*a, **k):  # 起動してはならない
        raise AssertionError("ps1 不在時に subprocess.run を呼んではならない")

    monkeypatch.setattr(module.subprocess, "run", fail_run)
    assert module.main(["launcher"]) == 1
    assert any("evolve_resume.ps1" in m for m in logged)


def test_main_returns_1_on_spawn_failure(monkeypatch):
    """powershell の起動自体が失敗したら、無コンソール下でも 1 を返しログへ残す。"""
    module = _load_launcher()

    def boom(*a, **k):
        raise FileNotFoundError("powershell not found")

    logged: list[str] = []
    monkeypatch.setattr(module.subprocess, "run", boom)
    monkeypatch.setattr(module, "_log", lambda msg: logged.append(msg))
    assert module.main(["launcher"]) == 1
    assert any("起動に失敗" in m for m in logged)


def test_powershell_path_resolves():
    """PATH 最小化下でも System32 の既定パスへフォールバックして解決する。"""
    module = _load_launcher()
    resolved = module._powershell_path()
    assert resolved.lower().endswith("powershell.exe") or resolved.lower().endswith("powershell")
