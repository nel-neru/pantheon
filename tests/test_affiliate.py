"""core/affiliate（短尺動画アフィリエイト）と CLI 配線のテスト。"""

from __future__ import annotations

from datetime import date

import pytest

from core.affiliate.generator import (
    fallback_post,
    plan_schedule,
    post_from_llm_json,
)
from core.affiliate.programs import AffiliateProgram, AffiliateProgramStore, slugify
from core.affiliate.short_video import (
    HOOK_TYPES,
    ShortVideoCalendarStore,
    ShortVideoPost,
    render_calendar_csv,
    render_calendar_markdown,
    schedule_dates,
)


# --------------------------------------------------------------------------- #
# AffiliateProgram / Store
# --------------------------------------------------------------------------- #
def test_program_roundtrip_and_normalization():
    p = AffiliateProgram(
        name="ElevenLabs",
        category="voice",
        recurring=True,
        japan_ok=True,  # yaml の bool は str 化される
        tier="A",  # 大文字も正規化
        topics=["AIナレーション", 3],  # 非 str は除去
    )
    assert p.program_id == "aff:elevenlabs"
    assert p.japan_ok == "true"
    assert p.tier == "a"
    assert p.topics == ["AIナレーション", "3"]
    d = p.to_dict()
    p2 = AffiliateProgram.from_dict({**d, "unknown_field": "drop me"})
    assert p2.program_id == p.program_id
    assert p2.recurring is True


def test_slugify():
    assert slugify("Adobe (Firefly / CC)") == "adobe-firefly-cc"
    assert slugify("   ") == "program"


def test_program_store_upsert_idempotent_and_corrupt_tolerant(tmp_path):
    store = AffiliateProgramStore(platform_home=tmp_path)
    store.upsert(AffiliateProgram(name="Jasper", category="writing", has_affiliate=True, tier="b"))
    store.upsert(AffiliateProgram(name="Jasper", category="writing", has_affiliate=True, tier="a"))
    progs = store.list_programs()
    assert len(progs) == 1  # 同 program_id は重複しない
    assert progs[0].tier == "a"  # 上書き

    # 破損レコード混入 → スキップして全体を壊さない
    store.path.write_text(
        '[{"name": "OK", "category": "video"}, 5, "bad", {"no_name": 1}]', encoding="utf-8"
    )
    progs = store.list_programs()
    names = [p.name for p in progs]
    assert "OK" in names

    # 非 list の JSON → 空扱い
    store.path.write_text("null", encoding="utf-8")
    assert store.list_programs() == []


def test_program_store_seed_from_config_idempotent(tmp_path):
    store = AffiliateProgramStore(platform_home=tmp_path)
    n1 = store.seed_from_config()  # リポジトリの config/affiliate_programs/ai_tools.yaml
    assert n1 > 0
    total1 = len(store.list_programs())
    n2 = store.seed_from_config()  # 再シードしても重複しない
    total2 = len(store.list_programs())
    assert total1 == total2
    assert n2 == n1
    # has_affiliate=True が tier 順で取れる
    enabled = store.affiliate_enabled()
    assert enabled and all(p.has_affiliate for p in enabled)
    tiers = [p.tier for p in enabled]
    assert tiers == sorted(tiers, key=lambda t: {"a": 0, "b": 1, "c": 2}.get(t, 3))


# --------------------------------------------------------------------------- #
# ShortVideoPost / CalendarStore
# --------------------------------------------------------------------------- #
def test_post_roundtrip_and_defaults():
    p = ShortVideoPost(day_index=7, date="2026-07-07", program_name="HeyGen", hook_type="VS")
    assert p.post_id == "sv:007"
    assert p.hook_type == "vs"
    p2 = ShortVideoPost.from_dict({**p.to_dict(), "junk": 1})
    assert p2.day_index == 7
    assert p2.program_name == "HeyGen"


def test_calendar_store_lifecycle(tmp_path):
    store = ShortVideoCalendarStore(platform_home=tmp_path)
    posts = [
        ShortVideoPost(day_index=2, date="2026-07-02", program_name="B"),
        ShortVideoPost(day_index=1, date="2026-07-01", program_name="A"),
    ]
    store.replace_all(posts)
    listed = store.list_posts()
    assert [p.day_index for p in listed] == [1, 2]  # day_index ソート

    nxt = store.next_unposted()
    assert nxt is not None and nxt.day_index == 1

    marked = store.mark_posted(nxt.post_id)
    assert marked is not None and marked.status == "posted"
    nxt2 = store.next_unposted()
    assert nxt2 is not None and nxt2.day_index == 2

    up = store.upcoming(today="2026-07-02", limit=5)
    assert [p.day_index for p in up] == [2]


def test_calendar_store_corrupt_tolerant(tmp_path):
    store = ShortVideoCalendarStore(platform_home=tmp_path)
    store.path.write_text('[{"day_index": 1, "date": "2026-07-01"}, 9, "x"]', encoding="utf-8")
    assert [p.day_index for p in store.list_posts()] == [1]
    store.path.write_text("{}", encoding="utf-8")  # 非 list
    assert store.list_posts() == []


