"""
SecurityAuditor — セキュリティ監査 (J-08)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SecurityIssue:
    issue_id: str
    severity: str
    description: str
    file_path: str
    line_number: int = 0


class SecurityAuditor:
    """Regex-based lightweight security auditor."""

    RULES = [
        ("api_key_exposure", "high", re.compile(r"(sk-[A-Za-z0-9_-]+|ghp_[A-Za-z0-9]+|AIza[0-9A-Za-z-_]+)"), "API key exposure risk"),
        ("eval_usage", "high", re.compile(r"\beval\s*\("), "Potential code injection via eval()"),
        ("exec_usage", "high", re.compile(r"\bexec\s*\("), "Potential code injection via exec()"),
        ("os_system_usage", "medium", re.compile(r"\bos\.system\s*\("), "Potential shell injection via os.system()"),
        ("pickle_loads_usage", "high", re.compile(r"\bpickle\.loads\s*\("), "Unsafe deserialization via pickle.loads()"),
    ]

    def audit_file(self, file_path: Path) -> list[SecurityIssue]:
        path = Path(file_path)
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []

        issues: list[SecurityIssue] = []
        for line_number, line in enumerate(lines, start=1):
            for rule_id, severity, pattern, description in self.RULES:
                if pattern.search(line):
                    issues.append(
                        SecurityIssue(
                            issue_id=f"{rule_id}:{path.name}:{line_number}",
                            severity=severity,
                            description=description,
                            file_path=str(path),
                            line_number=line_number,
                        )
                    )
        return issues

    def audit_directory(self, directory: Path) -> list[SecurityIssue]:
        issues: list[SecurityIssue] = []
        for py_file in sorted(Path(directory).rglob("*.py")):
            issues.extend(self.audit_file(py_file))
        return issues

    def format_report(self, issues: list[SecurityIssue]) -> str:
        if not issues:
            return "No security issues found."
        lines = ["Security Audit Report"]
        for issue in issues:
            lines.append(
                f"- [{issue.severity.upper()}] {issue.description} "
                f"({issue.file_path}:{issue.line_number})"
            )
        return "\n".join(lines)
