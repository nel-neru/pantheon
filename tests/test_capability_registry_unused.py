"""get_unused_capabilities のしきい値ロジックに対する回帰テスト。

旧実装は ``is_unused = usage_count == 0`` を無条件 unused 扱いし、日付計算は True を OR する
だけだったため、scan 直後の能力（usage_count==0）が threshold を無視してほぼ全件 unused 報告
されていた（Atlas 既知バグ）。さらに tz を無条件 ``replace(tzinfo=utc)`` で付与し、aware 非UTC を
黙って歪めていた。本テストは修正後のセマンティクスを load-bearing にピン留めする:

- 最終アクティビティ（last_used、無ければ added_at）が threshold 日以上前 → unused
- 一度も使われていなくても added_at が新しければ unused にしない（grace period）
- aware 非UTC タイムスタンプは瞬間を保って正しく比較される
- 解析不能なタイムスタンプは安全側で unused に含めない
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core.intelligence.capability_registry import CapabilityEntry, CapabilityRegistry


def _iso_days_ago(days: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def _registry_with(tmp_path, entries: list[CapabilityEntry]) -> CapabilityRegistry:
    registry = CapabilityRegistry(platform_home=tmp_path)
    # 自動スキャンで入った能力を除去し、テスト対象だけを残す（決定論化）。
    registry._capabilities.clear()
    for entry in entries:
        registry._capabilities[entry.id] = entry
    return registry


def test_never_used_but_recently_added_is_not_unused(tmp_path):
    """一度も使われていない新規能力は、追加が新しければ unused 報告しない（旧バグの核心）。"""
    fresh = CapabilityEntry(
        id="fresh",
        name="Fresh Agent",
        capability_type="agent",
        added_at=_iso_days_ago(1),
        usage_count=0,
        last_used=None,
    )
    registry = _registry_with(tmp_path, [fresh])
    unused_ids = {c["id"] for c in registry.get_unused_capabilities(days_threshold=90)}
    assert "fresh" not in unused_ids


def test_never_used_and_old_is_unused(tmp_path):
    """一度も使われず追加から threshold 以上経った能力は unused。"""
    stale = CapabilityEntry(
        id="stale",
        name="Stale Agent",
        capability_type="agent",
        added_at=_iso_days_ago(200),
        usage_count=0,
        last_used=None,
    )
    registry = _registry_with(tmp_path, [stale])
    unused_ids = {c["id"] for c in registry.get_unused_capabilities(days_threshold=90)}
    assert "stale" in unused_ids


def test_recently_used_is_not_unused_even_if_added_long_ago(tmp_path):
    """最近使われた能力は、追加が古くても unused にしない（last_used が優先）。"""
    active = CapabilityEntry(
        id="active",
        name="Active Agent",
        capability_type="agent",
        added_at=_iso_days_ago(300),
        usage_count=5,
        last_used=_iso_days_ago(2),
    )
    registry = _registry_with(tmp_path, [active])
    unused_ids = {c["id"] for c in registry.get_unused_capabilities(days_threshold=90)}
    assert "active" not in unused_ids


def test_used_long_ago_is_unused(tmp_path):
    """過去に使われたが threshold 以上放置された能力は unused。"""
    dormant = CapabilityEntry(
        id="dormant",
        name="Dormant Agent",
        capability_type="agent",
        added_at=_iso_days_ago(400),
        usage_count=3,
        last_used=_iso_days_ago(120),
    )
    registry = _registry_with(tmp_path, [dormant])
    unused_ids = {c["id"] for c in registry.get_unused_capabilities(days_threshold=90)}
    assert "dormant" in unused_ids


def test_days_alias_overrides_threshold(tmp_path):
    """days 引数は days_threshold を上書きする（後方互換）。"""
    cap = CapabilityEntry(
        id="cap",
        name="Cap",
        capability_type="agent",
        added_at=_iso_days_ago(30),
        usage_count=0,
        last_used=None,
    )
    registry = _registry_with(tmp_path, [cap])
    # 既定 90 では unused でないが、days=10 なら 30 日前は unused。
    assert "cap" not in {c["id"] for c in registry.get_unused_capabilities(days_threshold=90)}
    assert "cap" in {c["id"] for c in registry.get_unused_capabilities(days=10)}


def test_aware_non_utc_timestamp_not_corrupted(tmp_path):
    """aware な非UTC タイムスタンプは瞬間を保って比較される（無条件 replace の独立回帰防止）。

    旧実装の無条件 ``replace(tzinfo=utc)`` は ``+09:00`` の壁時計値を UTC と誤読し、瞬間を
    9 時間「未来」へずらしていた。ここでは真の経過が threshold をわずかに超える JST 値を作る:
    真値 = 90 日 + 3 時間前 → ``.days == 90`` → unused（正）。旧コードは +09:00 を剥がして
    瞬間を +9h ずらすため経過 = 89 日 18 時間 → ``.days == 89`` → unused に**ならない**（誤）。

    ``usage_count`` を正にして「未使用ショートサーキット」(バグ#1)を無効化することで、
    本テストは tz 破損のみを単独で検出する（バグ#1 とは独立）。
    """
    jst = timezone(timedelta(hours=9))
    true_instant = datetime.now(timezone.utc) - timedelta(days=90, hours=3)
    last_used_jst = true_instant.astimezone(jst).isoformat()  # 同じ瞬間を +09:00 表記で
    cap = CapabilityEntry(
        id="jst",
        name="JST Agent",
        capability_type="agent",
        added_at=(datetime.now(timezone.utc) - timedelta(days=400)).isoformat(),
        usage_count=3,
        last_used=last_used_jst,
    )
    registry = _registry_with(tmp_path, [cap])
    assert "jst" in {c["id"] for c in registry.get_unused_capabilities(days_threshold=90)}


def test_unparseable_timestamp_is_not_unused(tmp_path):
    """解析不能なタイムスタンプは経過日数不明なので安全側で unused に含めない。"""
    broken = CapabilityEntry(
        id="broken",
        name="Broken Agent",
        capability_type="agent",
        added_at="not-a-timestamp",
        usage_count=0,
        last_used=None,
    )
    registry = _registry_with(tmp_path, [broken])
    unused_ids = {c["id"] for c in registry.get_unused_capabilities(days_threshold=90)}
    assert "broken" not in unused_ids
