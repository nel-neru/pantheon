"""Cycle 23 — bare ``json.loads(LLM 出力)`` を ``extract_json_object`` へ統合した
consolidation の挙動ガード。

3 エージェント（code_review / improvement_executor / generic_skill）はかつて LLM の
生応答を ``json.loads`` に直接渡していた。実際の Claude CLI 出力は ```json … ``` の
コードフェンスや前後プローズで包まれることが多く、その場合 ``json.loads`` は
``JSONDecodeError`` を投げて各エージェントの fallback（``[]`` / ``("","")`` /
fallback dict）へ倒れていた＝**正しい JSON を取りこぼしていた**。正典ヘルパへ
統合したことで、フェンス/プローズ付きでも正しく抽出される。

これらは「単一正典化」で実際に挙動が改善する箇所なので、純粋 refactor とは違い
load-bearing な regression guard を書ける（旧コードでは fail する）。
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from agents.code_review_agent import CodeReviewAgent
from agents.generic_skill_agent import GenericSkillAgent
from agents.improvement_executor_agent import ImprovementExecutorAgent
from core.models.organization import AgentSkill, SpecialistAgent

# 典型的な LLM 出力: ```json フェンス + 前後プローズ。bare json.loads はこれで必ず落ちる。
_FENCED = (
    "ここに改善案を JSON で示します:\n"
    "```json\n"
    '{"suggestions": [{"title": "Fenced", "description": "desc", '
    '"file_path": "src/app.py", "priority": "high", "category": "security", '
    '"expected_impact": "impact"}]}\n'
    "```\n"
    "以上です。"
)


def _make_specialist(name: str = "Worker") -> SpecialistAgent:
    return SpecialistAgent(
        name=name,
        skills=[AgentSkill.CODEBASE_EXPLORATION, AgentSkill.DEEP_RESEARCH],
    )


# --------------------------- code_review --------------------------- #


def test_code_review_extracts_from_fenced_response(monkeypatch):
    """```json フェンス付き応答からも suggestion を抽出できる（旧 json.loads は []）。"""
    agent = CodeReviewAgent(_make_specialist("Reviewer"))
    fake_provider = SimpleNamespace(
        generate=AsyncMock(return_value=SimpleNamespace(content=_FENCED))
    )
    monkeypatch.setattr("agents.code_review_agent.get_llm_provider", lambda _name: fake_provider)

    suggestions = asyncio.run(agent._generate_suggestions("code", "repo"))

    assert [s.title for s in suggestions] == ["Fenced"]


def test_code_review_returns_empty_on_unparseable(monkeypatch):
    """JSON が無い応答では決定的に [] へ倒す（fallback 契約の保存・例外を投げない）。"""
    agent = CodeReviewAgent(_make_specialist("Reviewer"))
    fake_provider = SimpleNamespace(
        generate=AsyncMock(return_value=SimpleNamespace(content="JSON はありません。"))
    )
    monkeypatch.setattr("agents.code_review_agent.get_llm_provider", lambda _name: fake_provider)

    assert asyncio.run(agent._generate_suggestions("code", "repo")) == []


# ----------------------- improvement_executor ---------------------- #


def test_executor_extracts_from_fenced_response(monkeypatch):
    """```json フェンス付き応答からも (modified, summary) を抽出できる。"""
    agent = ImprovementExecutorAgent(_make_specialist("Executor"))
    body = (
        "適用結果です:\n"
        "```json\n"
        '{"modified_content": "print(\\"ok\\")", "change_summary": "fixed"}\n'
        "```"
    )
    fake_provider = SimpleNamespace(generate=AsyncMock(return_value=SimpleNamespace(content=body)))
    monkeypatch.setattr(
        "agents.improvement_executor_agent.get_llm_provider", lambda _name: fake_provider
    )

    modified, summary = asyncio.run(
        agent._generate_code_change("old", "src/a.py", {"title": "t", "description": "d"})
    )

    assert modified == 'print("ok")'
    assert summary == "fixed"


def test_executor_returns_empty_pair_on_unparseable(monkeypatch):
    """JSON が無い応答では ("", "") へ倒す（run() が success=False に写像する契約の保存）。"""
    agent = ImprovementExecutorAgent(_make_specialist("Executor"))
    fake_provider = SimpleNamespace(
        generate=AsyncMock(return_value=SimpleNamespace(content="解析不能"))
    )
    monkeypatch.setattr(
        "agents.improvement_executor_agent.get_llm_provider", lambda _name: fake_provider
    )

    assert asyncio.run(agent._generate_code_change("old", "src/a.py", {"title": "t"})) == ("", "")


# -------------------------- generic_skill -------------------------- #


class _FakeLLM:
    def __init__(self, reply: str) -> None:
        self._reply = reply

    def complete(self, messages, **kwargs) -> str:
        return self._reply


def _generic_agent(reply: str) -> GenericSkillAgent:
    return GenericSkillAgent.from_skills(
        [AgentSkill.DEEP_RESEARCH, AgentSkill.CODEBASE_EXPLORATION],
        llm_client=_FakeLLM(reply),
    )


def test_generic_skill_extracts_from_fenced_response():
    """```json フェンス付き応答から構造化 dict を抽出する（旧版は raw を result に詰める fallback）。"""
    from agents.base import AgentTask

    reply = (
        "結果です:\n"
        "```json\n"
        '{"result": "done", "key_findings": ["f1"], "recommendations": ["r1"], '
        '"confidence": 0.9}\n'
        "```"
    )
    agent = _generic_agent(reply)
    result = asyncio.run(agent.run(AgentTask(task_type="analysis", description="x")))

    assert result.success is True
    assert result.output["result"] == "done"
    assert result.output["key_findings"] == ["f1"]
    assert result.output["confidence"] == 0.9


