"""get_all_gaps の registry reconcile テスト（C44）。

C40 は resolver 経路（--resolve の mark_implemented）で充足ギャップを畳んだが、それ以外の経路
（外部登録 / scan_and_register_all / 手動 register）で能力が現れた場合、永続済みギャップは
``implemented=False`` のまま残り、format_for_agent / get_summary / --resolve で恒久的に
over-report されていた。本テストは get_all_gaps が read 時に registry と reconcile することを
load-bearing にピン留めする（検出 _analyze_heuristic と同一の active-name 集合を共有）。
"""

from __future__ import annotations

from core.intelligence.capability_gap_analyzer import CapabilityGap, CapabilityGapAnalyzer
from core.intelligence.capability_registry import CapabilityEntry, CapabilityRegistry


def _fresh_registry(tmp_path) -> CapabilityRegistry:
    registry = CapabilityRegistry(platform_home=tmp_path)
    registry._capabilities.clear()  # 自動スキャン分を除去して決定論化
    return registry


def _gap(name: str) -> CapabilityGap:
    return CapabilityGap(
        gap_id=f"gap:{name}",
        pattern_key="p1",
        description=f"{name} が不足",
        suggested_type="agent",
        suggested_name=name,
        rationale="reuse",
        priority="high",
    )


def test_get_all_gaps_reconciles_persisted_gap_with_active_capability(tmp_path, monkeypatch):
    """永続ギャップは、その suggested_name が active 能力に一致したら active ビューから消える。"""
    monkeypatch.setattr("core.platform.state.get_platform_home", lambda: tmp_path)
    registry = _fresh_registry(tmp_path)
    analyzer = CapabilityGapAnalyzer(capability_registry=registry, platform_home=tmp_path)
    analyzer._gaps.append(_gap("AsyncReviewAgent"))

    # 能力が未登録なら従来どおりギャップは active。
    assert [g.suggested_name for g in analyzer.get_all_gaps()] == ["AsyncReviewAgent"]
    assert analyzer.get_summary()["total_gaps"] == 1
    assert "AsyncReviewAgent" in analyzer.format_for_agent()

    # resolver 以外の経路で能力が現れる（外部登録）。
    registry.register(CapabilityEntry(id="ara", name="AsyncReviewAgent", capability_type="agent"))

    # read 時 reconcile でギャップは active ビューから消える（over-report 解消）。
    assert analyzer.get_all_gaps() == []
    assert analyzer.get_summary()["total_gaps"] == 0
    assert "なし" in analyzer.format_for_agent()


def test_reconcile_honors_is_active_false(tmp_path, monkeypatch):
    """非推奨化（is_active=False）した能力は reconcile 対象外＝ギャップが再び active に戻る。"""
    monkeypatch.setattr("core.platform.state.get_platform_home", lambda: tmp_path)
    registry = _fresh_registry(tmp_path)
    registry.register(CapabilityEntry(id="ara", name="AsyncReviewAgent", capability_type="agent"))
    analyzer = CapabilityGapAnalyzer(capability_registry=registry, platform_home=tmp_path)
    analyzer._gaps.append(_gap("AsyncReviewAgent"))

    # active な間は充足とみなされギャップは消える。
    assert analyzer.get_all_gaps() == []

    # 非推奨化すると充足とみなされず、ギャップが復活する（検出側 honor と一致）。
    registry.mark_for_deprecation("ara")
    assert [g.suggested_name for g in analyzer.get_all_gaps()] == ["AsyncReviewAgent"]


def test_reconcile_noop_without_registry(tmp_path, monkeypatch):
    """registry 未注入なら reconcile は no-op＝後方互換（従来どおり implemented だけで判定）。"""
    monkeypatch.setattr("core.platform.state.get_platform_home", lambda: tmp_path)
    analyzer = CapabilityGapAnalyzer(capability_registry=None, platform_home=tmp_path)
    analyzer._gaps.append(_gap("AsyncReviewAgent"))

    assert [g.suggested_name for g in analyzer.get_all_gaps()] == ["AsyncReviewAgent"]


def test_include_implemented_returns_all_despite_reconcile(tmp_path, monkeypatch):
    """include_implemented=True は reconcile を適用せず全永続ギャップを返す（履歴用途）。"""
    monkeypatch.setattr("core.platform.state.get_platform_home", lambda: tmp_path)
    registry = _fresh_registry(tmp_path)
    registry.register(CapabilityEntry(id="ara", name="AsyncReviewAgent", capability_type="agent"))
    analyzer = CapabilityGapAnalyzer(capability_registry=registry, platform_home=tmp_path)
    analyzer._gaps.append(_gap("AsyncReviewAgent"))

    assert analyzer.get_all_gaps() == []
    assert [g.suggested_name for g in analyzer.get_all_gaps(include_implemented=True)] == [
        "AsyncReviewAgent"
    ]
