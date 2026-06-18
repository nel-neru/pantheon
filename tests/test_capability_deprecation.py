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
