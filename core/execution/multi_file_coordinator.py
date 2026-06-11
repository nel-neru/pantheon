"""
MultiFileChangeCoordinator — 複数ファイル変更整合性 (F-04)
import関係・関数シグネチャの整合性を変更後に検証する
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ConsistencyIssue:
    file_path: str
    issue_type: str
    description: str


class MultiFileChangeCoordinator:
    def check_import_consistency(self, changed_files: list[Path]) -> list[ConsistencyIssue]:
        issues: list[ConsistencyIssue] = []
        python_files = [Path(path) for path in changed_files if Path(path).suffix == ".py"]
        module_map = self._build_module_map(python_files)

        for file_path in python_files:
            try:
                tree = ast.parse(file_path.read_text(encoding="utf-8"))
            except (OSError, SyntaxError) as exc:
                issues.append(
                    ConsistencyIssue(
                        file_path=str(file_path),
                        issue_type="parse_error",
                        description=f"Failed to parse file: {exc}",
                    )
                )
                continue

            for module_name in self._extract_imports(tree, file_path):
                if self._module_exists(module_name, file_path, module_map):
                    continue
                issues.append(
                    ConsistencyIssue(
                        file_path=str(file_path),
                        issue_type="broken_import",
                        description=f"Imported module '{module_name}' could not be resolved.",
                    )
                )
        return issues

    def check_signature_consistency(
        self, before: dict[str, str], after: dict[str, str]
    ) -> list[ConsistencyIssue]:
        issues: list[ConsistencyIssue] = []
        for file_path in sorted(set(before) & set(after)):
            before_sigs = self._extract_public_signatures(before[file_path])
            after_sigs = self._extract_public_signatures(after[file_path])
            for name, signature in before_sigs.items():
                changed = after_sigs.get(name)
                if changed is None or changed == signature:
                    continue
                issues.append(
                    ConsistencyIssue(
                        file_path=file_path,
                        issue_type="signature_changed",
                        description=f"Public function '{name}' signature changed from '{signature}' to '{changed}'.",
                    )
                )
        return issues

    def validate_changes(self, file_paths: list[Path]) -> tuple[bool, list[ConsistencyIssue]]:
        issues = self.check_import_consistency(file_paths)
        return not issues, issues

    def _build_module_map(self, file_paths: list[Path]) -> dict[str, Path]:
        module_map: dict[str, Path] = {}
        for file_path in file_paths:
            path = Path(file_path)
            module_map[path.stem] = path
            dotted = ".".join(path.with_suffix("").parts)
            if dotted:
                module_map[dotted] = path
            if path.name == "__init__.py" and path.parent.parts:
                module_map[".".join(path.parent.parts)] = path
        return module_map

    def _extract_imports(self, tree: ast.AST, file_path: Path) -> list[str]:
        imports: list[str] = []
        current_module = ".".join(file_path.with_suffix("").parts)
        current_parts = current_module.split(".") if current_module else []

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    base_parts = current_parts[: -node.level]
                    if node.module:
                        imports.append(".".join(base_parts + node.module.split(".")))
                    else:
                        imports.extend(
                            ".".join(base_parts + [alias.name])
                            for alias in node.names
                            if alias.name != "*"
                        )
                    continue

                if node.module:
                    imports.append(node.module)
                    imports.extend(
                        f"{node.module}.{alias.name}" for alias in node.names if alias.name != "*"
                    )
        return [name for name in imports if name and name != "__future__"]

    def _module_exists(
        self, module_name: str, file_path: Path, module_map: dict[str, Path]
    ) -> bool:
        if module_name in module_map:
            return True
        if module_name in sys.modules:
            return True
        try:
            if importlib.util.find_spec(module_name) is not None:
                return True
        except (ImportError, ValueError):
            pass

        module_parts = module_name.split(".")
        candidate = file_path.parent.joinpath(*module_parts)
        return candidate.with_suffix(".py").exists() or (candidate / "__init__.py").exists()

    def _extract_public_signatures(self, source: str) -> dict[str, str]:
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return {}

        signatures: dict[str, str] = {}
        for node in tree.body:
            if isinstance(
                node, (ast.FunctionDef, ast.AsyncFunctionDef)
            ) and not node.name.startswith("_"):
                signatures[node.name] = self._signature_repr(node)
        return signatures

    def _signature_repr(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
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
        return f"({', '.join(args)}) -> {returns}"
