"""Grok ブラウザ自動操作 collector のテスト — 実ブラウザ・実 claude CLI は起動しない。

conftest が ``PANTHEON_NO_CLAUDE=1``（採点はヒューリスティック）と ``PANTHEON_NO_BROWSER=1``
を張るため、純パーサ・フェイク driver・フェイク launcher 注入でフロー論理だけを検証する。
engineering-integrity の要: 壊れた応答/未接続/失効で **捏造せず [] ＋ needs_reconnect** を返すこと。
"""

from __future__ import annotations

from pathlib import Path

from core.publishing.session import SessionStore
from core.trends.collectors.grok import (
    COMPOSER_SELECTORS,
    GROK_URL,
    GrokQuery,
    build_prompt,
    collect_grok,
    load_grok_queries,
    parse_grok_response,
)
from core.trends.grok_connect import connect_grok
from core.trends.runner import collect_and_store

Q = GrokQuery(name="t", query="AI trends", genre="ai", lookback_days=5, topics=["llm"])


# --------------------------------------------------------------------------- #
# parse_grok_response — 厳密JSON / フェンス / 散文混在 / 壊れたJSON / 空 → [] 捏造禁止
# --------------------------------------------------------------------------- #
def test_parse_strict_json_array():
    text = '[{"title":"X ships agents","url":"https://e.com/a","summary":"s","topics":["a"]}]'
    items = parse_grok_response(text, Q)
    assert len(items) == 1
    assert items[0].source == "grok"
    assert items[0].genre == "ai"  # entry に genre 無し → Q.genre へフォールバック
    assert items[0].topics == ["a"]
    assert items[0].hash  # ensure_hash 適用済み


def test_parse_json_fence():
    text = '前置き\n```json\n[{"title":"t","url":"https://e.com/x"}]\n```\nおわり'
    items = parse_grok_response(text, Q)
    assert len(items) == 1
    assert items[0].title == "t"


def test_parse_prose_wrapped_array():
    text = 'こちらが結果です: [{"title":"t2","url":"https://e.com/y"}] 以上。'
    items = parse_grok_response(text, Q)
    assert len(items) == 1
    assert items[0].title == "t2"


def test_parse_broken_json_returns_empty():
    assert parse_grok_response("[{title: not valid json", Q) == []
    assert parse_grok_response("ただの文章でJSONなし", Q) == []


def test_parse_empty_returns_empty():
    assert parse_grok_response("", Q) == []
    assert parse_grok_response("   ", Q) == []


def test_parse_non_list_json_returns_empty():
    # 配列でない JSON オブジェクトは捏造せず []
    assert parse_grok_response('{"title":"t","url":"https://e.com/z"}', Q) == []


def test_parse_skips_entries_without_title_or_url():
    text = '[{"summary":"no title no url"},{"title":"ok","url":"https://e.com/ok"}]'
    items = parse_grok_response(text, Q)
    assert len(items) == 1
    assert items[0].title == "ok"


def test_parse_two_arrays_in_prose_takes_first_balanced():
    # 散文に2つの配列が混在しても、最初の閉じ配列を取り出す（find/rfind だと両方落ちる）。
    text = (
        'まず [{"title":"a","url":"https://e.com/a"}] 次に [{"title":"b","url":"https://e.com/b"}]'
    )
    items = parse_grok_response(text, Q)
    assert len(items) == 1
    assert items[0].title == "a"


def test_parse_handles_brackets_inside_string_values():
    # 値に ] を含んでも括弧の対応を文字列対応で正しく数える（早期クローズしない）。
    text = '[{"title":"arr[0] guide","url":"https://e.com/c","topics":["x","y"]}]'
    items = parse_grok_response(text, Q)
    assert len(items) == 1
    assert items[0].title == "arr[0] guide"
    assert items[0].topics == ["x", "y"]


# --------------------------------------------------------------------------- #
# build_prompt — lookback / query / genre / topics がプロンプトに入る（純検証）
# --------------------------------------------------------------------------- #
def test_build_prompt_includes_fields():
    p = build_prompt(Q)
    assert "直近5日" in p
    assert "AI trends" in p
    assert '"genre": "ai"' in p
    assert "llm" in p  # topics ヒント


