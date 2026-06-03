"""
CoreImprovementAgent — RepoCorp 自身（Core）を自律改善する内蔵コーディングエージェント

「WebGUI から Core を改善する」基盤。プロバイダー非依存（core/llm の LLMClient）で動き、
外部のコーディングCLIツールに一切依存しない。

ループ:
  1. 対象ファイルを読む
  2. LLM が指示に基づき変更後の全文を生成（generate_json）
  3. SafeChangeExecutor で バックアップ→書き込み→テスト実行→失敗時ロールバック
  4. テスト失敗ならエラーを文脈に戻して反復（上限付き）
  5. テスト成功:
       - validate_only(既定): 検証済み差分を作り、作業ツリーは元に戻す（人間承認用の提案にする）
       - apply: 変更を適用したまま残す（auto_approve ポリシー時のみ想定）

LLMクライアントが無い場合はスタブ生成せず、明確に失敗を返す
（自己コード改変でテンプレートを書き込むのは危険なため）。
"""

from __future__ import annotations

import difflib
import logging
from pathlib import Path
from typing import Any, Optional

from agents.base import AgentResult, AgentTask, BaseAgent
from core.execution.safe_executor import ChangeRequest, SafeChangeExecutor
from core.models.organization import AgentSkill, SpecialistAgent

logger = logging.getLogger(__name__)

CORE_IMPROVE_SYSTEM_PROMPT = """あなたは RepoCorp AI 自身のコードベースを改善するシニアエンジニアです。
与えられた「改善指示」を、対象ファイルの元コードに正確に反映してください。

必ず以下の JSON のみで返してください（説明文・コードブロック不要）:
{
  "modified_content": "変更後のファイル全体の内容（文字列）",
  "change_summary": "何をどう変えたかの1〜2行の説明"
}

制約:
- 指示の範囲のみを変更し、無関係な箇所は変えない
- 変更後のコードは構文的に正しく、既存テストを壊さないこと
- ファイル全体を返すこと（部分スニペット不可）
- 新規 .py は `from __future__ import annotations` で始め、`datetime.utcnow()` は使わない"""


def _make_default_specialist() -> SpecialistAgent:
    return SpecialistAgent(
        name="CoreImprover",
        skills=[AgentSkill.PROMPT_ENGINEERING, AgentSkill.CODEBASE_EXPLORATION],
        description="RepoCorp 自身のコードを安全に改善する内蔵エージェント。",
    )


