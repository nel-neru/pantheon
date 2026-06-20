"""
LintChecker — Lint統合 (F-08)
ruffをデフォルトとしてlintを自動実行する
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from core.runtime.process_utils import no_window_kwargs


@dataclass
class LintResult:
    file_path: str
    issues: list[str] = field(default_factory=list)
    passed: bool = True


class LintChecker:
    def __init__(self, linter: str = "ruff"):
        self.linter = linter

    def check_file(self, file_path: Path) -> LintResult:
        path = Path(file_path)
        command = [self.linter, "check", str(path), "--select", "E,W"]
        try:
            completed = subprocess.run(
                command, capture_output=True, text=True, check=False, **no_window_kwargs()
            )
        except FileNotFoundError:
            completed = subprocess.run(
                [sys.executable, "-m", "py_compile", str(path)],
                capture_output=True,
                text=True,
                check=False,
                **no_window_kwargs(),
            )

        output = "\n".join(
            part for part in [completed.stdout.strip(), completed.stderr.strip()] if part
        )
        issues = [line for line in output.splitlines() if line.strip()]
        return LintResult(file_path=str(path), issues=issues, passed=completed.returncode == 0)

    def check_files(self, file_paths: list[Path]) -> list[LintResult]:
        return [self.check_file(path) for path in file_paths]

    def all_passed(self, results: list[LintResult]) -> bool:
        return all(result.passed for result in results)
