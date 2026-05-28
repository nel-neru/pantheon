"""
SystemDoctor — システム整合性診断・修復 (G-06)
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from core.platform.state import get_platform_home


@dataclass
class DiagnosticIssue:
    issue_id: str
    severity: str
    description: str
    auto_fixable: bool


class SystemDoctor:
    def __init__(self, platform_home=None):
        self.platform_home = Path(platform_home) if platform_home else get_platform_home()
        self.platform_home.mkdir(parents=True, exist_ok=True)
        self.db_path = self.platform_home / "state.db"
        self.backups_dir = self.platform_home / "backups"
        self.profiles_dir = self.platform_home / "profiles"

    def diagnose(self) -> list[DiagnosticIssue]:
        issues: list[DiagnosticIssue] = []

        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.execute("PRAGMA integrity_check").fetchone()
            conn.close()
        except sqlite3.DatabaseError as exc:
            issues.append(
                DiagnosticIssue(
                    issue_id="sqlite_integrity",
                    severity="error",
                    description=f"SQLite DB is not accessible or may be corrupted: {exc}",
                    auto_fixable=False,
                )
            )

        for issue_id, path in (("missing_backups_dir", self.backups_dir), ("missing_profiles_dir", self.profiles_dir)):
            if not path.exists():
                issues.append(
                    DiagnosticIssue(
                        issue_id=issue_id,
                        severity="warning",
                        description=f"Required directory is missing: {path}",
                        auto_fixable=True,
                    )
                )

        limit_bytes = 10 * 1024 * 1024
        for json_file in self.platform_home.rglob("*.json"):
            try:
                if json_file.stat().st_size > limit_bytes:
                    issues.append(
                        DiagnosticIssue(
                            issue_id=f"json_bloat:{json_file.name}",
                            severity="warning",
                            description=f"JSON file exceeds 10MB: {json_file}",
                            auto_fixable=False,
                        )
                    )
            except OSError:
                continue

        return issues

    def fix_issues(self, issues: list[DiagnosticIssue]) -> int:
        fixed = 0
        for issue in issues:
            if not issue.auto_fixable:
                continue
            if issue.issue_id == "missing_backups_dir":
                self.backups_dir.mkdir(parents=True, exist_ok=True)
                fixed += 1
            elif issue.issue_id == "missing_profiles_dir":
                self.profiles_dir.mkdir(parents=True, exist_ok=True)
                fixed += 1
        return fixed

    def run_full_diagnosis(self) -> str:
        issues = self.diagnose()
        if not issues:
            return "SystemDoctor: no issues found."
        lines = ["SystemDoctor Report:"]
        for issue in issues:
            lines.append(f"- [{issue.severity}] {issue.issue_id}: {issue.description}")
        return "\n".join(lines)
