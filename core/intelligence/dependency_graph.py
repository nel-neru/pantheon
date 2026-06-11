"""
DependencyGraphBuilder — モジュール依存グラフ (K-09)
"""

from __future__ import annotations

import ast
import json
from pathlib import Path


class DependencyGraphBuilder:
    """Build a simple Python module dependency graph."""

    def build(self, repo_root: Path) -> dict[str, list[str]]:
        repo_root = Path(repo_root)
        py_files = sorted(repo_root.rglob("*.py"))
        module_map = {
            self._module_name(repo_root, path): path.relative_to(repo_root).as_posix()
            for path in py_files
        }

        graph: dict[str, list[str]] = {}
        for path in py_files:
            rel_path = path.relative_to(repo_root).as_posix()
            imports: list[str] = []
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (OSError, SyntaxError):
                graph[rel_path] = imports
                continue

            current_module = self._module_name(repo_root, path)
            is_package = path.name == "__init__.py"
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append(self._resolve_module(alias.name, module_map))
                elif isinstance(node, ast.ImportFrom):
                    for alias in node.names:
                        resolved = self._resolve_from_import(
                            current_module, is_package, node, alias.name, module_map
                        )
                        if resolved:
                            imports.append(resolved)
            graph[rel_path] = sorted(dict.fromkeys(imports))
        return graph

    def get_dependents(self, module_path: str, graph: dict) -> list[str]:
        return sorted([path for path, imports in graph.items() if module_path in imports])

    def detect_circular_imports(self, graph: dict) -> list[list[str]]:
        cycles: set[tuple[str, ...]] = set()
        visiting: list[str] = []
        visited: set[str] = set()

        def dfs(node: str):
            if node in visiting:
                idx = visiting.index(node)
                cycles.add(tuple(visiting[idx:] + [node]))
                return
            if node in visited:
                return
            visited.add(node)
            visiting.append(node)
            for dep in graph.get(node, []):
                if dep in graph:
                    dfs(dep)
            visiting.pop()

        for node in graph:
            dfs(node)
        return [list(cycle) for cycle in sorted(cycles)]

    def save_graph(self, graph: dict, output_path: Path) -> None:
        Path(output_path).write_text(
            json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _module_name(self, repo_root: Path, file_path: Path) -> str:
        rel = file_path.relative_to(repo_root).with_suffix("")
        parts = list(rel.parts)
        if parts and parts[-1] == "__init__":
            parts = parts[:-1]
        return ".".join(parts)

    def _resolve_module(self, module_name: str, module_map: dict[str, str]) -> str:
        return module_map.get(module_name, module_name)

    def _resolve_from_import(
        self,
        current_module: str,
        is_package: bool,
        node: ast.ImportFrom,
        alias_name: str,
        module_map: dict[str, str],
    ) -> str:
        if node.level:
            package_parts = (
                current_module.split(".") if is_package else current_module.split(".")[:-1]
            )
            trim = max(node.level - 1, 0)
            if trim:
                package_parts = package_parts[:-trim] if trim <= len(package_parts) else []
            base_parts = package_parts
            if node.module:
                base_parts = package_parts + node.module.split(".")
            if alias_name != "*":
                candidate = ".".join(base_parts + [alias_name]) if base_parts else alias_name
                if candidate in module_map:
                    return module_map[candidate]
            module_name = ".".join(base_parts)
            return module_map.get(module_name, module_name)
        module_name = node.module or alias_name
        if alias_name != "*" and module_name in module_map and alias_name:
            child = f"{module_name}.{alias_name}"
            if child in module_map:
                return module_map[child]
        return module_map.get(module_name, module_name)
