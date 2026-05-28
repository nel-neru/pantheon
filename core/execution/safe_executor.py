"""
SafeChangeExecutor — テスト検証付き変更実行 (F-01~F-03)

コード変更の前にバックアップを取り、
変更後にテストを実行し、
失敗した場合はロールバックする安全な変更実行システム。
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


@dataclass
class BackupRecord:
    original_path: str
    backup_path: str
    backed_up_at: str


@dataclass
class ChangeRequest:
    file_path: str
    new_content: str
    description: str


@dataclass
class ChangeResult:
    success: bool
    file_path: str
    backup_path: str
    tests_passed: bool
    rolled_back: bool
    error_message: str = ""


class SafeChangeExecutor:
    def __init__(self, project_root: Path, backup_dir: Optional[Path] = None):
        self.project_root = Path(project_root).resolve()
        self.backup_dir = Path(backup_dir) if backup_dir else self.project_root / ".repocorp" / "backups"
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.backup_dir / "manifest.json"
        if not self.manifest_path.exists():
            self.manifest_path.write_text("[]", encoding="utf-8")

    def apply_change(self, change: ChangeRequest) -> ChangeResult:
        target_path = self._resolve_path(change.file_path)
        backup_record = self.create_backup(str(target_path))

        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(change.new_content, encoding="utf-8")
            tests_passed, test_output, summary = self._run_tests()
            if not tests_passed:
                rolled_back = self.rollback(backup_record)
                return ChangeResult(
                    success=False,
                    file_path=str(target_path),
                    backup_path=backup_record.backup_path,
                    tests_passed=False,
                    rolled_back=rolled_back,
                    error_message=self._build_test_error_message(test_output, summary),
                )

            return ChangeResult(
                success=True,
                file_path=str(target_path),
                backup_path=backup_record.backup_path,
                tests_passed=True,
                rolled_back=False,
            )
        except Exception as exc:
            rolled_back = self.rollback(backup_record)
            return ChangeResult(
                success=False,
                file_path=str(target_path),
                backup_path=backup_record.backup_path,
                tests_passed=False,
                rolled_back=rolled_back,
                error_message=str(exc),
            )

    def rollback(self, backup_record: BackupRecord) -> bool:
        original_path = Path(backup_record.original_path)
        try:
            if backup_record.backup_path:
                original_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(backup_record.backup_path, original_path)
                return True
            if original_path.exists():
                original_path.unlink()
            return True
        except OSError:
            return False

    def create_backup(self, file_path: str) -> BackupRecord:
        original_path = self._resolve_path(file_path)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
        backup_path = ""

        if original_path.exists():
            backup_target = self.backup_dir / f"{timestamp}_{original_path.name}.bak"
            shutil.copy2(original_path, backup_target)
            backup_path = str(backup_target)

        record = BackupRecord(
            original_path=str(original_path),
            backup_path=backup_path,
            backed_up_at=datetime.now(timezone.utc).isoformat(),
        )
        self._append_manifest(record)
        return record

    def list_backups(self, file_path: str = None) -> list[BackupRecord]:
        records = [BackupRecord(**item) for item in self._load_manifest()]
        if file_path is not None:
            target = str(self._resolve_path(file_path))
            records = [record for record in records if record.original_path == target]
        records.sort(key=lambda record: record.backed_up_at, reverse=True)
        return records

    def _run_tests(self) -> tuple[bool, str, dict[str, int]]:
        completed = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/", "--tb=short", "-q"],
            cwd=self.project_root,
            capture_output=True,
            text=True,
            timeout=120,
        )
        output = "\n".join(part for part in [completed.stdout.strip(), completed.stderr.strip()] if part).strip()
        summary = self._parse_pytest_summary(output)
        tests_passed = completed.returncode == 0 and summary.get("failed", 0) == 0 and summary.get("errors", 0) == 0
        return tests_passed, output, summary

    def _parse_pytest_summary(self, output: str) -> dict[str, int]:
        summary: dict[str, int] = {"passed": 0, "failed": 0, "errors": 0}
        for key in summary:
            match = re.search(rf"(\d+)\s+{key}", output)
            if match:
                summary[key] = int(match.group(1))
        return summary

    def _build_test_error_message(self, output: str, summary: dict[str, int]) -> str:
        summary_text = ", ".join(
            f"{count} {name}" for name, count in summary.items() if count
        ) or "no pytest summary available"
        return f"Tests failed ({summary_text}). {output}".strip()

    def _append_manifest(self, record: BackupRecord) -> None:
        data = self._load_manifest()
        data.append(asdict(record))
        self.manifest_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _load_manifest(self) -> list[dict[str, str]]:
        try:
            return json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []

    def _resolve_path(self, file_path: str) -> Path:
        path = Path(file_path)
        if path.is_absolute():
            return path
        return self.project_root / path
