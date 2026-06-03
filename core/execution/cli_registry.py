"""
cli_registry — 外部コーディングCLIツールのレジストリ（CLI実行モード用）

RepoCorp はエージェント実行を2モードで切り替えられる:
- **api**: 内蔵のプロバイダー非依存エージェント（core/llm 経由）。
- **cli**: ユーザーが導入済みの外部コーディングCLI（Claude Code / Codex / Gemini 等）を
  埋め込みターミナルのワークスペースで起動・操作する。

ここは「どの外部CLIをサポートし、どのコマンドで起動するか」の唯一の定義。
コマンドはユーザー設定で上書き可能（gui_settings.cli_commands）。
"""

from __future__ import annotations

import shutil
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional

__all__ = [
    "CliTool",
    "CLI_TOOLS",
    "EXECUTION_MODES",
    "DEFAULT_EXECUTION_MODE",
    "DEFAULT_CLI_TOOL",
    "get_cli_tool",
    "all_cli_tools",
    "is_command_available",
    "resolve_cli_command",
]

EXECUTION_MODES = ["api", "cli"]
DEFAULT_EXECUTION_MODE = "api"
DEFAULT_CLI_TOOL = "claude"


@dataclass(frozen=True)
class CliTool:
    """外部コーディングCLIの定義。"""

    id: str
    label: str
    command: str  # 既定の実行ファイル名（PATH 上で解決）
    description: str
    install_hint: str = ""
    docs_url: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# id -> CliTool
CLI_TOOLS: Dict[str, CliTool] = {
    "claude": CliTool(
        id="claude",
        label="Claude Code",
        command="claude",
        description="Anthropic Claude のコーディングCLI。",
        install_hint="npm i -g @anthropic-ai/claude-code",
        docs_url="https://docs.claude.com/claude-code",
    ),
    "codex": CliTool(
        id="codex",
        label="Codex CLI",
        command="codex",
        description="OpenAI Codex のコーディングCLI。",
        install_hint="npm i -g @openai/codex",
        docs_url="https://github.com/openai/codex",
    ),
    "gemini": CliTool(
        id="gemini",
        label="Gemini CLI",
        command="gemini",
        description="Google Gemini のコーディングCLI。",
        install_hint="npm i -g @google/gemini-cli",
        docs_url="https://github.com/google-gemini/gemini-cli",
    ),
    "aider": CliTool(
        id="aider",
        label="Aider",
        command="aider",
        description="OSS のペアプロCLI（多数のプロバイダー対応）。",
        install_hint="pip install aider-install && aider-install",
        docs_url="https://aider.chat",
    ),
    "opencode": CliTool(
        id="opencode",
        label="OpenCode",
        command="opencode",
        description="OSS のターミナル型コーディングエージェント。",
        install_hint="npm i -g opencode-ai",
        docs_url="https://github.com/opencode-ai/opencode",
    ),
}


def get_cli_tool(tool_id: str) -> Optional[CliTool]:
    return CLI_TOOLS.get(tool_id)


def is_command_available(command: str) -> bool:
    """コマンドが PATH 上に存在するか。"""
    return bool(command) and shutil.which(command) is not None


def resolve_cli_command(tool_id: str, settings: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """ツールIDから実際に起動するコマンドを解決する（設定の上書きを考慮）。

    settings.cli_commands[tool_id] があればそれを優先。無ければ既定コマンド。
    """
    tool = get_cli_tool(tool_id)
    if tool is None:
        return None
    overrides = (settings or {}).get("cli_commands")
    if isinstance(overrides, dict) and overrides.get(tool_id):
        return str(overrides[tool_id])
    return tool.command


def all_cli_tools(settings: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """全CLIツールを、解決済みコマンドと PATH 上の可用性つきで返す（API/UI公開用）。"""
    result: List[Dict[str, Any]] = []
    for tool in CLI_TOOLS.values():
        command = resolve_cli_command(tool.id, settings) or tool.command
        entry = tool.to_dict()
        entry["resolved_command"] = command
        entry["available"] = is_command_available(command)
        result.append(entry)
    return result
