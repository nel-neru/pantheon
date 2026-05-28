from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from core.knowledge.classifier import KnowledgeClassifier
from core.knowledge.failure_patterns import FailurePatternRegistry
from core.knowledge.manager import KnowledgeManager
from core.metrics.group_balance import GroupBalanceEvaluator
from core.metrics.growth_history import GrowthHistoryRecorder
from core.metrics.health_calculator import HealthCalculator
from core.metrics.learning_curve import LearningCurveTracker
from core.metrics.lifecycle import LifecycleStage, OrganizationLifecycle
from core.metrics.milestones import MilestoneTracker
from core.metrics.velocity import VelocityCalculator


def _entry_path(km: KnowledgeManager, entry_id: str):
    return km.knowledge_dir / f"{entry_id}.json"


def _write_entry(km: KnowledgeManager, entry_id: str, **updates):
    path = _entry_path(km, entry_id)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.update(updates)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_knowledge_record_access_increments_usage(tmp_path):
    km = KnowledgeManager(tmp_path)
    entry_id = km.save_insight("Auth tip", "Use auth middleware", tags=["security", "api"])

    km.record_knowledge_access(["security"])

    payload = json.loads(_entry_path(km, entry_id).read_text(encoding="utf-8"))
    assert payload["usage_count"] == 1
    assert payload["last_referenced"]


def test_knowledge_get_by_importance_sorted(tmp_path):
    km = KnowledgeManager(tmp_path)
    first = km.save_insight("One", "content", tags=["a"])
    second = km.save_insight("Two", "content", tags=["b"])
    third = km.save_insight("Three", "content", tags=["c"])
    _write_entry(km, first, usage_count=2)
    _write_entry(km, second, usage_count=5)
    _write_entry(km, third, usage_count=1)

    ordered = km.get_by_importance()

    assert [entry["id"] for entry in ordered[:3]] == [second, first, third]


def test_classifier_detects_security_domain():
    classifier = KnowledgeClassifier()

    tags = classifier.classify("auth password vulnerability injection")

    assert "security" in tags


def test_classifier_auto_tag_entry():
    classifier = KnowledgeClassifier()

    entry = classifier.auto_tag_entry({"content": "pytest coverage improves test quality", "tags": ["existing"]})

    assert entry["tags"] == ["existing", "testing"]


def test_classifier_does_not_duplicate_existing_tags():
    classifier = KnowledgeClassifier()

    tags = classifier.classify("auth and password checks", existing_tags=["security"])

    assert tags == []


def test_learning_curve_record_and_trend(tmp_path):
    tracker = LearningCurveTracker(tmp_path)
    tracker.record_snapshot(knowledge_count=1, avg_quality=5.0, accepted=1)
    tracker.record_snapshot(knowledge_count=2, avg_quality=6.0, accepted=2)

    trend = tracker.get_trend()

    assert len(trend) == 2
    assert trend[-1].knowledge_count == 2
    assert trend[-1].accepted_count == 2


def test_learning_curve_correlation_positive(tmp_path):
    tracker = LearningCurveTracker(tmp_path)
    tracker.record_snapshot(knowledge_count=1, avg_quality=2.0, accepted=1)
    tracker.record_snapshot(knowledge_count=2, avg_quality=4.0, accepted=2)
    tracker.record_snapshot(knowledge_count=3, avg_quality=6.0, accepted=3)

    assert tracker.calculate_correlation() > 0.9


def test_learning_curve_format_for_cli(tmp_path):
    tracker = LearningCurveTracker(tmp_path)
    for index in range(4):
        tracker.record_snapshot(knowledge_count=index + 1, avg_quality=3.0 + index, accepted=index)

    rendered = tracker.format_for_cli()

    assert rendered
    assert all(char in "▁▂▃▄▅▆▇█" for char in rendered)


def test_failure_registry_suppresses_after_3(tmp_path):
    registry = FailurePatternRegistry(tmp_path)
    for _ in range(2):
        registry.record_failure("lint", "src/app.py", "flake8")

    assert registry.should_suppress("lint", "src/app.py") is False

    registry.record_failure("lint", "src/app.py", "flake8")

    assert registry.should_suppress("lint", "src/app.py") is True


