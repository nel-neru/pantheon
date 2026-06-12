"""note.com 投稿アダプタ。

note は公式の投稿 API が無いため **ブラウザ自動操作（Playwright）が前提**。Phase 1 では
「エディタを開いてタイトル/本文を流し込み、最終公開は人間（assisted）」を実装済み。
Phase 2 で予約公開の完全自動化（auto）を実装する。

assisted の契約（``base.py`` の PUBLISH_MODE_ASSISTED コメントと同じ）: 投稿画面まで
自動で開き本文を流し込むが、**最終送信は人間**。そのため成功時はブラウザを開いたまま
ハンドオフし、結果は ``handed_off=True``（published とは区別、成果指標に数えない）。

セレクタ/エディタ URL は note 側の変更で壊れうるためモジュール定数に隔離している。
実サイトでの動作検証はユーザー同席時の E2E で行う（CI では検証不能 — フェイク注入で
フロー論理のみ検証）。
"""

from __future__ import annotations

from typing import Any, Callable, List, Optional

from core.publishing.adapters.base import BrowserPublisher
from core.publishing.base import (
    PLATFORM_NOTE,
    PUBLISH_MODE_AUTO,
    PublishContent,
    PublishResult,
    PublishTarget,
)
from core.publishing.connect import PlaywrightLauncher
from core.publishing.session import SessionStore

# ---- 実サイト依存の定数（note 側の UI 変更時はここだけ直す。実機検証待ち） ----
NOTE_EDITOR_URL = "https://editor.note.com/new"
NOTE_TITLE_SELECTOR = 'textarea[placeholder="記事タイトル"]'
NOTE_BODY_SELECTOR = 'div[contenteditable="true"]'
EDITOR_READY_TIMEOUT_MS = 30_000

# assisted ハンドオフ中のブラウザを生かしておくための参照（GC で閉じない）。
# 人間がウィンドウを閉じるまで開いたままになる（Phase 1 の意図的な挙動）。
_HANDOFF_KEEPALIVE: List[Any] = []


class NotePublisher(BrowserPublisher):
    platform = PLATFORM_NOTE

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
                error="note の auto（完全自動公開）は未実装です（Phase 2）。mode=assisted を使ってください",
            )

        store = self._session_store or SessionStore()
        if not store.is_connected(self.platform):
            return PublishResult(
                ok=False,
                platform=self.platform,
                mode=target.mode,
                error="note が未接続です。`pantheon publish connect note` で一度ログインしてください",
            )

        state_path = str(store.state_path(self.platform))
        factory = self._launcher_factory or (lambda: PlaywrightLauncher(storage_state=state_path))
        launcher = factory()
        try:
            context = await launcher.launch()
            page = await context.new_page()
            await page.goto(NOTE_EDITOR_URL)
            await page.wait_for_selector(NOTE_TITLE_SELECTOR, timeout=EDITOR_READY_TIMEOUT_MS)
            await page.fill(NOTE_TITLE_SELECTOR, content.title)
            await page.fill(NOTE_BODY_SELECTOR, content.body)
        except Exception as exc:  # noqa: BLE001 — 流し込み失敗は閉じて正直に返す
            try:
                await launcher.close()
            except Exception:  # noqa: BLE001
                pass
            return PublishResult(
                ok=False,
                platform=self.platform,
                mode=target.mode,
                error=(
                    f"note エディタへの流し込みに失敗しました: {type(exc).__name__}: {exc}"
                    "（セッション期限切れなら `pantheon publish connect note` で再接続）"
                ),
            )

        # assisted の契約どおり、最終公開は人間 — ブラウザは開いたままハンドオフする。
        _HANDOFF_KEEPALIVE.append(launcher)
        return PublishResult(
            ok=True,
            platform=self.platform,
            mode=target.mode,
            handed_off=True,
            detail="エディタに下書きを流し込みました。開いたブラウザで内容を確認のうえ、公開してください",
        )
