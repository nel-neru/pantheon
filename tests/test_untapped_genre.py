"""P4.2: 未開拓ジャンル発見（core/trends/untapped_genre）のテスト（決定論・冪等・LLM 非依存）。"""

from __future__ import annotations

from core.org_factory import create_default_organization
from core.platform.state import PlatformStateManager
from core.trends.models import TrendItem
from core.trends.store import TrendStore
from core.trends.untapped_genre import (
    enumerate_genre_evidence,
    find_untapped_genres,
    scan_untapped_genre_proposals,
)


def _setup(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setattr("core.platform.state.get_platform_home", lambda: home)
    return home, PlatformStateManager(platform_home=home)


def _seed(home, rows):
    store = TrendStore(platform_home=home)
    for i, (genre, score) in enumerate(rows):
        store.add(
            TrendItem(
                source="web",
                url=f"https://ex.com/{genre}/{i}",
                title=f"{genre} trend {i}",
                summary="s",
                genre=genre,
                score=score,
            )
        )


def test_enumerate_genre_evidence(tmp_path, monkeypatch):
    home, _ = _setup(tmp_path, monkeypatch)
    _seed(home, [("cooking", 9.0), ("cooking", 7.5), ("gardening", 8.0)])
    ev = enumerate_genre_evidence(TrendStore(platform_home=home), min_score=7.0)
    assert ev["cooking"]["count"] == 2
    assert ev["cooking"]["max_score"] == 9.0
    assert ev["cooking"]["top_trend"].score == 9.0
    assert ev["gardening"]["count"] == 1


def test_find_untapped_excludes_covered(tmp_path, monkeypatch):
    home, _ = _setup(tmp_path, monkeypatch)
    _seed(home, [("cooking", 9.0), ("gardening", 8.0)])
    ev = enumerate_genre_evidence(TrendStore(platform_home=home), min_score=7.0)
    untapped = find_untapped_genres(ev, covered={"cooking"})
    assert untapped == ["gardening"]  # cooking は被覆済みで除外


def test_scan_enqueues_new_business_for_untapped(tmp_path, monkeypatch):
    home, psm = _setup(tmp_path, monkeypatch)
    # cooking は既存 org が被覆、gardening は未開拓
    org = create_default_organization("Cooking Co", "料理")
    org.industry_genre = "cooking"
    psm.save_organization(org)
    _seed(home, [("cooking", 9.0), ("gardening", 9.0), ("gardening", 8.0)])

    result = scan_untapped_genre_proposals(platform_home=home, min_score=7.0)
    assert result["proposals"] == 1
    sm = psm.get_org_state_manager(psm.load_organization_by_name("Cooking Co"))
    props = [p for p in sm.get_all_improvement_proposals() if p["category"] == "new_business"]
    assert len(props) == 1
    assert props[0]["dedupe_key"] == "untapped:gardening"
    assert props[0]["status"] == "proposed"
    assert props[0]["target_kind"] == "org_structure"


def test_scan_is_idempotent_by_genre(tmp_path, monkeypatch):
    home, psm = _setup(tmp_path, monkeypatch)
    psm.save_organization(create_default_organization("Content Org", "content"))
    _seed(home, [("gardening", 9.0)])

    first = scan_untapped_genre_proposals(platform_home=home, min_score=7.0)
    assert first["proposals"] == 1
    # 同ジャンルに別トレンドを足しても、ジャンル単位で冪等（1社/ジャンル）
    _seed(home, [("gardening", 9.5)])
    second = scan_untapped_genre_proposals(platform_home=home, min_score=7.0)
    assert second["proposals"] == 0


def test_evidence_floor_excludes_thin_genres(tmp_path, monkeypatch):
    home, _ = _setup(tmp_path, monkeypatch)
    _seed(home, [("gardening", 9.0)])  # 証拠 1 件
    ev = enumerate_genre_evidence(TrendStore(platform_home=home), min_score=7.0)
    assert find_untapped_genres(ev, covered=set(), min_evidence=2) == []  # 閾値未満で除外


def test_scan_no_org(tmp_path, monkeypatch):
    home, _ = _setup(tmp_path, monkeypatch)
    _seed(home, [("gardening", 9.0)])
    assert scan_untapped_genre_proposals(platform_home=home)["reason"] == "no_org"


def test_scan_does_not_invoke_claude(tmp_path, monkeypatch):
    home, psm = _setup(tmp_path, monkeypatch)
    psm.save_organization(create_default_organization("Content Org", "content"))
    _seed(home, [("gardening", 9.0)])

    def _boom(*a, **k):  # pragma: no cover
        raise AssertionError("claude CLI must not be invoked on the discovery path")

    monkeypatch.setattr("core.runtime.claude_code.claude_available", _boom, raising=False)
    assert scan_untapped_genre_proposals(platform_home=home, min_score=7.0)["proposals"] == 1
