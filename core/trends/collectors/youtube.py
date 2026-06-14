"""YouTube trend collector — channel RSS + best-effort captions, no API key.

YouTube exposes a per-channel Atom feed at
``https://www.youtube.com/feeds/videos.xml?channel_id=<ID>`` (recent uploads
with title, description, and view stats) that needs no API key. Captions are
fetched best-effort from the public ``timedtext`` endpoint and degrade to empty
when unavailable. HTTP fetch only — generation stays on the claude CLI.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import List
from xml.etree import ElementTree

from core.trends.collectors.web import MAX_ENTRIES_PER_SOURCE, _fetch, _local, _strip_tags
from core.trends.models import TrendItem

logger = logging.getLogger(__name__)

CHANNEL_FEED = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
TIMEDTEXT = "https://www.youtube.com/api/timedtext?lang={lang}&v={video_id}"
WATCH_URL = "https://www.youtube.com/watch?v={video_id}"


@dataclass
class YouTubeChannel:
    name: str
    channel_id: str
    genre: str = ""


def channel_feed_url(channel_id: str) -> str:
    return CHANNEL_FEED.format(channel_id=channel_id)


def parse_youtube_feed(xml_text: str, channel: YouTubeChannel) -> List[TrendItem]:
    """YouTube チャンネル Atom フィードから TrendItem 群を抽出する（純関数）。"""
    if not xml_text or not xml_text.strip():
        return []
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError as exc:
        logger.debug("youtube feed parse error for %s: %s", channel.name, exc)
        return []

    items: List[TrendItem] = []
    for el in root.iter():
        if _local(el.tag) != "entry":
            continue
        title = ""
        url = ""
        video_id = ""
        description = ""
        views = 0
        for node in el.iter():
            name = _local(node.tag)
            if name == "title" and node.text and not title:
                title = _strip_tags(node.text)
            elif name == "videoid" and node.text:
                video_id = node.text.strip()
            elif name == "link" and not url:
                url = node.attrib.get("href", "") or url
            elif name == "description" and node.text and not description:
                description = _strip_tags(node.text)
            elif name == "statistics":
                raw_views = node.attrib.get("views")
                if raw_views and raw_views.isdigit():
                    views = int(raw_views)
        if video_id and not url:
            url = WATCH_URL.format(video_id=video_id)
        if not (title or url):
            continue
        topics = [f"views:{views}"] if views else []
        items.append(
            TrendItem(
                source="youtube",
                url=url,
                title=title or url,
                summary=description[:1000],
                genre=channel.genre,
                topics=topics,
                raw_excerpt=description[:2000],
            ).ensure_hash()
        )
        if len(items) >= MAX_ENTRIES_PER_SOURCE:
            break
    return items


_TT_TEXT_RE = re.compile(r"<text[^>]*>(.*?)</text>", re.DOTALL)


def parse_timedtext(xml_text: str) -> str:
    """timedtext XML から字幕テキストを連結して返す（純関数、空なら ""）。"""
    if not xml_text or "<text" not in xml_text:
        return ""
    parts = [_strip_tags(m) for m in _TT_TEXT_RE.findall(xml_text)]
    return " ".join(p for p in parts if p).strip()


def _video_id_from_url(url: str) -> str:
    m = re.search(r"[?&]v=([\w-]+)", url or "")
    return m.group(1) if m else ""


def fetch_captions(video_id: str, *, lang: str = "en", fetch=None) -> str:
    """公開 timedtext から字幕を取得する（取得不可なら ""）。ベストエフォート。"""
    if not video_id:
        return ""
    fetch = fetch or _fetch
    xml_text = fetch(TIMEDTEXT.format(lang=lang, video_id=video_id))
    if not xml_text:
        return ""
    return parse_timedtext(xml_text)


def collect_youtube(
    channels: List[YouTubeChannel],
    *,
    fetch=None,
    with_captions: bool = False,
    caption_lang: str = "en",
) -> List[TrendItem]:
    """全チャンネルの最新動画を収集する。``with_captions`` で字幕を要約素材に足す。"""
    fetch = fetch or _fetch
    collected: List[TrendItem] = []
    for channel in channels:
        try:
            xml_text = fetch(channel_feed_url(channel.channel_id))
            if not xml_text:
                continue
            items = parse_youtube_feed(xml_text, channel)
            if with_captions:
                for item in items:
                    vid = _video_id_from_url(item.url)
                    captions = fetch_captions(vid, lang=caption_lang, fetch=fetch)
                    if captions:
                        # 字幕は要約・採点の素材として raw_excerpt に追記する。
                        item.raw_excerpt = (item.raw_excerpt + "\n\n" + captions)[:4000]
            collected.extend(items)
        except Exception as exc:  # noqa: BLE001
            logger.info("collect_youtube failed for %s: %s", channel.name, exc)
    return collected


def load_channels(path=None) -> List[YouTubeChannel]:
    """``config/trend_sources.yaml`` の ``youtube_channels`` を読み込む（欠落時は空）。"""
    if path is None:
        from core.paths import resource_path

        path = resource_path("config", "trend_sources.yaml")
    try:
        import yaml

        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001
        logger.debug("trend_sources.yaml unavailable (%s)", exc)
        return []
    raw = data.get("youtube_channels", []) if isinstance(data, dict) else []
    channels: List[YouTubeChannel] = []
    for entry in raw:
        if not isinstance(entry, dict) or not entry.get("channel_id"):
            continue
        channels.append(
            YouTubeChannel(
                name=str(entry.get("name", entry["channel_id"])),
                channel_id=str(entry["channel_id"]),
                genre=str(entry.get("genre", "")),
            )
        )
    return channels
