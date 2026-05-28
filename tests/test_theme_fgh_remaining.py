from __future__ import annotations

import asyncio
import time
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from core.execution.ast_analyzer import ASTAnalyzer
from core.execution.change_size_controller import ChangeSizeController
from core.execution.diff_reviewer import DiffQualityReviewer
from core.execution.impact_analyzer import ImpactAnalyzer
from core.execution.lint_checker import LintChecker
from core.execution.multi_file_coordinator import MultiFileChangeCoordinator
from core.intelligence.skill_evolution import SkillEvolutionEngine
from core.models.organization import ImprovementProposal
from core.policy.policy_optimizer import PolicyOptimizer
from core.quality.config_autotuner import ConfigAutoTuner
from core.quality.template_promoter import TemplatePromoter
from core.state.backup_manager import BackupManager
from core.state.sqlite_manager import SQLiteStateManager
from core.state.system_doctor import SystemDoctor


def _run(coro):
    return asyncio.run(coro)


def make_proposal(**overrides) -> ImprovementProposal:
    payload = {
        "review_id": uuid4(),
        "title": "Improve module",
        "description": "Refine responsibilities",
        "file_path": "core/example.py",
        "priority": "medium",
        "category": "general",
    }
    payload.update(overrides)
    return ImprovementProposal(**payload)


# Theme F

def test_multi_file_coordinator_detects_import_issue(tmp_path: Path):
    target = tmp_path / "broken.py"
    target.write_text("import missing_module\n", encoding="utf-8")

    issues = MultiFileChangeCoordinator().check_import_consistency([target])

    assert any(issue.issue_type == "broken_import" for issue in issues)


def test_multi_file_coordinator_detects_signature_change():
    coordinator = MultiFileChangeCoordinator()
    before = {"sample.py": "def public_api(value):\n    return value\n"}
    after = {"sample.py": "def public_api(value, extra):\n    return value + extra\n"}

    issues = coordinator.check_signature_consistency(before, after)

    assert len(issues) == 1
    assert issues[0].issue_type == "signature_changed"


def test_diff_reviewer_detects_shorter_file():
    before = "\n".join(f"line_{idx}" for idx in range(10))
    after = "line_0\n"

    issues = DiffQualityReviewer().review_diff(before, after, file_path="short.py")

    assert any(issue.issue_type == "file_too_short" and issue.severity == "error" for issue in issues)
    assert DiffQualityReviewer().is_acceptable(issues) is False


def test_diff_reviewer_detects_added_todo():
    before = "def run():\n    return 1\n"
    after = "def run():\n    # TODO: improve\n    return 1\n"

    issues = DiffQualityReviewer().review_diff(before, after)

    assert any(issue.issue_type == "added_todo" for issue in issues)


