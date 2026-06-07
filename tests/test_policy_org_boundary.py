"""Tests for PolicyEngine の組織分離境界チェック（_check_org_boundary）。

汎用ガード: external 組織（isolation_level=="external"）の提案が自ワークスペース外を
変更しようとしている場合のみ作動する。org_context=None / standard / core では完全に no-op。
特定ドメイン（アフィリエイト等）の知識は一切含まない。
"""

from core.policy.engine import ApprovalDecision, OrgBoundaryContext, PolicyEngine


def _engine():
    return PolicyEngine()  # デフォルトポリシー


def _proposal(priority="low", category="style", file_path="content/post.md"):
    return {
        "id": "test-id",
        "priority": priority,
        "category": category,
        "file_path": file_path,
        "title": "テスト提案",
        "description": "説明",
    }


def _external(scope=None):
    return OrgBoundaryContext(isolation_level="external", allowed_path_scope=scope)


# ---- external: ワークスペース外脱出は REJECT ----


def test_external_absolute_path_is_rejected():
    v = _engine().evaluate(_proposal(file_path="/etc/passwd"), org_context=_external())
    assert v.decision == ApprovalDecision.REJECT
    assert v.rule_name == "org_boundary.escape"


def test_external_parent_traversal_is_rejected():
    v = _engine().evaluate(_proposal(file_path="../../outside.py"), org_context=_external())
    assert v.decision == ApprovalDecision.REJECT
    assert v.rule_name == "org_boundary.escape"


def test_external_backslash_parent_traversal_is_rejected():
    # Windows 区切りの `..` も検出する（コード側で区切り正規化）。
    v = _engine().evaluate(_proposal(file_path="..\\secrets.py"), org_context=_external())
    assert v.decision == ApprovalDecision.REJECT
    assert v.rule_name == "org_boundary.escape"


# ---- external: 宣言スコープ外は HUMAN_REQUIRED ----


def test_external_out_of_scope_requires_human():
    ctx = _external(scope=["content"])
    v = _engine().evaluate(_proposal(file_path="scripts/run.py"), org_context=ctx)
    assert v.decision == ApprovalDecision.HUMAN_REQUIRED
    assert v.rule_name == "org_boundary.out_of_scope"


def test_external_scope_prefix_does_not_match_partial_segment():
    # スコープ "content" は "contentious/..." に誤一致してはならない（セグメント境界一致）。
    ctx = _external(scope=["content"])
    v = _engine().evaluate(_proposal(file_path="contentious/x.md"), org_context=ctx)
    assert v.decision == ApprovalDecision.HUMAN_REQUIRED
    assert v.rule_name == "org_boundary.out_of_scope"


def test_external_in_scope_passes_boundary():
    # スコープ内（content/ 配下）の low/style 提案は境界で止まらず通常ルール（auto_approve）へ。
    ctx = _external(scope=["content"])
    v = _engine().evaluate(_proposal(file_path="content/post.md"), org_context=ctx)
    assert v.decision == ApprovalDecision.AUTO_APPROVE
    assert not v.rule_name.startswith("org_boundary")


def test_external_no_scope_allows_workspace_relative():
    # allowed_path_scope 未宣言（空）なら、脱出しない相対パスは境界を通過する。
    v = _engine().evaluate(_proposal(file_path="content/post.md"), org_context=_external())
    assert v.decision == ApprovalDecision.AUTO_APPROVE
    assert not v.rule_name.startswith("org_boundary")


def test_external_empty_file_path_is_boundary_noop():
    # 空 file_path（meta）は境界では扱わない。meta は human_required.categories へフォールスルー。
    p = _proposal(category="meta", file_path="")
    p["is_meta"] = True
    v = _engine().evaluate(p, org_context=_external())
    assert v.decision == ApprovalDecision.HUMAN_REQUIRED
    assert not v.rule_name.startswith("org_boundary")


# ---- standard / core / None: 完全 no-op（従来挙動） ----


def test_standard_org_is_not_boundary_checked():
    # standard 組織なら絶対パスでも境界 REJECT は発生しない（external 限定の汎用ガード）。
    v = _engine().evaluate(
        _proposal(file_path="/etc/passwd"),
        org_context=OrgBoundaryContext(isolation_level="standard"),
    )
    assert v.rule_name != "org_boundary.escape"


def test_core_org_is_not_boundary_checked():
    v = _engine().evaluate(
        _proposal(file_path="/etc/passwd"),
        org_context=OrgBoundaryContext(isolation_level="core"),
    )
    assert v.rule_name != "org_boundary.escape"


def test_no_org_context_is_unchanged():
    # org_context を渡さない既存呼び出しは完全に従来挙動（境界チェック不作動）。
    p = _proposal(file_path="/etc/passwd")
    default = _engine().evaluate(p)
    explicit_none = _engine().evaluate(p, org_context=None)
    assert default.decision == explicit_none.decision
    assert default.rule_name == explicit_none.rule_name
    assert default.rule_name != "org_boundary.escape"
