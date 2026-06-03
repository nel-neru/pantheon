"""
長文入力の汎用トリム戦略（B8）。

`max_tokens` 超過による失敗を避けるため、メッセージ列を概算トークン予算内に収める。
方針: system メッセージと直近 `keep_recent` 件は温存し、中間の古いメッセージから落とす。
それでも収まらない場合は最大のメッセージ本文を末尾省略する。プロバイダー非依存。
"""

from __future__ import annotations

from typing import List

from .base import LLMMessage

__all__ = ["estimate_tokens", "trim_messages"]

_CHARS_PER_TOKEN = 4  # 粗い概算（英日混在の安全側）
_TRUNCATION_MARKER = "\n…[truncated]…\n"


def estimate_tokens(text: str) -> int:
    """文字数からの粗いトークン概算。"""
    return max(1, len(text) // _CHARS_PER_TOKEN)


def _total_tokens(messages: List[LLMMessage]) -> int:
    return sum(estimate_tokens(m.content or "") for m in messages)


def trim_messages(
    messages: List[LLMMessage],
    max_tokens: int,
    *,
    keep_recent: int = 2,
) -> List[LLMMessage]:
    """概算トークンが `max_tokens` 以内になるよう非破壊でトリムした列を返す。

    - system ロールと末尾 `keep_recent` 件は常に温存。
    - 中間（古い順）の非温存メッセージを削除して予算内を目指す。
    - なお超過する場合、最大の温存外メッセージ本文を末尾省略する。
    """
    if max_tokens <= 0 or _total_tokens(messages) <= max_tokens:
        return list(messages)

    n = len(messages)
    protected_idx = set()
    for i, m in enumerate(messages):
        if m.role == "system":
            protected_idx.add(i)
    for i in range(max(0, n - keep_recent), n):
        protected_idx.add(i)

    # 中間（古い順）から削除
    droppable = [i for i in range(n) if i not in protected_idx]
    keep = set(range(n))
    for i in droppable:
        if _total_tokens([messages[j] for j in sorted(keep)]) <= max_tokens:
            break
        keep.discard(i)

    result = [messages[j] for j in sorted(keep)]
    if _total_tokens(result) <= max_tokens:
        return result

    # まだ超過 → 最大の温存外メッセージ本文を末尾省略
    budget_chars = max_tokens * _CHARS_PER_TOKEN
    over = _total_tokens(result) * _CHARS_PER_TOKEN - budget_chars
    trimmed: List[LLMMessage] = []
    target_done = False
    # 末尾省略対象 = 温存外で最大本文
    candidates = [(idx, m) for idx, m in enumerate(result) if m.role != "system"]
    target_pos = None
    if candidates:
        target_pos = max(candidates, key=lambda t: len(t[1].content or ""))[0]
    for idx, m in enumerate(result):
        if idx == target_pos and not target_done and over > 0:
            content = m.content or ""
            cut = min(len(content), over + len(_TRUNCATION_MARKER))
            keep_len = max(0, len(content) - cut)
            head = keep_len // 2
            tail = keep_len - head
            new_content = (content[:head] + _TRUNCATION_MARKER + content[len(content) - tail:]) if keep_len else _TRUNCATION_MARKER
            trimmed.append(LLMMessage(role=m.role, content=new_content, name=m.name, tool_calls=m.tool_calls))
            target_done = True
        else:
            trimmed.append(m)
    return trimmed
