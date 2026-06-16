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
        # 投稿前バリデーション: プレビューは外部に作用しないが、実投稿（_publish_live）が
        # 弾く不正コンテンツはここでも正直に ok=False で返す。さもないと空/不正な下書きが
        # プレビューで「成功」に見え、人間が handed_off まで進めてから初めて失敗に気づく
        # （検証の非対称を解消＝投稿前に問題を可視化する）。
        title = (content.title or "").strip()
        body = (content.body or "").strip()
        if not title and not body:
            return PublishResult(
                ok=False,
                platform=self.platform,
                url="",
                dry_run=True,
                mode=target.mode,
                error="投稿内容が空です（title も body もありません）",
            )

        head = body.splitlines()[0][:80] if body else ""
        detail = f"dry-run: title='{title[:60]}' body_head='{head}'"
        warnings = self._preview_warnings(content, target)
        if warnings:
            detail += " | 警告: " + " / ".join(warnings)
        return PublishResult(
            ok=True,
            platform=self.platform,
            url="",
            dry_run=True,
            mode=target.mode,
            detail=detail,
        )

    def _preview_warnings(self, content: PublishContent, target: PublishTarget) -> list[str]:
        """プレビューに添える非致命的な投稿前警告（文字数超過など）の拡張点。

        サブクラスがプラットフォーム固有の警告を返す（既定は警告なし）。致命的な不正は
        ``_preview`` 側で ``ok=False`` にし、ここは「投稿はできるが人間が確認すべき」事項に使う。
        """
        return []
