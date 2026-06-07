from __future__ import annotations

from core.policy.engine import ApprovalDecision, PolicyEngine

engine = PolicyEngine()


def test_policy_engine_empty_proposals():
    assert engine.get_auto_approvable([]) == []
    assert engine.get_human_required([]) == []


def test_policy_engine_unknown_category():
    verdict = engine.evaluate({"priority": "low", "category": "unknown", "file_path": "src/file.py"})
    assert verdict.decision == ApprovalDecision.HUMAN_REQUIRED


def test_policy_engine_special_chars_in_filepath():
    verdict = engine.evaluate({"priority": "low", "category": "style", "file_path": "src/space name/ファイル.py"})
    assert verdict.decision == ApprovalDecision.AUTO_APPROVE


def test_policy_engine_all_auto_approve():
    proposals = [{"priority": "low", "category": "style", "file_path": f"src/{i}.py"} for i in range(3)]
    assert len(engine.get_auto_approvable(proposals)) == 3


def test_policy_engine_all_human_required():
    proposals = [{"priority": "high", "category": "style", "file_path": f"src/{i}.py"} for i in range(3)]
    assert len(engine.get_human_required(proposals)) == 3


def test_policy_engine_ignores_invalid_changed_files_entries():
    proposal = {
        "priority": "low",
        "category": "style",
        "file_path": "src/app.py",
        "changed_files": [
            None,
            "bad-entry",
            {"path": "src/app.py", "size_kb": 1},
        ],
    }

    verdict = engine.evaluate(proposal)

    assert verdict.decision == ApprovalDecision.AUTO_APPROVE


def test_policy_engine_rejects_oversized_changed_file():
    proposal = {
        "priority": "low",
        "category": "style",
        "file_path": "src/app.py",
        "changed_files": [
            {"path": "src/app.py", "size_bytes": 150 * 1024},
        ],
    }

    verdict = engine.evaluate(proposal)

    assert verdict.decision == ApprovalDecision.HUMAN_REQUIRED
