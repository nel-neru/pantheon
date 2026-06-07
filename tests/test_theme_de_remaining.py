from __future__ import annotations

from datetime import datetime

from core.hierarchy.capability_gap_detector import CapabilityGapDetector
from core.hierarchy.cross_org_collaborator import CrossOrgCollaborator
from core.hierarchy.division_coordinator import DivisionCoordinator
from core.hierarchy.org_diagnostics import OrgSelfDiagnostics
from core.hierarchy.org_goals import OrgGoalManager
from core.hierarchy.org_snapshot import OrgSnapshotManager
from core.hierarchy.org_wizard import OrgWizard
from core.metrics.coevolution_graph import CoevolutionGraph
from core.models.organization import Organization
from core.profile import activity_tracker as activity_tracker_module
from core.profile.activity_tracker import ActivityTracker
from core.profile.developer_growth import DeveloperGrowthTracker
from core.profile.developer_profile import (
    CommunicationStyle,
    DeveloperProfileManager,
)
from core.profile.goal_manager import DeveloperGoalManager
from core.profile.growth_reporter import GrowthReporter
from core.profile.multi_user import MultiUserManager


class FrozenDateTime(datetime):
    current = datetime(2024, 1, 1, 20, 0, 0)

    @classmethod
    def now(cls):
        return cls.current


def test_communication_style_verbose_hint(tmp_path):
    manager = DeveloperProfileManager(platform_home=tmp_path)
    manager.update_communication_style(CommunicationStyle.VERBOSE.value)

    profile = manager.get_profile()

    assert manager.get_description_length_hint(profile) == "詳細な説明と根拠を含めてください（500文字以上）"


def test_communication_style_concise_hint(tmp_path):
    manager = DeveloperProfileManager(platform_home=tmp_path)
    manager.update_communication_style(CommunicationStyle.CONCISE.value)

    profile = manager.get_profile()

    assert manager.get_description_length_hint(profile) == "簡潔に要点のみ記載してください（100文字以内）"


def test_activity_tracker_records_and_summarizes(tmp_path, monkeypatch):
    monkeypatch.setattr(activity_tracker_module, "datetime", FrozenDateTime)
    tracker = ActivityTracker(platform_home=tmp_path)

    timestamps = [
        datetime(2024, 1, 1, 20, 0),
        datetime(2024, 1, 1, 20, 30),
        datetime(2024, 1, 1, 21, 0),
        datetime(2024, 1, 1, 21, 30),
        datetime(2024, 1, 1, 22, 0),
        datetime(2024, 1, 1, 22, 30),
        datetime(2024, 1, 2, 9, 0),
    ]
    for ts in timestamps:
        FrozenDateTime.current = ts
        tracker.record_activity("pytest")

    assert tracker.log_path.exists()
    assert tracker.get_active_hours() == [20, 21, 22]
    assert tracker.get_activity_summary() == "最もアクティブな時間帯: 20-22時"


def test_activity_tracker_peak_day(tmp_path, monkeypatch):
    monkeypatch.setattr(activity_tracker_module, "datetime", FrozenDateTime)
    tracker = ActivityTracker(platform_home=tmp_path)

    for ts in [
        datetime(2024, 1, 1, 20, 0),
        datetime(2024, 1, 1, 21, 0),
        datetime(2024, 1, 3, 20, 0),
    ]:
        FrozenDateTime.current = ts
        tracker.record_activity("run")

    assert tracker.get_peak_day() == "月曜日"


def test_weakness_detection_triggers_at_threshold(tmp_path):
    manager = DeveloperProfileManager(platform_home=tmp_path)
    manager.record_approval("ux", approved=False)
    manager.record_approval("ux", approved=False)
    manager.record_approval("ux", approved=True)

    profile = manager.get_profile()

    assert "ux" in profile.weak_categories
    assert "ux" not in profile.avoided_categories


def test_growth_reporter_monthly_report(tmp_path):
    reporter = GrowthReporter(platform_home=tmp_path)

    report = reporter.generate_monthly_report(
        org_name="Pantheon",
        current_score=78.0,
        prev_score=70.0,
        accepted_count=3,
        knowledge_count=4,
    )

    formatted = reporter.format_for_cli(report)

    assert report.period_label == "今月"
    assert report.metrics_delta["score_delta"] == 8.0
    assert any("向上" in item for item in report.improvements)
    assert formatted.startswith("📈 今月の成長レポート")


def test_motivation_message_5_accepted(tmp_path):
    reporter = GrowthReporter(platform_home=tmp_path)

    assert reporter.generate_motivation_message(5, 3) == "今週は5件の改善を承認しました！すばらしい進歩です🎉"


def test_motivation_message_zero_accepted(tmp_path):
    reporter = GrowthReporter(platform_home=tmp_path)

    assert reporter.generate_motivation_message(0, 0) == "今週はまだ改善がありません。小さな一歩から始めましょう👋"


def test_developer_goal_set_and_achieve(tmp_path):
    manager = DeveloperGoalManager(platform_home=tmp_path)

    goal = manager.set_goal("Improve test coverage", "coverage", 80.0)
    achieved = manager.update_progress(goal.goal_id, 82.0)

    assert achieved is True
    assert manager.get_active_goals() == []


def test_developer_goal_priority_categories(tmp_path):
    manager = DeveloperGoalManager(platform_home=tmp_path)
    goals = [
        manager.set_goal("Improve security review quality", "security_score", 10.0),
        manager.set_goal("Reduce performance latency", "latency", 20.0),
    ]

    categories = manager.get_priority_categories(goals)

    assert categories == ["security", "performance"]