def test_failure_registry_persists_patterns(tmp_path):
    registry = FailurePatternRegistry(tmp_path)
    registry.record_failure("tests", "pkg/test_module.py", "timeout")

    reloaded = FailurePatternRegistry(tmp_path)
    patterns = reloaded.get_patterns()

    assert len(patterns) == 1
    assert patterns[0].category == "tests"
    assert patterns[0].file_pattern == "*.py"


def test_best_practice_auto_promote(tmp_path):
    km = KnowledgeManager(tmp_path)
    promoted_id = km.save_insight("High quality", "Useful", tags=["quality"], quality_score=8.7)
    km.save_insight("Low quality", "Ignore", tags=["quality"], quality_score=7.9)

    count = km.auto_promote_high_quality()
    promoted = json.loads(_entry_path(km, promoted_id).read_text(encoding="utf-8"))

    assert count == 1
    assert promoted["importance"] == "best_practice"
    assert len(km.get_best_practices()) == 1


def test_promote_to_best_practice_requires_quality_threshold(tmp_path):
    km = KnowledgeManager(tmp_path)
    entry_id = km.save_insight("Average", "Not enough", quality_score=7.0)

    assert km.promote_to_best_practice(entry_id) is False


def test_knowledge_archive_stale(tmp_path):
    km = KnowledgeManager(tmp_path)
    stale_id = km.save_insight("Old", "stale", tags=["ops"])
    fresh_id = km.save_insight("Fresh", "fresh", tags=["ops"])
    never_id = km.save_insight("Never", "never", tags=["ops"])
    _write_entry(
        km,
        stale_id,
        usage_count=4,
        last_referenced=(datetime.now(timezone.utc) - timedelta(days=45)).isoformat(),
    )
    _write_entry(
        km,
        fresh_id,
        usage_count=1,
        last_referenced=(datetime.now(timezone.utc) - timedelta(days=5)).isoformat(),
    )

    archived = km.archive_stale_entries(days_inactive=30)
    active_ids = {entry["id"] for entry in km.get_active_entries()}

    assert archived == 1
    assert stale_id not in active_ids
    assert fresh_id in active_ids
    assert never_id in active_ids


def test_knowledge_repo_specific_context(tmp_path):
    km = KnowledgeManager(tmp_path)
    km.save_with_repo_tag("Repo alpha", ["analysis"], "repo-a", title="A")
    km.save_with_repo_tag("Repo beta", ["analysis"], "repo-b", title="B")
    entry_id = km.save_insight("Manual", "Other", tags=["repo:repo-a"], usage_count=4)
    _write_entry(km, entry_id, usage_count=4)

    repo_entries = km.get_for_repo("repo-a")

    assert len(repo_entries) == 2
    assert all("repo:repo-a" in entry["tags"] for entry in repo_entries)
    assert repo_entries[0]["usage_count"] == 4


def test_lifecycle_stage_incubating():
    lifecycle = OrganizationLifecycle()

    assert lifecycle.determine_stage(29.9) == LifecycleStage.INCUBATING


def test_lifecycle_stage_mature_at_60():
    lifecycle = OrganizationLifecycle()

    assert lifecycle.determine_stage(60) == LifecycleStage.MATURE


def test_lifecycle_autonomous_bonus():
    lifecycle = OrganizationLifecycle()

    assert lifecycle.get_auto_approve_bonus(LifecycleStage.AUTONOMOUS) == 0.4


def test_lifecycle_review_intensity_autonomous():
    lifecycle = OrganizationLifecycle()

    assert lifecycle.get_review_intensity(LifecycleStage.AUTONOMOUS) == "light"


def test_health_calculator_basic_score():
    calculator = HealthCalculator()
    recent = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()

    snapshot = calculator.calculate(
        "OrgA",
        proposals=[{"status": "pending"}, {"status": "done"}],
        decisions=[{"status": "accepted", "decided_at": recent}, {"status": "rejected", "decided_at": recent}],
    )

    assert snapshot.pending_proposals == 1
    assert snapshot.accepted_ratio == 0.5
    assert snapshot.score == 74.8
    assert calculator.format_score(snapshot).startswith("●●●●○ 75/100")


def test_health_calculator_clamps_to_100():
    calculator = HealthCalculator()
    recent = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()

    snapshot = calculator.calculate(
        "OrgA",
        proposals=[],
        decisions=[{"status": "accepted", "decided_at": recent}] * 10,
    )

    assert snapshot.score == 90.0
    assert calculator.format_score(snapshot) == "●●●●○ 90/100 (AUTONOMOUS)"


