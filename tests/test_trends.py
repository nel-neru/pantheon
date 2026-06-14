"""Tests for trend collection (core.trends.*). No network: fetch is injected."""

from __future__ import annotations

from datetime import datetime, timezone

from core.trends.collectors.web import TrendSource, collect_web, load_sources, parse_feed
from core.trends.collectors.youtube import load_channels
from core.trends.models import TrendItem, normalize_url
from core.trends.runner import collect_and_store
from core.trends.scoring import _heuristic_score, score_trend
from core.trends.store import TrendStore

RSS_FIXTURE = """<?xml version="1.0"?>
<rss version="2.0"><channel>
  <title>Example Feed</title>
  <item>
    <title>AI breakthrough in agents</title>
    <link>https://example.com/ai-agents?utm=rss</link>
    <description>A new &lt;b&gt;agent&lt;/b&gt; framework ships.</description>
  </item>
  <item>
    <title>Second story</title>
    <link>https://example.com/second/</link>
    <description>More details here.</description>
  </item>
</channel></rss>
"""

ATOM_FIXTURE = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Atom Example</title>
  <entry>
    <title>Side business idea</title>
    <link href="https://atom.example.com/idea"/>
    <summary>Bootstrap a SaaS in a weekend.</summary>
  </entry>
</feed>
"""


# ---- models ----
def test_normalize_url_dedup_basis():
    assert normalize_url("https://Example.com/Path/?a=1#frag") == "https://example.com/Path"
    assert normalize_url("https://example.com/path/") == "https://example.com/path"
    # query 違いは同一視される
    a = normalize_url("https://x.com/p?utm=1")
    b = normalize_url("https://x.com/p?utm=2")
    assert a == b


def test_trenditem_hash_stable():
    a = TrendItem(source="web", url="https://x.com/p?utm=1", title="T").ensure_hash()
    b = TrendItem(source="web", url="https://x.com/p?utm=2", title="Different").ensure_hash()
    assert a.hash == b.hash  # 正規化 URL が同じなら同一


def test_trenditem_hash_falls_back_to_title():
    a = TrendItem(source="x", url="", title="No URL Trend").ensure_hash()
    assert a.hash  # URL 無しでも hash が付く


# ---- feed parsing ----
def test_parse_rss():
    items = parse_feed(RSS_FIXTURE, TrendSource(name="ex", url="u", genre="ai"))
    assert len(items) == 2
    first = items[0]
    assert first.title == "AI breakthrough in agents"
    assert first.url == "https://example.com/ai-agents?utm=rss"
    assert "agent framework" in first.summary  # タグ除去・unescape
    assert first.genre == "ai"
    assert first.source == "web"


def test_parse_atom_link_href():
    items = parse_feed(ATOM_FIXTURE, TrendSource(name="atom", url="u", genre="side_business"))
    assert len(items) == 1
    assert items[0].url == "https://atom.example.com/idea"
    assert items[0].genre == "side_business"


def test_parse_malformed_returns_empty():
    assert parse_feed("<not xml", TrendSource(name="x", url="u")) == []
    assert parse_feed("", TrendSource(name="x", url="u")) == []


def test_collect_web_with_injected_fetch():
    sources = [
        TrendSource(name="a", url="https://a/feed", genre="ai"),
        TrendSource(name="b", url="https://b/feed", genre="side_business"),
    ]
    feeds = {"https://a/feed": RSS_FIXTURE, "https://b/feed": ATOM_FIXTURE}
    items = collect_web(sources, fetch=lambda url, **kw: feeds.get(url))
    assert len(items) == 3  # 2 from RSS + 1 from Atom


def test_collect_web_tolerates_fetch_failure():
    sources = [TrendSource(name="dead", url="https://dead/feed")]
    items = collect_web(sources, fetch=lambda url, **kw: None)
    assert items == []


def test_fetch_aborts_on_oversized_response(monkeypatch):
    from core.trends.collectors import web

    class _Resp:
        encoding = "utf-8"

        def raise_for_status(self):
            return None

        def iter_bytes(self):
            # MAX_FETCH_BYTES を超えるチャンクを返す
            yield b"x" * (web.MAX_FETCH_BYTES + 1)

    class _Stream:
        def __enter__(self):
            return _Resp()

        def __exit__(self, *a):
            return False

    import httpx

    monkeypatch.setattr(httpx, "stream", lambda *a, **k: _Stream())
    assert web._fetch("https://huge/feed") is None


# ---- store dedup ----
def test_store_dedup(tmp_path):
    store = TrendStore(platform_home=tmp_path)
    item = TrendItem(source="web", url="https://x.com/a", title="A")
    assert store.add(item) is True
    # 同 URL（query 違い）は重複として弾かれる
    dup = TrendItem(source="web", url="https://x.com/a?utm=2", title="A again")
    assert store.add(dup) is False
    assert len(store.list()) == 1


def test_store_add_many_dedups_within_batch(tmp_path):
    store = TrendStore(platform_home=tmp_path)
    items = [
        TrendItem(source="web", url="https://x.com/a", title="A"),
        TrendItem(source="web", url="https://x.com/a?ref=1", title="A dup"),
        TrendItem(source="web", url="https://x.com/b", title="B"),
    ]
    assert store.add_many(items) == 2


def test_store_list_filters_and_sorts(tmp_path):
    store = TrendStore(platform_home=tmp_path)
    store.add(TrendItem(source="web", url="https://x/1", title="low", score=3.0, genre="ai"))
    store.add(TrendItem(source="web", url="https://x/2", title="high", score=9.0, genre="ai"))
    store.add(TrendItem(source="youtube", url="https://y/3", title="yt", score=8.0, genre="ai"))

    top = store.list(min_score=5.0)
    assert [i.title for i in top] == ["high", "yt"]  # スコア降順
    assert [i.title for i in store.list(source="youtube")] == ["yt"]
    assert [i.title for i in store.list(genre="ai", limit=1)] == ["high"]


# ---- scoring (offline heuristic) ----
def test_heuristic_score_range():
    now = datetime(2026, 6, 11, 12, 0, 0, tzinfo=timezone.utc)
    item = TrendItem(
        source="web",
        url="https://x/1",
        title="t",
        summary="s" * 400,
        genre="ai",
        topics=["a", "b"],
        collected_at=now.isoformat(),
    )
    score = _heuristic_score(item, now=now)
    assert 0.0 <= score <= 10.0
    assert score > 5.0  # 鮮度＋情報量＋ジャンルで基準超え


async def test_score_trend_offline_uses_heuristic(monkeypatch):
    # conftest が PANTHEON_NO_CLAUDE=1 → claude_available()=False
    item = TrendItem(source="web", url="https://x/1", title="t", summary="hello", genre="ai")
    score = await score_trend(item)
    assert 0.0 <= score <= 10.0


# ---- end-to-end orchestration ----
async def test_collect_and_store_e2e(tmp_path, monkeypatch):
    monkeypatch.setattr("core.platform.state.get_platform_home", lambda: tmp_path)
    monkeypatch.setattr(
        "core.trends.runner.load_sources",
        lambda path=None: [TrendSource(name="a", url="https://a/feed", genre="ai")],
    )
    # YouTube は実ネットワークを叩かないよう空に（B-2 collector は別テストで検証）
    monkeypatch.setattr("core.trends.runner.load_channels", lambda path=None: [])
    monkeypatch.setattr("core.trends.collectors.web._fetch", lambda url, **kw: RSS_FIXTURE)
    result = await collect_and_store(platform_home=tmp_path)
    assert result["collected"] == 2
    assert result["added"] == 2
    stored = TrendStore(platform_home=tmp_path).list()
    assert len(stored) == 2
    assert all(i.score >= 0 for i in stored)


def test_bundled_trend_sources_are_well_formed():
    """同梱 config/trend_sources.yaml が collector の契約を満たすことを構造検証する。

    このファイルは手編集でソースを足す運用（"追加・削除はこのファイルだけで完結"）
    なので、type の打ち間違いや genre 抜けなど **黙って収集が痩せる** 類の誤りを
    早期に捕まえる。実ネットワークは叩かない（パース対象のメタだけ検証）。
    """
    sources = load_sources()  # 同梱の実ファイルを読む
    assert sources, "同梱 trend_sources.yaml の sources が空"
    for s in sources:
        assert s.name, f"name 欠落: {s}"
        assert s.url.startswith(("http://", "https://")), f"url が http(s) でない: {s}"
        assert s.type in {"rss", "atom"}, f"未知の type={s.type!r}: {s.name}"
        assert s.genre, f"genre 欠落: {s.name}"

    channels = load_channels()
    for c in channels:
        assert c.channel_id.startswith("UC"), f"channel_id が UC... でない: {c}"
        assert c.genre, f"genre 欠落: {c.name}"


def test_claude_code_genre_has_multiple_sources():
    """CC 設定最適化ループ（E フェーズ）の入力が単一フィードに痩せない soft floor。

    `>= 2` の最小値ガード（等値ピンではない）。ソース追加では壊れず、CC ジャンルが
    1 本以下へ退行したときだけ落ちる＝退行検知の意図に一致する。
    """
    cc = [s for s in load_sources() if s.genre == "claude_code"]
    assert len(cc) >= 2, f"claude_code ソースが {len(cc)} 本（>=2 を期待）"
