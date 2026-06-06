"""Tests for PolicyEngine"""

import pytest

from core.policy.engine import ApprovalDecision, PolicyEngine


@pytest.fixture
def engine():
    return PolicyEngine()  # デフォルトポリシー


def _proposal(priority="low", category="style", file_path="src/utils.py"):
    return {
        "id": "test-id",
        "priority": priority,
        "category": category,
        "file_path": file_path,
        "title": "テスト提案",
        "description": "説明",
    }


# ---- auto_reject ----


def test_empty_file_path_is_rejected(engine):
    p = _proposal(file_path="")
    v = engine.evaluate(p)
    assert v.decision == ApprovalDecision.REJECT
    assert "empty_file_path" in v.rule_name


def test_meta_proposal_with_empty_file_path_is_not_rejected(engine):
    # meta 提案は file_path が空でも auto_reject されず human_required へフォールスルー
    p = _proposal(category="meta", file_path="")
    p["is_meta"] = True
    v = engine.evaluate(p)
    assert v.decision == ApprovalDecision.HUMAN_REQUIRED
    assert v.decision != ApprovalDecision.REJECT


# ---- human_required ----


def test_high_priority_requires_human(engine):
    p = _proposal(priority="high")
    v = engine.evaluate(p)
    assert v.decision == ApprovalDecision.HUMAN_REQUIRED


def test_security_category_requires_human(engine):
    p = _proposal(priority="low", category="security")
    v = engine.evaluate(p)
    assert v.decision == ApprovalDecision.HUMAN_REQUIRED


def test_critical_file_requires_human(engine):
    p = _proposal(priority="low", category="style", file_path="core/models/organization.py")
    v = engine.evaluate(p)
    assert v.decision == ApprovalDecision.HUMAN_REQUIRED


def test_main_py_requires_human(engine):
    p = _proposal(priority="low", category="documentation", file_path="main.py")
    v = engine.evaluate(p)
    assert v.decision == ApprovalDecision.HUMAN_REQUIRED


def test_pyproject_requires_human(engine):
    p = _proposal(priority="low", category="style", file_path="pyproject.toml")
    v = engine.evaluate(p)
    assert v.decision == ApprovalDecision.HUMAN_REQUIRED


# ---- auto_approve ----


def test_low_priority_style_is_auto_approved(engine):
    p = _proposal(priority="low", category="style", file_path="src/utils.py")
    v = engine.evaluate(p)
    assert v.decision == ApprovalDecision.AUTO_APPROVE


def test_low_priority_documentation_is_auto_approved(engine):
    p = _proposal(priority="low", category="documentation", file_path="src/helper.py")
    v = engine.evaluate(p)
    assert v.decision == ApprovalDecision.AUTO_APPROVE


def test_medium_priority_is_human_required(engine):
    p = _proposal(priority="medium", category="style", file_path="src/utils.py")
    v = engine.evaluate(p)
    # medium は max_priority=low を超えるので auto_approve にならない → human_required
    assert v.decision == ApprovalDecision.HUMAN_REQUIRED


def test_large_single_file_is_not_auto_approved(engine):
    p = _proposal(priority="low", category="style", file_path="src/large.py")
    p["file_size_kb"] = 150
    v = engine.evaluate(p)
    assert v.decision == ApprovalDecision.HUMAN_REQUIRED


def test_large_changed_file_entry_is_not_auto_approved(engine):
    p = _proposal(priority="low", category="style", file_path="src/small.py")
    p["changed_files"] = [
        {"path": "src/small.py", "size_kb": 20},
        {"path": "src/huge.py", "size_bytes": 150 * 1024},
    ]
    v = engine.evaluate(p)
    assert v.decision == ApprovalDecision.HUMAN_REQUIRED


# ---- batch ----


def test_get_auto_approvable(engine):
    proposals = [
        _proposal(priority="low", category="style", file_path="src/a.py"),
        _proposal(priority="high", category="style", file_path="src/b.py"),
        _proposal(priority="low", category="security", file_path="src/c.py"),
        _proposal(priority="low", category="comment", file_path="src/d.py"),
    ]
    auto = engine.get_auto_approvable(proposals)
    assert len(auto) == 2  # a.py と d.py だけ


def test_get_human_required(engine):
    proposals = [
        _proposal(priority="low", category="style", file_path="src/a.py"),
        _proposal(priority="high", category="style", file_path="src/b.py"),
    ]
    human = engine.get_human_required(proposals)
    assert len(human) == 1
    assert human[0]["file_path"] == "src/b.py"


def test_save_default_policy(tmp_path):
    engine = PolicyEngine()
    policy_path = tmp_path / "policy.yaml"
    engine.save_default_policy(policy_path)
    assert policy_path.exists()
    import yaml

    loaded = yaml.safe_load(policy_path.read_text())
    assert "auto_approve" in loaded
    assert "human_required" in loaded