# --------------------------------------------------------------------------- #
# load_grok_queries — section 読み込み / enabled / 欠落時の正直な ([], False)
# --------------------------------------------------------------------------- #
def test_load_grok_queries_reads_section(tmp_path):
    p = tmp_path / "trend_sources.yaml"
    p.write_text(
        "grok_research:\n"
        "  enabled: true\n"
        "  queries:\n"
        "    - {name: q1, query: 'topic one', genre: ai, lookback_days: 3, topics: [a, b]}\n",
        encoding="utf-8",
    )
    queries, enabled = load_grok_queries(p)
    assert enabled is True
    assert len(queries) == 1
    assert queries[0].query == "topic one"
    assert queries[0].lookback_days == 3
    assert queries[0].topics == ["a", "b"]


def test_load_grok_queries_missing_section(tmp_path):
    p = tmp_path / "empty.yaml"
    p.write_text("sources: []\n", encoding="utf-8")
    queries, enabled = load_grok_queries(p)
    assert queries == []
    assert enabled is False


def test_bundled_config_grok_section_parses():
    # 同梱 config/trend_sources.yaml の grok_research が妥当な YAML で読めること（既定オフ）。
    queries, enabled = load_grok_queries()
    assert enabled is False
    assert len(queries) >= 1


# --------------------------------------------------------------------------- #
# collect_grok — フェイク driver 注入（実ブラウザ無し）。失効/未接続/空応答の正直なシグナル
# --------------------------------------------------------------------------- #
class _FakeDriver:
    def __init__(self, *, response: str = "", valid: bool = True):
        self._response = response
        self._valid = valid
        self.prompts: list[str] = []

    async def is_session_valid(self) -> bool:
        return self._valid

    async def run_query(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self._response


async def test_collect_grok_with_fake_driver():
    drv = _FakeDriver(response='[{"title":"t","url":"https://e.com/z"}]')
    items, reconnect = await collect_grok([Q], driver=drv)
    assert reconnect is False
    assert len(items) == 1
    assert items[0].source == "grok"
    assert drv.prompts  # run_query が呼ばれた


async def test_collect_grok_session_invalid_signals_reconnect():
    drv = _FakeDriver(valid=False)
    items, reconnect = await collect_grok([Q], driver=drv)
    assert items == []
    assert reconnect is True


async def test_collect_grok_empty_response_flags_reconnect():
    drv = _FakeDriver(response="")  # 空応答=コンポーザ未検出/失効の疑い
    items, reconnect = await collect_grok([Q], driver=drv)
    assert items == []
    assert reconnect is True


async def test_collect_grok_non_json_response_no_reconnect():
    # JSON で返らなかっただけ（応答自体はある）→ [] だが reconnect ではない（品質問題）。
    drv = _FakeDriver(response="今週のトレンドは色々あります（JSONではない散文）")
    items, reconnect = await collect_grok([Q], driver=drv)
    assert items == []
    assert reconnect is False


async def test_collect_grok_adhoc_query_overrides_config():
    drv = _FakeDriver(response='[{"title":"t","url":"https://e.com/q"}]')
    items, reconnect = await collect_grok([Q], driver=drv, grok_query="特定トピックX")
    assert len(items) == 1
    assert any("特定トピックX" in p for p in drv.prompts)


async def test_collect_grok_not_connected_signals_reconnect(tmp_path):
    # driver 省略 + 未接続 → ([], True)（Playwright を触らず正直に reconnect）。
    store = SessionStore(platform_home=tmp_path)
    items, reconnect = await collect_grok([Q], session_store=store)
    assert items == []
    assert reconnect is True


async def test_collect_grok_no_browser_skips_quietly(tmp_path):
    # 接続済みに見せかける + PANTHEON_NO_BROWSER（conftest 既定）→ ([], False)。未導入は reconnect でない。
    store = SessionStore(platform_home=tmp_path)
    store.ensure_dir("grok")
    store.state_path("grok").write_text("{}", encoding="utf-8")
    items, reconnect = await collect_grok([Q], session_store=store)
    assert items == []
    assert reconnect is False


# --------------------------------------------------------------------------- #
# connect_grok — フェイク launcher 注入（interactive_login の述語経路）
# --------------------------------------------------------------------------- #
class _FakeHandle:
    def __init__(self, visible: bool = True):
        self._visible = visible

    async def is_visible(self) -> bool:
        return self._visible


class _FakeGrokPage:
    def __init__(self, *, composer: bool = True, guest: bool = False):
        self.url = "about:blank"
        self._composer = composer
        self._guest = guest  # サインイン/新規登録 導線がある＝未ログイン（ゲスト）
        self.goto_urls: list[str] = []

    async def goto(self, url: str) -> None:
        self.goto_urls.append(url)
        self.url = url

    async def query_selector(self, sel: str):
        if self._composer and sel in COMPOSER_SELECTORS:
            return _FakeHandle(True)
        return None

    async def evaluate(
        self, expr: str = "", arg=None
    ):  # _grok_logged_in の guest 判定をエミュレート
        return self._guest


class _FakeGrokContext:
    def __init__(self, page: _FakeGrokPage):
        self._page = page
        self.saved_paths: list[str] = []

    async def new_page(self) -> _FakeGrokPage:
        return self._page

    async def storage_state(self, path: str):
        Path(path).write_text('{"cookies": [{"name": "stub"}]}', encoding="utf-8")
        self.saved_paths.append(str(path))
        return {}


class _FakeLauncher:
    def __init__(self, context):
        self._context = context
        self.closed = False

    async def launch(self):
        return self._context

    async def close(self) -> None:
        self.closed = True


async def test_connect_grok_detects_composer_and_saves_state(tmp_path):
    store = SessionStore(platform_home=tmp_path)
    page = _FakeGrokPage(composer=True)
    ctx = _FakeGrokContext(page)
    launcher = _FakeLauncher(ctx)

    result = await connect_grok(session_store=store, launcher=launcher, timeout_s=30)

    assert result.ok is True
    assert store.is_connected("grok") is True
    assert page.goto_urls == [GROK_URL]
    assert launcher.closed is True  # 成功してもブラウザは必ず後始末


async def test_connect_grok_times_out_when_not_logged_in(tmp_path):
    store = SessionStore(platform_home=tmp_path)
    page = _FakeGrokPage(composer=False)  # コンポーザ無し=未ログイン
    ctx = _FakeGrokContext(page)
    launcher = _FakeLauncher(ctx)

    result = await connect_grok(session_store=store, launcher=launcher, timeout_s=0)

    assert result.ok is False
    assert store.is_connected("grok") is False
    assert launcher.closed is True


async def test_connect_grok_rejects_guest_session(tmp_path):
    # grok.com はゲストでも入力欄を出す。サインイン/新規登録 導線が在る間は接続成功にしない
    # （composer の存在だけで保存する偽陽性を防ぐ・facade 化させない）。
    store = SessionStore(platform_home=tmp_path)
    page = _FakeGrokPage(composer=True, guest=True)  # 入力欄あり but ゲスト導線あり
    ctx = _FakeGrokContext(page)
    launcher = _FakeLauncher(ctx)

    result = await connect_grok(session_store=store, launcher=launcher, timeout_s=0)

    assert result.ok is False
    assert store.is_connected("grok") is False


# --------------------------------------------------------------------------- #
# runner — sources 未指定で従来挙動（grok=0）/ {"grok"} で grok 件数が混ざる（後方互換）
# --------------------------------------------------------------------------- #
async def test_runner_grok_off_by_default(tmp_path, monkeypatch):
    monkeypatch.setattr("core.trends.runner.load_sources", lambda path=None: [])
    monkeypatch.setattr("core.trends.runner.load_channels", lambda path=None: [])
    result = await collect_and_store(platform_home=tmp_path)
    assert result["grok"] == 0
    assert result["grok_needs_reconnect"] is False
    assert "web" in result and "youtube" in result


async def test_runner_includes_grok_when_selected(tmp_path, monkeypatch):
    from core.trends.models import TrendItem

    monkeypatch.setattr("core.trends.runner.load_sources", lambda path=None: [])
    monkeypatch.setattr("core.trends.runner.load_channels", lambda path=None: [])

    async def fake_collect_grok(queries, *, grok_query=None, **kw):
        return [TrendItem(source="grok", url="https://e.com/g", title="g").ensure_hash()], False

    monkeypatch.setattr("core.trends.collectors.grok.collect_grok", fake_collect_grok)
    monkeypatch.setattr(
        "core.trends.collectors.grok.load_grok_queries",
        lambda path=None: ([GrokQuery(name="x", query="y")], True),
    )

    result = await collect_and_store(platform_home=tmp_path, sources={"grok"})
    assert result["grok"] == 1
    assert result["grok_needs_reconnect"] is False
