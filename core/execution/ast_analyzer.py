"""
ASTAnalyzer — ASTベースセマンティックコード理解 (F-07)
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class FunctionInfo:
    name: str
    args: list[str] = field(default_factory=list)
    returns: str = ""
    lineno: int = 0
    is_public: bool = True
    docstring: str = ""


@dataclass
class ClassInfo:
    name: str
    methods: list[str] = field(default_factory=list)
    bases: list[str] = field(default_factory=list)
    lineno: int = 0


class ASTAnalyzer:
    def analyze_file(self, file_path: Path) -> dict:
        path = Path(file_path)
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except (OSError, SyntaxError):
            return {}

        functions: list[FunctionInfo] = []
        classes: list[ClassInfo] = []
        imports: list[str] = []

        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append(self._function_info(node))
            elif isinstance(node, ast.ClassDef):
                classes.append(
                    ClassInfo(
                        name=node.name,
                        methods=[child.name for child in node.body if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))],
                        bases=[ast.unparse(base) if hasattr(ast, "unparse") else getattr(base, "id", "") for base in node.bases],
                        lineno=node.lineno,
                    )
                )

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)

        return {
            "functions": functions,
            "classes": classes,
            "imports": imports,
            "line_count": len(source.splitlines()),
        }

    def find_function(self, file_path: Path, function_name: str) -> FunctionInfo | None:
        result = self.analyze_file(file_path)
        for function in result.get("functions", []):
            if function.name == function_name:
                return function
        return None

    def get_change_location(self, file_path: Path, function_name: str) -> int | None:
        function = self.find_function(file_path, function_name)
        return function.lineno if function else None

    def _function_info(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> FunctionInfo:
        args = [arg.arg for arg in node.args.posonlyargs + node.args.args]
        if node.args.vararg:
            args.append(f"*{node.args.vararg.arg}")
        args.extend(arg.arg for arg in node.args.kwonlyargs)
        if node.args.kwarg:
            args.append(f"**{node.args.kwarg.arg}")
        returns = ast.unparse(node.returns) if node.returns is not None and hasattr(ast, "unparse") else ""
        return FunctionInfo(
            name=node.name,
            args=args,
            returns=returns,
            lineno=node.lineno,
            is_public=not node.name.startswith("_"),
            docstring=ast.get_docstring(node) or "",
        )
