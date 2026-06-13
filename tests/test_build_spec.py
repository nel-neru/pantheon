"""P3.1: PyInstaller spec 健全性チェックのテスト（ビルド硬化）。"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_checker():
    spec_path = REPO_ROOT / "scripts" / "check_build_spec.py"
    spec = importlib.util.spec_from_file_location("check_build_spec", spec_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def test_real_spec_has_no_critical_errors():
    """同梱中の packaging/pantheon.spec は重要リソースを全て datas に含む。"""
    checker = _load_checker()
    errors, _warnings = checker.check_build_spec(REPO_ROOT)
    assert errors == [], f"spec の致命的問題: {errors}"


def test_missing_resource_is_detected(tmp_path: Path):
    """重要リソースが datas から欠落していたら error として検出される。"""
    checker = _load_checker()
    # config を datas に含まない壊れた spec を再現
    (tmp_path / "packaging").mkdir()
    (tmp_path / "packaging" / "pantheon.spec").write_text(
        "datas = []\nhiddenimports = []\n", encoding="utf-8"
    )
    errors, _ = checker.check_build_spec(tmp_path)
    assert any("config" in e for e in errors)
    assert any("hiddenimports" in e for e in errors)


def test_spec_syntax_error_is_detected(tmp_path: Path):
    checker = _load_checker()
    (tmp_path / "packaging").mkdir()
    (tmp_path / "packaging" / "pantheon.spec").write_text("datas = [\n", encoding="utf-8")
    errors, _ = checker.check_build_spec(tmp_path)
    assert any("構文エラー" in e for e in errors)
