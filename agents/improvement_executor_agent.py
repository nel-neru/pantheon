"""
Improvement Executor Agent

承認された改善提案をコードに適用し、GitHub に PR を作成する SpecialistAgent。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from core.llm import LLMMessage, get_llm_provider
from core.models.organization import SpecialistAgent

from .base import AgentResult, AgentTask, BaseAgent

logger = logging.getLogger(__name__)

APPLY_SYSTEM_PROMPT = """あなたはシニアソフトウェアエンジニアです。
与えられた改善提案を、元のコードに正確に適用してください。

必ず以下のJSONのみで返してください（説明文・コードブロック不要）:
{
  "modified_content": "変更後のファイル全体の内容（文字列）",
  "change_summary": "何をどう変えたかの1〜2行の説明"
}

制約:
- 改善提案の内容のみを変更し、無関係な箇所は変えない
- 変更後のコードは構文的に正しくなければならない
- ファイル全体を返すこと（部分的なスニペットは不可）"""


class ImprovementExecutorAgent(BaseAgent):
    """
    承認済みの改善提案をコードに適用し、PR を作成する SpecialistAgent。
    GitHub token がない場合はローカルのブランチに変更を保存する。
    """

    def __init__(self, specialist: SpecialistAgent, provider_name: str = "anthropic"):
        super().__init__(specialist)
        self._provider_name = provider_name

    async def run(self, task: AgentTask) -> AgentResult:
        repo_path = Path(task.input.get("repo_path", ".")).resolve()
        suggestion: Dict[str, Any] = task.input.get("suggestion", {})
        github_token: Optional[str] = task.input.get("github_token")
        github_repo: Optional[str] = task.input.get("github_repo")

        if not suggestion:
            return AgentResult(success=False, error="No suggestion provided.")

        file_path: str = suggestion.get("file_path", "")
        if not file_path:
            return AgentResult(success=False, error="suggestion.file_path is required.")

        try:
            target_file = self._resolve_repo_file_path(repo_path, file_path)
        except ValueError as exc:
            return AgentResult(success=False, error=str(exc))
        normalized_file_path = str(target_file.relative_to(repo_path))
        if not target_file.exists():
            return AgentResult(
                success=False, error=f"Target file not found: {normalized_file_path}"
            )

        original_content = target_file.read_text(encoding="utf-8")

        modified_content, change_summary = await self._generate_code_change(
            original_content, normalized_file_path, suggestion
        )
        if not modified_content:
            return AgentResult(success=False, error="LLM failed to generate a valid code change.")

        if github_token and github_repo:
            try:
                from github_integration.pr_creator import create_improvement_pr

                pr_url = await create_improvement_pr(
                    repo_path=repo_path,
                    github_token=github_token,
                    github_repo=github_repo,
                    file_path=normalized_file_path,
                    modified_content=modified_content,
                    suggestion=suggestion,
                )
                output = {
                    "pr_url": pr_url,
                    "change_summary": change_summary,
                    "file_path": normalized_file_path,
                }
            except Exception as e:
                return AgentResult(success=False, error=f"PR creation failed: {e}")
        else:
            try:
                output = self._apply_local_change(
                    repo_path, normalized_file_path, modified_content, change_summary, suggestion
                )
            except Exception as e:
                return AgentResult(success=False, error=f"Local change failed: {e}")

        return AgentResult(
            success=True,
            output=output,
            thinking_process=f"改善提案「{suggestion.get('title')}」を {normalized_file_path} に適用",
            execution_log=f"Modified {normalized_file_path}: {change_summary}",
        )

    def _apply_local_change(
        self,
        repo_path: Path,
        file_path: str,
        modified_content: str,
        change_summary: str,
        suggestion: Dict[str, Any],
    ) -> Dict[str, Any]:
        """git branch を作成してローカルにコミットする（直接上書きしない）"""
        try:
            import git
        except ImportError:
            raise ImportError("GitPython が必要です: pip install GitPython")

        import re
        from datetime import datetime, timezone

        slug = re.sub(r"[^a-z0-9]+", "-", suggestion.get("title", "improvement").lower())[:40]
        branch_name = (
            f"pantheon/improvement-{slug}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        )

        repo_root = repo_path.resolve()
        target = self._resolve_repo_file_path(repo_root, file_path)
        relative_file_path = str(target.relative_to(repo_root))

        repo = git.Repo(repo_root)
        repo.git.checkout("-b", branch_name)

        target.write_text(modified_content, encoding="utf-8")
        repo.index.add([relative_file_path])
        repo.index.commit(f"refactor: {suggestion.get('title', 'Apply improvement')}")

        return {
            "branch": branch_name,
            "change_summary": change_summary,
            "file_path": relative_file_path,
        }

    def _resolve_repo_file_path(self, repo_path: Path, file_path: str) -> Path:
        candidate = Path(file_path)
        if candidate.is_absolute():
            raise ValueError("Absolute paths are not allowed in suggestion.file_path")
        if any(part == ".." for part in candidate.parts):
            raise ValueError("Path traversal is not allowed in suggestion.file_path")

        resolved_repo_path = repo_path.resolve()
        resolved_target = (resolved_repo_path / candidate).resolve(strict=False)
        if not self._is_within_repo(resolved_target, resolved_repo_path):
            raise ValueError("Resolved path escapes the repository root")
        return resolved_target

    def _is_within_repo(self, path: Path, repo_path: Path) -> bool:
        try:
            path.relative_to(repo_path)
            return True
        except ValueError:
            return False

    async def _generate_code_change(
        self,
        original_content: str,
        file_path: str,
        suggestion: Dict[str, Any],
    ) -> Tuple[str, str]:
        provider = get_llm_provider(self._provider_name)
        user_prompt = (
            f"ファイル: {file_path}\n\n"
            f"【改善提案】\n"
            f"タイトル: {suggestion.get('title')}\n"
            f"説明: {suggestion.get('description')}\n\n"
            f"【元のコード】\n"
            f"{original_content}"
        )
        messages = [
            LLMMessage(role="system", content=APPLY_SYSTEM_PROMPT),
            LLMMessage(role="user", content=user_prompt),
        ]
        try:
            response = await provider.generate(
                messages=messages,
                temperature=0.2,
                max_tokens=8000,
                task_type="improvement_execution",
            )
            data = json.loads(response.content)
            return data.get("modified_content", ""), data.get("change_summary", "")
        except json.JSONDecodeError as e:
            logger.warning("ImprovementExecutorAgent: JSON parse failed: %s", e)
            return "", ""
        except Exception as e:
            logger.error("ImprovementExecutorAgent: LLM call failed: %s", e)
            raise
