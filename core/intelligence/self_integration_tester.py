"""
SelfIntegrationTester — 自動統合テスト (L-06)

SelfCodeWriter が生成したコードを本番統合前に自動テストする。
- 生成コードの Python syntax 検証
- 既存テストスイートの実行（pytest）
- 基本的な import テスト
"""

from __future__ import annotations

import ast
import importlib.util
import re
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from agents.self_code_writer import CodeOutput


@dataclass
class ValidationResult:
    is_valid: bool
    errors: list[str]
    warnings: list[str]


@dataclass
class TestRunResult:
    passed: bool
    failed: bool
    errors: list[str]
    test_count: int
    duration_seconds: float


@dataclass
class ImportTestResult:
    can_import: bool
    error_message: str = ""


@dataclass
class FullValidationResult:
    syntax_ok: bool
    tests_passed: bool
    can_import: bool
    overall_pass: bool
    details: dict[str, Any]


ValidationResult.__test__ = False
TestRunResult.__test__ = False
ImportTestResult.__test__ = False
FullValidationResult.__test__ = False


class SelfIntegrationTester:
    """自己生成コードの安全性を事前検証するユーティリティ。"""

    def validate_syntax(self, code_output: CodeOutput) -> ValidationResult:
        """ast.parse() で Python 構文を検証する。"""
        try:
            ast.parse(code_output.code_content)
            warnings: list[str] = []
            if not code_output.code_content.endswith("\n"):
                warnings.append("Generated code does not end with a newline.")
            return ValidationResult(is_valid=True, errors=[], warnings=warnings)
        except SyntaxError as exc:
            line = exc.text.strip() if exc.text else ""
            return ValidationResult(
                is_valid=False,
                errors=[f"SyntaxError at line {exc.lineno}: {exc.msg}", line],
                warnings=[],
            )

    def run_existing_tests(self, project_root: Path) -> TestRunResult:
        """既存 pytest スイートを実行し、簡易サマリを返す。"""
        start = time.perf_counter()
        completed = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/", "--tb=short", "-q"],
            cwd=project_root,
            capture_output=True,
            text=True,
            check=False,
        )
        duration = time.perf_counter() - start
        combined_output = "\n".join(
            part for part in [completed.stdout, completed.stderr] if part
        ).strip()
        test_count = self._parse_test_count(combined_output)
        errors: list[str] = []
        if completed.returncode != 0:
            errors = [line for line in combined_output.splitlines()[-20:] if line.strip()]
        return TestRunResult(
            passed=completed.returncode == 0,
            failed=completed.returncode != 0,
            errors=errors,
            test_count=test_count,
            duration_seconds=duration,
        )

    def test_import(self, code_output: CodeOutput, project_root: Path) -> ImportTestResult:
        """生成コードを一時ファイルとして import し、基本 import 可否を検証する。"""
        validation_dir = project_root / ".pantheon" / "self_validation"
        validation_dir.mkdir(parents=True, exist_ok=True)

        module_name = (
            f"_pantheon_validation_{code_output.output_id.replace(':', '_').replace('-', '_')}"
        )
        temp_file = validation_dir / f"{module_name}.py"
        sys_path_entries = [str(project_root), str(validation_dir)]

        try:
            temp_file.write_text(code_output.code_content, encoding="utf-8")
            for entry in reversed(sys_path_entries):
                if entry not in sys.path:
                    sys.path.insert(0, entry)

            spec = importlib.util.spec_from_file_location(module_name, temp_file)
            if spec is None or spec.loader is None:
                return ImportTestResult(
                    can_import=False, error_message="Could not create import spec."
                )

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            return ImportTestResult(can_import=True, error_message="")
        except Exception as exc:
            return ImportTestResult(can_import=False, error_message=str(exc))
        finally:
            sys.modules.pop(module_name, None)
            for entry in sys_path_entries:
                while entry in sys.path:
                    sys.path.remove(entry)
            if temp_file.exists():
                temp_file.unlink()
            pycache_dir = validation_dir / "__pycache__"
            if pycache_dir.exists():
                for item in pycache_dir.iterdir():
                    item.unlink()
                pycache_dir.rmdir()
            if validation_dir.exists() and not any(validation_dir.iterdir()):
                validation_dir.rmdir()

    def run_full_validation(
        self, code_output: CodeOutput, project_root: Path
    ) -> FullValidationResult:
        """構文・import・既存テストをまとめて実行する。"""
        syntax_result = self.validate_syntax(code_output)
        if not syntax_result.is_valid:
            return FullValidationResult(
                syntax_ok=False,
                tests_passed=False,
                can_import=False,
                overall_pass=False,
                details={
                    "syntax": asdict(syntax_result),
                    "tests": None,
                    "import": None,
                },
            )

        import_result = self.test_import(code_output, project_root)
        test_result = self.run_existing_tests(project_root)
        return FullValidationResult(
            syntax_ok=syntax_result.is_valid,
            tests_passed=test_result.passed,
            can_import=import_result.can_import,
            overall_pass=syntax_result.is_valid and test_result.passed and import_result.can_import,
            details={
                "syntax": asdict(syntax_result),
                "tests": asdict(test_result),
                "import": asdict(import_result),
            },
        )

    def _parse_test_count(self, output: str) -> int:
        counts = [
            int(value)
            for value in re.findall(
                r"(\d+)\s+(?:passed|failed|error|errors|skipped|xfailed|xpassed)", output
            )
        ]
        return sum(counts)
