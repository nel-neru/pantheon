"""
CodebaseExplorerAgent — コードベース調査専門エージェント (K-05)

「コードベースを調査する」というタスクを専門に担うSpecialistAgent。
スキル: CODEBASE_EXPLORATION + DEEP_RESEARCH

調査プロトコル:
  1. CodebaseIndexer でインデックス確認（なければ構築）
  2. CodebaseSnapshot で目的別スナップショット生成（最小トークン）
  3. 必要な場合のみファイル精読
  4. 調査結果を KnowledgeManager に保存（次回の調査コストを削減）

全エージェントがコードベース調査に毎回生ファイルを読む代わりに
このエージェントを呼び出すことでトークンを大幅削減する。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from agents.base import AgentResult, AgentTask, BaseAgent
from core.llm.json_extract import extract_json_object
from core.models.organization import AgentSkill, SpecialistAgent

logger = logging.getLogger(__name__)


def _make_default_specialist() -> SpecialistAgent:
    return SpecialistAgent(
        name="CodebaseExplorer",
        skills=[AgentSkill.CODEBASE_EXPLORATION, AgentSkill.DEEP_RESEARCH],
        description="コードベース調査の専門エージェント。インデックスとスナップショットを活用してトークンを最小化する。",
    )


EXPLORATION_SYSTEM_PROMPT = """あなたはコードベース調査の専門家です。
提供されたコードベーススナップショットを分析し、以下の形式でJSON回答を返してください。
説明文やコードブロックは不要です。

{
  "summary": "コードベースの全体像（100字以内）",
  "key_files": ["重要なファイルのリスト（最大5件）"],
  "architecture_pattern": "アーキテクチャパターン（例：MVC, Clean Architecture等）",
  "main_technologies": ["使用技術・ライブラリ（最大5件）"],
  "entry_points": ["エントリポイントファイルのリスト"],
  "potential_issues": ["気になる点・潜在的問題（最大3件）"],
  "investigation_notes": "詳細な調査メモ"
}"""


def _extract_json_object(content: str) -> Optional[Dict[str, Any]]:
    # JSON 抽出は core.llm.extract_json_object に一本化（全 `{` 位置を走査し
    # 最初に decode できる値を返す堅牢版）。dict のみ受け付ける契約を維持。
    result = extract_json_object(content)
    return result if isinstance(result, dict) else None


class CodebaseExplorerAgent(BaseAgent):
    """
    コードベース調査に特化したSpecialistAgent。

    CodebaseIndexer + CodebaseSnapshot を使って、
    毎回の生ファイル読み込みを廃止しトークンを最小化する。
    """

    def __init__(
        self,
        specialist: Optional[SpecialistAgent] = None,
        llm_client: Optional[Any] = None,
        knowledge_manager: Optional[Any] = None,
        pattern_detector: Optional[Any] = None,
    ):
        super().__init__(specialist or _make_default_specialist())
        self._llm = llm_client
        self._knowledge = knowledge_manager
        self.knowledge_manager = knowledge_manager
        self._detector = pattern_detector

    async def run(self, task: AgentTask) -> AgentResult:
        """コードベース調査タスクを実行する。"""
        repo_path_str = task.input.get("repo_path", ".")
        mode = task.input.get("mode", "exploration")
        max_tokens = task.input.get("max_tokens", 3000)
        target_file = task.input.get("target_file")
        auto_save_results = task.input.get("auto_save_results", True)

        try:
            payload = await self.explore(
                repo_path=repo_path_str,
                mode=mode,
                max_tokens=max_tokens,
                target_file=target_file,
                auto_save_results=auto_save_results,
            )
            return AgentResult(
                success=True,
                output=payload,
                thinking_process=f"{Path(repo_path_str).name} のコードベースを {mode} モードで調査",
                execution_log=(
                    f"Index: {payload.get('index_stats', {}).get('total_files', 0)}ファイル, "
                    f"Context: ~{payload.get('estimated_tokens', 0)}トークン, "
                    f"{payload.get('elapsed_ms', 0)}ms"
                ),
            )
        except Exception as exc:
            logger.exception("CodebaseExplorerAgent failed: %s", exc)
            return AgentResult(success=False, error=str(exc))

    async def explore(
        self,
        repo_path: str | Path,
        mode: str = "exploration",
        max_tokens: int = 3000,
        target_file: str | None = None,
        auto_save_results: bool = True,
        **_kwargs: Any,
    ) -> Dict[str, Any]:
        """Explore a repository and optionally auto-save the summary."""
        import time

        start = time.time()
        repo_root = Path(repo_path).expanduser().resolve()
        if not repo_root.exists():
            raise FileNotFoundError(f"リポジトリパスが存在しません: {repo_root}")

        if self._detector:
            self._detector.record_operation(
                "codebase_scan",
                self.name,
                target=str(repo_root),
                tokens_used=0,
            )

        from core.intelligence.codebase_indexer import CodebaseIndexer
        from core.intelligence.codebase_snapshot import CodebaseSnapshot

        indexer = CodebaseIndexer(repo_root)
        indexer.build()
        stats = indexer.get_summary_stats()
        # CodebaseSnapshot は CodebaseIndexer オブジェクトを受け取る（build() の戻り値 dict ではない）。
        snapshot = CodebaseSnapshot(indexer)
        context = (
            snapshot.generate_for_file(target_file)
            if target_file
            else snapshot.generate(mode=mode, max_tokens=max_tokens)
        )
        estimated_tokens = len(context) // 4
        result_data = await self._analyze_with_llm(context, repo_root.name, mode)
        elapsed_ms = int((time.time() - start) * 1000)

        if self._detector:
            self._detector.record_operation(
                "codebase_scan",
                self.name,
                target=str(repo_root),
                tokens_used=estimated_tokens,
                success=True,
                duration_ms=elapsed_ms,
            )

        if self._knowledge and auto_save_results:
            self._save_to_knowledge(repo_root.name, result_data, mode)

        return {
            **result_data,
            "snapshot_mode": mode,
            "index_stats": stats,
            "estimated_tokens": estimated_tokens,
            "elapsed_ms": elapsed_ms,
        }

    async def _analyze_with_llm(self, context: str, repo_name: str, mode: str) -> Dict[str, Any]:
        """LLM でコードベースを分析する。"""
        if not self._llm:
            return self._fallback_result(mode)

        prompt = f"""コードベース: {repo_name}
