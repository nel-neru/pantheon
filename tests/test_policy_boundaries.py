"""PolicyEngine の境界網羅テスト（F6）。

評価優先度（auto_reject > human_required > auto_approve > default）と各条件の
境界（優先度順序・カテゴリ・ファイルパターン・サイズ上限）を固定する。
"""

from __future__ import annotations

from core.policy.engine import ApprovalDecision, PolicyEngine

ENGINE = PolicyEngine()


def _verdict(**proposal):
    return ENGINE.evaluate(proposal)


def test_empty_file_path_is_rejected():
    assert _verdict(category="documentation", priority="low").decision == ApprovalDecision.REJECT


def test_high_and_critical_priority_require_human():
    for priority in ("high", "critical"):
        v = _verdict(file_path="docs/x.md", category="documentation", priority=priority)
        assert v.decision == ApprovalDecision.HUMAN_REQUIRED
        assert v.rule_name == "human_required.min_priority"


def test_sensitive_categories_require_human():
    for category in ("security", "architecture", "database", "auth"):
        v = _verdict(file_path="docs/x.md", category=category, priority="low")
        assert v.decision == ApprovalDecision.HUMAN_REQUIRED
        assert v.rule_name == "human_required.categories"


def test_sensitive_file_patterns_require_human():
    for path in ("main.py", "core/models/organization.py", "tests/test_x.py"):
        v = _verdict(file_path=path, category="documentation", priority="low")
        assert v.decision == ApprovalDecision.HUMAN_REQUIRED
        assert v.rule_name == "human_required.file_patterns"


def test_low_priority_safe_doc_is_auto_approved():
    v = _verdict(file_path="docs/guide.md", category="documentation", priority="low")
    assert v.decision == ApprovalDecision.AUTO_APPROVE


def test_medium_priority_falls_through_to_default_human():
    # medium は auto_approve(max=low) を満たさず human_required(min=high) にも該当せず → default
    v = _verdict(file_path="docs/guide.md", category="documentation", priority="medium")
    assert v.decision == ApprovalDecision.HUMAN_REQUIRED
    assert v.rule_name == "default"


def test_forbidden_pattern_blocks_auto_approve():
    # .yaml は forbidden_pattern → auto_approve 不成立 → default human
    v = _verdict(file_path="config/app.yaml", category="documentation", priority="low")
    assert v.decision == ApprovalDecision.HUMAN_REQUIRED


def test_non_allowed_category_blocks_auto_approve():
    v = _verdict(file_path="docs/guide.md", category="refactor", priority="low")
    assert v.decision == ApprovalDecision.HUMAN_REQUIRED


def test_oversized_changed_file_blocks_auto_approve():
    v = _verdict(
        file_path="docs/guide.md",
        category="documentation",
        priority="low",
        changed_files=[{"file_path": "docs/guide.md", "size_kb": 250}],
    )
    assert v.decision == ApprovalDecision.HUMAN_REQUIRED


def test_helpers_partition_proposals():
    proposals = [
        {"file_path": "docs/a.md", "category": "documentation", "priority": "low"},  # auto
        {"file_path": "main.py", "category": "documentation", "priority": "low"},    # human
        {"category": "documentation", "priority": "low"},                            # reject
    ]
    auto = ENGINE.get_auto_approvable(proposals)
    human = ENGINE.get_human_required(proposals)
    assert len(auto) == 1 and auto[0]["file_path"] == "docs/a.md"
    assert len(human) == 1 and human[0]["file_path"] == "main.py"


def test_custom_policy_yaml_roundtrip(tmp_path):
    policy_file = tmp_path / "policy.yaml"
    ENGINE.save_default_policy(policy_file)
    loaded_engine = PolicyEngine(policy_path=policy_file)
    v = loaded_engine.evaluate({"file_path": "docs/a.md", "category": "documentation", "priority": "low"})
    assert v.decision == ApprovalDecision.AUTO_APPROVE
