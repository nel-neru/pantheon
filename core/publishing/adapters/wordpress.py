"""アフィリエイト記事 CMS（WordPress 想定）投稿アダプタ。

WordPress は公式 REST API（Application Passwords）もあるが、Pantheon は資格情報を保存しない
方針（`session.py` 参照）のため、note / X と同じく **ブラウザ自動操作（Playwright）＋ assisted**
を Phase 1 の既定とする。一度ログインして作った storage_state を使って wp-admin の新規投稿
エディタを開き、タイトルを流し込んで（本文は block editor の構造差が大きいため best-effort）、
**最終公開は人間**に引き渡す（handed_off=True）。

note / X と違い WordPress サイト URL は利用者ごとに異なるため、投稿先サイトの base URL は
``PublishTarget.account`` で受け取る（例: ``https://example.com``）。エディタ URL は
``{account}/wp-admin/post-new.php``。REST API 連携と完全自動公開（auto）は Phase 2。

セレクタ/管理画面パスは WordPress 側の変更・ロケールで壊れうるためモジュール定数に隔離し、
本文流し込みは失敗しても editor を開いたままハンドオフする（実機検証待ち）。
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from core.publishing.adapters.base import EMPTY_CONTENT_ERROR, BrowserPublisher
from core.publishing.adapters.handoff import keep_alive, prune_handoff_keepalive
from core.publishing.base import (
    PLATFORM_WORDPRESS,
    PUBLISH_MODE_AUTO,
    PublishContent,
    PublishResult,
    PublishTarget,
)
from core.publishing.connect import PlaywrightLauncher
from core.publishing.session import SessionStore

# ---- 実サイト依存の定数（WordPress 側の UI 変更／ロケール時はここだけ直す。実機検証待ち） ----
WP_ADMIN_NEW_POST_PATH = "/wp-admin/post-new.php"
# Gutenberg のタイトル欄（classic/旧エディタの textarea も含めカンマ区切りで最初の一致を使う）。
WP_TITLE_SELECTOR = (
    "h1.wp-block-post-title, .editor-post-title__input, textarea.editor-post-title__input"
)
EDITOR_READY_TIMEOUT_MS = 30_000


class WordPressPublisher(BrowserPublisher):
    platform = PLATFORM_WORDPRESS

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
                error="WordPress の auto（完全自動公開）は未実装です（Phase 2）。mode=assisted を使ってください",
            )

        site = (target.account or "").strip().rstrip("/")
        if not site:
            return PublishResult(
                ok=False,
                platform=self.platform,
                mode=target.mode,
                error="WordPress サイトURLが未指定です（投稿先サイトの base URL を account に指定してください）",
            )

        store = self._session_store or SessionStore()
        if not store.is_connected(self.platform):
            return PublishResult(
                ok=False,
                platform=self.platform,
                mode=target.mode,
                error="WordPress が未接続です。`pantheon publish connect wordpress` で一度ログインしてください",
            )

        # 投稿前バリデーション: 空の下書きでブラウザを起動して空エディタをハンドオフしない
        # （X / note と同契約・preview≥live の honesty を一様化）。
        if self._is_empty_content(content):
            return PublishResult(
                ok=False,
                platform=self.platform,
                mode=target.mode,
                error=EMPTY_CONTENT_ERROR,
            )

        state_path = str(store.state_path(self.platform))
        factory = self._launcher_factory or (lambda: PlaywrightLauncher(storage_state=state_path))
        await prune_handoff_keepalive()
        launcher = factory()
        try:
            context = await launcher.launch()
            page = await context.new_page()
            await page.goto(f"{site}{WP_ADMIN_NEW_POST_PATH}")
            await page.wait_for_selector(WP_TITLE_SELECTOR, timeout=EDITOR_READY_TIMEOUT_MS)
        except Exception as exc:  # noqa: BLE001 — 起動/遷移失敗は閉じて正直に返す
            try:
                await launcher.close()
            except Exception:  # noqa: BLE001
                pass
            hint = "（セッション期限切れなら `pantheon publish connect wordpress` で再接続）"
            return PublishResult(
                ok=False,
                platform=self.platform,
                mode=target.mode,
                error=f"WordPress エディタの起動に失敗しました: {type(exc).__name__}: {exc}{hint}",
            )

        # 本文は block editor の構造差が大きいため best-effort（失敗しても editor を開いたまま
        # 人間にハンドオフする — note/X が fill 失敗を hard error にするのとは別方針）。
        filled = False
        try:
            await page.fill(WP_TITLE_SELECTOR, content.title)
            filled = True
        except Exception:  # noqa: BLE001 — タイトル流し込み失敗はハンドオフで吸収
            filled = False

        detail = (
            "wp-admin の新規投稿エディタを開きました。"
            + (
                "タイトルを流し込みました。"
                if filled
                else "タイトル欄が見つからなかったため未入力です。"
            )
            + "本文を貼り付け、内容を確認のうえ公開してください（本文の自動流し込みは Phase 2）"
        )
        # assisted の契約どおり、最終公開は人間 — ブラウザは開いたままハンドオフする。
        keep_alive(launcher)
        return PublishResult(
            ok=True,
            platform=self.platform,
            mode=target.mode,
            handed_off=True,
            detail=detail,
        )
