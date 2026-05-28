"""
Code Review Agent

リポジトリのコードを読み込み、LLM で改善提案を生成する SpecialistAgent。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.llm import LLMMessage, get_llm_provider
from core.models.organization import SpecialistAgent

from .base import AgentResult, AgentTask, BaseAgent

logger = logging.getLogger(__name__)

MAX_FILES = 15
MAX_FILE_SIZE_BYTES = 8_000
MAX_TOTAL_CHARS = 40_000

PRIORITY_STEMS = {"main", "app", "cli", "__main__", "server", "api", "run", "index"}

REVIEW_SYSTEM_PROMPT = """あなたはシニアソフトウェアエンジニアです。
与えられたコードリポジトリを分析し、品質・保守性・パフォーマンス・セキュリティの観点から
実行可能な改善提案を3〜5件生成してください。

必ず以下のJSONのみで返してください（説明文・コードブロック不要）:
{
  "suggestions": [
    {
      "title": "改善タイトル（短く具体的に）",
      "description": "問題の詳細な説明と解決方法",
      "file_path": "対象ファイルの相対パス（例: core/models/organization.py）",
      "priority": "high|medium|low",
      "category": "bug|performance|security|maintainability|testing",
      "expected_impact": "改善後の具体的な効果"
    }
  ]
}"""


@dataclass
class CodeImprovementSuggestion:
    """コード改善提案の構造体"""

    title: str
    description: str
    file_path: str
    priority: str = "medium"
    category: str = "maintainability"
    expected_impact: str = ""


class CodeReviewAgent(BaseAgent):
    """
    リポジトリのコードを LLM で分析し、改善提案を生成する SpecialistAgent。

    Sprint 1 アップグレード:
    - スキルエンジンによりシステムプロンプトにスキル専門知識を注入 (A-01)
    - 実行前に KnowledgeManager から関連知識を取得してプロンプトに追加 (B-01)
    - 実行後に分析結果をナレッジとして保存 (B-02)
    """

    def __init__(
        self,
        specialist: SpecialistAgent,
        provider_name: str = "anthropic",
        knowledge_manager: Optional[Any] = None,
    ):
        super().__init__(specialist)
        self._provider_name = provider_name
        self._knowledge = knowledge_manager

    async def run(self, task: AgentTask) -> AgentResult:
        repo_path = Path(task.input.get("repo_path", "."))

        if not repo_path.exists():
            return AgentResult(
                success=False,
                error=f"Repository path does not exist: {repo_path}",
            )

        files_content = self._collect_code_files(
            repo_path,
            max_files=task.input.get("max_files", MAX_FILES),
        )
        if not files_content:
            return AgentResult(success=False, error="No code files found in repository.")

        prior_knowledge = ""
        if self._knowledge:
            prior_knowledge = self._enrich_with_knowledge(
                self._knowledge,
                extra_tags=["code_review", repo_path.name],
            )

        code_context = self._build_code_context(files_content)
        try:
            suggestions = await self._generate_suggestions(
                code_context, repo_path.name, prior_knowledge=prior_knowledge
            )
        except Exception as exc:
            logger.warning("CodeReviewAgent: falling back to heuristic suggestions: %s", exc)
            suggestions = self._generate_fallback_suggestions(files_content)

        if not suggestions:
            suggestions = self._generate_fallback_suggestions(files_content)

        result = AgentResult(
            success=True,
            output={
                "suggestions": [vars(s) for s in suggestions],
                "files_reviewed": len(files_content),
                "knowledge_injected": bool(prior_knowledge),
            },
            thinking_process=f"リポジトリ {repo_path.name} の {len(files_content)} ファイルを分析",
            execution_log=f"Analyzed {len(files_content)} files, generated {len(suggestions)} suggestions",
        )

        if self._knowledge:
            self._save_execution_knowledge(
                self._knowledge,
                result,
                task,
                extra_tags=["code_review", repo_path.name],
            )

        return result

    def _collect_code_files(self, repo_path: Path, max_files: int) -> Dict[str, str]:
        """エントリポイント優先・更新日時順でコードファイルを収集する"""
        exclude_dirs = {
            ".git",
            "__pycache__",
            "node_modules",
            ".venv",
            "venv",
            "dist",
            "build",
            ".mypy_cache",
            ".pytest_cache",
            ".repocorp",
        }
        code_exts = {".py", ".ts", ".js", ".go", ".rs", ".java", ".rb", ".cpp", ".c"}

        candidates: List[Path] = []
        for f in repo_path.rglob("*"):
            if f.is_dir():
                continue
            if f.suffix not in code_exts:
                continue
            if any(part in exclude_dirs for part in f.relative_to(repo_path).parts):
                continue
            candidates.append(f)

        def priority_key(f: Path) -> tuple:
            is_entry = f.stem.lower() in PRIORITY_STEMS
            try:
                mtime = f.stat().st_mtime
            except OSError:
                mtime = 0.0
            return (not is_entry, -mtime)

        candidates.sort(key=priority_key)

        result: Dict[str, str] = {}
        total_chars = 0
        for f in candidates:
            if len(result) >= max_files or total_chars >= MAX_TOTAL_CHARS:
                break
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
                if len(content) > MAX_FILE_SIZE_BYTES:
                    content = content[:MAX_FILE_SIZE_BYTES] + "\n... (truncated)"
                rel = str(f.relative_to(repo_path))
                result[rel] = content
                total_chars += len(content)
            except OSError:
                continue

        return result

    def _build_code_context(self, files: Dict[str, str]) -> str:
        return "\n\n".join(f"=== {path} ===\n{content}" for path, content in files.items())

    def _generate_fallback_suggestions(
        self,
        files: Dict[str, str],
    ) -> List[CodeImprovementSuggestion]:
        """LLM が使えない場合にファイル一覧から規則的な提案を生成する。"""
        file_list = list(files.keys())
        templates = [
            ("型アノテーションの追加", "型ヒントを追加して保守性を向上させる", "maintainability", "high"),
            ("テストカバレッジの向上", "ユニットテストを追加してバグリスクを低減する", "testing", "medium"),
            ("エラーハンドリングの強化", "例外処理を追加して信頼性を向上させる", "bug", "high"),
        ]
        result = []
        for i, (title, desc, category, priority) in enumerate(templates):
            fp = file_list[i % len(file_list)] if file_list else ""
            result.append(
                CodeImprovementSuggestion(
                    title=title,
                    description=desc,
                    file_path=fp,
                    priority=priority,
                    category=category,
                    expected_impact="コードの品質と保守性が向上する",
                )
            )
        return result

    async def _generate_suggestions(
        self, code_context: str, repo_name: str, prior_knowledge: str = ""
    ) -> List[CodeImprovementSuggestion]:
        provider = get_llm_provider(self._provider_name)

        system_prompt = self.apply_skills_to_prompt(REVIEW_SYSTEM_PROMPT)
        knowledge_section = f"\n\n{prior_knowledge}\n" if prior_knowledge else ""

        user_prompt = (
            f"以下はリポジトリ「{repo_name}」のコードです。\n"
            "このコードを詳しく分析し、実行可能な改善提案を生成してください。\n"
            f"{knowledge_section}\n"
            f"{code_context}"
        )
        messages = [
            LLMMessage(role="system", content=system_prompt),
            LLMMessage(role="user", content=user_prompt),
        ]
        try:
            response = await provider.generate(messages=messages, temperature=0.3, max_tokens=3000)
            data = json.loads(response.content)
            return [CodeImprovementSuggestion(**s) for s in data.get("suggestions", [])]
        except json.JSONDecodeError as e:
            logger.warning("CodeReviewAgent: JSON parse failed: %s", e)
            return []
        except Exception as e:
            logger.error("CodeReviewAgent: LLM call failed: %s", e)
            raise
