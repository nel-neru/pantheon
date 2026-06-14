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

from pathlib import Path
from typing import List, Optional

from core.intelligence.playbook import PlaybookEntry, PlaybookStore

# プロンプト注入時の既定件数（少数の高有用度プレイのみを文脈に載せる）。
DEFAULT_RECALL_LIMIT = 3


class MemoryBank:
    """Playbook を生成/実行の両経路へ橋渡しする Layered Memory ファサード。"""

    def __init__(self, platform_home: Optional[Path] = None):
        self._store = PlaybookStore(platform_home)

    # ---- read（生成前の参照） ----

    def recall(
        self, *, category: Optional[str] = None, limit: int = DEFAULT_RECALL_LIMIT
    ) -> List[PlaybookEntry]:
        """有用度上位の施策ノートを返す（category 指定時はそのカテゴリ内で上位）。"""
        if category is None:
            return self._store.top(limit=limit)
        entries = [e for e in self._store.list_entries(category=category)]
        entries.sort(key=lambda e: e.usefulness_score, reverse=True)
        if limit < 0:
            limit = 0
        return entries[:limit]

    def recall_prompt_context(
        self, *, category: Optional[str] = None, limit: int = DEFAULT_RECALL_LIMIT
    ) -> str:
        """有用度上位の施策をプロンプト注入用テキストへ整形する（無ければ空文字）。

        生成前のエージェントが「過去にうまくいった施策」を文脈として読めるようにする。
        空のときは空文字を返し、呼び出し側のプロンプトを一切変えない（既存挙動を壊さない）。
        """
        entries = self.recall(category=category, limit=limit)
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
