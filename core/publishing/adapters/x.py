"""X (Twitter) 投稿アダプタ。

無料での投稿はブラウザ自動操作が現実的（X API は有料枠）。Phase 1 は assisted:
**web intent URL**（``x.com/intent/post?text=…``）でコンポーズ画面に本文をプリフィルし、
最終送信は人間が行う。intent は X が公開している共有用エンドポイントのため、
contenteditable へのセレクタ fill より UI 変更に強い。

280字を超える本文のスレッド自動分割と auto（完全自動送信）は Phase 2。
"""

from __future__ import annotations

from typing import Any, Callable, Optional
from urllib.parse import quote

from core.publishing.adapters.base import BrowserPublisher
from core.publishing.adapters.handoff import keep_alive, prune_handoff_keepalive
from core.publishing.base import (
    PLATFORM_X,
    PUBLISH_MODE_AUTO,
    PublishContent,
    PublishResult,
    PublishTarget,
)
from core.publishing.connect import PlaywrightLauncher
from core.publishing.session import SessionStore

# X の共有用 web intent（公開エンドポイント。ログイン済みならコンポーズ画面に直行する）。
X_COMPOSE_INTENT_URL = "https://x.com/intent/post"
# 無料アカウントの 1 ポスト上限。判定は len()（code point 数）の粗い近似で、
# X 実機の weighted 算定（URL=23 字換算・CJK/絵文字=2 重み）とはずれる。
# 正確なゲートではなく「人間がコンポーズ画面で確認する前提の警告」専用（分割は Phase 2）。
X_POST_CHAR_LIMIT = 280


class XPublisher(BrowserPublisher):
    platform = PLATFORM_X

    def __init__(
        self,
        session_store: Optional[SessionStore] = None,
        launcher_factory: Optional[Callable[[], Any]] = None,
    ) -> None:
        self._session_store = session_store
        self._launcher_factory = launcher_factory

    async def _publish_live(self, content: PublishContent, target: PublishTarget) -> PublishResult:
        if target.mode == PUBLISH_MODE_AUTO:
            return PublishResult(
                ok=False,
                platform=self.platform,
                mode=target.mode,
                error="X の auto（完全自動送信）は未実装です（Phase 2）。mode=assisted を使ってください",
            )

        store = self._session_store or SessionStore()
        if not store.is_connected(self.platform):
            return PublishResult(
                ok=False,
                platform=self.platform,
                mode=target.mode,
                error="X が未接続です。`pantheon publish connect x` で一度ログインしてください",
            )

        # X は単文投稿が基本のため body を本文とし、無ければ title を使う。
        text = (content.body or content.title or "").strip()
        if not text:
            return PublishResult(
                ok=False,
                platform=self.platform,
                mode=target.mode,
                error="投稿本文が空です（body も title もありません）",
            )

        state_path = str(store.state_path(self.platform))
        factory = self._launcher_factory or (lambda: PlaywrightLauncher(storage_state=state_path))
        await prune_handoff_keepalive()
        launcher = factory()
        try:
            context = await launcher.launch()
            page = await context.new_page()
            await page.goto(f"{X_COMPOSE_INTENT_URL}?text={quote(text)}")
        except Exception as exc:  # noqa: BLE001 — 起動/遷移失敗は閉じて正直に返す
            try:
                await launcher.close()
            except Exception:  # noqa: BLE001
                pass
            return PublishResult(
                ok=False,
                platform=self.platform,
                mode=target.mode,
                error=(
                    f"X コンポーズ画面の起動に失敗しました: {type(exc).__name__}: {exc}"
                    "（セッション期限切れなら `pantheon publish connect x` で再接続）"
                ),
            )

        detail = "コンポーズ画面に本文を流し込みました。開いたブラウザで内容を確認のうえ、ポストしてください"
        if len(text) > X_POST_CHAR_LIMIT:
            detail += (
                f"（本文が {len(text)} 字で {X_POST_CHAR_LIMIT} 字を超えています — "
                "投稿前に編集するかスレッド化してください。自動分割は Phase 2）"
            )

        # assisted の契約どおり、最終送信は人間 — ブラウザは開いたままハンドオフする。
        keep_alive(launcher)
        return PublishResult(
            ok=True,
            platform=self.platform,
            mode=target.mode,
            handed_off=True,
            detail=detail,
        )