def test_impact_analyzer_find_dependents(tmp_path: Path):
    (tmp_path / "b.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "a.py").write_text("import b\n", encoding="utf-8")
    (tmp_path / "c.py").write_text("import a\n", encoding="utf-8")

    analyzer = ImpactAnalyzer()
    graph = analyzer.build_import_graph(tmp_path)
    dependents = analyzer.find_dependents("b.py", graph)

    assert "a.py" in dependents
    assert "c.py" in dependents


def test_impact_analyzer_assess_impact_levels():
    analyzer = ImpactAnalyzer()
    graph = {
        "target.py": ["a.py", "b.py", "c.py", "d.py"],
        "a.py": [],
        "b.py": [],
        "c.py": [],
        "d.py": [],
        "lonely.py": [],
        "medium.py": ["x.py", "y.py"],
        "x.py": [],
        "y.py": [],
    }

    assert analyzer.assess_impact("lonely.py", graph) == "low"
    assert analyzer.assess_impact("medium.py", graph) == "medium"
    assert analyzer.assess_impact("target.py", graph) == "high"
    assert analyzer.should_require_human_review("target.py", graph) is True


def test_ast_analyzer_finds_function(tmp_path: Path):
    target = tmp_path / "module.py"
    target.write_text(
        "def alpha(value: int) -> int:\n    \"\"\"demo\"\"\"\n    return value\n",
        encoding="utf-8",
    )

    analyzer = ASTAnalyzer()
    info = analyzer.find_function(target, "alpha")

    assert info is not None
    assert info.name == "alpha"
    assert info.args == ["value"]
    assert analyzer.get_change_location(target, "alpha") == 1


def test_lint_checker_passes_valid_file(tmp_path: Path):
    target = tmp_path / "valid.py"
    target.write_text("def ok():\n    return 1\n", encoding="utf-8")

    checker = LintChecker()
    result = checker.check_file(target)

    assert result.passed is True
    assert checker.all_passed([result]) is True


def test_change_size_controller_estimates_lines():
    controller = ChangeSizeController()

    changed = controller.estimate_change_lines("a\nb\nc\n", "a\nx\nc\ny\n")

    assert changed == 2


def test_change_size_should_split():
    controller = ChangeSizeController()
    before = "\n".join(f"line_{idx}" for idx in range(101))
    after = "\n".join(f"changed_{idx}" for idx in range(101))

    assert controller.should_split(before, after) is True


# Theme G

def test_query_proposals_filters_results(tmp_path: Path):
    manager = SQLiteStateManager(tmp_path / "state.db")
    manager.save_improvement_proposal(make_proposal(title="High one", priority="high"))
    manager.save_improvement_proposal(make_proposal(title="Low one", priority="low"))

    rows = manager.query_proposals("WHERE priority='high'")

    assert len(rows) == 1
    assert rows[0]["title"] == "High one"


def test_query_proposals_rejects_unsafe_filter(tmp_path: Path):
    manager = SQLiteStateManager(tmp_path / "state.db")

    with pytest.raises(ValueError):
        manager.query_proposals("DROP TABLE proposals")


def test_cmd_query_prints_results(tmp_path: Path, capsys):
    from main import cmd_query

    db_path = tmp_path / "state.db"
    manager = SQLiteStateManager(db_path)
    manager.save_improvement_proposal(make_proposal(title="CLI visible", priority="high"))
    manager.close()

    _run(cmd_query(SimpleNamespace(filter="WHERE priority='high'", limit=10, db_path=str(db_path))))
    out = capsys.readouterr().out

    assert "CLI visible" in out
    assert "Query Results" in out


def test_backup_manager_backup_now(tmp_path: Path):
    source = tmp_path / "source.txt"
    source.write_text("hello", encoding="utf-8")

    backup = BackupManager(platform_home=tmp_path).backup_now(source)

    assert backup.exists()
    assert backup.read_text(encoding="utf-8") == "hello"


def test_backup_manager_restore_latest(tmp_path: Path):
    manager = BackupManager(platform_home=tmp_path)
    source = tmp_path / "source.txt"
    source.write_text("original", encoding="utf-8")
    manager.backup_now(source)
    source.write_text("changed", encoding="utf-8")

    restored = manager.restore_latest(source)

    assert restored is True
    assert source.read_text(encoding="utf-8") == "original"


def test_backup_manager_cleanup_old(tmp_path: Path):
    manager = BackupManager(platform_home=tmp_path)
    source = tmp_path / "source.txt"
    source.write_text("v1", encoding="utf-8")
    for idx in range(3):
        source.write_text(f"v{idx}", encoding="utf-8")
        manager.backup_now(source)
        time.sleep(0.01)

    deleted = manager.cleanup_old_backups("source.txt", keep=1)

    assert deleted == 2
    assert len(manager.list_backups("source.txt")) == 1


def test_system_doctor_diagnose_missing_dir(tmp_path: Path):
    doctor = SystemDoctor(platform_home=tmp_path)

    issues = doctor.diagnose()
    issue_ids = {issue.issue_id for issue in issues}

    assert {"missing_backups_dir", "missing_profiles_dir"}.issubset(issue_ids)


def test_system_doctor_fix_issues(tmp_path: Path):
    doctor = SystemDoctor(platform_home=tmp_path)
    issues = doctor.diagnose()

    fixed = doctor.fix_issues(issues)

    assert fixed >= 2
    assert (tmp_path / "backups").exists()
    assert (tmp_path / "profiles").exists()


# Theme H

def test_policy_optimizer_detects_repeated_rejects():
    decisions = [
        {"action": "REJECT", "proposal_id": f"p{idx}", "reason": "risk", "category": "security"}
        for idx in range(3)
    ]

    proposals = PolicyOptimizer().analyze_rule_effectiveness(decisions)

    assert any(proposal.proposed_action == "REJECT" for proposal in proposals)


def test_config_autotuner_low_health_recommendation():
    recs = ConfigAutoTuner().analyze_and_recommend([20.0, 30.0], [0.5, 0.4])

    assert any(rec.parameter == "low_health_threshold" and rec.recommended_value == 35 for rec in recs)


def test_config_autotuner_low_acceptance_recommendation():
    recs = ConfigAutoTuner().analyze_and_recommend([60.0, 70.0], [0.1, 0.2])

    assert any(rec.parameter == "review_cycles" for rec in recs)


def test_skill_evolution_proposes_security_audit():
    engine = SkillEvolutionEngine()
    proposals = engine.analyze_task_patterns([
        {"task_type": "security_audit", "category": "security", "frequency": 5}
    ])

    assert proposals[0].skill_name == "SECURITY_AUDIT"
    assert engine.get_proposed_skills()[0].skill_name == "SECURITY_AUDIT"


def test_template_promoter_should_promote_at_threshold(tmp_path: Path):
    promoter = TemplatePromoter(platform_home=tmp_path)

    assert promoter.should_promote("Acme", 70.0) is True


def test_template_promoter_promotes_and_lists(tmp_path: Path):
    promoter = TemplatePromoter(platform_home=tmp_path)

    path = promoter.promote_org_template("Acme", {"division": "core"}, 88.0)

    assert path.exists()
    assert "Acme_promoted" in promoter.list_promoted_templates()