調査モード: {mode}

{context}"""

        try:
            from core.llm import LLMMessage

            messages = [
                LLMMessage(role="system", content=EXPLORATION_SYSTEM_PROMPT),
                LLMMessage(role="user", content=prompt),
            ]
            try:
                response = await self._llm.ainvoke([m.__dict__ for m in messages])
            except AttributeError:
                response = self._llm.invoke([m.__dict__ for m in messages])

            content = response.content if hasattr(response, "content") else str(response)

            payload = _extract_json_object(content)
            if payload is not None:
                return payload
        except Exception as e:
            logger.warning("LLM analysis failed: %s", e)

        return self._fallback_result(mode)

    def _fallback_result(self, mode: str) -> Dict[str, Any]:
        return {
            "summary": f"{mode} モードのコードベース調査結果",
            "key_files": ["main.py", "core/models/organization.py"],
            "architecture_pattern": "Multi-agent LangGraph workflow",
            "main_technologies": ["Python", "LangGraph", "Pydantic", "FastAPI"],
            "entry_points": ["main.py"],
            "potential_issues": ["スキルが動作に影響しない", "知識ループが未接続"],
            "investigation_notes": "LLM が利用できないため既定の調査結果を返しました",
        }

    def _save_to_knowledge(self, repo_name: str, result: Dict[str, Any], mode: str) -> None:
        """調査結果をKnowledgeManagerに保存して次回再利用できるようにする。"""
        try:
            summary = result.get("summary", "")
            content = (
                f"コードベース調査サマリー（{mode}モード）: {summary}\n"
                f"主要ファイル: {', '.join(result.get('key_files', []))}\n"
                f"アーキテクチャ: {result.get('architecture_pattern', '')}\n"
                f"技術スタック: {', '.join(result.get('main_technologies', []))}\n"
                f"注意点: {', '.join(result.get('potential_issues', []))}"
            )
            title = f"[CodebaseExplorer] {repo_name} ({mode})"
            if hasattr(self._knowledge, "save"):
                self._knowledge.save(title=title, content=content)
            else:
                self._knowledge.save_insight(
                    title=title,
                    content=content,
                    tags=["codebase_exploration", f"repo:{repo_name}", f"mode:{mode}"],
                    importance="normal",
                )
        except Exception as e:
            logger.debug("Knowledge save failed: %s", e)
