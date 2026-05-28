"""
RepoBibliography — リポジトリ百科事典自動生成 (K-13)
"""

from __future__ import annotations

import ast
from pathlib import Path


class RepoBibliography:
    """Generate a markdown bibliography from repository docs and module docstrings."""

    def __init__(self):
        pass

    def generate(self, repo_root: Path) -> str:
        repo_root = Path(repo_root)
        lines = ["# Repository Bibliography"]
        readme = repo_root / "README.md"
        if readme.exists():
            lines.extend(["", "## README", "", readme.read_text(encoding="utf-8")])

        docs = self.extract_module_docs(repo_root)
        lines.extend(["", "## Module Documentation"])
        if not docs:
            lines.extend(["", "(none)"])
        else:
            for rel_path, docstring in sorted(docs.items()):
                lines.extend(["", f"### {rel_path}", "", docstring])
        return "\n".join(lines) + "\n"

    def extract_module_docs(self, repo_root: Path) -> dict[str, str]:
        repo_root = Path(repo_root)
        docs: dict[str, str] = {}
        for py_file in sorted(repo_root.rglob("*.py")):
            try:
                tree = ast.parse(py_file.read_text(encoding="utf-8"))
            except (OSError, SyntaxError):
                continue
            docstring = ast.get_docstring(tree)
            if docstring:
                docs[str(py_file.relative_to(repo_root))] = docstring
        return docs
