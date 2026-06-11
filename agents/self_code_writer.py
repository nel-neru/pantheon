"""
SelfCodeWriter — 自己コード生成エージェント (L-05)

ToolDesignAgent が生成した実装仕様書を元に実際の Python コードを生成する。
既存コードスタイル・命名規則に従ったコードを生成し、
既存テストへの影響を最小化する。
"""

from __future__ import annotations

import ast
import json
import logging
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from agents.base import AgentResult, AgentTask, BaseAgent
from agents.tool_design_agent import ImplementationSpec
from core.models.organization import AgentSkill, SpecialistAgent

logger = logging.getLogger(__name__)

CODE_WRITER_SYSTEM_PROMPT = """あなたは Pantheon の Python 実装エージェントです。
ImplementationSpec の内容だけを満たす、構文的に正しい Python コードを返してください。"""


@dataclass
class CodeOutput:
    """生成されたコード本体。"""

    output_id: str
    file_path: str
    code_content: str
    is_new_file: bool
    spec_id: str
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()
        if not self.output_id:
            self.output_id = f"code:{self.spec_id}:{uuid4().hex[:8]}"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CodeOutput":
        allowed = {key for key in cls.__dataclass_fields__}
        return cls(**{key: value for key, value in data.items() if key in allowed})


def _make_default_specialist() -> SpecialistAgent:
    return SpecialistAgent(
        name="SelfCodeWriter",
        skills=[AgentSkill.PROMPT_ENGINEERING, AgentSkill.TOOL_INTEGRATION],
        description="実装仕様から Pantheon 互換の Python コードを生成する。",
    )


