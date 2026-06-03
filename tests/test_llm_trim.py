"""長文入力トリム戦略（B8, core/llm/trim.py）のテスト。"""

from __future__ import annotations

from core.llm.base import LLMMessage
from core.llm.trim import estimate_tokens, trim_messages


def test_no_trim_when_within_budget():
    msgs = [LLMMessage(role="user", content="short message")]
    out = trim_messages(msgs, max_tokens=1000)
    assert [m.content for m in out] == ["short message"]


def test_trims_middle_keeps_system_and_recent():
    msgs = [
        LLMMessage(role="system", content="SYS"),
        LLMMessage(role="user", content="A" * 400),
        LLMMessage(role="assistant", content="B" * 400),
        LLMMessage(role="user", content="RECENT" * 10),
    ]
    out = trim_messages(msgs, max_tokens=50, keep_recent=1)
    roles = [m.role for m in out]
    assert "system" in roles  # system は温存
    assert out[-1].content == msgs[-1].content  # 直近は温存
    assert len(out) < len(msgs)  # 中間が落ちている


def test_truncates_largest_when_still_over_budget():
    msgs = [LLMMessage(role="user", content="X" * 10000)]
    out = trim_messages(msgs, max_tokens=10)
    assert len(out) == 1
    assert len(out[0].content) < 10000
    assert "truncated" in out[0].content


def test_estimate_tokens_monotonic():
    assert estimate_tokens("a") >= 1
    assert estimate_tokens("a" * 400) > estimate_tokens("a" * 4)
