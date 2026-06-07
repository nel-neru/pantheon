"""
scripts/check_planning_docs.py の検証（Phase 5 デリバラブル）。

tests/test_check_flows.py と同じスタイル: importlib でスクリプトをロードし、
live tree では通る／計画ドキュメントが docs/design/ にあると検出することを確認する。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_planning_docs.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("check_planning_docs", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_live_tree_passes():
    module = _load_module()
    assert module.check_planning_docs() == []


def test_detects_kickoff_in_design_dir(tmp_path, monkeypatch):
    module = _load_module()
    design = tmp_path / "docs" / "design"
    design.mkdir(parents=True)
    (design / "phase9-kickoff.md").write_text("# kickoff", encoding="utf-8")
    (design / "architecture-overview.md").write_text("# ok", encoding="utf-8")
    monkeypatch.setattr(module, "DESIGN_DIR", design)
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)

    errors = module.check_planning_docs()
    assert len(errors) == 1
    assert "phase9-kickoff.md" in errors[0]


def test_permanent_design_docs_pass(tmp_path, monkeypatch):
    module = _load_module()
    design = tmp_path / "docs" / "design"
    design.mkdir(parents=True)
    (design / "architecture-overview.md").write_text("# ok", encoding="utf-8")
    (design / "dashboard-wireframes.md").write_text("# ok", encoding="utf-8")
    monkeypatch.setattr(module, "DESIGN_DIR", design)
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)

    assert module.check_planning_docs() == []


def test_main_returns_nonzero_on_violation(tmp_path, monkeypatch, capsys):
    module = _load_module()
    design = tmp_path / "docs" / "design"
    design.mkdir(parents=True)
    (design / "group-monetization-roadmap.md").write_text("# roadmap", encoding="utf-8")
    monkeypatch.setattr(module, "DESIGN_DIR", design)
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)

    assert module.main() == 1
    out = capsys.readouterr().out
    assert "roadmap" in out
