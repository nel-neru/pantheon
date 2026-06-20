"""WIRE-MEM: MemoryBank（Layered Memory ファサード）と BaseAgent 配線のテスト。

PlaybookStore を「生成（recall）／実行後（capture）」の両経路から使える統一メモリにした
配線を検証する。決定論・冪等・LLM 非依存（claude CLI を呼ばない）。
"""

from __future__ import annotations

from agents.base import AgentResult, AgentTask, BaseAgent
from core.intelligence.memory_bank import MemoryBank
from core.intelligence.playbook import PlaybookStore
from core.models.organization import AgentSkill, SpecialistAgent


def _bank(tmp_path, monkeypatch) -> MemoryBank:
    monkeypatch.setattr("core.platform.state.get_platform_home", lambda: tmp_path)
    return MemoryBank(tmp_path)


def test_memory_cli_capture_and_list_parity(tmp_path, monkeypatch, capsys):
    """pantheon memory capture/list が GUI /api/memory/playbook と同じ MemoryBank を叩く（finding 18）。"""
    import argparse

    import main
    from commands.memory import cmd_memory_capture, cmd_memory_list

    monkeypatch.setattr("core.platform.state.get_platform_home", lambda: tmp_path)
    assert "cmd_memory_capture" in main.HANDLERS and "cmd_memory_list" in main.HANDLERS

    cmd_memory_capture(
        argparse.Namespace(
            title="X投稿は朝が伸びる", content="9時投稿でCTR+30%", category="growth", org_name="Co"
        )
    )
    # 冪等: 同じ title/category/org は二重追加しない
    cmd_memory_capture(
        argparse.Namespace(
            title="X投稿は朝が伸びる", content="dup", category="growth", org_name="Co"
        )
    )
    assert len(MemoryBank(tmp_path).recall(category="growth")) == 1

    cmd_memory_list(argparse.Namespace(category="growth", limit=10, verbose=True))
    out = capsys.readouterr().out
    assert "X投稿は朝が伸びる" in out and "9時投稿" in out


# ------------------------------------------------------------------ #
# MemoryBank
# ------------------------------------------------------------------ #


def test_capture_is_idempotent(tmp_path, monkeypatch):
    bank = _bank(tmp_path, monkeypatch)
    bank.capture(" X集客のコツ", "短文+画像が伸びる", category="audience", org_name="Co")
    bank.capture(
        "X集客のコツ",
        "別内容でも同 title/cat/org なら追加しない",
        category="audience",
        org_name="Co",
    )
    assert len(PlaybookStore(tmp_path).list_entries()) == 1


def test_recall_orders_by_usefulness(tmp_path, monkeypatch):
    bank = _bank(tmp_path, monkeypatch)
    low = bank.capture("low", "c", category="g", org_name="Co")
    high = bank.capture("high", "c", category="g", org_name="Co")
    bank.record_applied(high.entry_id, success=True)
    bank.record_applied(high.entry_id, success=True)
    bank.record_applied(low.entry_id, success=False)

    top = bank.recall(limit=2)
    assert top[0].title == "high"  # 有用度上位が先頭


# ------------------------------------------------------------------ #
# C5: セマンティックリコール（query 再ランク + kill-switch）
# ------------------------------------------------------------------ #


def _seed_three(bank: MemoryBank) -> None:
    """異なる主題の 3 件。usefulness は意味と逆相関させ、再ランクの効果を可視化する。"""
    a = bank.capture("X集客のコツ", "短文と画像で伸ばす", category="g", org_name="Co")
    b = bank.capture(
        "note有料記事の構成", "価値提示と価格設計を最適化", category="g", org_name="Co"
    )
    c = bank.capture("Shortsサムネ最適化", "クリック率を上げる構図", category="g", org_name="Co")
    # 関連の薄い a を usefulness 最上位にして、query 再ランクが順位を入れ替えることを示す。
    bank.record_applied(a.entry_id, success=True)
    bank.record_applied(a.entry_id, success=True)
    bank.record_applied(c.entry_id, success=True)
    _ = b  # b は usefulness 最下位（query で初めて先頭に来るべき対象）


def test_recall_query_reranks_by_relevance(tmp_path, monkeypatch):
    """query を与えると usefulness ではなく意味的関連で先頭が決まる（既定 on）。"""
    monkeypatch.delenv("PANTHEON_SEMANTIC_RECALL", raising=False)
    bank = _bank(tmp_path, monkeypatch)
    _seed_three(bank)

    top = bank.recall(limit=1, query="note 有料記事 価格設計")
    assert top[0].title == "note有料記事の構成"  # usefulness 最下位でも関連で先頭へ


def test_recall_without_query_keeps_usefulness_order(tmp_path, monkeypatch):
    """query 無しは従来どおり usefulness 上位（既存挙動と一致）。"""
    monkeypatch.delenv("PANTHEON_SEMANTIC_RECALL", raising=False)
    bank = _bank(tmp_path, monkeypatch)
    _seed_three(bank)
    assert bank.recall(limit=1)[0].title == "X集客のコツ"  # usefulness 最上位


