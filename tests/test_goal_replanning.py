"""Goal 再計画フィードバックループ（達成度<70% → 再計画 meta 提案）の検証。

純粋 proposer の生成条件（達成度・サイクル上限）と、pipeline からの best-effort 起票（冪等・
Meta 組織の承認キュー）を確認する。決定論・LLM 非依存。
"""

from __future__ import annotations

from types import SimpleNamespace

from core.goals.goal_replanning_proposer import (
    MAX_REPLAN_CYCLES,
    propose_replanning,
)


def _goal():
    return SimpleNamespace(goal_id="g1", description="テストを追加して品質を上げたい")


def _verification(pct, achieved=False, unmet=None, recs=None):
    return SimpleNamespace(
        goal_id="g1",
        goal_description="テストを追加して品質を上げたい",
        overall_achieved=achieved,
        achievement_pct=pct,
        unmet_criteria=unmet or ["テストが80%以上完了している"],
        recommendations=recs or ["未達成の成功基準を重点的に対処してください"],
    )


def test_propose_replanning_emitted_when_below_threshold():
    p = propose_replanning(_goal(), _verification(40.0))
    assert p is not None
    assert p.category == "meta" and p.is_meta is True
    assert p.intervention_spec["kind"] == "goal_replanning"
    assert p.intervention_spec["replan_cycle"] == 1
    assert "40%" in p.title


def test_propose_replanning_none_when_achieved():
    assert propose_replanning(_goal(), _verification(95.0, achieved=True)) is None
    assert propose_replanning(_goal(), _verification(70.0)) is None  # しきい値ちょうどは出さない


def test_propose_replanning_respects_cycle_cap():
    # サイクル上限以上では再計画しない（無限ループ防止）。
    assert propose_replanning(_goal(), _verification(10.0), replan_cycle=MAX_REPLAN_CYCLES) is None
    assert propose_replanning(_goal(), _verification(10.0), replan_cycle=0) is not None


def test_pipeline_enqueues_replanning_into_meta_org(tmp_path, monkeypatch):
    """pipeline の hook が Meta 組織の承認キューへ再計画提案を冪等に積む（best-effort）。"""
    monkeypatch.setattr("core.platform.state.get_platform_home", lambda: tmp_path)
    from core.goals.abstract_goal_pipeline import AbstractGoalPipeline
    from core.org_factory import create_default_organization
    from core.platform.state import PlatformStateManager

    psm = PlatformStateManager(platform_home=tmp_path)
    try:
        from core.bootstrap import META_ORG_NAME

        meta_name = META_ORG_NAME
    except Exception:
        meta_name = "Meta-Improvement Organization"
    psm.save_organization(create_default_organization(meta_name, "メタ"))

    pipeline = AbstractGoalPipeline()
    monkeypatch.setattr(pipeline, "_resolve_platform_home", lambda: tmp_path)

    pipeline._maybe_propose_replanning(_goal(), _verification(30.0))
    pipeline._maybe_propose_replanning(_goal(), _verification(30.0))  # 2 回目は冪等

    meta = psm.load_organization_by_name(meta_name)
    sm = psm.get_org_state_manager(meta)
    replans = [
        p
        for p in sm.get_all_improvement_proposals()
        if p.get("category") == "meta" and str(p.get("dedupe_key", "")).startswith("replan:")
    ]
    assert len(replans) == 1  # 冪等（重複起票なし）
