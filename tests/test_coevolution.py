import json
from pathlib import Path

import pytest

from core.execution.safe_executor import BackupRecord, ChangeRequest, SafeChangeExecutor
from core.hierarchy.org_designer import OrganizationDesigner
from core.models.organization import (
    AgentSkill,
    Division,
    DivisionType,
    Organization,
    SpecialistAgent,
    Team,
)
from core.profile.developer_profile import DeveloperProfileManager


# -------------------- DeveloperProfileManager --------------------

def test_create_default_profile(tmp_path):
    manager = DeveloperProfileManager(platform_home=tmp_path)

    profile = manager.get_profile()

    assert profile.user_id == "default"
    assert profile.communication_style == "balanced"
    assert profile.approval_patterns == {}


def test_record_approval_updates_patterns(tmp_path):
    manager = DeveloperProfileManager(platform_home=tmp_path)

    manager.record_approval("security", approved=True)

    profile = manager.get_profile()
    assert profile.approval_patterns["security"].approved_count == 1
    assert profile.approval_patterns["security"].rejected_count == 0


def test_preferred_categories_after_repeated_approvals(tmp_path):
    manager = DeveloperProfileManager(platform_home=tmp_path)

    for _ in range(3):
        manager.record_approval("security", approved=True)

    profile = manager.get_profile()
    assert "security" in profile.preferred_categories
    assert profile.approval_patterns["security"].approval_rate > 0.6


def test_avoided_categories_after_repeated_rejections(tmp_path):
    manager = DeveloperProfileManager(platform_home=tmp_path)

    for _ in range(3):
        manager.record_approval("testing", approved=False)

    profile = manager.get_profile()
    assert "testing" in profile.avoided_categories
    assert profile.approval_patterns["testing"].approval_rate < 0.4


def test_focus_areas_use_top_categories(tmp_path):
    manager = DeveloperProfileManager(platform_home=tmp_path)

    manager.record_approval("security", approved=True)
    manager.record_approval("security", approved=True)
    manager.record_approval("performance", approved=True)
    manager.record_approval("performance", approved=False)
    manager.record_approval("testing", approved=False)
    manager.record_approval("testing", approved=False)

    profile = manager.get_profile()
    assert profile.focus_areas[0] == "security"
    assert set(profile.focus_areas) == {"security", "performance", "testing"}


def test_personalization_context_format(tmp_path):
    manager = DeveloperProfileManager(platform_home=tmp_path)
    for _ in range(3):
        manager.record_approval("security", approved=True)
    for _ in range(3):
        manager.record_approval("testing", approved=False)

    context = manager.get_personalization_context()

    assert context.startswith("【開発者の好み】")
    assert "好む変更: security" in context
    assert "避ける変更: testing" in context


def test_persistence_save_and_load(tmp_path):
    manager = DeveloperProfileManager(platform_home=tmp_path)
    manager.record_approval("performance", approved=True)

    reloaded = DeveloperProfileManager(platform_home=tmp_path)
    profile = reloaded.get_profile()

    assert profile.approval_patterns["performance"].approved_count == 1
    assert (tmp_path / "developer_profiles" / "default.json").exists()


# -------------------- OrganizationDesigner --------------------

def test_design_with_security_purpose(tmp_path):
    designer = OrganizationDesigner(platform_home=tmp_path)

    spec = designer.design("Improve security posture")

    division_names = [division.name for division in spec.divisions]
    assert "SecurityDivision" in division_names
    assert "CoreDivision" in division_names


def test_design_with_testing_purpose(tmp_path):
    designer = OrganizationDesigner(platform_home=tmp_path)

    spec = designer.design("Expand test automation and test coverage")

    division_names = [division.name for division in spec.divisions]
    assert "QualityDivision" in division_names


def test_instantiate_creates_organization(tmp_path):
    designer = OrganizationDesigner(platform_home=tmp_path)
    spec = designer.design("Improve performance and knowledge sharing", org_name="Pantheon Ops")

    organization = designer.instantiate(spec)

    assert organization.name == "Pantheon Ops"
    assert len(organization.divisions) >= 2
    assert len(organization.get_all_agents()) >= 2
    assert all(len(agent.skills) >= 2 for agent in organization.get_all_agents())


def test_save_and_load_template(tmp_path):
    designer = OrganizationDesigner(platform_home=tmp_path)
    spec = designer.design("Improve security")

    template_path = designer.save_as_template(spec, "security-template")
    loaded = designer.load_template("security-template")

    assert template_path.exists()
    assert loaded.template_name == "security-template"
    assert loaded.divisions[0].name == spec.divisions[0].name
    assert "security-template" in designer.list_templates()