def test_recall_kill_switch_restores_usefulness(tmp_path, monkeypatch):
    """PANTHEON_SEMANTIC_RECALL=0 なら query を渡しても usefulness 順（kill-switch）。"""
    monkeypatch.setenv("PANTHEON_SEMANTIC_RECALL", "0")
    bank = _bank(tmp_path, monkeypatch)
    _seed_three(bank)
    assert bank.recall(limit=1, query="note 有料記事 価格設計")[0].title == "X集客のコツ"


def test_recall_query_no_overlap_falls_back(tmp_path, monkeypatch):
    """query が候補と一切重ならなければ usefulness 順を維持（関連シグナル皆無のフォールバック）。"""
    monkeypatch.delenv("PANTHEON_SEMANTIC_RECALL", raising=False)
    bank = _bank(tmp_path, monkeypatch)
    _seed_three(bank)
    assert bank.recall(limit=1, query="xyzzy 量子 フーバー")[0].title == "X集客のコツ"


def test_recall_prompt_context_empty_when_no_entries(tmp_path, monkeypatch):
    bank = _bank(tmp_path, monkeypatch)
    assert bank.recall_prompt_context() == ""  # 空なら何も足さない（既存挙動を壊さない）


def test_recall_prompt_context_renders_entries(tmp_path, monkeypatch):
    bank = _bank(tmp_path, monkeypatch)
    bank.capture(
        "note有料記事の構成", "冒頭で価値提示→無料/有料境界を最適化", category="monetization"
    )
    ctx = bank.recall_prompt_context()
    assert "過去の学び（Playbook）" in ctx
    assert "note有料記事の構成" in ctx


# ------------------------------------------------------------------ #
# BaseAgent 配線（recall をプロンプトへ / capture を成功実行で）
# ------------------------------------------------------------------ #


class _DummyAgent(BaseAgent):
    async def run(self, task: AgentTask) -> AgentResult:  # pragma: no cover - 未使用
        return AgentResult(success=True)


def _agent() -> _DummyAgent:
    spec = SpecialistAgent(
        name="Tester",
        role="tester",
        skills=[AgentSkill.STRATEGIC_PLANNING, AgentSkill.DEEP_RESEARCH],
    )
    return _DummyAgent(spec)


def test_apply_skills_to_prompt_injects_playbook(tmp_path, monkeypatch):
    """有用度上位の Playbook がエージェントのシステムプロンプトに注入される（recall 配線）。"""
    monkeypatch.setattr("core.platform.state.get_platform_home", lambda: tmp_path)
    MemoryBank(tmp_path).capture("勝ちパターンA", "これが効く", category="general")

    prompt = _agent().apply_skills_to_prompt("BASE")
    assert "BASE" in prompt
    assert "過去の学び（Playbook）" in prompt
    assert "勝ちパターンA" in prompt


def test_apply_skills_to_prompt_unchanged_when_no_playbook(tmp_path, monkeypatch):
    """Playbook が空なら従来どおり（メモリブロックを足さない）。"""
    monkeypatch.setattr("core.platform.state.get_platform_home", lambda: tmp_path)
    prompt = _agent().apply_skills_to_prompt("BASE")
    assert "過去の学び（Playbook）" not in prompt


def test_save_execution_knowledge_captures_playbook_on_success(tmp_path, monkeypatch):
    """成功実行が Playbook に蓄積される（capture 配線・knowledge_manager 不要）。"""
    monkeypatch.setattr("core.platform.state.get_platform_home", lambda: tmp_path)
    agent = _agent()
    task = AgentTask(task_type="code_review", description="ダッシュボードの分割")
    result = AgentResult(success=True, thinking_process="小さく分割すると保守性が上がる")

    agent._save_execution_knowledge(None, result, task)  # type: ignore[arg-type]

    entries = PlaybookStore(tmp_path).list_entries()
    assert len(entries) == 1
    assert entries[0].category == "code_review"
    assert entries[0].org_name == "Tester"


def test_save_execution_knowledge_skips_on_failure(tmp_path, monkeypatch):
    monkeypatch.setattr("core.platform.state.get_platform_home", lambda: tmp_path)
    agent = _agent()
    task = AgentTask(task_type="code_review", description="失敗ケース")
    agent._save_execution_knowledge(None, AgentResult(success=False), task)  # type: ignore[arg-type]
    assert PlaybookStore(tmp_path).list_entries() == []


def test_capture_then_recall_closes_the_loop(tmp_path, monkeypatch):
    """capture→recall が同一ストアで閉じる（生成→蓄積→再利用ループ）。"""
    monkeypatch.setattr("core.platform.state.get_platform_home", lambda: tmp_path)
    agent = _agent()
    task = AgentTask(task_type="content", description="バズる導入文の型")
    agent._save_execution_knowledge(  # type: ignore[arg-type]
        None, AgentResult(success=True, thinking_process="結論先出し"), task
    )
    assert "バズる導入文の型" in _agent().apply_skills_to_prompt("BASE")
