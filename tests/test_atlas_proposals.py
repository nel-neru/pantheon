"""
Phase 1 — Atlas を自己改善の燃料に: known_issues → meta ImprovementProposal 生成 + 重複排除。
"""

from __future__ import annotations

from core.atlas.proposal_generator import build_atlas_proposals, generate_atlas_proposals
from core.policy.engine import ApprovalDecision, PolicyEngine
from core.state.manager import RepoStateManager

_ATLAS = {
    "flows": [
        {
            "id": "analyze-propose-approve-apply",
            "name": "分析→提案→承認→適用",
            "known_issues": [
                {
                    "severity": "high",
                    "title": "Web approve が PolicyEngine を通らない",
                    "detail": "詳細1",
                    "file": "web/server.py",
                },
                {
                    "severity": "medium",
                    "title": "SQLite ストアが write-orphaned",
                    "detail": "詳細2",
                    "file": "core/state/sqlite_manager.py",
                },
            ],
        },
        {
            "id": "goal-pipeline",
            "name": "ゴールパイプライン",
            "known_issues": [
                {"severity": "high", "title": "file 無しの課題", "detail": "詳細3", "file": ""},
            ],
        },
        {"id": "solid-flow", "name": "健全フロー", "known_issues": []},
    ]
}


def test_build_atlas_proposals_shape():
    proposals = build_atlas_proposals(_ATLAS)
    assert len(proposals) == 3  # 0 件のフローは無視
    for p in proposals:
        assert p.is_meta is True
        assert p.category == "meta"
        assert p.dedupe_key
        assert p.title.startswith("[meta]")
    by_title = {p.title: p for p in proposals}
    # severity → priority マッピング
    assert by_title["[meta] Web approve が PolicyEngine を通らない"].priority == "high"
    assert by_title["[meta] SQLite ストアが write-orphaned"].priority == "medium"
    # file パスが提案に引き継がれる
    assert by_title["[meta] Web approve が PolicyEngine を通らない"].file_path == "web/server.py"
    assert by_title["[meta] file 無しの課題"].file_path == ""


def test_dedupe_key_is_stable_across_runs():
    keys1 = {p.dedupe_key for p in build_atlas_proposals(_ATLAS)}
    keys2 = {p.dedupe_key for p in build_atlas_proposals(_ATLAS)}
    assert keys1 == keys2
    assert len(keys1) == 3


def test_generate_persists_and_dedupes(tmp_path):
    sm = RepoStateManager(tmp_path, "Meta-Improvement Organization")
    first = generate_atlas_proposals(_ATLAS, sm)
    assert len(first["created"]) == 3
    assert first["skipped"] == []
    # 永続化された
    saved = list((sm.state_dir / "improvements").glob("*.json"))
    assert len(saved) == 3
    # 2 回目は全部重複スキップ（新規 0）
    second = generate_atlas_proposals(_ATLAS, sm)
    assert second["created"] == []
    assert len(second["skipped"]) == 3


def test_dedupe_survives_terminal_status(tmp_path):
    sm = RepoStateManager(tmp_path, "Meta-Improvement Organization")
    result = generate_atlas_proposals(_ATLAS, sm)
    assert len(result["created"]) == 3
    # 1 件を done にしても、再生成で復活しない
    pending = sm.get_pending_improvement_proposals(limit=50)
    sm.update_proposal_status(str(pending[0]["id"]), "done")
    again = generate_atlas_proposals(_ATLAS, sm)
    assert again["created"] == []


def test_dry_run_does_not_persist(tmp_path):
    sm = RepoStateManager(tmp_path, "Meta-Improvement Organization")
    result = generate_atlas_proposals(_ATLAS, sm, dry_run=True)
    assert len(result["created"]) == 3
    assert result["dry_run"] is True
    assert not (sm.state_dir / "improvements").exists() or not list(
        (sm.state_dir / "improvements").glob("*.json")
    )


def test_meta_proposal_passes_policy_when_file_path_empty():
    engine = PolicyEngine()  # DEFAULT_POLICY
    meta_no_file = build_atlas_proposals(_ATLAS)[2].model_dump()
    assert meta_no_file["file_path"] == ""
    verdict = engine.evaluate(meta_no_file)
    # meta は auto_reject されず human_required にフォールスルー
    assert verdict.decision == ApprovalDecision.HUMAN_REQUIRED
    assert verdict.decision != ApprovalDecision.REJECT