def test_multi_user_default_user(monkeypatch):
    monkeypatch.delenv("PANTHEON_USER", raising=False)
    manager = MultiUserManager()

    assert manager.get_current_user() == "default"


def test_multi_user_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("PANTHEON_USER", "alice")
    manager = MultiUserManager()

    assert manager.get_current_user() == "alice"
    assert manager.get_profile_path(tmp_path).name == "developer_profile.json"
    assert "alice" in str(manager.get_profile_path(tmp_path))


def test_developer_growth_snapshot(tmp_path):
    tracker = DeveloperGrowthTracker(platform_home=tmp_path)
    tracker.record_snapshot(0.4, 0.5, ["testing"])
    snapshot = tracker.record_snapshot(0.7, 0.8, ["testing", "security"])

    trend = tracker.get_growth_trend()
    summary = tracker.summarize_growth()

    assert snapshot.focus_categories == ["testing", "security"]
    assert len(trend) == 2
    assert "承認率 0.50→0.80" in summary


def test_coevolution_graph_records_and_formats(tmp_path):
    graph = CoevolutionGraph(platform_home=tmp_path)
    graph.record_coevolution_point(60.0, 40.0)
    graph.record_coevolution_point(75.0, 55.0)

    org_scores, approval_rates = graph.get_both_trends()
    chart = graph.format_ascii_chart()

    assert org_scores == [60.0, 75.0]
    assert approval_rates == [40.0, 55.0]
    assert "Org | Dev" in chart


def test_capability_gap_detector_triggers_at_threshold():
    detector = CapabilityGapDetector()
    for _ in range(5):
        detector.record_repeated_issue("security")

    proposals = detector.check_for_new_division()

    assert len(proposals) == 1
    assert proposals[0].division_name == "Security Division"
    assert detector.get_proposal_count() == 1


def test_org_snapshot_take_and_list(tmp_path):
    manager = OrgSnapshotManager(platform_home=tmp_path)
    org = Organization(name="Ops Org", purpose="Improve testing")

    snapshot = manager.take_snapshot(org, label="baseline")
    snapshots = manager.list_snapshots("Ops Org")

    assert snapshot.label == "baseline"
    assert len(snapshots) == 1
    assert snapshots[0].snapshot_id == snapshot.snapshot_id


def test_org_snapshot_restore(tmp_path):
    manager = OrgSnapshotManager(platform_home=tmp_path)
    org = Organization(name="Recovery Org", purpose="Improve security")

    snapshot = manager.take_snapshot(org)
    restored = manager.restore_snapshot(snapshot.snapshot_id)

    assert restored["name"] == "Recovery Org"
    assert restored["purpose"] == "Improve security"


def test_division_coordinator_assign_security():
    coordinator = DivisionCoordinator()

    assigned = coordinator.assign_divisions(
        "security review for API",
        ["Security", "Engineering", "QA"],
    )

    assert assigned == ["Security", "Engineering"]


def test_org_wizard_get_steps():
    wizard = OrgWizard()

    steps = wizard.get_steps()

    assert [step.step_id for step in steps] == ["step1", "step2", "step3"]
    assert steps[1].options == ["小（1チーム）", "中（2-3チーム）", "大（4+チーム）"]


def test_org_wizard_process_answers():
    wizard = OrgWizard()

    spec = wizard.process_answers(
        {
            "step1": "セキュリティ強化",
            "step2": "中（2-3チーム）",
            "step3": "セキュリティ, テスト",
        }
    )

    assert spec["purpose"] == "セキュリティ強化"
    assert spec["focus_areas"] == ["セキュリティ", "テスト"]
    assert spec["suggested_name"] == "SecurityEnhancement Org"


def test_cross_org_collaborator_request_and_accept():
    collaborator = CrossOrgCollaborator()

    request = collaborator.request_collaboration("Core Org", "QA Org", "test strategy review")
    pending = collaborator.get_pending_requests("QA Org")

    assert len(pending) == 1
    assert collaborator.accept_collaboration(request.request_id) is True
    assert collaborator.get_pending_requests("QA Org") == []


def test_org_goal_manager_set_and_weights(tmp_path):
    manager = OrgGoalManager(platform_home=tmp_path)

    goal = manager.set_goal("Pantheon", "Improve security posture", "security")
    active = manager.get_active_goals("Pantheon")
    weights = manager.get_category_weights("Pantheon")

    assert active[0].goal_id == goal.goal_id
    assert weights["security"] == 2.0
    assert weights["performance"] == 1.0


def test_org_diagnostics_strengths_weaknesses():
    diagnostics = OrgSelfDiagnostics()

    report = diagnostics.diagnose(
        org_name="Pantheon",
        health_score=45.0,
        accepted_count=1,
        rejected_count=4,
        knowledge_count=1,
    )

    assert "自律スコアの改善が必要" in report.weaknesses
    assert "提案の質向上が必要" in report.weaknesses
    assert "知識蓄積の強化が必要" in report.weaknesses
    assert len(report.next_steps) >= 2


def test_org_diagnostics_format():
    diagnostics = OrgSelfDiagnostics()
    report = diagnostics.diagnose(
        org_name="Healthy Org",
        health_score=85.0,
        accepted_count=6,
        rejected_count=1,
        knowledge_count=12,
    )

    formatted = diagnostics.format_report(report)

    assert "🩺 組織自己診断: Healthy Org" in formatted
    assert "高い自律スコア" in formatted
    assert "豊富な知識ベース" in formatted