class CoreImprovementAgent(BaseAgent):
    """RepoCorp 自身のコードを LLM で編集し、テストで検証する自己改善エージェント。"""

    def __init__(
        self,
        specialist: Optional[SpecialistAgent] = None,
        llm_client: Optional[Any] = None,
        project_root: Optional[Path] = None,
        executor: Optional[SafeChangeExecutor] = None,
        max_iterations: int = 3,
    ) -> None:
        super().__init__(specialist or _make_default_specialist())
        self._llm = llm_client
        self._project_root = Path(project_root) if project_root else Path(__file__).resolve().parents[1]
        self._executor = executor or SafeChangeExecutor(self._project_root)
        self._max_iterations = max(1, int(max_iterations))

    async def run(self, task: AgentTask) -> AgentResult:
        instruction = str(task.input.get("instruction", "")).strip()
        auto_apply = bool(task.input.get("auto_apply", False))
        max_iterations = max(1, int(task.input.get("max_iterations", self._max_iterations)))

        # 単一(file_path) / 複数(files) の両方を受け付ける
        raw_files = task.input.get("files")
        if isinstance(raw_files, list) and raw_files:
            rel_inputs = [str(f).strip() for f in raw_files if str(f).strip()]
        else:
            single = str(task.input.get("file_path", "")).strip()
            rel_inputs = [single] if single else []

        if not instruction:
            return AgentResult(success=False, error="task.input['instruction'] is required")
        if not rel_inputs:
            return AgentResult(success=False, error="task.input['file_path'] または 'files' が必要です")
        if self._llm is None:
            return AgentResult(
                success=False,
                error="LLM クライアントが未設定です。APIキーを設定してください（自己改善にはLLMが必須）。",
            )

        # 対象ファイルを解決して原文を読む
        targets: list[tuple[str, Path, str]] = []  # (rel, abs_path, original)
        for rel in rel_inputs:
            try:
                abs_path = self._resolve_target(rel)
            except ValueError as exc:
                return AgentResult(success=False, error=str(exc))
            if not abs_path.exists():
                return AgentResult(success=False, error=f"対象ファイルが見つかりません: {rel}")
            targets.append((str(abs_path.relative_to(self._project_root)), abs_path, abs_path.read_text(encoding="utf-8")))

        multi = len(targets) > 1
        last_error = ""
        for attempt in range(1, max_iterations + 1):
            proposed: list[tuple[str, Path, str, str, str]] = []  # (rel, path, original, new, summary)
            for rel, abs_path, original in targets:
                generated = self._generate_change(instruction, rel, original, last_error, multi=multi)
                if generated is None:
                    return AgentResult(
                        success=False,
                        error="LLM が有効な変更を生成できませんでした。",
                        execution_log=f"attempt={attempt}, file={rel}",
                    )
                new_content, summary = generated
                proposed.append((rel, abs_path, original, new_content, summary))

            result = self._executor.apply_changes([
                ChangeRequest(file_path=rel, new_content=new, description=f"core-improve: {summary or instruction[:60]}")
                for (rel, _abs, _orig, new, summary) in proposed
            ])

            if result.success:
                changes = [
                    {"file_path": rel, "new_content": new, "diff": self._unified_diff(orig, new, rel)}
                    for (rel, _abs, orig, new, _summary) in proposed
                ]
                combined_diff = "\n".join(change["diff"] for change in changes)
                change_summary = "; ".join(
                    dict.fromkeys(summary for *_rest, summary in proposed if summary)
                ) or f"{len(changes)} ファイルを更新"

                if not auto_apply:
                    # 検証済みなので作業ツリーは元に戻す（人間承認用の提案にする）。
                    for _rel, abs_path, original, _new, _summary in proposed:
                        abs_path.write_text(original, encoding="utf-8")

                return AgentResult(
                    success=True,
                    output={
                        "file_path": changes[0]["file_path"],
                        "files": [change["file_path"] for change in changes],
                        "change_summary": change_summary,
                        "modified_content": changes[0]["new_content"],  # 後方互換(単一)
                        "changes": changes,
                        "diff": combined_diff,
                        "validated": True,
                        "applied": auto_apply,
                        "attempts": attempt,
                        "instruction": instruction,
                    },
                    thinking_process=f"{attempt} 回目の試行で検証に成功（テスト緑, {len(changes)} ファイル）",
                    execution_log=f"core-improve {', '.join(c['file_path'] for c in changes)}: {change_summary}",
                )

            last_error = result.error_message or "tests failed"
            logger.info("CoreImprovementAgent attempt %d failed: %s", attempt, last_error[:200])

        return AgentResult(
            success=False,
            error=f"{max_iterations} 回の試行で検証に通りませんでした。",
            output={
                "files": [rel for rel, _abs, _orig in targets],
                "last_error": last_error[:2000],
                "attempts": max_iterations,
            },
            execution_log=f"core-improve failed for {', '.join(rel for rel, _abs, _orig in targets)}",
        )

    def _generate_change(
        self,
        instruction: str,
        file_path: str,
        original_content: str,
        last_error: str,
        multi: bool = False,
    ) -> Optional[tuple[str, str]]:
        retry_block = (
            f"\n\n【前回の試行は失敗しました。テスト出力（抜粋）】\n{last_error[:1500]}\n"
            "この失敗を踏まえて修正してください。"
            if last_error
            else ""
        )
        multi_block = (
            "\n\nこれは複数ファイルにまたがる変更の一部です。指示全体の整合性を保ち、"
            "この対象ファイルが担うべき変更のみを返してください。"
            if multi
            else ""
        )
        prompt = (
            f"{CORE_IMPROVE_SYSTEM_PROMPT}\n\n"
            f"対象ファイル: {file_path}\n\n"
            f"【改善指示】\n{instruction}{multi_block}\n\n"
            f"【元のコード】\n{original_content}{retry_block}"
        )
        try:
            data = self._llm.generate_json(prompt)
        except Exception as exc:  # noqa: BLE001
            logger.warning("CoreImprovementAgent: LLM generate_json failed: %s", exc)
            return None
        modified = data.get("modified_content")
        if not isinstance(modified, str) or not modified.strip():
            return None
        return modified, str(data.get("change_summary", "")).strip()

    def _unified_diff(self, original: str, modified: str, file_path: str) -> str:
        diff_lines = difflib.unified_diff(
            original.splitlines(keepends=True),
            modified.splitlines(keepends=True),
            fromfile=f"a/{file_path}",
            tofile=f"b/{file_path}",
        )
        return "".join(diff_lines)

    def _resolve_target(self, file_path: str) -> Path:
        candidate = Path(file_path)
        if candidate.is_absolute():
            raise ValueError("file_path に絶対パスは使えません")
        if any(part == ".." for part in candidate.parts):
            raise ValueError("file_path に親ディレクトリ参照は使えません")
        resolved = (self._project_root / candidate).resolve(strict=False)
        try:
            resolved.relative_to(self._project_root.resolve())
        except ValueError as exc:
            raise ValueError("file_path がプロジェクトルートの外を指しています") from exc
        return resolved
