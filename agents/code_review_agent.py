"""
Code Review Agent

リポジトリのコードを読み込み、LLM で改善提案を生成する SpecialistAgent。
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional

from core.llm import LLMMessage, get_llm_provider
from core.models.organization import SpecialistAgent

from .base import AgentResult, AgentTask, BaseAgent

logger = logging.getLogger(__name__)

MAX_FILES = 15
MAX_FILE_SIZE_BYTES = 8_000
MAX_TOTAL_CHARS = 40_000

PRIORITY_STEMS = {"main", "app", "cli", "__main__", "server", "api", "run", "index"}
VALID_PRIORITIES = {"high", "medium", "low"}
VALID_CATEGORIES = {
    "architecture",
    "bug",
    "comment",
    "documentation",
    "general",
    "maintainability",
    "performance",
    "quality",
    "security",
    "self_extension",
    "style",
    "testing",
}

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


def _normalize_choice(value: str, *, field_name: str, allowed_values: set[str]) -> str:
    normalized = (value or "").strip().lower()
    if normalized not in allowed_values:
        allowed = ", ".join(sorted(allowed_values))
        raise ValueError(f"{field_name} must be one of: {allowed}")
    return normalized


def _normalize_relative_file_path(file_path: str) -> str:
    normalized = (file_path or "").strip().replace("\\", "/")
    if not normalized:
        raise ValueError("file_path must not be empty")
    if normalized.startswith("/") or normalized.startswith("~"):
        raise ValueError("file_path must be a repository-relative path")
    if len(normalized) >= 2 and normalized[1] == ":" and normalized[0].isalpha():
        raise ValueError("file_path must be a repository-relative path")

    pure_path = PurePosixPath(normalized)
    if pure_path.name in {"", ".", ".."} or any(part in {".", ".."} for part in pure_path.parts):
        raise ValueError("file_path must stay within the repository root")
    return pure_path.as_posix()


@dataclass
class CodeImprovementSuggestion:
    """コード改善提案の構造体"""

    title: str
    description: str
    file_path: str
    priority: str = "medium"
    category: str = "maintainability"
    expected_impact: str = ""

    def __post_init__(self) -> None:
        self.priority = _normalize_choice(
            self.priority,
            field_name="priority",
            allowed_values=VALID_PRIORITIES,
        )
        self.category = _normalize_choice(
            self.category,
            field_name="category",
            allowed_values=VALID_CATEGORIES,
        )
        self.file_path = _normalize_relative_file_path(self.file_path)


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
        self.knowledge_manager = knowledge_manager

    async def run(self, task: AgentTask) -> AgentResult:
        repo_path = Path(task.input.get("repo_path", ".")).resolve()

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
            ".pantheon",
        }
        code_exts = {".py", ".ts", ".js", ".go", ".rs", ".java", ".rb", ".cpp", ".c"}
        repo_root = repo_path.resolve()

        candidates: List[Path] = []
        for current_root, dirnames, filenames in os.walk(repo_root, followlinks=False):
            current_path = Path(current_root)
            dirnames[:] = [
                dirname
                for dirname in dirnames
                if dirname not in exclude_dirs and not (current_path / dirname).is_symlink()
            ]
            for filename in filenames:
                candidate = current_path / filename
                if candidate.is_symlink() or candidate.suffix not in code_exts:
                    continue
                try:
                    resolved_candidate = candidate.resolve()
                    resolved_candidate.relative_to(repo_root)
                except (OSError, ValueError):
                    continue
                candidates.append(resolved_candidate)

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
                rel = f.relative_to(repo_root).as_posix()
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
            (
                "型アノテーションの追加",
                "型ヒントを追加して保守性を向上させる",
                "maintainability",
                "high",
            ),
            (
                "テストカバレッジの向上",
                "ユニットテストを追加してバグリスクを低減する",
                "testing",
                "medium",
            ),
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

    @staticmethod
    def _build_recall_query(repo_name: str, code_context: str, *, max_chars: int = 2000) -> str:
        """意味リコール（C5）用の query を、レビュー対象そのものから作る。

        リポジトリ名＋コード本文の先頭 ``max_chars`` 文字を連結した代表サンプルを返す。
        この query を ``apply_skills_to_prompt`` 経由で ``MemoryBank.recall`` に渡すと、
        過去の Playbook が「いま見ているコードとの関連度」で再ランクされる。
        コード本文は大きくなり得るので有界化し、BM25 のトークン化コストを抑える。
        """
        return f"{repo_name}\n{code_context[:max_chars]}"

    async def _generate_suggestions(
        self, code_context: str, repo_name: str, prior_knowledge: str = ""
    ) -> List[CodeImprovementSuggestion]:
        provider = get_llm_provider(self._provider_name)

        recall_query = self._build_recall_query(repo_name, code_context)
        system_prompt = self.apply_skills_to_prompt(REVIEW_SYSTEM_PROMPT, query=recall_query)
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
            response = await provider.generate(
                messages=messages, temperature=0.3, max_tokens=3000, task_type="code_review"
            )
            data = json.loads(response.content)
            suggestions: List[CodeImprovementSuggestion] = []
            for raw_suggestion in data.get("suggestions", []):
                try:
                    suggestions.append(CodeImprovementSuggestion(**raw_suggestion))
                except (TypeError, ValueError) as exc:
                    logger.warning("CodeReviewAgent: skipping invalid suggestion: %s", exc)
            return suggestions
        except json.JSONDecodeError as e:
            logger.warning("CodeReviewAgent: JSON parse failed: %s", e)
            return []
        except Exception as e:
            logger.error("CodeReviewAgent: LLM call failed: %s", e)
            raise
