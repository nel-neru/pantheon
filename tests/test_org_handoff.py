"""
Cross-org 引き渡し（OrgHandoff / OrgHandoffStore）の検証。

カバー範囲:
- PolicyEngine: cross_org_handoff は常に HUMAN_REQUIRED（空 file_path でも auto_reject されず、
  auto_approve にも落ちない）。kill-switch（disabled_categories）では REJECT。
- ストア: 作成→承認/却下→消費のライフサイクル、不正遷移、フィルタ、永続化 round-trip、前方互換。
"""

from __future__ import annotations

import json

import pytest

from core.hierarchy.org_handoff import (
    HANDOFF_APPROVED,
    HANDOFF_CONSUMED,
    HANDOFF_PENDING,
    HANDOFF_REJECTED,
    OrgHandoffStore,
)
from core.policy.engine import ApprovalDecision, PolicyEngine

# --------------------------------------------------------------------------- #
# PolicyEngine                                                                 #
# --------------------------------------------------------------------------- #


def test_policy_handoff_is_human_required():
    engine = PolicyEngine()
    verdict = engine.evaluate(
        {"category": "cross_org_handoff", "priority": "medium", "file_path": ""}
    )
    assert verdict.decision == ApprovalDecision.HUMAN_REQUIRED
    assert verdict.rule_name == "human_required.cross_org_handoff"


def test_policy_handoff_not_auto_rejected_despite_empty_file_path():
    """引き渡しはファイルを持たない設計。empty_file_path で棄却してはいけない。"""
    engine = PolicyEngine()
    verdict = engine.evaluate({"category": "cross_org_handoff", "priority": "low", "file_path": ""})
    assert verdict.decision == ApprovalDecision.HUMAN_REQUIRED


def test_policy_handoff_not_confused_with_structural_intervention():
    """category だけで識別。target_org_* を持たないので介入ルールには載らない。"""
    engine = PolicyEngine()
    verdict = engine.evaluate(
        {"category": "cross_org_handoff", "priority": "medium", "file_path": ""}
    )
    assert verdict.rule_name != "intervention.cross_org"


def test_policy_handoff_kill_switch_rejects(tmp_path):
    """運用者が cross_org_handoff を disabled_categories に入れたら REJECT になる。"""
    import yaml

    policy_path = tmp_path / "policy.yaml"
    policy = {
        "auto_reject": {
            "conditions": {
                "empty_file_path": True,
                "disabled_categories": ["cross_org_handoff"],
            }
        },
        "human_required": {"conditions": {"categories": ["cross_org_handoff"]}},
    }
    policy_path.write_text(yaml.safe_dump(policy, allow_unicode=True), encoding="utf-8")
    engine = PolicyEngine(policy_path)
    verdict = engine.evaluate(
        {"category": "cross_org_handoff", "priority": "medium", "file_path": ""}
    )
    assert verdict.decision == ApprovalDecision.REJECT
    assert verdict.rule_name == "auto_reject.disabled_categories"


# --------------------------------------------------------------------------- #
# ストア: 作成                                                                  #
# --------------------------------------------------------------------------- #


def test_create_handoff_is_pending_and_records_policy(tmp_path):
    store = OrgHandoffStore(platform_home=tmp_path)
    handoff = store.create(
        source_org="SNS運用",
        target_org="note販売",
        kind="audience_signal",
        title="検証済み需要: 〇〇に関心の高いセグメント",
        payload={"segment": "creator", "evidence": "保存数が高い投稿群"},
    )
    assert handoff.status == HANDOFF_PENDING
    assert handoff.policy_decision == ApprovalDecision.HUMAN_REQUIRED.value
    assert handoff.handoff_id.startswith("handoff:")
    # 永続化されている
    reloaded = OrgHandoffStore(platform_home=tmp_path).get(handoff.handoff_id)
    assert reloaded is not None
    assert reloaded.payload["segment"] == "creator"


def test_create_handoff_same_org_raises(tmp_path):
    store = OrgHandoffStore(platform_home=tmp_path)
    with pytest.raises(ValueError):
        store.create(
            source_org="SNS運用",
            target_org="SNS運用",
            kind="audience_signal",
            title="x",
        )


def test_create_handoff_rejected_by_policy_not_persisted(tmp_path):
    """kill-switch で REJECT のとき、引き渡しは作成・永続化されない。"""
    import yaml

    policy_path = tmp_path / "policy.yaml"
    policy = {
        "auto_reject": {
            "conditions": {"empty_file_path": True, "disabled_categories": ["cross_org_handoff"]}
        }
    }
    policy_path.write_text(yaml.safe_dump(policy, allow_unicode=True), encoding="utf-8")
    store = OrgHandoffStore(platform_home=tmp_path)
    with pytest.raises(ValueError):
        store.create(
            source_org="SNS運用",
            target_org="note販売",
            kind="audience_signal",
            title="x",
            policy=PolicyEngine(policy_path),
        )
    assert store.list_handoffs() == []


