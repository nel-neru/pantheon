"""core 中立性ガードをテストゲートで強制する（業務を core に置かせない仕組み化）。"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent


def _load_guard():
    spec = importlib.util.spec_from_file_location(
        "check_core_neutrality", _REPO / "scripts" / "check_core_neutrality.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_core_is_neutral():
    """core/config/docs/content に業務固有アーティファクトが無いこと。"""
    guard = _load_guard()
    violations = guard.find_violations(_REPO)
    assert violations == [], f"core 中立性違反: {violations}"


def test_guard_detects_injected_violation(tmp_path):
    """ガードが違反を検知できること（偽陰性でないことの確認）。"""
    guard = _load_guard()
    (tmp_path / "core" / "affiliate").mkdir(parents=True)
    assert "core/affiliate" in guard.find_violations(tmp_path)