class SelfCodeWriter(BaseAgent):
    """ImplementationSpec から Python コードを生成する自己拡張エージェント。"""

    def __init__(
        self,
        specialist: Optional[SpecialistAgent] = None,
        llm_client: Optional[Any] = None,
    ) -> None:
        super().__init__(specialist or _make_default_specialist())
        self._llm = llm_client

    def write_code(self, spec: ImplementationSpec, existing_code_context: str = "") -> CodeOutput:
        """実装仕様を Python コードに変換する。"""
        if self._llm:
            llm_code = self._write_with_llm(spec, existing_code_context=existing_code_context)
            if llm_code is not None:
                return llm_code
        return self._write_template(spec)

    async def run(self, task: AgentTask) -> AgentResult:
        raw_spec = task.input.get("spec")
        if raw_spec is None:
            return AgentResult(success=False, error="task.input['spec'] is required")

        spec = (
            raw_spec
            if isinstance(raw_spec, ImplementationSpec)
            else ImplementationSpec.from_dict(raw_spec)
        )
        code_output = self.write_code(
            spec,
            existing_code_context=task.input.get("existing_code_context", ""),
        )
        return AgentResult(
            success=True,
            output={"code_output": code_output},
            thinking_process=f"ImplementationSpec {spec.spec_id} を Python コードへ変換",
            execution_log=f"Generated {code_output.file_path}",
        )

    def _write_template(self, spec: ImplementationSpec) -> CodeOutput:
        code_content = (
            self._render_agent_template(spec)
            if self._is_agent_spec(spec)
            else self._render_utility_template(spec)
        )
        self._validate_generated_code(code_content, spec.file_path)
        self._warn_on_placeholder_code(code_content, spec)
        return CodeOutput(
            output_id=f"code:{spec.spec_id}",
            file_path=spec.file_path,
            code_content=code_content,
            is_new_file=True,
            spec_id=spec.spec_id,
        )

    def _write_with_llm(
        self,
        spec: ImplementationSpec,
        existing_code_context: str = "",
    ) -> Optional[CodeOutput]:
        prompt = f"""{CODE_WRITER_SYSTEM_PROMPT}

ImplementationSpec:
{json.dumps(spec.to_dict(), ensure_ascii=False, indent=2)}

Existing code context:
{existing_code_context or "(none)"}
"""
        try:
            response = self._llm.invoke(prompt)
            content = response.content if hasattr(response, "content") else str(response)
            code_content = content.strip()
            self._validate_generated_code(code_content, spec.file_path)
            self._warn_on_placeholder_code(code_content, spec)
            return CodeOutput(
                output_id=f"code:{spec.spec_id}",
                file_path=spec.file_path,
                code_content=code_content,
                is_new_file=True,
                spec_id=spec.spec_id,
            )
        except Exception as exc:
            logger.warning("SelfCodeWriter LLM generation failed: %s", exc)
            return None

    def _validate_generated_code(self, code: str, file_path: str) -> None:
        try:
            ast.parse(code)
        except SyntaxError as exc:
            raise ValueError(
                f"Generated code is not syntactically valid for {file_path}: {exc}"
            ) from exc

    def _warn_on_placeholder_code(self, code: str, spec: ImplementationSpec) -> None:
        if "TODO" in code:
            logger.warning(
                "SelfCodeWriter generated placeholder TODO code for %s (%s)",
                spec.spec_id,
                spec.file_path,
            )

    def detect_required_libraries(self, code: str) -> list[str]:
        """Detect likely third-party imports from generated code."""
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return []

        stdlib = set(getattr(sys, "stdlib_module_names", set()))
        repo_root = Path(__file__).resolve().parents[1]
        project_modules = {path.stem for path in repo_root.glob("*.py")}
        project_modules.update(
            path.name
            for path in repo_root.iterdir()
            if path.is_dir() and (path / "__init__.py").exists()
        )

        libraries: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    continue
                modules = [(node.module or "").split(".")[0]]
            else:
                continue
            for module in modules:
                if not module or module in stdlib or module in project_modules:
                    continue
                libraries.add(module)
        return sorted(libraries)

    def suggest_pyproject_additions(self, libraries: list[str]) -> str:
        """Return a pyproject.toml dependency suggestion."""
        if not libraries:
            return ""
        joined = ", ".join(sorted(dict.fromkeys(libraries)))
        return f"pyproject.tomlへの追加を推奨:\n  dependencies: {joined}"

    def _render_agent_template(self, spec: ImplementationSpec) -> str:
        imports = [
            "from typing import Any",
            "from agents.base import AgentResult, AgentTask, BaseAgent",
            "from core.models.organization import AgentSkill, SpecialistAgent",
        ]
        imports.extend(spec.required_imports)
        lines = [
            f'"""{spec.description}"""',
            "",
            "from __future__ import annotations",
            "",
        ]
        lines.extend(self._dedupe_imports(imports))
        lines.extend(
            [
                "",
                "",
                "def _make_default_specialist() -> SpecialistAgent:",
                "    return SpecialistAgent(",
                f'        name="{spec.class_name}",',
                "        skills=[AgentSkill.PROMPT_ENGINEERING, AgentSkill.TOOL_INTEGRATION],",
                f'        description="{self._escape_string(spec.description)}",',
                "    )",
                "",
                "",
                f"class {spec.class_name}(BaseAgent):",
                f'    """{self._escape_string(spec.description)}"""',
                "",
                "    def __init__(self, specialist: SpecialistAgent | None = None) -> None:",
                "        super().__init__(specialist or _make_default_specialist())",
            ]
        )
        for signature in spec.method_signatures:
            lines.extend(["", *self._render_method(signature, spec)])
        return "\n".join(lines) + "\n"

    def _render_utility_template(self, spec: ImplementationSpec) -> str:
        imports = ["from typing import Any"]
        imports.extend(spec.required_imports)
        lines = [
            f'"""{spec.description}"""',
            "",
            "from __future__ import annotations",
            "",
        ]
        lines.extend(self._dedupe_imports(imports))
        lines.extend(
            [
                "",
                "",
                f"class {spec.class_name}:",
                f'    """{self._escape_string(spec.description)}"""',
                "",
                "    def __init__(self) -> None:",
                f'        self.spec_id = "{spec.spec_id}"',
                f'        self.description = "{self._escape_string(spec.description)}"',
            ]
        )
        for signature in spec.method_signatures:
            lines.extend(["", *self._render_method(signature, spec)])
        return "\n".join(lines) + "\n"

    def _render_method(self, signature: str, spec: ImplementationSpec) -> list[str]:
        normalized = self._normalize_signature(signature)
        method_name = self._method_name_from_signature(normalized)
        indent = "    "
        body_indent = f"{indent}    "
        method_lines = [f"{indent}{normalized}"]

        if method_name == "run":
            method_lines.extend(
                [
                    f'{body_indent}"""Auto-generated execution entrypoint."""',
                    f"{body_indent}# TODO: Replace the placeholder workflow with the behavior described in the spec.",
                    f"{body_indent}return AgentResult(",
                    f"{body_indent}    success=True,",
                    f"{body_indent}    output={{'status': 'generated_stub', 'spec_id': '{spec.spec_id}', 'task_type': task.task_type}},",
                    f"{body_indent}    thinking_process='Generated stub execution path',",
                    f"{body_indent}    execution_log='SelfCodeWriter generated placeholder run() implementation',",
                    f"{body_indent})",
                ]
            )
            return method_lines

        method_lines.extend(
            [
                f'{body_indent}"""Auto-generated stub for {method_name}."""',
                f"{body_indent}# TODO: Implement according to ImplementationSpec {spec.spec_id}.",
                f"{body_indent}{self._default_return_statement(normalized)}",
            ]
        )
        return method_lines

    def _default_return_statement(self, signature: str) -> str:
        match = re.search(r"->\s*([^:]+)", signature)
        annotation = match.group(1).strip() if match else "None"
        if annotation.startswith("dict"):
            return "return {}"
        if annotation.startswith("list"):
            return "return []"
        if annotation == "str":
            return "return ''"
        if annotation == "bool":
            return "return False"
        if annotation == "int":
            return "return 0"
        if annotation == "float":
            return "return 0.0"
        if annotation in {"None", "None | dict[str, Any]"}:
            return "return None"
        return "return None"

    def _normalize_signature(self, signature: str) -> str:
        normalized = signature.strip()
        if not normalized.endswith(":"):
            normalized = f"{normalized}:"
        return normalized

    def _method_name_from_signature(self, signature: str) -> str:
        match = re.search(r"def\s+([a-zA-Z_][a-zA-Z0-9_]*)", signature)
        return match.group(1) if match else "generated_method"

    def _dedupe_imports(self, imports: list[str]) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for line in imports:
            stripped = line.strip()
            if not stripped or stripped in seen:
                continue
            seen.add(stripped)
            ordered.append(stripped)
        return ordered

    def _is_agent_spec(self, spec: ImplementationSpec) -> bool:
        return spec.file_path.startswith("agents/") or spec.class_name.endswith("Agent")

    def _escape_string(self, value: str) -> str:
        return (
            value.replace("\\", "\\\\")
            .replace("\n", "\\n")
            .replace("\r", "\\r")
            .replace("\t", "\\t")
            .replace('"', '\\"')
        )
