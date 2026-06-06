"""
Phase 4 — flows.json 整合性チェッカー（scripts/check_flows.py）の検証。
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_check_flows():
    spec = importlib.util.spec_from_file_location(
        "check_flows", _REPO_ROOT / "scripts" / "check_flows.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_flows_json_is_in_sync():
    module = _load_check_flows()
    errors = module.check_flows()
    assert errors == [], f"flows.json is stale/inconsistent: {errors}"


def test_check_flows_detects_missing_verification(tmp_path, monkeypatch):
    module = _load_check_flows()
    bad = {
        "flows": [
            {
                "id": "x",
                "name": "X",
                "summary": "s",
                "trigger": {"kind": "cli", "name": "x"},
                "steps": [{"component": "core/does_not_exist_zzz.py:Foo", "action": "a"}],
                "surfaces": [],
                "status": "solid",
                "verification": ["tests/test_does_not_exist_zzz.py"],
            }
        ]
    }
    bad_path = tmp_path / "flows.json"
    bad_path.write_text(json.dumps(bad), encoding="utf-8")
    monkeypatch.setattr(module, "FLOWS_PATH", bad_path)

    errors = module.check_flows()
    assert any("verification file missing" in e for e in errors)
    assert any("step component file missing" in e for e in errors)


def test_check_flows_detects_invalid_status(tmp_path, monkeypatch):
    module = _load_check_flows()
    bad = {
        "flows": [
            {
                "id": "y",
                "name": "Y",
                "summary": "s",
                "trigger": {"kind": "cli", "name": "y"},
                "steps": [],
                "surfaces": [],
                "status": "totally-bogus",
            }
        ]
    }
    bad_path = tmp_path / "flows.json"
    bad_path.write_text(json.dumps(bad), encoding="utf-8")
    monkeypatch.setattr(module, "FLOWS_PATH", bad_path)

    errors = module.check_flows()
    assert any("invalid status" in e for e in errors)
