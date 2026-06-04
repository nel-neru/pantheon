"""
SetupWizard — セットアップウィザード (I-09)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from core.platform.state import get_platform_home


@dataclass
class SetupStep:
    step_number: int
    title: str
    description: str
    completed: bool = False


class SetupWizard:
    """Simple setup guide backed by platform state checks."""

    def get_steps(self) -> list[SetupStep]:
        return [
            SetupStep(
                1,
                "Claude CLI 認証",
                "claude をインストールし `claude` でログインしてください（Pantheon は API キー不要）",
            ),
            SetupStep(
                2, "初期組織の作成", "pantheon org add <name> コマンドで組織を作成してください"
            ),
            SetupStep(3, "リポジトリの登録", "分析対象のリポジトリパスを登録してください"),
            SetupStep(4, "初回分析の実行", "pantheon analyze コマンドで初回分析を開始してください"),
        ]

    def check_completion_status(self) -> dict[str, bool]:
        platform_home = get_platform_home()
        org_dir = platform_home / "organizations"
        org_files = sorted(org_dir.glob("*.json")) if org_dir.exists() else []

        has_backend = self._claude_backend_ready()
        has_org = bool(org_files)
        has_repo = False
        has_analysis = False

        for path in org_files:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            repo_path = (
                Path(data.get("target_repo_path", "")).expanduser()
                if data.get("target_repo_path")
                else None
            )
            if repo_path and str(repo_path):
                has_repo = has_repo or repo_path.exists()
                has_analysis = has_analysis or (repo_path / ".pantheon").exists()

        return {
            "Claude CLI 認証": has_backend,
            "初期組織の作成": has_org,
            "リポジトリの登録": has_repo,
            "初回分析の実行": has_analysis,
        }

    def format_wizard_cli(self) -> str:
        status = self.check_completion_status()
        lines = ["Pantheon セットアップウィザード"]
        for step in self.get_steps():
            completed = status.get(step.title, False)
            icon = "✅" if completed else "⬜"
            lines.append(f"{icon} Step {step.step_number}: {step.title}")
            lines.append(f"   {step.description}")
        return "\n".join(lines)

    def _claude_backend_ready(self) -> bool:
        """True when the local ``claude`` CLI backend is available (Pantheon uses no API keys)."""
        try:
            from core.runtime.claude_code import claude_available

            return claude_available()
        except Exception:
            return False
