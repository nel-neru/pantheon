"""
DiffQualityReviewer — 変更差分品質レビュー (F-05)
"""

from __future__ import annotations

import ast
import difflib
from dataclasses import dataclass


@dataclass
class DiffIssue:
    issue_type: str
    description: str
    severity: str


class DiffQualityReviewer:
    def review_diff(self, before: str, after: str, file_path: str = "") -> list[DiffIssue]:
        issues: list[DiffIssue] = []
        before_lines = before.splitlines()
        after_lines = after.splitlines()

        if sum('"""' in line for line in before_lines) > sum('"""' in line for line in after_lines):
            issues.append(
                DiffIssue(
                    issue_type="removed_docstring",
                    description=self._describe(file_path, "Docstring may have been removed."),
                    severity="warning",
                )
            )

        added_lines = [
            line[2:] for line in difflib.ndiff(before_lines, after_lines) if line.startswith("+ ")
        ]
        if any(
            token in line.upper() for line in added_lines for token in ("TODO", "FIXME", "HACK")
        ):
            issues.append(
                DiffIssue(
                    issue_type="added_todo",
                    description=self._describe(file_path, "TODO/FIXME/HACK comment added."),
                    severity="warning",
                )
            )

        if before_lines and len(after_lines) < max(1, int(len(before_lines) * 0.8)):
            issues.append(
                DiffIssue(
                    issue_type="file_too_short",
                    description=self._describe(
                        file_path, "File became significantly shorter after the change."
                    ),
                    severity="error",
                )
            )

        for name, old_sig in self._extract_signatures(before).items():
            new_sig = self._extract_signatures(after).get(name)
            if new_sig and new_sig != old_sig:
                issues.append(
                    DiffIssue(
                        issue_type="signature_changed",
                        description=self._describe(
                            file_path, f"Public function '{name}' signature changed."
                        ),
                        severity="warning",
                    )
                )
        return issues

    def is_acceptable(self, issues: list[DiffIssue]) -> bool:
        return all(issue.severity != "error" for issue in issues)

    def _extract_signatures(self, source: str) -> dict[str, str]:
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return {}

        signatures: dict[str, str] = {}
        for node in tree.body:
            if isinstance(
                node, (ast.FunctionDef, ast.AsyncFunctionDef)
            ) and not node.name.startswith("_"):
                args = [arg.arg for arg in node.args.posonlyargs + node.args.args]
                if node.args.vararg:
                    args.append(f"*{node.args.vararg.arg}")
                args.extend(arg.arg for arg in node.args.kwonlyargs)
                if node.args.kwarg:
                    args.append(f"**{node.args.kwarg.arg}")
                returns = (
                    ast.unparse(node.returns)
                    if node.returns is not None and hasattr(ast, "unparse")
                    else ""
                )
                signatures[node.name] = f"({', '.join(args)}) -> {returns}"
        return signatures

    def _describe(self, file_path: str, message: str) -> str:
        return f"{file_path}: {message}" if file_path else message
