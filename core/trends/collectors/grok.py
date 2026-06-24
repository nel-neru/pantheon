"""Grok ブラウザ自動操作トレンド collector — grok.com を Playwright で駆動する。

RSS/YouTube collector が HTTP でフィードを取得するのと違い、本 collector は一度きりの
人間ログイン（``core/trends/grok_connect.py`` が Playwright の storage_state として保存）を
再利用して grok.com の Web UI を駆動する: 「X(旧Twitter)投稿・GitHub・YouTube・Web を横断して
最新トレンドを厳密 JSON 配列で返せ」というリサーチ用プロンプトを投入し、ストリーミング応答の
完了を待ち、JSON を ``TrendItem`` に解析する。

engineering-integrity（正直さ）: 下の DOM セレクタは実機 discovery で確定すべき隔離定数で、
セレクタが見つからない・応答が妥当な JSON でない・保存セッションが失効した場合は **``[]`` を返し
（捏造したアイテムは絶対に作らない）**、``needs_reconnect`` を立てて呼び出し側が正直に提示できる
ようにする。ブラウザスクレイピングは LLM generation ではないので「生成は claude CLI のみ」規約に
抵触しない（収集後の採点は従来どおり ``score_all`` ＝ claude CLI が担う）。
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, List, Optional, Protocol, Tuple

from core.trends.models import TrendItem

logger = logging.getLogger(__name__)

GROK_PLATFORM = "grok"  # SessionStore のキー（grok_connect.py がこれを import する）
GROK_URL = "https://grok.com/"
MAX_ITEMS_PER_QUERY = 20
DEFAULT_RESPONSE_TIMEOUT_S = 180.0

# --- DOM セレクタ（2026-06 実機 discovery で確定。複数候補をフォールバック順に並べる）---
# grok.com の入力欄は TipTap/ProseMirror の contenteditable（aria-label="Ask Grok anything"）。
# 送信は data-testid="chat-submit"（入力があると有効化される）。壊れても例外でなく [] で落とす。
COMPOSER_SELECTORS: Tuple[str, ...] = (
    '[aria-label="Ask Grok anything"]',
    "div.ProseMirror[contenteditable='true']",
    "[contenteditable='true']",
    "[role='textbox']",
    "textarea",
)
SEND_SELECTORS: Tuple[str, ...] = (
    '[data-testid="chat-submit"]',
    "button[type='submit']",
)
# 応答コンテナ。ユーザー/アシスタント双方が .message-bubble。最後の bubble が最新応答
# （アシスタントが最後に話すため）。STOP は生成中インジケータ（完了検知の最確指標）。
RESPONSE_SELECTORS: Tuple[str, ...] = (
    ".response-content-markdown",
    ".message-bubble",
    "[class*='message-bubble']",
)
STOP_STREAMING_SELECTORS: Tuple[str, ...] = (
    '[data-testid="chat-stop"]',
    "button[aria-label*='Stop' i]",
    "button[aria-label*='停止']",
)


@dataclass
class GrokQuery:
    name: str
    query: str
    genre: str = ""
    lookback_days: int = 7
    topics: List[str] = field(default_factory=list)


PROMPT_TEMPLATE = (
    "あなたはトレンドリサーチャーです。次のテーマについて、直近{lookback_days}日間で"
    "X(旧Twitter)の投稿・GitHub・YouTube・Webニュース/ブログを横断し、いま注目されている"
    "トレンドを最大{limit}件、新しさと話題性の高い順に挙げてください。\n\n"
    "テーマ: {query}\n"
    "{topics_hint}\n"
    "出力は厳密なJSON配列のみで、各要素は次のキーを持つこと:\n"
    '  - "title": 見出し（日本語可・80字以内）\n'
    '  - "summary": 1〜2文の要約\n'
    '  - "url": 一次情報のURL（無ければ空文字）\n'
    '  - "genre": "{genre}"\n'
    '  - "topics": 関連キーワードの配列（無ければ空配列）\n\n'
    "JSON配列以外（前置き・後置き・説明文）は一切出力しないこと。"
)


def build_prompt(q: GrokQuery) -> str:
    """GrokQuery から Grok へ投入するプロンプトを組み立てる（純関数）。"""
    topics_hint = ""
    if q.topics:
        topics_hint = "関連キーワードの例: " + ", ".join(q.topics) + "\n"
    return PROMPT_TEMPLATE.format(
        lookback_days=max(1, int(q.lookback_days or 7)),
        limit=MAX_ITEMS_PER_QUERY,
        query=q.query.strip(),
        genre=q.genre or "",
        topics_hint=topics_hint,
    )


_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def _first_balanced_array(text: str) -> str:
    """text 中の最初のトップレベル JSON 配列 ``[...]`` を括弧の対応で切り出す（純関数）。

    ``find('[')`` + ``rfind(']')`` だと「散文に2つの配列が混在」や末尾の余計な ``]`` で
    不正スライスになり両方落とすため、深さを数えて最初の閉じ配列までを返す。文字列リテラル内の
    ``[`` / ``]`` は深さに数えない（値に括弧を含む URL/タイトルで誤検知しないため）。
    """
    start = text.find("[")
    if start == -1:
        return ""
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return ""  # 閉じない＝壊れた応答 → 呼び出し側で [] に落ちる（捏造しない）


def _extract_json_array(text: str) -> str:
    """応答テキストから JSON 配列部分を取り出す（```json フェンス除去 → 最初の閉じ配列）。"""
    if not text:
        return ""
    m = _JSON_FENCE_RE.search(text)
    candidate = m.group(1).strip() if m else text
    return _first_balanced_array(candidate)


def parse_grok_response(text: str, q: GrokQuery) -> List[TrendItem]:
    """Grok 応答テキストから TrendItem 群を抽出する（純関数）。

    厳密 JSON 配列・```json フェンス付き・前後に散文がある配列のいずれも受ける。
    JSON として解釈できない/配列でない場合は [] を返す（捏造しない）。
    """
    raw = _extract_json_array(text)
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    items: List[TrendItem] = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        title = str(entry.get("title") or "").strip()
        url = str(entry.get("url") or "").strip()
        if not (title or url):
            continue
        summary = str(entry.get("summary") or "").strip()
        raw_topics = entry.get("topics")
        topics = (
            [str(t).strip() for t in raw_topics if str(t).strip()]
            if isinstance(raw_topics, (list, tuple))
            else []
        )
        genre = str(entry.get("genre") or q.genre or "").strip()
        items.append(
            TrendItem(
                source="grok",
                url=url,
                title=title or url,
                summary=summary[:1000],
                topics=topics,
                genre=genre,
                raw_excerpt=summary[:2000],
            ).ensure_hash()
        )
        if len(items) >= MAX_ITEMS_PER_QUERY:
            break
    return items


class GrokDriver(Protocol):
    """Grok 駆動の注入境界。テストはフェイクを渡して実ブラウザ無しで論理を検証する。"""

    async def run_query(self, prompt: str) -> str: ...

    async def is_session_valid(self) -> bool: ...


async def _find_visible(page: Any, selectors: Tuple[str, ...]) -> Any:
    """selectors を順に試し、最初に見つかった（可視）要素ハンドルを返す（無ければ None）。"""
    for sel in selectors:
        try:
            handle = await page.query_selector(sel)
        except Exception:  # noqa: BLE001 — セレクタ不正/コンテキスト消滅は次候補へ
            continue
        if handle is None:
            continue
        try:
            if await handle.is_visible():
                return handle
        except Exception:  # noqa: BLE001 — 可視判定不可でも要素はあるので採用
            return handle
    return None


class PlaywrightGrokDriver:
    """保存済みセッションで grok.com を駆動する実 driver（Playwright async_api）。

    ``PlaywrightLauncher(storage_state=...)`` を流用して context を再オープンし、コンポーザに
    プロンプトを入力→送信→応答完了を検知→最新応答テキストを返す。セレクタは上の隔離定数を使う。
    実ブラウザを起動するためテストでは使わない（テストはフェイク ``GrokDriver``）。
    """

    def __init__(
        self,
        *,
        state_path: str,
        launcher: Any = None,
        response_timeout_s: float = DEFAULT_RESPONSE_TIMEOUT_S,
        poll_interval_s: float = 1.0,
    ) -> None:
        self._state_path = state_path
        self._launcher = launcher
        self._response_timeout_s = response_timeout_s
        self._poll_interval_s = poll_interval_s
        self._context: Any = None
        self._page: Any = None

    async def _ensure_page(self) -> Any:
        if self._page is not None:
            return self._page
        if self._launcher is None:
            from core.publishing.connect import PlaywrightLauncher

            self._launcher = PlaywrightLauncher(storage_state=self._state_path)
        self._context = await self._launcher.launch()
        self._page = await self._context.new_page()
        await self._page.goto(GROK_URL)
        return self._page

    async def is_session_valid(self) -> bool:
        """grok.com でコンポーザ入力欄が見えるか（＝ログイン済みか）を判定する。"""
        page = await self._ensure_page()
        return (await _find_visible(page, COMPOSER_SELECTORS)) is not None

    async def run_query(self, prompt: str) -> str:
        page = await self._ensure_page()
        composer = await _find_visible(page, COMPOSER_SELECTORS)
        if composer is None:
            logger.info("grok composer not found (session expired or UI changed)")
            return ""
        try:
            await composer.click()
            # 入力欄は ProseMirror(contenteditable) で fill が効かないことがあるため、実キー入力で
            # 挿入する（送信ボタンの有効化トリガにもなる）。
            await page.keyboard.insert_text(prompt)
        except Exception as exc:  # noqa: BLE001
            logger.info("grok composer input failed: %s", exc)
            return ""
        # 送信ボタン(chat-submit)は入力があると有効化される。click は actionable まで自動待機する。
        send = await _find_visible(page, SEND_SELECTORS)
        try:
            if send is not None:
                await send.click()
            else:
                await page.keyboard.press("Enter")
        except Exception as exc:  # noqa: BLE001
            logger.info("grok send failed: %s", exc)
            return ""
        await self._wait_for_response_complete(page)
        return await self._latest_response_text(page)

    async def _wait_for_response_complete(self, page: Any) -> None:
        """応答完了を頑健に検知する（停止ボタンの消滅 → テキスト安定化 → ハード上限）。"""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._response_timeout_s
        # ① 停止ボタン（生成中インジケータ）の出現→消滅を待つ＝最確の完了指標。
        if (await _find_visible(page, STOP_STREAMING_SELECTORS)) is not None:
            while loop.time() < deadline:
                if (await _find_visible(page, STOP_STREAMING_SELECTORS)) is None:
                    return
                await asyncio.sleep(self._poll_interval_s)
            return
        # ② 停止ボタンが discovery できない場合の保険＝最新応答テキストの安定化。
        last = ""
        stable = 0
        while loop.time() < deadline:
            text = await self._latest_response_text(page)
            if text and text == last:
                stable += 1
                if stable >= 3:
                    return
            else:
                stable = 0
                last = text
            await asyncio.sleep(self._poll_interval_s)
        # ③ ハード上限超過: 現時点テキストで返す（配列が閉じていればパース成立しうる）。

    async def _latest_response_text(self, page: Any) -> str:
        for sel in RESPONSE_SELECTORS:
            try:
                nodes = await page.query_selector_all(sel)
            except Exception:  # noqa: BLE001
                continue
            if nodes:
                try:
                    return (await nodes[-1].inner_text()).strip()
                except Exception:  # noqa: BLE001
                    continue
        return ""

    async def close(self) -> None:
        if self._launcher is not None:
            try:
                await self._launcher.close()
            except Exception:  # noqa: BLE001 — close 失敗で結果を壊さない
                pass


async def collect_grok(
    queries: List[GrokQuery],
    *,
    driver: Optional[GrokDriver] = None,
    session_store: Any = None,
    grok_query: Optional[str] = None,
) -> Tuple[List[TrendItem], bool]:
    """Grok を駆動して全クエリのトレンドを収集する。

    戻り値 ``(items, needs_reconnect)``。``grok_query`` を渡すと config を無視しその 1 クエリだけ
    実行する（タスク次第のアドホック）。``driver`` 省略時は保存済みセッション＋Playwright を使い、
    未接続なら ``([], True)``、Playwright 未導入なら ``([], False)`` を正直に返す。各クエリは独立
    try で 1 件失敗が他を巻き込まない。応答が JSON でない/失効時は捏造せず ``[]`` に集約する。
    """
    if grok_query:
        queries = [GrokQuery(name="adhoc", query=grok_query)]
    if not queries:
        return [], False

    own_driver = driver is None
    if own_driver:
        from core.publishing.base import playwright_available
        from core.publishing.session import SessionStore

        store = session_store or SessionStore()
        if not store.is_connected(GROK_PLATFORM):
            logger.info("grok not connected; skip collection (needs_reconnect)")
            return [], True
        if not playwright_available():
            logger.info("playwright unavailable; skip grok collection")
            return [], False
        driver = PlaywrightGrokDriver(state_path=str(store.state_path(GROK_PLATFORM)))

    items: List[TrendItem] = []
    needs_reconnect = False
    try:
        try:
            if not await driver.is_session_valid():
                return [], True
        except Exception as exc:  # noqa: BLE001
            logger.info("grok session check failed: %s", exc)
            return [], True
        for q in queries:
            try:
                text = await driver.run_query(build_prompt(q))
                parsed = parse_grok_response(text, q)
                if not parsed and not text:
                    # 空応答＝コンポーザ未検出/失効の疑い（JSON で返らなかっただけなら text は非空）。
                    needs_reconnect = True
                items.extend(parsed)
            except Exception as exc:  # noqa: BLE001
                logger.info("grok query '%s' failed: %s", q.name, exc)
    finally:
        if own_driver:
            close = getattr(driver, "close", None)
            if close is not None:
                try:
                    await close()
                except Exception:  # noqa: BLE001
                    pass
    return items, needs_reconnect


def load_grok_queries(path: Any = None) -> Tuple[List[GrokQuery], bool]:
    """``config/trend_sources.yaml`` の ``grok_research`` を読む。戻り値 ``(queries, enabled)``。

    ``enabled`` が False/欠落、または ``queries`` が無ければ ``([], enabled)`` を返す。
    """
    if path is None:
        from core.paths import resource_path

        path = resource_path("config", "trend_sources.yaml")
    try:
        import yaml

        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001
        logger.debug("trend_sources.yaml unavailable (%s)", exc)
        return [], False
    section = data.get("grok_research", {}) if isinstance(data, dict) else {}
    if not isinstance(section, dict):
        return [], False
    enabled = bool(section.get("enabled", False))
    raw = section.get("queries", [])
    queries: List[GrokQuery] = []
    if isinstance(raw, list):
        for entry in raw:
            if not isinstance(entry, dict) or not entry.get("query"):
                continue
            raw_topics = entry.get("topics")
            topics = (
                [str(t) for t in raw_topics if str(t).strip()]
                if isinstance(raw_topics, (list, tuple))
                else []
            )
            queries.append(
                GrokQuery(
                    name=str(entry.get("name", entry["query"])),
                    query=str(entry["query"]),
                    genre=str(entry.get("genre", "")),
                    lookback_days=int(entry.get("lookback_days", 7) or 7),
                    topics=topics,
                )
            )
    return queries, enabled
