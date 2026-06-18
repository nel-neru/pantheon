"""capability 非推奨機能（mark_for_deprecation）の read-path 有効化テスト。

旧状態: ``mark_for_deprecation`` は呼び出し元ゼロの dead code で、書いていた ``deprecated``
キーはどの読取経路も参照しない inert なノイズだった。本テストは「非推奨マーカー
（is_active=False）が実際に効く」ことを load-bearing にピン留めする:

- ``mark_for_deprecation`` は ``is_active=False`` を永続化し、再ロードしても残る
- 非推奨化した能力は ``get_unused_capabilities`` の候補から消える（再ナグ停止）
- 非推奨化した能力は ``format_for_agent`` の宣伝一覧から消える
- 存在しない id では何もせず False を返す
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core.intelligence.capability_registry import CapabilityEntry, CapabilityRegistry


def _iso_days_ago(days: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def _fresh_registry(tmp_path) -> CapabilityRegistry:
    registry = CapabilityRegistry(platform_home=tmp_path)
    registry._capabilities.clear()  # 自動スキャン分を除去して決定論化
    return registry


def test_mark_for_deprecation_persists_is_active_false(tmp_path):
    """is_active=False が永続化され、別インスタンスで再ロードしても残る。"""
    registry = _fresh_registry(tmp_path)
    registry.register(CapabilityEntry(id="old", name="Old Agent", capability_type="agent"))
    assert registry.mark_for_deprecation("old") is True

    # 別インスタンスでディスクから読み直しても非推奨が残る（_save 経由の永続化）。
    reloaded = CapabilityRegistry(platform_home=tmp_path)
    entry = reloaded.get("old")
    assert entry is not None
    assert entry.is_active is False


def test_mark_for_deprecation_unknown_id_is_noop_false(tmp_path):
    """存在しない id では何もせず False を返す（CLI が not-found を報告できる）。"""
    registry = _fresh_registry(tmp_path)
    registry.register(CapabilityEntry(id="keep", name="Keep", capability_type="agent"))
    assert registry.mark_for_deprecation("does-not-exist") is False
    assert registry.get("keep").is_active is True  # 無関係な能力は不変


def test_deprecated_capability_excluded_from_unused_report(tmp_path):
    """非推奨化した古い能力は get_unused_capabilities の候補から消える（再ナグ停止）。"""
    registry = _fresh_registry(tmp_path)
    registry.register(
        CapabilityEntry(
            id="stale",
            name="Stale Agent",
            capability_type="agent",
            added_at=_iso_days_ago(200),
            usage_count=0,
            last_used=None,
        )
    )
    # 非推奨化前は候補に出る（古く未使用）。
    assert "stale" in {c["id"] for c in registry.get_unused_capabilities(days_threshold=90)}
    registry.mark_for_deprecation("stale")
    # 非推奨化後は候補から除外される。
    assert "stale" not in {c["id"] for c in registry.get_unused_capabilities(days_threshold=90)}


def test_deprecated_capability_excluded_from_format_for_agent(tmp_path):
    """非推奨化した能力はエージェント宣伝一覧（format_for_agent）から消える。"""
    registry = _fresh_registry(tmp_path)
    registry.register(CapabilityEntry(id="live", name="Live Agent", capability_type="agent"))
    registry.register(CapabilityEntry(id="dead", name="Dead Agent", capability_type="agent"))

    before = registry.format_for_agent()
    assert "Live Agent" in before
    assert "Dead Agent" in before

    registry.mark_for_deprecation("dead")
    after = registry.format_for_agent()
    assert "Live Agent" in after  # アクティブは残る
    assert "Dead Agent" not in after  # 非推奨は宣伝されない


def test_deprecated_capability_does_not_suppress_gap_reproposal(tmp_path, monkeypatch):
    """非推奨化した能力は gap 分析の再提案抑制から外れる（heuristic 経路が is_active を honor）。

    C30 で format_for_agent（LLM 分析経路が読む）が is_active を honor したため、heuristic 経路の
    `existing_cap_names` も active 限定にしないと 2 経路が「その能力は在るか」で食い違う。さらに
    非推奨マーカーが必要再燃時の再提案を恒久抑止する zombie 化も防ぐ（再提案は HITL ゲートを通る）。
    """
    from types import SimpleNamespace

    from core.intelligence.capability_gap_analyzer import CapabilityGapAnalyzer

    monkeypatch.setattr("core.platform.state.get_platform_home", lambda: tmp_path)
    registry = _fresh_registry(tmp_path)
    # HEURISTIC_RULES の suggested_name と同名の能力を登録する。
    registry.register(
        CapabilityEntry(id="cea", name="CodebaseExplorerAgent", capability_type="agent")
    )
    analyzer = CapabilityGapAnalyzer(capability_registry=registry, platform_home=tmp_path)
    pattern = SimpleNamespace(operation_type="codebase_scan", pattern_key="p1", total_tokens=1000)

    # アクティブな間は「既存」とみなされ、同名 gap は抑制される（従来挙動を維持）。
    assert analyzer._analyze_heuristic([pattern]) == []

    # 非推奨化すると再提案が許される。
    registry.mark_for_deprecation("cea")
    gaps = analyzer._analyze_heuristic([pattern])
    assert [g.suggested_name for g in gaps] == ["CodebaseExplorerAgent"]
