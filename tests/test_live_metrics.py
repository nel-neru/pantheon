"""live_metrics — 実リポジトリ状態から指標を計算することのテスト。

GUI の health/autonomy/velocity が作成時デフォルト（40/50/~32.5）ではなく、実際の
提案・決定履歴を反映することを保証する。
"""

from __future__ import annotations

from uuid import uuid4

from core.metrics.live_metrics import (
    compute_live_group_metrics,
    compute_live_org_metrics,
)
from core.models.organization import ImprovementProposal
from core.org_factory import create_default_organization
from core.platform.state import PlatformStateManager


def _org(tmp_path, name="MetricsOrg"):
    org = create_default_organization(name, "metrics", repo_path=str(tmp_path))
    return org


def _save_proposal(sm, status, title="p"):
    proposal = ImprovementProposal(
        review_id=uuid4(), title=title, description="d", priority="medium", category="general"
    )
    proposal.status = status
    sm.save_improvement_proposal(proposal)


def test_empty_org_reflects_no_activity(tmp_path):
    """活動の無い組織は autonomy=0 / velocity=0（捏造された 40/50 ではない）。"""
    psm = PlatformStateManager(platform_home=tmp_path / "home")
    org = _org(tmp_path)
    psm.save_organization(org)
    sm = psm.get_org_state_manager(org)

    live = compute_live_org_metrics(org, sm)
    assert live.autonomy_score == 0.0
    assert live.improvement_velocity == 0.0
    assert live.pending_proposals == 0
    # 静的デフォルト 40.0 とは異なる（実状態由来）
    assert live.autonomy_score != org.autonomy_score


def test_metrics_react_to_real_proposals(tmp_path):
    """承認/適用済みの提案があると autonomy/velocity が上がる（実状態に反応）。"""
    psm = PlatformStateManager(platform_home=tmp_path / "home")
    org = _org(tmp_path, "ActiveOrg")
    psm.save_organization(org)
    sm = psm.get_org_state_manager(org)

    for i in range(3):
        _save_proposal(sm, status="done", title=f"applied{i}")
    _save_proposal(sm, status="rejected", title="rej")
    _save_proposal(sm, status="pending", title="pend")

    live = compute_live_org_metrics(org, sm)
    # 決着4件中3件承認 → autonomy 75.0
    assert live.autonomy_score == 75.0
    assert live.improvement_velocity > 0.0
    assert live.pending_proposals == 1
    assert 0.0 <= live.health_score <= 100.0


def test_group_metrics_aggregate_real_health(tmp_path):
    psm = PlatformStateManager(platform_home=tmp_path / "home")
    items = []
    for name in ("A", "B"):
        org = _org(tmp_path / name, name)
        (tmp_path / name).mkdir(parents=True, exist_ok=True)
        psm.save_organization(org)
        sm = psm.get_org_state_manager(org)
        items.append((org, compute_live_org_metrics(org, sm)))

    group = compute_live_group_metrics(items)
    assert group.total_organizations == 2
    assert 0.0 <= group.group_health_score <= 100.0
    assert group.weakest_organization in {"A", "B"}
    assert group.strongest_organization in {"A", "B"}


def test_empty_group_metrics():
    group = compute_live_group_metrics([])
    assert group.total_organizations == 0
    assert group.weakest_organization is None
    # 空プラットフォームは health/balance ともに 0（0 と 100 の矛盾を出さない）
    assert group.group_health_score == 0.0
    assert group.balance_score == 0.0


def test_naive_timestamp_does_not_crash(tmp_path):
    """tz 無しの日時を持つ提案 JSON があってもエンドポイントが 500 しない（aware に正規化）。"""
    import json
    import uuid

    psm = PlatformStateManager(platform_home=tmp_path / "home")
    org = _org(tmp_path)
    psm.save_organization(org)
    sm = psm.get_org_state_manager(org)
    improvements = sm.state_dir / "improvements"
    improvements.mkdir(parents=True, exist_ok=True)
    (improvements / f"{uuid.uuid4().hex}.json").write_text(
        json.dumps({"id": uuid.uuid4().hex, "status": "done", "created_at": "2026-06-01T00:00:00"}),
        encoding="utf-8",
    )
    live = compute_live_org_metrics(org, sm)  # 例外を投げない
    assert 0.0 <= live.health_score <= 100.0
    assert live.autonomy_score == 100.0  # 決着1件・承認1件


def test_recency_uses_acceptance_time_last_updated(tmp_path):
    """直近性ボーナスは作成時刻でなく承認時刻（last_updated）で判定される。"""
    import json
    import uuid
    from datetime import datetime, timedelta, timezone

    psm = PlatformStateManager(platform_home=tmp_path / "home")
    org = _org(tmp_path)
    psm.save_organization(org)
    sm = psm.get_org_state_manager(org)
    improvements = sm.state_dir / "improvements"
    improvements.mkdir(parents=True, exist_ok=True)
    old = (datetime.now(timezone.utc) - timedelta(days=20)).isoformat()
    today = datetime.now(timezone.utc).isoformat()
    (improvements / f"{uuid.uuid4().hex}.json").write_text(
        json.dumps({"id": uuid.uuid4().hex, "status": "done", "created_at": old, "last_updated": today}),
        encoding="utf-8",
    )
    live = compute_live_org_metrics(org, sm)
    # 20日前作成でも今日承認 → 直近性ボーナス(+10)が乗る: 50 + 100%*30 + 10 = 90
    assert live.health_score == 90.0
    assert live.last_improvement.startswith(today[:10])
