"""Tests for the context compactor (core.intelligence.context_compactor)."""

from __future__ import annotations

from core.intelligence.context_compactor import ContextCompactor
from core.intelligence.token_budget_manager import TokenBudget, TokenBudgetManager


def _manager_with_small_budget() -> TokenBudgetManager:
    # max_context_tokens=10 → max_chars=40
    budget = TokenBudget(
        task_type="tiny",
        max_context_tokens=10,
        max_prompt_tokens=20,
        max_output_tokens=10,
    )
    return TokenBudgetManager(custom_budgets={"tiny": budget})


async def test_short_context_passes_through_unchanged(tmp_path, monkeypatch):
    monkeypatch.setattr("core.platform.state.get_platform_home", lambda: tmp_path)
    comp = ContextCompactor(_manager_with_small_budget(), platform_home=tmp_path)
    short = "short"
    assert await comp.compact(short, "tiny") == short


async def test_oversized_falls_back_to_truncation_offline(tmp_path, monkeypatch):
    # conftest が PANTHEON_NO_CLAUDE=1 → claude_available()=False → 決定論トリミング
    monkeypatch.setattr("core.platform.state.get_platform_home", lambda: tmp_path)
    comp = ContextCompactor(_manager_with_small_budget(), platform_home=tmp_path)
    big = "あ" * 200
    result = await comp.compact(big, "tiny")
    assert len(result) < len(big)
    assert "省略" in result  # fit_context のトリミングマーカー


async def test_compaction_uses_claude_and_caches(tmp_path, monkeypatch):
    monkeypatch.setattr("core.platform.state.get_platform_home", lambda: tmp_path)
    monkeypatch.setattr("core.runtime.claude_code.claude_available", lambda: True)

    calls = []

    class _Resp:
        content = "圧縮済み要約"

    class _Provider:
        async def generate(self, **kwargs):
            calls.append(kwargs.get("task_type"))
            return _Resp()

    monkeypatch.setattr("core.llm.get_llm_provider", lambda *a, **k: _Provider())

    comp = ContextCompactor(_manager_with_small_budget(), platform_home=tmp_path)
    big = "あ" * 200

    result1 = await comp.compact(big, "tiny")
    assert result1 == "圧縮済み要約"
    assert calls == ["compaction"]  # light ティアの task_type で呼ばれる

    # 2 回目はキャッシュから返り、claude を再度呼ばない（再圧縮でトークンを浪費しない）
    result2 = await comp.compact(big, "tiny")
    assert result2 == "圧縮済み要約"
    assert calls == ["compaction"]  # 呼び出し回数は増えない


async def test_claude_failure_falls_back_to_truncation(tmp_path, monkeypatch):
    monkeypatch.setattr("core.platform.state.get_platform_home", lambda: tmp_path)
    monkeypatch.setattr("core.runtime.claude_code.claude_available", lambda: True)

    class _Provider:
        async def generate(self, **kwargs):
            raise RuntimeError("boom")

    monkeypatch.setattr("core.llm.get_llm_provider", lambda *a, **k: _Provider())

    comp = ContextCompactor(_manager_with_small_budget(), platform_home=tmp_path)
    big = "あ" * 200
    result = await comp.compact(big, "tiny")
    assert "省略" in result  # 例外時はトリミングへフォールバック