def test_generic_skill_falls_back_on_unparseable():
    """JSON が無い応答では raw を result に詰める fallback dict を保つ（例外を投げない）。"""
    from agents.base import AgentTask

    agent = _generic_agent("ただのテキスト回答です")
    result = asyncio.run(agent.run(AgentTask(task_type="analysis", description="x")))

    assert result.success is True
    assert result.output["result"] == "ただのテキスト回答です"
    assert result.output["confidence"] == 0.7


# ----------------------- internal_consultant ---------------------- #


class _ScriptedProvider:
    """応答列を順に返す provider（リトライ挙動の検証用）。"""

    def __init__(self, replies: list[str]) -> None:
        self._replies = list(replies)
        self.calls = 0

    async def generate(self, **_kwargs) -> SimpleNamespace:
        reply = self._replies[min(self.calls, len(self._replies) - 1)]
        self.calls += 1
        return SimpleNamespace(content=reply)


def test_consultant_extracts_from_fenced_response():
    """```json フェンス付き応答から dict を抽出する（旧 ad-hoc 除去より堅牢・全{走査）。"""
    from core.quality.internal_consultant import _generate_and_parse_json

    fenced = '評価結果:\n```json\n{"overall_score": 7.5, "consultant_comment": "ok"}\n```'
    provider = _ScriptedProvider([fenced])

    data = asyncio.run(_generate_and_parse_json(provider, [], max_retries=2))

    assert data["overall_score"] == 7.5
    assert provider.calls == 1


def test_consultant_retries_then_succeeds():
    """1回目が解析不能でも2回目で dict が得られれば成功する（retry 契約の保存）。"""
    from core.quality.internal_consultant import _generate_and_parse_json

    provider = _ScriptedProvider(["JSON ではない", '{"overall_score": 6.0}'])

    data = asyncio.run(_generate_and_parse_json(provider, [], max_retries=2))

    assert data["overall_score"] == 6.0
    assert provider.calls == 2


def test_consultant_raises_after_exhausting_retries():
    """全試行で dict が得られなければ RuntimeError を送出する（raise 契約の保存）。"""
    import pytest

    from core.quality.internal_consultant import _generate_and_parse_json

    provider = _ScriptedProvider(["まだ JSON なし"])

    with pytest.raises(RuntimeError, match="JSON parse failed after 2 attempts"):
        asyncio.run(_generate_and_parse_json(provider, [], max_retries=2))
    assert provider.calls == 2


def test_consultant_rejects_top_level_json_array():
    """トップレベルが JSON 配列なら dict 契約違反として retry→RuntimeError（旧版は list を返し
    呼び出し側 data.get で AttributeError になり得た脆弱性の根治）。"""
    import pytest

    from core.quality.internal_consultant import _generate_and_parse_json

    # `{` アンカーで配列内の最初のオブジェクトを拾う可能性があるため、オブジェクトを
    # 含まない純粋なスカラ配列を使い「dict が得られない」ことを確実に突く。
    provider = _ScriptedProvider(["[1, 2, 3]"])

    with pytest.raises(RuntimeError):
        asyncio.run(_generate_and_parse_json(provider, [], max_retries=2))