# --------------------------------------------------------------------------- #
# ストア: ライフサイクル                                                        #
# --------------------------------------------------------------------------- #


def _create(store):
    return store.create(
        source_org="SNS運用",
        target_org="note販売",
        kind="audience_signal",
        title="検証済み需要",
    )


def test_approve_then_consume(tmp_path):
    store = OrgHandoffStore(platform_home=tmp_path)
    handoff = _create(store)

    approved = store.approve(handoff.handoff_id)
    assert approved.status == HANDOFF_APPROVED
    assert approved.decided_at

    # 承認済みは「着手できる仕事」キューに出る
    assert [h.handoff_id for h in store.ready_for("note販売")] == [handoff.handoff_id]
    assert store.pending_for("note販売") == []

    consumed = store.mark_consumed(handoff.handoff_id, consumed_ref="proposal:abc")
    assert consumed.status == HANDOFF_CONSUMED
    assert consumed.consumed_ref == "proposal:abc"
    assert consumed.consumed_at


def test_reject(tmp_path):
    store = OrgHandoffStore(platform_home=tmp_path)
    handoff = _create(store)
    rejected = store.reject(handoff.handoff_id)
    assert rejected.status == HANDOFF_REJECTED
    assert store.pending_for("note販売") == []


def test_invalid_transition_raises(tmp_path):
    store = OrgHandoffStore(platform_home=tmp_path)
    handoff = _create(store)
    # pending を直接 consume できない
    with pytest.raises(ValueError):
        store.mark_consumed(handoff.handoff_id)
    # 承認後に再承認できない
    store.approve(handoff.handoff_id)
    with pytest.raises(ValueError):
        store.approve(handoff.handoff_id)


def test_transition_unknown_id_raises(tmp_path):
    store = OrgHandoffStore(platform_home=tmp_path)
    with pytest.raises(KeyError):
        store.approve("handoff:does-not-exist")


def test_pending_for_filters_by_target(tmp_path):
    store = OrgHandoffStore(platform_home=tmp_path)
    store.create(source_org="SNS運用", target_org="note販売", kind="audience_signal", title="a")
    store.create(source_org="SNS運用", target_org="アフィリ", kind="monetization_lead", title="b")
    assert len(store.pending_for("note販売")) == 1
    assert len(store.pending_for("アフィリ")) == 1
    assert len(store.list_handoffs(source_org="SNS運用")) == 2
    assert len(store.list_handoffs(kind="monetization_lead")) == 1


# --------------------------------------------------------------------------- #
# 永続化 / 互換                                                                 #
# --------------------------------------------------------------------------- #


def test_forward_compatible_load_skips_unknown_keys(tmp_path):
    """未知キーを含む item はスキップして全体を壊さない。"""
    store = OrgHandoffStore(platform_home=tmp_path)
    good = _create(store)
    # 手書きで壊れた item を混ぜる
    raw = json.loads(store.handoffs_path.read_text(encoding="utf-8"))
    raw.append({"totally": "unknown", "shape": 1})
    store.handoffs_path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    loaded = OrgHandoffStore(platform_home=tmp_path).list_handoffs()
    assert [h.handoff_id for h in loaded] == [good.handoff_id]


def test_corrupt_json_returns_empty(tmp_path):
    store = OrgHandoffStore(platform_home=tmp_path)
    store.handoffs_path.write_text("{ not json", encoding="utf-8")
    assert store.list_handoffs() == []


# --------------------------------------------------------------------------- #
# マテリアライズ（承認 → 受け手 org に content_asset ブリーフ提案を自動生成）       #
# --------------------------------------------------------------------------- #


def _psm_with_target(tmp_path, name="Note Sales"):
    from core.org_factory import create_default_organization
    from core.platform.state import PlatformStateManager

    psm = PlatformStateManager(platform_home=tmp_path / "home")
    repo = tmp_path / "target-repo"
    repo.mkdir()
    target = create_default_organization(name, "target org", repo_path=repo)
    psm.save_organization(target)
    return psm, target


def test_materialize_creates_content_asset_in_target(tmp_path):
    from core.hierarchy.org_handoff import materialize_handoff

    psm, target = _psm_with_target(tmp_path)
    store = OrgHandoffStore(platform_home=psm.platform_home)
    handoff = store.create(
        source_org="SNS Growth",
        target_org="Note Sales",
        kind="audience_signal",
        title="検証済み需要: ChatGPT議事録",
        payload={"theme": "ChatGPTで議事録自動化"},
    )
    store.approve(handoff.handoff_id)
    proposal = materialize_handoff(store.get(handoff.handoff_id), psm=psm)
    assert proposal is not None
    assert proposal.category == "content_asset"
    assert proposal.file_path.startswith("content/")
    # 受け手 org の正準ストアに content_asset 提案が積まれている
    sm = psm.get_org_state_manager(target)
    pending = sm.get_pending_improvement_proposals(limit=50)
    assert any(p.get("category") == "content_asset" for p in pending)
    # ブリーフ本文に検証済みの型（無料エリア3要素・3倍刻み）が含まれる
    content = proposal.intervention_spec["content"]
    assert "3要素" in content and "3倍刻み" in content


