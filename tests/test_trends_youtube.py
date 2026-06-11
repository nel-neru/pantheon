"""Tests for the YouTube trend collector (core.trends.collectors.youtube)."""

from __future__ import annotations

from core.trends.collectors.youtube import (
    YouTubeChannel,
    channel_feed_url,
    collect_youtube,
    fetch_captions,
    parse_timedtext,
    parse_youtube_feed,
)

YT_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015"
      xmlns:media="http://search.yahoo.com/mrss/"
      xmlns="http://www.w3.org/2005/Atom">
  <title>Example Channel</title>
  <entry>
    <id>yt:video:ABC123</id>
    <yt:videoId>ABC123</yt:videoId>
    <title>How AI agents work</title>
    <link rel="alternate" href="https://www.youtube.com/watch?v=ABC123"/>
    <media:group>
      <media:title>How AI agents work</media:title>
      <media:description>Deep dive into agent loops and tools.</media:description>
      <media:community>
        <media:statistics views="123456"/>
      </media:community>
    </media:group>
  </entry>
  <entry>
    <id>yt:video:DEF456</id>
    <yt:videoId>DEF456</yt:videoId>
    <title>Second video</title>
    <link rel="alternate" href="https://www.youtube.com/watch?v=DEF456"/>
    <media:group>
      <media:description>Another topic.</media:description>
      <media:community><media:statistics views="42"/></media:community>
    </media:group>
  </entry>
</feed>
"""

TIMEDTEXT_XML = """<?xml version="1.0"?>
<transcript>
  <text start="0" dur="3">Hello and welcome</text>
  <text start="3" dur="2">to the &amp;quot;show&amp;quot;</text>
</transcript>
"""


def test_channel_feed_url():
    url = channel_feed_url("UC123")
    assert "channel_id=UC123" in url
    assert url.startswith("https://www.youtube.com/feeds/videos.xml")


def test_parse_youtube_feed():
    ch = YouTubeChannel(name="ex", channel_id="UC123", genre="ai")
    items = parse_youtube_feed(YT_FEED, ch)
    assert len(items) == 2
    first = items[0]
    assert first.source == "youtube"
    assert first.title == "How AI agents work"
    assert first.url == "https://www.youtube.com/watch?v=ABC123"
    assert "agent loops" in first.summary
    assert first.genre == "ai"
    assert "views:123456" in first.topics


def test_parse_youtube_feed_malformed():
    ch = YouTubeChannel(name="x", channel_id="UC")
    assert parse_youtube_feed("<broken", ch) == []
    assert parse_youtube_feed("", ch) == []


def test_parse_timedtext():
    text = parse_timedtext(TIMEDTEXT_XML)
    assert "Hello and welcome" in text
    assert "show" in text


def test_parse_timedtext_empty():
    assert parse_timedtext("") == ""
    assert parse_timedtext("<transcript></transcript>") == ""


def test_fetch_captions_best_effort():
    # 取得成功
    got = fetch_captions("ABC123", fetch=lambda url, **kw: TIMEDTEXT_XML)
    assert "Hello and welcome" in got
    # 取得失敗 → 空
    assert fetch_captions("ABC123", fetch=lambda url, **kw: None) == ""
    # video_id 無し → 空
    assert fetch_captions("", fetch=lambda url, **kw: TIMEDTEXT_XML) == ""


def test_collect_youtube_with_injected_fetch():
    channels = [YouTubeChannel(name="ex", channel_id="UC123", genre="ai")]
    items = collect_youtube(channels, fetch=lambda url, **kw: YT_FEED)
    assert len(items) == 2
    assert all(i.source == "youtube" for i in items)


def test_collect_youtube_with_captions():
    channels = [YouTubeChannel(name="ex", channel_id="UC123", genre="ai")]

    def fake_fetch(url, **kw):
        return TIMEDTEXT_XML if "timedtext" in url else YT_FEED

    items = collect_youtube(channels, fetch=fake_fetch, with_captions=True)
    assert len(items) == 2
    assert "Hello and welcome" in items[0].raw_excerpt


def test_collect_youtube_tolerates_failure():
    channels = [YouTubeChannel(name="dead", channel_id="UC")]
    assert collect_youtube(channels, fetch=lambda url, **kw: None) == []
