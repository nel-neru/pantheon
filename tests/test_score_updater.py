"""Unit tests for ScoreUpdater"""

from agents.base import AgentResult
from core.metrics.score_updater import ExecutionOutcome, ScoreUpdater
from core.models.organization import Organization


class TestScoreUpdater:
    def test_successful_execution_increases_autonomy_score(self):
        updater = ScoreUpdater()
        org = Organization(name="TestOrg", purpose="Testing", autonomy_score=40.0)

        updater.update(org, ExecutionOutcome(success=True, suggestions_count=1))

        assert org.autonomy_score > 40.0

    def test_failed_execution_decreases_autonomy_score(self):
        updater = ScoreUpdater()
        org = Organization(name="TestOrg", purpose="Testing", autonomy_score=40.0)

        updater.update(org, ExecutionOutcome(success=False))

        assert org.autonomy_score < 40.0

    def test_self_initiated_execution_gets_extra_bonus(self):
        updater = ScoreUpdater()
        baseline = Organization(name="Baseline", purpose="Testing", autonomy_score=40.0)
        self_started = Organization(name="SelfStarted", purpose="Testing", autonomy_score=40.0)

        updater.update(baseline, ExecutionOutcome(success=True))
        updater.update(self_started, ExecutionOutcome(success=True, self_initiated=True))

        assert self_started.autonomy_score > baseline.autonomy_score

    def test_score_is_clamped_to_valid_range(self):
        updater = ScoreUpdater()
        high = Organization(
            name="High",
            purpose="Testing",
            autonomy_score=99.9,
            improvement_velocity=99.9,
        )
        low = Organization(
            name="Low",
            purpose="Testing",
            autonomy_score=0.1,
            improvement_velocity=0.1,
        )

        updater.update(
            high,
            ExecutionOutcome(
                success=True,
                suggestions_count=20,
                accepted_suggestions=10,
                quality_score=10.0,
                self_initiated=True,
                used_cached_knowledge=True,
            ),
        )
        updater.update(low, ExecutionOutcome(success=False))

        assert 0.0 <= high.autonomy_score <= 100.0
        assert 0.0 <= high.improvement_velocity <= 100.0
        assert 0.0 <= low.autonomy_score <= 100.0
        assert 0.0 <= low.improvement_velocity <= 100.0

    def test_outcome_from_agent_result_maps_fields(self):
        result = AgentResult(
            success=True,
            output={
                "suggestions": [{"title": "one"}, {"title": "two"}],
                "knowledge_injected": True,
            },
        )

        outcome = ScoreUpdater.outcome_from_agent_result(
            result,
            accepted_suggestions=1,
            self_initiated=True,
            quality_score=8.5,
        )

        assert outcome == ExecutionOutcome(
            success=True,
            suggestions_count=2,
            accepted_suggestions=1,
            quality_score=8.5,
            used_cached_knowledge=True,
            self_initiated=True,
        )

    def test_ema_smoothing_prevents_full_delta_jump(self):
        updater = ScoreUpdater()
        org = Organization(name="TestOrg", purpose="Testing", autonomy_score=40.0)

        updater.update(org, ExecutionOutcome(success=True))

        assert 40.0 < org.autonomy_score < 42.0