def test_materialize_missing_target_returns_none(tmp_path):
    from core.hierarchy.org_handoff import materialize_handoff
    from core.platform.state import PlatformStateManager

    psm = PlatformStateManager(platform_home=tmp_path)
    store = OrgHandoffStore(platform_home=tmp_path)
    handoff = store.create(
        source_org="SNS Growth", target_org="DoesNotExist", kind="audience_signal", title="x"
    )
    store.approve(handoff.handoff_id)
    assert materialize_handoff(store.get(handoff.handoff_id), psm=psm) is None


def test_record_materialization(tmp_path):
    store = OrgHandoffStore(platform_home=tmp_path)
    handoff = store.create(
        source_org="SNS Growth", target_org="Note Sales", kind="audience_signal", title="x"
    )
    store.approve(handoff.handoff_id)
    store.record_materialization(handoff.handoff_id, "proposal:abc123")
    assert store.get(handoff.handoff_id).materialized_ref == "proposal:abc123"


# --------------------------------------------------------------------------- #
# 本文ドラフト生成（claude 不在 → 決定論フォールバック）                        #
# --------------------------------------------------------------------------- #


def test_draft_handoff_deterministic_fallback(tmp_path):
    """conftest が PANTHEON_NO_CLAUDE=1 → claude 不在。決定論テンプレで本文ドラフト提案が出る。"""
    import asyncio

    from core.hierarchy.org_handoff import draft_handoff

    psm, target = _psm_with_target(tmp_path)
    store = OrgHandoffStore(platform_home=psm.platform_home)
    handoff = store.create(
        source_org="SNS Growth",
        target_org="Note Sales",
        kind="audience_signal",
        title="検証済み需要: Claudeでレビュー",
        payload={"theme": "Claudeでコードレビュー"},
    )
    store.approve(handoff.handoff_id)
    proposal = asyncio.run(draft_handoff(store.get(handoff.handoff_id), psm=psm))
    assert proposal is not None
    assert proposal.category == "content_asset"
    assert proposal.file_path.startswith("content/draft-")
    body = proposal.intervention_spec["content"]
    assert "本文ドラフト" in body
    # 型（無料エリア3要素・3倍刻み）がフォールバック本文にも含まれる
    assert "3要素" in body and "3倍刻み" in body
    # 受け手 org の pending に積まれている
    sm = psm.get_org_state_manager(target)
    assert any(
        p.get("category") == "content_asset" for p in sm.get_pending_improvement_proposals(limit=50)
    )


def test_generate_draft_body_returns_title_and_markdown(tmp_path):
    import asyncio

    from core.hierarchy.org_handoff import generate_draft_body

    store = OrgHandoffStore(platform_home=tmp_path)
    handoff = store.create(
        source_org="Note Sales",
        target_org="Affiliate Revenue",
        kind="monetization_lead",
        title="物販導線: Notion AI",
        payload={"offer": "Notion AI"},
    )
    title, body = asyncio.run(generate_draft_body(store.get(handoff.handoff_id)))
    assert title and body
    assert "PR" in body  # monetization_lead の決定論本文は PR 表記を含む


# --------------------------------------------------------------------------- #
# CLI（pantheon handoff create → approve → consume）                            #
# --------------------------------------------------------------------------- #


def test_cli_handoff_create_approve_consume(tmp_path, capsys):
    import asyncio
    from types import SimpleNamespace

    from commands.handoff import cmd_handoff
    from core.platform.state import PlatformStateManager

    psm = PlatformStateManager(platform_home=tmp_path)

    # create
    asyncio.run(
        cmd_handoff(
            SimpleNamespace(
                handoff_command="create",
                source="SNS運用",
                target="note販売",
                kind="audience_signal",
                title="検証済み需要",
                priority="high",
                note="",
                payload_json='{"segment": "creator"}',
            ),
            get_psm=lambda: psm,
        )
    )
    out = capsys.readouterr().out
    assert "引き渡しを作成しました" in out

    store = OrgHandoffStore(platform_home=tmp_path)
    handoff = store.list_handoffs()[0]
    assert handoff.status == HANDOFF_PENDING
    assert handoff.payload == {"segment": "creator"}

    # approve（先頭一致 ID）
    short_id = handoff.handoff_id[: len("handoff:") + 8]
    asyncio.run(
        cmd_handoff(
            SimpleNamespace(handoff_command="approve", handoff_id=short_id),
            get_psm=lambda: psm,
        )
    )
    assert store.get(handoff.handoff_id).status == HANDOFF_APPROVED

    # consume
    asyncio.run(
        cmd_handoff(
            SimpleNamespace(
                handoff_command="consume", handoff_id=handoff.handoff_id, ref="proposal:xyz"
            ),
            get_psm=lambda: psm,
        )
    )
    consumed = store.get(handoff.handoff_id)
    assert consumed.status == HANDOFF_CONSUMED
    assert consumed.consumed_ref == "proposal:xyz"
