"""MemoryBank — Layered Memory の統一ファサード（WIRE-MEM / 計画 §9）。

P2.3 の :class:`~core.intelligence.playbook.PlaybookStore`（再利用可能な施策ノートの永続層）を
「生成（recall）／実行後（capture）」の両経路から使える 1 つの記憶レイヤーとして束ねる。

X.1 完全性クリティックが指摘した「PlaybookStore が誰からも使われていない dead store」を解消する
配線の中心。設計は PlaybookStore と同様 **決定論・冪等・LLM 非依存**:

- :meth:`recall` / :meth:`recall_prompt_context` — 有用度上位の施策をプロンプト注入用テキストへ
  （生成前にエージェントが過去の学びを参照する read 経路）。
- :meth:`capture` — 成功した実行などを施策ノートとして蓄積する write 経路。**冪等**:
  同じ (title, category, org_name) のエントリが既にあれば二重追加しない（24/7 運用での無限増殖防止）。
- :meth:`record_applied` — 施策の使用実績（成功/失敗）を反映（PlaybookStore.record_use 委譲）。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

from core.intelligence.embeddings import rank_scores
from core.intelligence.playbook import PlaybookEntry, PlaybookStore

# プロンプト注入時の既定件数（少数の高有用度プレイのみを文脈に載せる）。
DEFAULT_RECALL_LIMIT = 3

# C5: セマンティックリコールの kill-switch。既定 on（未設定 or truthy）。
# ``0`` / ``false`` / ``no`` / ``off`` で明示的に無効化＝従来の usefulness 上位リコールへ。
_SEMANTIC_FALSY = {"0", "false", "no", "off"}


def _semantic_recall_enabled() -> bool:
    """``PANTHEON_SEMANTIC_RECALL`` の解釈（既定 on; 明示 falsy でのみ無効）。"""
    return os.getenv("PANTHEON_SEMANTIC_RECALL", "").strip().lower() not in _SEMANTIC_FALSY


class MemoryBank:
    """Playbook を生成/実行の両経路へ橋渡しする Layered Memory ファサード。"""

    def __init__(self, platform_home: Optional[Path] = None):
        self._store = PlaybookStore(platform_home)

    # ---- read（生成前の参照） ----

    def recall(
        self,
        *,
        category: Optional[str] = None,
        limit: int = DEFAULT_RECALL_LIMIT,
        query: Optional[str] = None,
    ) -> List[PlaybookEntry]:
        """施策ノートを上位 ``limit`` 件返す（category 指定時はそのカテゴリ内）。

        ``query`` が与えられ ``PANTHEON_SEMANTIC_RECALL`` が有効（既定 on）なら、候補プールを
        意味的関連度（:func:`core.intelligence.embeddings.rank_scores` — 任意の埋め込み or
        vendored BM25）で再ランクし上位を返す。query が無い／kill-switch off／関連シグナルが
        皆無のときは従来どおり ``usefulness_score`` 上位を返す（既存挙動と byte 一致）。
        """
        if limit < 0:
            limit = 0
        pool = self._store.list_entries(category=category)
        # usefulness 降順（保存順を保つ安定ソート）＝従来の決定的順序。
        by_usefulness = sorted(pool, key=lambda e: e.usefulness_score, reverse=True)

        q = (query or "").strip()
        if q and limit and len(pool) > 1 and _semantic_recall_enabled():
            docs = [f"{e.title}\n{e.content}" for e in by_usefulness]
            scores = rank_scores(q, docs)
            # 関連シグナルが全く無ければ意味再ランクせず usefulness 順を維持（フォールバック）。
            if scores and max(scores) > 0.0:
                # 関連度降順、同点は by_usefulness の並び（usefulness 順）を安定タイブレークに。
                order = sorted(range(len(by_usefulness)), key=lambda i: scores[i], reverse=True)
                return [by_usefulness[i] for i in order][:limit]

        return by_usefulness[:limit]

    def recall_prompt_context(
        self,
        *,
        category: Optional[str] = None,
        limit: int = DEFAULT_RECALL_LIMIT,
        query: Optional[str] = None,
    ) -> str:
        """有用度上位の施策をプロンプト注入用テキストへ整形する（無ければ空文字）。

        生成前のエージェントが「過去にうまくいった施策」を文脈として読めるようにする。
        ``query`` を渡すと :meth:`recall` が意味的関連度で再ランクする（既定 on / kill-switch）。
        空のときは空文字を返し、呼び出し側のプロンプトを一切変えない（既存挙動を壊さない）。
        """
        entries = self.recall(category=category, limit=limit, query=query)
        if not entries:
            return ""
        lines = [
            f"- {e.title}（有用度 {e.usefulness_score:.1f}・使用 {e.usage_count}回）: {e.content.strip()[:240]}"
            for e in entries
        ]
        return (
            "\n\n===【過去の学び（Playbook）】===\n"
            "以下は過去にうまくいった施策の要約です。関連するものは参考にしてください。\n"
            + "\n".join(lines)
            + "\n===========================\n"
        )

    # ---- write（実行後の蓄積） ----

    def capture(
        self,
        title: str,
        content: str,
        *,
        category: str = "general",
        org_name: str = "",
    ) -> PlaybookEntry:
        """施策ノートを蓄積する（冪等: 同 title/category/org は二重追加しない）。

        title は前後空白を正規化して比較・保存する（空白差での重複増殖を防ぐ）。
        """
        title = str(title).strip()
        category = str(category).strip() or "general"
        org_name = str(org_name)
        for existing in self._store.list_entries(category=category):
            if existing.title == title and existing.org_name == org_name:
                return existing  # 既出は何もしない（無限増殖防止）
        return self._store.add(title, content, category=category, org_name=org_name)

    def record_applied(self, entry_id: str, *, success: bool) -> Optional[PlaybookEntry]:
        """施策の使用実績（成功/失敗）を反映する（PlaybookStore.record_use 委譲）。"""
        return self._store.record_use(entry_id, success=success)
