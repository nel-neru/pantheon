"""
ImpactAnalyzer — 変更影響範囲分析 (F-06)
"""

from __future__ import annotations

import ast
from collections import deque
from pathlib import Path


class ImpactAnalyzer:
    def build_import_graph(self, repo_root: Path) -> dict[str, list[str]]:
        repo_root = Path(repo_root)
        python_files = sorted(repo_root.rglob("*.py"))
        module_to_path: dict[str, str] = {}
        graph: dict[str, list[str]] = {}

        for file_path in python_files:
            rel_path = str(file_path.relative_to(repo_root))
            graph.setdefault(rel_path, [])
            module_name = self._module_name(repo_root, file_path)
            if module_name:
                module_to_path[module_name] = rel_path
            module_to_path[file_path.stem] = rel_path

        for file_path in python_files:
            importer = str(file_path.relative_to(repo_root))
            try:
                tree = ast.parse(file_path.read_text(encoding="utf-8"))
            except (OSError, SyntaxError):
                continue

            for module_name in self._extract_imports(tree):
                target = self._resolve_module_path(module_name, module_to_path)
                if not target or target == importer:
                    continue
                graph.setdefault(target, [])
                if importer not in graph[target]:
                    graph[target].append(importer)
        return graph

    def find_dependents(self, file_path: str, graph: dict) -> list[str]:
        start = self._normalize_graph_key(file_path, graph)
        if not start:
            return []

        queue = deque([(start, 0)])
        seen = {start}
        dependents: list[str] = []

        while queue:
            current, depth = queue.popleft()
            if depth >= 3:
                continue
            for dependent in graph.get(current, []):
                if dependent in seen:
                    continue
                seen.add(dependent)
                dependents.append(dependent)
                queue.append((dependent, depth + 1))
        return dependents

    def assess_impact(self, file_path: str, graph: dict) -> str:
        count = len(self.find_dependents(file_path, graph))
        if count == 0:
            return "low"
        if count <= 3:
            return "medium"
        return "high"

    def should_require_human_review(self, file_path: str, graph: dict) -> bool:
        return self.assess_impact(file_path, graph) == "high"

    def _module_name(self, repo_root: Path, file_path: Path) -> str:
        rel = file_path.relative_to(repo_root).with_suffix("")
        parts = list(rel.parts)
        if parts and parts[-1] == "__init__":
            parts = parts[:-1]
        return ".".join(parts)

    def _extract_imports(self, tree: ast.AST) -> list[str]:
        modules: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules.append(node.module)
                modules.extend(
                    f"{node.module}.{alias.name}" for alias in node.names if alias.name != "*"
                )
        return modules

    def _resolve_module_path(self, module_name: str, module_to_path: dict[str, str]) -> str | None:
        if module_name in module_to_path:
            return module_to_path[module_name]
        parts = module_name.split(".")
        while parts:
            candidate = ".".join(parts)
            if candidate in module_to_path:
                return module_to_path[candidate]
            parts.pop()
        return None

    def _normalize_graph_key(self, file_path: str, graph: dict) -> str | None:
        if file_path in graph:
            return file_path
        path_obj = Path(file_path)
        normalized = path_obj.as_posix()
        if normalized in graph:
            return normalized
        for key in graph:
            if key.endswith(normalized) or Path(key).name == path_obj.name:
                return key
        return None
