"""NotificationCenter（P3.3）のテスト — 集約・既読・設定・静音時間帯。"""

from __future__ import annotations

from pathlib import Path

from core.notifications import NotificationCenter


def test_add_list_and_unread_count(tmp_path: Path) -> None:
    center = NotificationCenter(platform_home=tmp_path)
    assert center.unread_count() == 0
    center.add(level="info", message="hello", org_name="Co")
    center.add(level="warn", message="watch out", org_name="Co")

    items = center.list()
    assert len(items) == 2
    assert center.unread_count() == 2
    assert all(not i["read"] for i in items)


def test_mark_read_is_idempotent_and_nondestructive(tmp_path: Path) -> None:
    center = NotificationCenter(platform_home=tmp_path)
    note = center.add(level="info", message="m", org_name="Co")
    nid = note["id"]

    assert center.mark_read(nid) is True
    assert center.unread_count() == 0
    # 冪等: 2 回目は no-op（False）だが状態は既読のまま
    assert center.mark_read(nid) is False
    assert center.unread_count() == 0
    # append-only ログは消えない（一覧には残る）
    assert len(center.list()) == 1
    assert center.list()[0]["read"] is True


def test_mark_read_unknown_id_returns_false(tmp_path: Path) -> None:
    center = NotificationCenter(platform_home=tmp_path)
    center.add(level="info", message="m")
    assert center.mark_read("does-not-exist") is False


def test_mark_all_read(tmp_path: Path) -> None:
    center = NotificationCenter(platform_home=tmp_path)
    center.add(level="info", message="a")
    center.add(level="warn", message="b")
    assert center.mark_all_read() == 2
    assert center.unread_count() == 0
    # 再度は新規既読 0
    assert center.mark_all_read() == 0


def test_unread_only_filter(tmp_path: Path) -> None:
    center = NotificationCenter(platform_home=tmp_path)
    n1 = center.add(level="info", message="a")
    center.add(level="warn", message="b")
    center.mark_read(n1["id"])
    unread = center.list(unread_only=True)
    assert len(unread) == 1
    assert unread[0]["message"] == "b"


def test_reads_existing_proactive_notifier_log(tmp_path: Path) -> None:
    """ProactiveNotifier が書いた既存ログ（notification_id スキーマ）を読める。"""
    from core.monitoring.proactive_notifier import ProactiveNotifier

    notifier = ProactiveNotifier(platform_home=tmp_path)
    notes = notifier.check_org_health("Co", current_score=10.0, previous_score=50.0)
    for n in notes:
        notifier.save_notification(n)

    center = NotificationCenter(platform_home=tmp_path)
    items = center.list()
    assert len(items) == len(notes) >= 1
    assert all(i["id"] for i in items)  # notification_id が id に正規化される


def test_settings_defaults_and_update(tmp_path: Path) -> None:
    center = NotificationCenter(platform_home=tmp_path)
    settings = center.get_settings()
    assert settings["min_level"] == "info"
    assert settings["quiet_hours_start"] == 0

    updated = center.update_settings(
        {"min_level": "warn", "quiet_hours_start": 22, "quiet_hours_end": 7}
    )
    assert updated["min_level"] == "warn"
    assert updated["quiet_hours_start"] == 22
    # 永続化される
    assert NotificationCenter(platform_home=tmp_path).get_settings()["min_level"] == "warn"


def test_settings_invalid_values_are_normalized(tmp_path: Path) -> None:
    center = NotificationCenter(platform_home=tmp_path)
    updated = center.update_settings({"min_level": "bogus", "quiet_hours_start": 99})
    assert updated["min_level"] == "info"  # 未知レベルは info へ
    assert updated["quiet_hours_start"] == 23  # 0..23 にクランプ


def test_should_push_respects_min_level(tmp_path: Path) -> None:
    center = NotificationCenter(platform_home=tmp_path)
    center.update_settings({"min_level": "warn"})
    assert center.should_push("info", hour=12) is False
    assert center.should_push("warn", hour=12) is True
    assert center.should_push("critical", hour=12) is True


def test_should_push_respects_quiet_hours_overnight(tmp_path: Path) -> None:
    center = NotificationCenter(platform_home=tmp_path)
    center.update_settings({"quiet_hours_start": 22, "quiet_hours_end": 7})
    assert center.should_push("warn", hour=23) is False  # 静音中
    assert center.should_push("warn", hour=3) is False  # 日跨ぎ静音中
    assert center.should_push("warn", hour=12) is True  # 日中は OK
