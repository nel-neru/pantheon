"""
DocGenerator — ドキュメント自動生成 (I-11)
docstringからMarkdownドキュメントを生成する
"""

from __future__ import annotations

import ast
from pathlib import Path


class DocGenerator:
    """Generate markdown documentation from Python docstrings."""

    def __init__(self):
        pass

    def extract_docstrings(self, file_path: Path) -> dict:
        tree = ast.parse(Path(file_path).read_text(encoding="utf-8"))
        classes: dict[str, dict] = {}
        functions: dict[str, str] = {}

        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                methods = {}
                for child in node.body:
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        methods[child.name] = ast.get_docstring(child) or ""
                classes[node.name] = {
                    "docstring": ast.get_docstring(node) or "",
                    "methods": methods,
                }
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions[node.name] = ast.get_docstring(node) or ""

        return {
            "module": ast.get_docstring(tree) or "",
            "classes": classes,
            "functions": functions,
        }

    def generate_markdown(self, file_path: Path) -> str:
        extracted = self.extract_docstrings(file_path)
        lines = [f"# {Path(file_path).name}"]
        if extracted["module"]:
            lines.extend(["", extracted["module"]])

        lines.extend(["", "## Classes"])
        if extracted["classes"]:
            for name, payload in extracted["classes"].items():
                lines.extend(["", f"### {name}"])
                if payload["docstring"]:
                    lines.append(payload["docstring"])
                for method_name, method_doc in payload["methods"].items():
                    lines.extend(["", f"#### {method_name}()"])
                    lines.append(method_doc or "(no docstring)")
        else:
            lines.extend(["", "(none)"])

        lines.extend(["", "## Functions"])
        if extracted["functions"]:
            for name, docstring in extracted["functions"].items():
                lines.extend(["", f"### {name}()"])
                lines.append(docstring or "(no docstring)")
        else:
            lines.extend(["", "(none)"])
        return "\n".join(lines) + "\n"

    def generate_for_directory(self, directory: Path, output_file: Path) -> int:
        docs: list[str] = []
        count = 0
        for py_file in sorted(Path(directory).rglob("*.py")):
            if py_file == output_file:
                continue
            docs.append(self.generate_markdown(py_file))
            count += 1
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text("\n\n---\n\n".join(docs), encoding="utf-8")
        return count
