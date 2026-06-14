"""アダプタ共通の基底（dry-run プレビューと実投稿の分岐）。

``publish()`` は dry-run（または Playwright 未導入）なら外部に一切作用せず検証用の
``PublishResult`` を返す。実投稿は ``_publish_live()`` に委譲し、各プラットフォームの
アダプタが Playwright 自動操作（または公式 API）で実装する＝段階展開の拡張点。
"""

from __future__ import annotations

from core.publishing.base import (
    PublishContent,
    PublishResult,
    PublishTarget,
    playwright_available,
)


class BrowserPublisher:
    """ブラウザ自動操作系アダプタの基底。サブクラスは ``platform`` と ``_publish_live`` を定義する。"""

    platform: str = ""
    #: 無人での実 auto 送信を実装済みか（PUB-AUTO）。既定 False＝実送信は人手ゲート（handed_off）。
    #: True にできるのは各プラットフォームの実 auto 送信を実装したアダプタのみ（Phase 2 の拡張点）。
    supports_auto_send: bool = False

    async def publish(
        self,
        content: PublishContent,
        target: PublishTarget,
        *,
        dry_run: bool = False,
    ) -> PublishResult:
        # dry-run は外部に一切作用しないプレビュー。
        if dry_run:
            return self._preview(content, target)
        # 実投稿の要求だが Playwright が無ければ「投稿できない」と正直に失敗を返す
        # （プレビュー成功と実投稿成功を混同して未投稿を published にしないため）。
        if not playwright_available():
            return PublishResult(
                ok=False,
                platform=self.platform,
                dry_run=False,
                mode=target.mode,
                error="ブラウザ未接続または Playwright 未導入のため実投稿できません（プレビューのみ可）",
            )
        return await self._publish_live(content, target)

    # ---- サブクラスが実装 ----
    async def _publish_live(self, content: PublishContent, target: PublishTarget) -> PublishResult:
        """実投稿（Playwright 自動操作）。Phase 1/2 で各アダプタが実装する。"""
        raise NotImplementedError(
            f"{self.platform}: 実投稿は未実装（プラットフォーム接続と段階展開で実装予定）"
        )

    # ---- 共通の dry-run プレビュー ----
    def _preview(self, content: PublishContent, target: PublishTarget) -> PublishResult:
        snippet = (content.body or "").strip().splitlines()
        head = snippet[0][:80] if snippet else ""
        return PublishResult(
            ok=True,
            platform=self.platform,
            url="",
            dry_run=True,
            mode=target.mode,
            detail=f"dry-run: title='{content.title[:60]}' body_head='{head}'",
        )
