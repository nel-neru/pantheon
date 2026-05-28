"""
SetupWizard — セットアップウィザード (I-09)
"""

from __future__ import annotations

import json
import os
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
            SetupStep(1, "API キー設定", "ANTHROPIC_API_KEY を .env に設定してください"),
            SetupStep(2, "初期組織の作成", "repocorp org add <name> コマンドで組織を作成してください"),
            SetupStep(3, "リポジトリの登録", "分析対象のリポジトリパスを登録してください"),
            SetupStep(4, "初回分析の実行", "repocorp analyze コマンドで初回分析を開始してください"),
        ]

    def check_completion_status(self) -> dict[str, bool]:
        platform_home = get_platform_home()
        org_dir = platform_home / "organizations"
        org_files = sorted(org_dir.glob("*.json")) if org_dir.exists() else []

        has_api_key = bool(os.environ.get("ANTHROPIC_API_KEY")) or self._env_has_api_key()
        has_org = bool(org_files)
        has_repo = False
        has_analysis = False

        for path in org_files:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            repo_path = Path(data.get("target_repo_path", "")).expanduser() if data.get("target_repo_path") else None
            if repo_path and str(repo_path):
                has_repo = has_repo or repo_path.exists()
                has_analysis = has_analysis or (repo_path / ".repocorp").exists()

        return {
            "API キー設定": has_api_key,
            "初期組織の作成": has_org,
            "リポジトリの登録": has_repo,
            "初回分析の実行": has_analysis,
        }

    def format_wizard_cli(self) -> str:
        status = self.check_completion_status()
        lines = ["RepoCorp AI セットアップウィザード"]
        for step in self.get_steps():
            completed = status.get(step.title, False)
            icon = "✅" if completed else "⬜"
            lines.append(f"{icon} Step {step.step_number}: {step.title}")
            lines.append(f"   {step.description}")
        return "\n".join(lines)

    def _env_has_api_key(self) -> bool:
        env_path = Path.cwd() / ".env"
        if not env_path.exists():
            return False
        try:
            return "ANTHROPIC_API_KEY=" in env_path.read_text(encoding="utf-8")
        except OSError:
            return False
