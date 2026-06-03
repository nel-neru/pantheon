"""Tests for EventDetector"""


import pytest

from core.events.detector import EventDetector, EventType


@pytest.fixture
def detector(tmp_path):
    return EventDetector(platform_home=tmp_path)


def test_no_orgs_returns_empty(detector):
    events = detector.detect_all()
    assert events == []


def test_health_drop_detected(tmp_path):
    from core.org_factory import create_default_organization
    from core.platform.state import PlatformStateManager

    psm = PlatformStateManager(tmp_path)
    org = create_default_organization("LowHealthOrg", "テスト")
    psm.save_organization(org)

    detector = EventDetector(platform_home=tmp_path, health_drop_threshold=50.0)
    events = detector.detect_all()

    health_events = [e for e in events if e.event_type == EventType.HEALTH_DROP]
    assert len(health_events) >= 1
    assert health_events[0].org_name == "LowHealthOrg"


def test_pending_spike_detected(tmp_path):
    from uuid import uuid4

    from core.models.organization import ImprovementProposal
    from core.org_factory import create_default_organization
    from core.platform.state import PlatformStateManager

    psm = PlatformStateManager(tmp_path)
    org = create_default_organization("SpikeOrg", "テスト")
    psm.save_organization(org)
    sm = psm.get_org_state_manager(org)

    # 3件の提案を追加（limit=2 に設定してスパイクにする）
    for i in range(3):
        p = ImprovementProposal(
            review_id=uuid4(), priority="low", category="style",
            title=f"提案{i}", description="説明", file_path=f"src/f{i}.py",
        )
        sm.save_improvement_proposal(p)

    detector = EventDetector(platform_home=tmp_path, pending_spike_limit=2)
    events = detector.detect_all()

    spike_events = [e for e in events if e.event_type == EventType.PENDING_SPIKE]
    assert len(spike_events) == 1
    assert spike_events[0].details["pending_count"] == 3


def test_commit_cache_saves(tmp_path):
    from core.org_factory import create_default_organization
    from core.platform.state import PlatformStateManager

    psm = PlatformStateManager(tmp_path)
    org = create_default_organization("RepoOrg", "テスト")
    org.target_repo_path = "/tmp/nonexistent"
    psm.save_organization(org)

    detector = EventDetector(platform_home=tmp_path)
    detector.detect_all()
    # キャッシュが作られていること
    cache_path = tmp_path / "event_cache.json"
    assert cache_path.exists()


def test_load_commit_cache_logs_warning_for_invalid_json(tmp_path, caplog):
    cache_path = tmp_path / "event_cache.json"
    cache_path.write_text("{not-json", encoding="utf-8")

    caplog.set_level("WARNING")
    detector = EventDetector(platform_home=tmp_path)

    assert detector._last_commits == {}
    assert "Failed to load commit cache" in caplog.text


def test_save_commit_cache_creates_parent_directory(tmp_path):
    platform_home = tmp_path / "nested" / "platform-home"
    detector = EventDetector(platform_home=platform_home)
    detector._last_commits = {"org-1": "abc123"}

    detector._save_commit_cache()

    cache_path = platform_home / "event_cache.json"
    assert cache_path.exists()
    assert '"org-1": "abc123"' in cache_path.read_text(encoding="utf-8")
