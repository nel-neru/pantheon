from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_validate_config_module():
    script_path = Path(__file__).resolve().parent.parent / "scripts" / "validate_config.py"
    spec = importlib.util.spec_from_file_location("validate_config", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_validate_config_passes_for_repo_root():
    module = _load_validate_config_module()
    repo_root = Path(__file__).resolve().parent.parent
    assert module.main(["--root", str(repo_root)]) == 0


def test_validate_config_reports_invalid_skill_file(tmp_path, capsys):
    module = _load_validate_config_module()

    skills_dir = tmp_path / "skills"
    skills_dir.mkdir(parents=True)
    (skills_dir / "broken.yaml").write_text("name: Broken Skill\n", encoding="utf-8")

    exit_code = module.main(["--root", str(tmp_path)])
    out = capsys.readouterr().out

    assert exit_code == 1
    assert "Config validation failed" in out
    assert "missing required key 'schema_version'" in out
