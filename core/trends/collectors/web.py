"""Web/RSS trend collector.

Fetches public RSS/Atom feeds (and plain HTML pages) listed in
``config/trend_sources.yaml``, parses out entries with the stdlib XML parser
(no third-party feed lib), and turns each into a :class:`TrendItem`. Network
fetch is isolated in :func:`_fetch` so the pure parsers are unit-tested with
fixtures (no network in tests). HTTP fetching is not LLM generation, so it
respects the "generation only via claude CLI" rule.
"""

from __future__ import annotations

import html
import logging
import re
from dataclasses import dataclass
from typing import List, Optional
from xml.etree import ElementTree

from core.trends.models import TrendItem

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 15.0
MAX_ENTRIES_PER_SOURCE = 20
# 巨大/無限レスポンスでメモリを使い切らないための上限（フィードとしては十分大きい）。
MAX_FETCH_BYTES = 5 * 1024 * 1024
_TAG_RE = re.compile(r"<[^>]+>")


@dataclass
class TrendSource:
    name: str
    url: str
    type: str = "rss"  # "rss" | "atom"
    genre: str = ""


def _strip_tags(text: str) -> str:
    return html.unescape(_TAG_RE.sub("", text or "")).strip()


def _local(tag: str) -> str:
    """名前空間を除いたローカルタグ名（``{ns}entry`` → ``entry``）。"""
    return tag.rsplit("}", 1)[-1].lower()


def parse_feed(xml_text: str, source: TrendSource) -> List[TrendItem]:
    """RSS 2.0 / Atom の XML 文字列から TrendItem 群を抽出する（純関数）。"""
    if not xml_text or not xml_text.strip():
        return []
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError as exc:
        logger.debug("feed parse error for %s: %s", source.name, exc)
        return []

    items: List[TrendItem] = []
    for el in root.iter():
        if _local(el.tag) not in {"item", "entry"}:
            continue
        title = ""
        link = ""
        summary = ""
        for child in el:
            name = _local(child.tag)
            if name == "title" and child.text:
                title = _strip_tags(child.text)
            elif name == "link":
                # RSS: <link>text</link> / Atom: <link href="..."/>
                href = child.attrib.get("href")
                link = href or (child.text or "").strip()
            elif name in {"description", "summary", "content"} and (child.text or ""):
                if not summary:
                    summary = _strip_tags(child.text)
        if not (title or link):
            continue
        items.append(
            TrendItem(
                source="web",
                url=link,
                title=title or link,
                summary=summary[:1000],
                genre=source.genre,
                raw_excerpt=summary[:2000],
            ).ensure_hash()
        )
        if len(items) >= MAX_ENTRIES_PER_SOURCE:
            break
    return items


def _fetch(url: str, *, timeout: float = DEFAULT_TIMEOUT) -> Optional[str]:
    """公開 URL を取得して本文文字列を返す（失敗時 None）。ネットワーク境界。

    レスポンスは :data:`MAX_FETCH_BYTES` までしか読まない（リダイレクト先が
    悪意ある巨大/無限ストリームでもメモリを使い切らないため）。
    """
    try:
        import httpx

        headers = {
            "User-Agent": "Pantheon-TrendCollector/1.0 (+https://github.com/nel-neru/pantheon)"
        }
        with httpx.stream(
            "GET", url, timeout=timeout, follow_redirects=True, headers=headers
        ) as resp:
            resp.raise_for_status()
            chunks: list[bytes] = []
            total = 0
            for chunk in resp.iter_bytes():
                total += len(chunk)
                if total > MAX_FETCH_BYTES:
                    logger.info("trend fetch aborted (>%d bytes): %s", MAX_FETCH_BYTES, url)
                    return None
                chunks.append(chunk)
            return b"".join(chunks).decode(resp.encoding or "utf-8", "replace")
    except Exception as exc:  # noqa: BLE001
        logger.info("trend fetch failed for %s: %s", url, exc)
        return None


def collect_source(source: TrendSource, *, fetch=None) -> List[TrendItem]:
    """1 ソースを取得・解析して TrendItem 群を返す（fetch は注入可能でテスト容易）。

    ``fetch`` 省略時はモジュールの ``_fetch`` を呼び出し時に解決する
    （default 引数で束縛しないため、monkeypatch やテスト注入が効く）。
    """
    fetch = fetch or _fetch
    xml_text = fetch(source.url)
    if not xml_text:
        return []
    return parse_feed(xml_text, source)


def collect_web(sources: List[TrendSource], *, fetch=None) -> List[TrendItem]:
    """全ソースを横断収集する（採点・保存は呼び出し側）。"""
    collected: List[TrendItem] = []
    for source in sources:
        try:
            collected.extend(collect_source(source, fetch=fetch))
        except Exception as exc:  # noqa: BLE001
            logger.info("collect_source failed for %s: %s", source.name, exc)
    return collected


def load_sources(path=None) -> List[TrendSource]:
    """``config/trend_sources.yaml`` からソース定義を読み込む（欠落時は空）。"""
    if path is None:
        from core.paths import resource_path

        path = resource_path("config", "trend_sources.yaml")
    try:
        import yaml

        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001
        logger.debug("trend_sources.yaml unavailable (%s)", exc)
        return []
    raw = data.get("sources", []) if isinstance(data, dict) else []
    sources: List[TrendSource] = []
    for entry in raw:
        if not isinstance(entry, dict) or not entry.get("url"):
            continue
        sources.append(
            TrendSource(
                name=str(entry.get("name", entry["url"])),
                url=str(entry["url"]),
                type=str(entry.get("type", "rss")),
                genre=str(entry.get("genre", "")),
            )
        )
    return sources
