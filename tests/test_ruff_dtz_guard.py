"""Pin: the tz-aware datetime rule is mechanically enforced by ruff (DTZ).

The repo-wide convention "no datetime.utcnow() / no naive datetime.now(),
always datetime.now(timezone.utc)" used to live only in prose (CLAUDE.md /
AGENTS.md) + code-review. Cycle 4 fixed it by adding the flake8-datetimez (DTZ)
ruleset to ruff. This test fails if that guard is silently dropped, so the
fixation survives future config edits.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

_PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


def _ruff_lint_config() -> dict:
    data = tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))
    return data["tool"]["ruff"]["lint"]


def test_ruff_selects_dtz_ruleset():
    """DTZ must be selected so naive datetime usage fails lint, not review."""
    assert "DTZ" in _ruff_lint_config()["select"]


def test_tests_dir_waives_dtz():
    """Test fixtures may build naive datetimes; DTZ is waived only under tests/."""
    per_file = _ruff_lint_config().get("per-file-ignores", {})
    assert "DTZ" in per_file.get("tests/**", [])