def test_optimize_underperforming_teams_adds_support_agent(tmp_path):
    designer = OrganizationDesigner(platform_home=tmp_path)
    organization = Organization(name="Ops", purpose="Improve execution quality")
    division = Division(name="Core", type=DivisionType.ORG_EVOLUTION)
    team = Team(name="GeneralTeam", division_type=DivisionType.ORG_EVOLUTION)
    team.agents.append(
        SpecialistAgent(
            name="Worker",
            skills=[AgentSkill.STRATEGIC_PLANNING, AgentSkill.DEEP_RESEARCH],
            performance_score=20.0,
        )
    )
    division.add_team(team)
    organization.add_division(division)

    spec = designer.optimize_underperforming_teams(organization, threshold=30.0)

    assert spec.divisions[0].teams[0].agents[-1].name == "GeneralTeam Optimizer"


# -------------------- SafeChangeExecutor --------------------

def test_create_backup_existing_file(tmp_path):
    file_path = tmp_path / "sample.py"
    file_path.write_text("original", encoding="utf-8")
    executor = SafeChangeExecutor(project_root=tmp_path)

    backup = executor.create_backup(str(file_path))

    assert Path(backup.backup_path).exists()
    assert Path(backup.backup_path).read_text(encoding="utf-8") == "original"


def test_create_backup_missing_file_records_intent(tmp_path):
    executor = SafeChangeExecutor(project_root=tmp_path)

    backup = executor.create_backup("missing.py")

    assert backup.backup_path == ""
    assert backup.original_path.endswith("missing.py")
    assert executor.list_backups("missing.py")


def test_rollback_restores_file(tmp_path):
    file_path = tmp_path / "sample.py"
    file_path.write_text("before", encoding="utf-8")
    executor = SafeChangeExecutor(project_root=tmp_path)
    backup = executor.create_backup(str(file_path))
    file_path.write_text("after", encoding="utf-8")

    rolled_back = executor.rollback(backup)

    assert rolled_back is True
    assert file_path.read_text(encoding="utf-8") == "before"


def test_apply_change_writes_file(tmp_path, monkeypatch):
    file_path = tmp_path / "sample.py"
    file_path.write_text("before", encoding="utf-8")
    executor = SafeChangeExecutor(project_root=tmp_path)

    monkeypatch.setattr(
        executor,
        "_run_tests",
        lambda: (True, "1 passed", {"passed": 1, "failed": 0, "errors": 0}),
    )

    result = executor.apply_change(
        ChangeRequest(
            file_path=str(file_path),
            new_content="after",
            description="Update file",
        )
    )

    assert result.success is True
    assert result.tests_passed is True
    assert file_path.read_text(encoding="utf-8") == "after"


def test_apply_change_rolls_back_on_failed_tests(tmp_path, monkeypatch):
    file_path = tmp_path / "sample.py"
    file_path.write_text("before", encoding="utf-8")
    executor = SafeChangeExecutor(project_root=tmp_path)

    monkeypatch.setattr(
        executor,
        "_run_tests",
        lambda: (False, "1 failed", {"passed": 0, "failed": 1, "errors": 0}),
    )

    result = executor.apply_change(
        ChangeRequest(
            file_path=str(file_path),
            new_content="after",
            description="Update file",
        )
    )

    assert result.success is False
    assert result.rolled_back is True
    assert file_path.read_text(encoding="utf-8") == "before"


def test_resolve_path_rejects_parent_traversal(tmp_path):
    executor = SafeChangeExecutor(project_root=tmp_path)

    with pytest.raises(ValueError, match="escapes project root"):
        executor._resolve_path("../escape.py")


def test_resolve_path_rejects_absolute_path(tmp_path):
    executor = SafeChangeExecutor(project_root=tmp_path)

    with pytest.raises(ValueError, match="escapes project root"):
        executor._resolve_path("/etc/passwd")



def test_resolve_path_rejects_absolute_path_outside_project(tmp_path):
    executor = SafeChangeExecutor(project_root=tmp_path)
    outside_path = tmp_path.parent / "escape.py"

    with pytest.raises(ValueError, match="escapes project root"):
        executor._resolve_path(str(outside_path))



def test_list_backups(tmp_path):
    file_path = tmp_path / "sample.py"
    file_path.write_text("original", encoding="utf-8")
    executor = SafeChangeExecutor(project_root=tmp_path)
    executor.create_backup(str(file_path))
    executor.create_backup(str(file_path))

    backups = executor.list_backups(str(file_path))

    assert len(backups) == 2
    assert all(backup.original_path == str(file_path) for backup in backups)