def test_growth_recorder_saves_and_loads(tmp_path):
    recorder = GrowthHistoryRecorder(tmp_path)
    recorder.record("OrgA", autonomy_score=40, improvement_velocity=20, knowledge_count=3, proposal_count=4, accepted_count=1)
    recorder.record("OrgA", autonomy_score=45, improvement_velocity=22, knowledge_count=4, proposal_count=5, accepted_count=2)

    history = recorder.get_history("OrgA")

    assert len(history) == 2
    assert history[-1].autonomy_score == 45


def test_growth_trend_summary(tmp_path):
    recorder = GrowthHistoryRecorder(tmp_path)
    for score in [40, 43, 46, 49, 52]:
        recorder.record("OrgA", autonomy_score=score, improvement_velocity=20, knowledge_count=1, proposal_count=1, accepted_count=1)

    assert recorder.get_trend_summary("OrgA") == "成長中"


def test_group_balance_evaluator():
    evaluator = GroupBalanceEvaluator()

    balance = evaluator.evaluate({"OrgA": 20, "OrgB": 50, "OrgC": 80})
    recommendations = evaluator.get_rebalance_recommendations(balance)

    assert balance.total_orgs == 3
    assert balance.weakest_org == "OrgA"
    assert balance.strongest_org == "OrgC"
    assert recommendations == [
        "組織間の格差が大きいです。OrgAに注力してください",
        "OrgAが危機的状態です",
    ]


def test_velocity_calculator():
    calculator = VelocityCalculator()

    assert calculator.calculate(accepted_count=15, days_elapsed=5) == 30.0


def test_velocity_classify():
    calculator = VelocityCalculator()

    assert calculator.classify_velocity(5) == "低速"
    assert calculator.classify_velocity(20) == "標準"
    assert calculator.classify_velocity(45) == "高速"
    assert calculator.classify_velocity(75) == "超高速"


def test_predict_score_requires_3_points(tmp_path):
    recorder = GrowthHistoryRecorder(tmp_path)
    recorder.record("OrgA", autonomy_score=40, improvement_velocity=10, knowledge_count=1, proposal_count=1, accepted_count=1)
    recorder.record("OrgA", autonomy_score=45, improvement_velocity=10, knowledge_count=1, proposal_count=1, accepted_count=1)

    assert recorder.predict_score("OrgA") is None


def test_predict_score_projects_growth(tmp_path):
    recorder = GrowthHistoryRecorder(tmp_path)
    path = recorder.history_file
    records = [
        {
            "org_name": "OrgA",
            "timestamp": (datetime.now(timezone.utc) - timedelta(days=20)).isoformat(),
            "autonomy_score": 20,
            "improvement_velocity": 10,
            "knowledge_count": 1,
            "proposal_count": 1,
            "accepted_count": 1,
        },
        {
            "org_name": "OrgA",
            "timestamp": (datetime.now(timezone.utc) - timedelta(days=10)).isoformat(),
            "autonomy_score": 30,
            "improvement_velocity": 15,
            "knowledge_count": 2,
            "proposal_count": 2,
            "accepted_count": 1,
        },
        {
            "org_name": "OrgA",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "autonomy_score": 40,
            "improvement_velocity": 20,
            "knowledge_count": 3,
            "proposal_count": 3,
            "accepted_count": 2,
        },
    ]
    path.write_text("\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n", encoding="utf-8")

    prediction = recorder.predict_score("OrgA", days_ahead=10)

    assert prediction == 50.0


def test_milestone_first_awarded(tmp_path):
    tracker = MilestoneTracker(tmp_path)

    achieved = tracker.check_and_award("OrgA", autonomy_score=40, accepted_count=1, knowledge_count=0)

    assert [milestone.milestone_id for milestone in achieved] == ["first_proposal"]
    assert tracker.get_achieved("OrgA")[0].milestone_id == "first_proposal"


def test_milestone_not_awarded_twice(tmp_path):
    tracker = MilestoneTracker(tmp_path)
    tracker.check_and_award("OrgA", autonomy_score=85, accepted_count=2, knowledge_count=12)

    achieved = tracker.check_and_award("OrgA", autonomy_score=90, accepted_count=3, knowledge_count=12)

    assert achieved == []