# --------------------------------------------------------------------------- #
# generator
# --------------------------------------------------------------------------- #
def test_schedule_dates():
    ds = schedule_dates(date(2026, 7, 1), 3)
    assert ds == ["2026-07-01", "2026-07-02", "2026-07-03"]
    assert schedule_dates(date(2026, 7, 1), 0) == []


def test_plan_schedule_rotation_and_count():
    programs = [
        AffiliateProgram(name="A", has_affiliate=True, tier="a"),
        AffiliateProgram(name="B", has_affiliate=True, tier="b"),
        AffiliateProgram(name="Bait", has_affiliate=False, tier="c"),
    ]
    plan = plan_schedule(programs, date(2026, 7, 1), 12)
    assert len(plan) == 12
    assert [e["day_index"] for e in plan] == list(range(1, 13))
    # フック型が 6 種ローテ
    assert plan[0]["hook_type"] == HOOK_TYPES[0]
    assert plan[6]["hook_type"] == HOOK_TYPES[0]
    # program が割り当てられている
    assert all(e["program"] is not None for e in plan)
    # 集客ネタ(has_affiliate=False)も混ざる
    used = {e["program"].name for e in plan}
    assert "Bait" in used and ("A" in used or "B" in used)


def test_fallback_post_quality_and_cta():
    aff = AffiliateProgram(
        name="Fliki", category="video", has_affiliate=True, topics=["テキストから動画"]
    )
    bait = AffiliateProgram(
        name="ChatGPT", category="general", has_affiliate=False, topics=["プロンプト術"]
    )
    pa = fallback_post(aff, "result", "2026-07-01", 1)
    pb = fallback_post(bait, "pain", "2026-07-02", 2)
    assert pa.title and pa.hook and pa.script and pa.cta and pa.hashtags
    assert "無料で試せる" in pa.cta  # has_affiliate=True の CTA
    assert pa.affiliate_url_slug.startswith("fliki")
    assert "無料で試せる" not in pb.cta  # 集客ネタは別 CTA
    assert pa.platform == "youtube_shorts"


def test_post_from_llm_json_fills_and_falls_back():
    prog = AffiliateProgram(name="Canva", category="design", has_affiliate=True, topics=["サムネ"])
    raw = {
        "title": "Canvaで神サムネ #shorts",
        "hook": "サムネで再生数、変わります。",
        "script": "1) ...\n2) ...",
        "onscreen_text": ["before", "after"],
        "hashtags": ["#canva", "#サムネ"],
        "cta": "概要欄から無料で。",
        # caption 欠損 → fallback で補完
    }
    p = post_from_llm_json(raw, prog, "howto", "2026-08-01", 32)
    assert p.title == "Canvaで神サムネ #shorts"
    assert p.onscreen_text == ["before", "after"]
    assert p.caption  # 欠損は fallback で埋まる
    assert p.day_index == 32 and p.hook_type == "howto"


@pytest.mark.asyncio
async def test_generate_post_falls_back_without_claude(monkeypatch):
    monkeypatch.setattr("core.runtime.claude_code.claude_available", lambda: False)
    from core.affiliate.generator import generate_post

    prog = AffiliateProgram(
        name="Descript", category="video", has_affiliate=True, topics=["動画編集"]
    )
    p = await generate_post(prog, "vs", "2026-07-01", 1)
    assert p.program_name == "Descript"
    assert p.title and p.script  # fallback が返る


# --------------------------------------------------------------------------- #
# exporters
# --------------------------------------------------------------------------- #
def test_exporters():
    posts = [
        ShortVideoPost(
            day_index=1, date="2026-07-01", program_name="A", title="T1", hashtags=["#a"]
        ),
        ShortVideoPost(day_index=2, date="2026-08-01", program_name="B", title="T2"),
    ]
    csv_text = render_calendar_csv(posts)
    assert csv_text.splitlines()[0].startswith("day,date,platform")
    assert "T1" in csv_text and "T2" in csv_text
    md = render_calendar_markdown(posts)
    assert "## 2026-07" in md and "## 2026-08" in md
    assert "Day 1" in md and "T1" in md


# --------------------------------------------------------------------------- #
# CLI 配線
# --------------------------------------------------------------------------- #
def test_cli_parser_and_handlers_wired():
    from commands import build_parser

    parser = build_parser()
    args = parser.parse_args(["affiliate", "programs"])
    assert args.handler_name == "cmd_affiliate_programs"
    args = parser.parse_args(["affiliate", "record", "--metric", "clicks", "--value", "5"])
    assert args.handler_name == "cmd_affiliate_record"
    assert args.metric == "clicks" and args.value == 5.0

    import main

    for name in (
        "cmd_affiliate_seed",
        "cmd_affiliate_programs",
        "cmd_affiliate_calendar",
        "cmd_affiliate_next",
        "cmd_affiliate_done",
        "cmd_affiliate_record",
        "cmd_affiliate_stats",
    ):
        assert name in main.HANDLERS
