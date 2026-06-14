"""Tests for Theme A remaining items (A-04 through A-12)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from core.intelligence.agent_knowledge import AgentKnowledgeAccumulator
from core.intelligence.persona_loader import PersonaLoader
from core.intelligence.self_evaluator import AgentSelfEvaluator
from core.intelligence.skill_gap_detector import SkillGapDetector
from core.intelligence.skill_proficiency import (
    SkillProficiencyManager,
    SkillProficiencyRecord,
)
from core.intelligence.skill_propagator import SkillPropagator
from core.knowledge.manager import KnowledgeManager
from core.orchestration.task_matcher import TaskMatcher
from core.orchestration.team_coordinator import TeamCoordinator

PERSONAS_DIR = Path(__file__).resolve().parents[1] / "config" / "personas"


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        loop.close()
        asyncio.set_event_loop(None)


def test_skill_proficiency_record_use_increments(tmp_path):
    manager = SkillProficiencyManager(platform_home=tmp_path)

    record = manager.record_use("agent-1", "security", success=True)

    assert record.agent_id == "agent-1"
    assert record.skill_name == "security"
    assert record.use_count == 1
    assert record.success_count == 1


def test_skill_proficiency_success_increases_score(tmp_path):
    manager = SkillProficiencyManager(platform_home=tmp_path)

    record = manager.record_use("agent-1", "testing", success=True)

    assert record.proficiency > 1.0


def test_skill_proficiency_failure_decreases_score(tmp_path):
    manager = SkillProficiencyManager(platform_home=tmp_path)
    improved_score = manager.record_use("agent-1", "testing", success=True).proficiency

    failed = manager.record_use("agent-1", "testing", success=False)

    assert failed.proficiency < improved_score
    assert failed.proficiency >= 1.0


def test_skill_proficiency_caps_at_100(tmp_path):
    manager = SkillProficiencyManager(platform_home=tmp_path)

    for _ in range(40):
        record = manager.record_use("agent-1", "architecture", success=True)

    assert record.proficiency == 100.0


def test_skill_proficiency_prompt_enhancement_levels(tmp_path):
    manager = SkillProficiencyManager(platform_home=tmp_path)
    manager._records = {
        "agent-1": {
            "low": SkillProficiencyRecord("agent-1", "low", proficiency=10.0),
            "mid": SkillProficiencyRecord("agent-1", "mid", proficiency=50.0),
            "high": SkillProficiencyRecord("agent-1", "high", proficiency=80.0),
        }
    }
    manager._save()

    assert (
        manager.get_prompt_enhancement("agent-1", "low") == "基本的な分析を丁寧に行ってください。"
    )
    assert (
        manager.get_prompt_enhancement("agent-1", "mid")
        == "経験を活かした精度の高い分析を行ってください。"
    )
    assert (
        manager.get_prompt_enhancement("agent-1", "high")
        == "専門家レベルの深い洞察を提供してください。"
    )


def test_skill_proficiency_persists_records(tmp_path):
    manager = SkillProficiencyManager(platform_home=tmp_path)
    manager.record_use("agent-1", "security", success=True)

    restored = SkillProficiencyManager(platform_home=tmp_path)

    assert restored.get_proficiency("agent-1", "security") > 1.0


def test_skill_proficiency_get_all_proficiencies(tmp_path):
    manager = SkillProficiencyManager(platform_home=tmp_path)
    manager.record_use("agent-1", "security", success=True)
    manager.record_use("agent-1", "testing", success=False)

    proficiencies = manager.get_all_proficiencies("agent-1")

    assert set(proficiencies) == {"security", "testing"}


def test_task_matcher_returns_ranked_agents():
    matcher = TaskMatcher()
    agents = [
        {
            "agent_id": "agent-a",
            "skills": ["tool_integration", "deep_research"],
            "performance_score": 1.0,
        },
        {
            "agent_id": "agent-b",
            "skills": ["tool_integration"],
            "performance_score": 0.5,
        },
        {
            "agent_id": "agent-c",
            "skills": ["prompt_engineering"],
            "performance_score": 3.0,
        },
    ]

    ranked = matcher.match("security", agents)

    assert [agent["agent_id"] for agent in ranked] == ["agent-a", "agent-c", "agent-b"]
    assert ranked[0]["matched_skills"] == ["deep_research", "tool_integration"]


def test_task_matcher_match_rate():
    matcher = TaskMatcher()
    agents = [
        {"agent_id": "a", "skills": ["codebase_exploration"], "performance_score": 1.0},
        {"agent_id": "b", "skills": ["tool_integration"], "performance_score": 2.0},
        {"agent_id": "c", "skills": ["prompt_engineering"], "performance_score": 3.0},
    ]

    assert matcher.get_match_rate("testing", agents) == 2 / 3


def test_task_matcher_unknown_category_returns_zero_rate():
    matcher = TaskMatcher()

    assert matcher.get_match_rate("unknown", [{"agent_id": "a", "skills": []}]) == 0.0


def test_agent_knowledge_record_and_retrieve(tmp_path):
    accumulator = AgentKnowledgeAccumulator(
        knowledge_manager=KnowledgeManager(tmp_path),
        platform_home=tmp_path,
    )
    accumulator.record_success("agent-1", "security", "audit", "Pattern A", 7.5)
    accumulator.record_success("agent-2", "security", "audit", "Pattern B", 9.0)

    patterns = accumulator.get_patterns_for_task("audit", skill_name="security")

    assert [pattern.pattern_summary for pattern in patterns] == ["Pattern B", "Pattern A"]


def test_agent_knowledge_record_saves_to_knowledge_manager(tmp_path):
    km = KnowledgeManager(tmp_path)
    accumulator = AgentKnowledgeAccumulator(knowledge_manager=km, platform_home=tmp_path)

    accumulator.record_success("agent-1", "testing", "review", "Useful pattern", 8.0)

    insights = km.get_insights(tags=["agent_success", "testing", "review"])
    assert len(insights) == 1


def test_skill_propagator_identifies_top_agents(tmp_path):
    proficiency_manager = SkillProficiencyManager(platform_home=tmp_path)
    for _ in range(14):
        proficiency_manager.record_use("top-agent", "security", success=True)
    for _ in range(5):
        proficiency_manager.record_use("mid-agent", "security", success=True)

    propagator = SkillPropagator(
        proficiency_manager=proficiency_manager,
        knowledge_accumulator=AgentKnowledgeAccumulator(platform_home=tmp_path),
    )

    assert propagator.identify_top_agents("security") == ["top-agent"]


def test_skill_propagator_propagates(tmp_path):
    accumulator = AgentKnowledgeAccumulator(platform_home=tmp_path)
    accumulator.record_success("source", "security", "audit", "Harden auth checks", 9.0)
    propagator = SkillPropagator(
        proficiency_manager=SkillProficiencyManager(platform_home=tmp_path),
        knowledge_accumulator=accumulator,
    )

    propagated = propagator.propagate("source", "target", "security")
    target_patterns = [
        pattern
        for pattern in accumulator._load_patterns()
        if pattern.agent_id == "target" and pattern.skill_name == "security"
    ]

    assert propagated is True
    assert len(target_patterns) == 1
    assert "継承元" in target_patterns[0].pattern_summary


def test_skill_propagator_auto_propagates_top_patterns(tmp_path):
    proficiency_manager = SkillProficiencyManager(platform_home=tmp_path)
    for _ in range(14):
        proficiency_manager.record_use("source", "security", success=True)
    proficiency_manager.record_use("target", "security", success=True)
    accumulator = AgentKnowledgeAccumulator(platform_home=tmp_path)
    accumulator.record_success("source", "security", "audit", "Share this pattern", 9.0)
    propagator = SkillPropagator(
        proficiency_manager=proficiency_manager,
        knowledge_accumulator=accumulator,
    )

    count = propagator.auto_propagate_top_patterns("security")

    assert count == 1


def test_skill_gap_detector_triggers_after_3_failures():
    detector = SkillGapDetector()
    for _ in range(3):
        detector.record_failure("security")

    gaps = detector.detect_gaps()

    assert len(gaps) == 1
    assert gaps[0].detected_skill_name == "TOOL_INTEGRATION"
    assert detector.detect_gaps() == []


def test_skill_gap_detector_recommendation():
    detector = SkillGapDetector()

    assert detector.get_skill_recommendation("architecture") == "STRATEGIC_PLANNING"
    assert detector.get_skill_recommendation("unknown") is None


def test_persona_loader_loads_yaml():
    loader = PersonaLoader(PERSONAS_DIR)

    persona = loader.load_persona("strategic_analyst")

    assert persona is not None
    assert persona["role"] == "戦略的分析者"
    assert "architecture" in persona["focus_areas"]


def test_persona_loader_missing_persona_returns_empty():
    loader = PersonaLoader(PERSONAS_DIR)

    assert loader.load_persona("missing_persona") is None
    assert loader.get_system_prompt_addon("missing_persona") == ""


def test_persona_loader_list_personas():
    loader = PersonaLoader(PERSONAS_DIR)

    personas = loader.list_personas()

    assert "strategic_analyst" in personas
    assert "security_expert" in personas


def test_persona_loader_supports_legacy_nested_yaml():
    loader = PersonaLoader(PERSONAS_DIR)

    persona = loader.load_persona("ceo")

    assert persona is not None
    assert persona["name"] == "Strategic CEO"
    assert persona["tone"] == "strategic and encouraging"


def test_self_evaluator_scores_good_output_high():
    evaluator = AgentSelfEvaluator()
    output = (
        "1. 改善 proposal\n"
        "- src/app.py:12 で認証処理を改善します。\n"
        "- src/auth.py:40 でエラー処理を解決します。\n"
        "この改善により保守性とセキュリティが向上し、レビューの根拠も明確になります。"
    )

    result = evaluator.evaluate(output, "code_review")

    assert result.score >= 8.0
    assert result.should_retry is False


def test_self_evaluator_scores_empty_output_low():
    evaluator = AgentSelfEvaluator()

    result = evaluator.evaluate("", "code_review")

    assert result.score < 4.0


def test_self_evaluator_should_retry_when_low():
    evaluator = AgentSelfEvaluator()

    result = evaluator.evaluate("失敗", "code_review")

    assert result.should_retry is True


def test_self_evaluator_evaluate_with_retry():
    evaluator = AgentSelfEvaluator()
    outputs = iter(
        [
            "失敗",
            "1. 改善 proposal\n- src/core.py:10 を修正\n十分に詳しい説明を追加して再評価に通すための長い文章です。",
        ]
    )

    final_output, evaluation = evaluator.evaluate_with_retry(lambda: next(outputs), "code_review")

    assert "src/core.py:10" in final_output
    assert evaluation.should_retry is False


def test_team_coordinator_context_sharing():
    coordinator = TeamCoordinator()
    coordinator.add_contribution("task-1", "agent-a", "初期分析を実施")
    coordinator.add_contribution("task-1", "agent-b", "改善案を作成")

    context = coordinator.get_context_for_agent("task-1", "agent-a")

    assert "agent-b" in context
    assert "改善案を作成" in context
    assert "agent-a" not in context.splitlines()[-1]


def test_team_coordinator_synthesize_outputs():
    coordinator = TeamCoordinator()
    coordinator.add_contribution("task-2", "agent-a", "課題を特定")
    coordinator.add_contribution("task-2", "agent-b", "修正方針を提示")

    summary = coordinator.synthesize_outputs("task-2")

    assert "agent-a" in summary
    assert "agent-b" in summary
    assert "task-2" in summary


def test_team_coordinator_empty_context_message():
    coordinator = TeamCoordinator()

    context = coordinator.get_context_for_agent("task-3", "agent-a")

    assert "まだ他の貢献はありません" in context


def test_agent_status_cli_empty_message(capsys, tmp_path):
    from main import cmd_agent_status

    with patch("core.platform.state.get_platform_home", return_value=tmp_path):
        _run(cmd_agent_status(SimpleNamespace(org_name="DemoOrg")))

    assert "エージェントの実績データがありません" in capsys.readouterr().out


def test_agent_status_cli_shows_table(capsys, tmp_path):
    from main import cmd_agent_status

    SkillProficiencyManager(platform_home=tmp_path).record_use("agent-1", "security", success=True)

    with patch("core.platform.state.get_platform_home", return_value=tmp_path):
        _run(cmd_agent_status(SimpleNamespace(org_name="DemoOrg")))

    out = capsys.readouterr().out
    assert "Agent Status" in out
    assert "agent-1" in out
    assert "security=6.0/100" in out
