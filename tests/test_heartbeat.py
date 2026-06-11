"""Tests for daemon heartbeat files (core.runtime.heartbeat)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core.runtime.heartbeat import (
    MIN_STALE_SECONDS,
    heartbeat_age_seconds,
    heartbeat_path,
    is_stale,
    read_heartbeat,
    stale_threshold_seconds,
    write_heartbeat,
)


def test_write_and_read_roundtrip(tmp_path):
    write_heartbeat("content", {"status": "running", "cycle": 3}, platform_home=tmp_path)

    record = read_heartbeat("content", platform_home=tmp_path)
    assert record is not None
    assert record["name"] == "content"
    assert record["status"] == "running"
    assert record["cycle"] == 3
    assert heartbeat_path("content", tmp_path).exists()


def test_age_and_staleness(tmp_path):
    write_heartbeat("improvement", {"interval_seconds": 60}, platform_home=tmp_path)

    age = heartbeat_age_seconds("improvement", platform_home=tmp_path)
    assert age is not None and age < 5.0
    assert is_stale("improvement", 60.0, platform_home=tmp_path) is False

    future = datetime.now(timezone.utc) + timedelta(minutes=10)
    assert is_stale("improvement", 60.0, now=future, platform_home=tmp_path) is True


def test_missing_heartbeat_is_stale(tmp_path):
    assert read_heartbeat("ghost", platform_home=tmp_path) is None
    assert heartbeat_age_seconds("ghost", platform_home=tmp_path) is None
    assert is_stale("ghost", 99999.0, platform_home=tmp_path) is True


def test_corrupt_heartbeat_is_stale(tmp_path):
    path = heartbeat_path("content", tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{broken", encoding="utf-8")
    assert read_heartbeat("content", platform_home=tmp_path) is None
    assert is_stale("content", 99999.0, platform_home=tmp_path) is True


def test_stale_threshold_scaling():
    # interval×3、ただし極端に短い interval でも下限を維持
    assert stale_threshold_seconds(600) == 1800.0
    assert stale_threshold_seconds(10) == MIN_STALE_SECONDS
    assert stale_threshold_seconds(None) == MIN_STALE_SECONDS
    assert stale_threshold_seconds(0) == MIN_STALE_SECONDS
