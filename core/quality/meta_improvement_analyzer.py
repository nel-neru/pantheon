"""
MetaImprovementAnalyzer — Meta-Improvement Organization 特別分析 (H-01)

Meta-Improvement OrgがCoreリポジトリを分析する際に
通常コードレビューではなくアーキテクチャレビューを行う。
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from core.models.organization import ImprovementProposal


@dataclass
class ArchitectureAnalysis:
    repo_root: str
    total_files: int
    total_lines: int
    total_classes: int
    total_functions: int
    large_files: list[str]
    complex_modules: list[str]
    circular_import_hints: list[str]
    analyzed_at: str = ""


class MetaImprovementAnalyzer:
    """Heuristic architecture analyzer for the core repository."""

    def __init__(self, llm_client=None):
        self.llm_client = llm_client
        self._last_line_counts: dict[str, int] = {}
        self._last_function_counts: dict[str, int] = {}

    def analyze_architecture(self, repo_root: Path) -> ArchitectureAnalysis:
        repo_root = Path(repo_root)
        python_files = sorted(repo_root.rglob("*.py"))
        module_names = {self._module_name(repo_root, path) for path in python_files}
        imports_by_module: dict[str, set[str]] = {}

        total_lines = 0
        total_classes = 0
        total_functions = 0
        large_files: list[str] = []
        complex_modules: list[str] = []
        self._last_line_counts = {}
        self._last_function_counts = {}

        for path in python_files:
            relative_path = path.relative_to(repo_root).as_posix()
            source = path.read_text(encoding="utf-8", errors="ignore")
            line_count = len(source.splitlines())
            total_lines += line_count
            self._last_line_counts[relative_path] = line_count
            if line_count > 500:
                large_files.append(relative_path)

            module_name = self._module_name(repo_root, path)
            function_count = 0
            class_count = 0
            imports_by_module[module_name] = set()
            try:
                tree = ast.parse(source)
            except SyntaxError:
                continue

            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    class_count += 1
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    function_count += 1
                elif isinstance(node, ast.Import):
                    imports_by_module[module_name].update(
                        self._extract_imports_from_import(node, module_names)
                    )
                elif isinstance(node, ast.ImportFrom):
                    imports_by_module[module_name].update(
                        self._extract_imports_from_from(node, module_name, module_names)
                    )

            total_classes += class_count
            total_functions += function_count
            self._last_function_counts[relative_path] = function_count
            if function_count > 20:
                complex_modules.append(relative_path)

        circular_import_hints = self._detect_circular_imports(imports_by_module)
        return ArchitectureAnalysis(
            repo_root=str(repo_root),
            total_files=len(python_files),
            total_lines=total_lines,
            total_classes=total_classes,
            total_functions=total_functions,
            large_files=large_files,
            complex_modules=complex_modules,
            circular_import_hints=circular_import_hints,
            analyzed_at=datetime.now(timezone.utc).isoformat(),
        )

    def generate_meta_proposals(self, analysis: ArchitectureAnalysis) -> list[ImprovementProposal]:
        review_id = uuid4()
        proposals: list[ImprovementProposal] = []

        for file_path in analysis.large_files:
            line_count = self._last_line_counts.get(file_path, 0)
            proposals.append(
                ImprovementProposal(
                    review_id=review_id,
                    priority="high" if line_count > 1000 else "medium",
                    category="architecture",
                    title=f"大型モジュール分割: {file_path}",
                    description=(
                        f"{file_path} は {line_count} 行で、500行を超えています。"
                        "責務ごとに分割して変更容易性を高めてください。"
                    ),
                    file_path=file_path,
                    expected_impact="保守性と変更容易性の向上",
                    implementation_difficulty="medium" if line_count <= 1000 else "high",
                )
            )

        for file_path in analysis.complex_modules:
            function_count = self._last_function_counts.get(file_path, 0)
            line_count = self._last_line_counts.get(file_path, 0)
            proposals.append(
                ImprovementProposal(
                    review_id=review_id,
                    priority="high" if line_count > 1000 else "medium",
                    category="architecture",
                    title=f"複雑モジュール整理: {file_path}",
                    description=(
                        f"{file_path} には {function_count} 個の関数があります。"
                        "責務を見直し、モジュール分割または抽象化を検討してください。"
                    ),
                    file_path=file_path,
                    expected_impact="理解容易性とテスト容易性の向上",
                    implementation_difficulty="medium",
                )
            )

        return proposals

    def _module_name(self, repo_root: Path, path: Path) -> str:
        relative = path.relative_to(repo_root).with_suffix("")
        return ".".join(relative.parts)

    def _extract_imports_from_import(self, node: ast.Import, local_modules: set[str]) -> set[str]:
        imports: set[str] = set()
        for alias in node.names:
            name = alias.name
            if name in local_modules:
                imports.add(name)
                continue
            matches = {module for module in local_modules if module.startswith(f"{name}.")}
            imports.update(matches)
        return imports

    def _extract_imports_from_from(
        self,
        node: ast.ImportFrom,
        module_name: str,
        local_modules: set[str],
    ) -> set[str]:
        imports: set[str] = set()
        base_parts = module_name.split(".")[:-1]
        if node.level:
            trim = max(len(base_parts) - (node.level - 1), 0)
            base_parts = base_parts[:trim]
        if node.module:
            target = ".".join(base_parts + node.module.split("."))
            if target in local_modules:
                imports.add(target)
            for alias in node.names:
                candidate = f"{target}.{alias.name}"
                if candidate in local_modules:
                    imports.add(candidate)
        else:
            for alias in node.names:
                candidate = ".".join(base_parts + [alias.name])
                if candidate in local_modules:
                    imports.add(candidate)
        return imports

    def _detect_circular_imports(self, imports_by_module: dict[str, set[str]]) -> list[str]:
        hints: list[str] = []
        for module, imports in imports_by_module.items():
            for imported in imports:
                reverse_imports = imports_by_module.get(imported, set())
                if module in reverse_imports and module < imported:
                    hints.append(f"{module} <-> {imported}")
        return sorted(hints)
