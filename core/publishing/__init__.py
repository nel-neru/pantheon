"""core.publishing — 承認済みコンテンツを外部プラットフォーム（note / X / CMS）へ投稿する層。

設計上の不変条件:
- **人間承認ゲートは常に維持**する。投稿は外部副作用なので PolicyEngine の ``external_action``
  カテゴリで常に ``human_required`` 扱いとし、承認なしに自動投稿しない。
- **資格情報は保存しない**。ログインはユーザーが手動で行い、Pantheon は Playwright の
  セッション state（storage_state）だけを ``~/.pantheon/browser_sessions/<platform>/`` に保持する。
- 実投稿は **ブラウザ自動操作（Playwright）** で行う。Playwright は遅延 import し、
  未導入環境（テスト/CI）でも本パッケージの import と dry-run は成功する。

公開シンボルは遅延的に解決する（重い依存をトップレベル import で引き込まないため）。
"""

from __future__ import annotations

from core.publishing.base import (
    PLATFORM_NOTE,
    PLATFORM_WORDPRESS,
    PLATFORM_X,
    SUPPORTED_PLATFORMS,
    PublishContent,
    PublishResult,
    PublishTarget,
    playwright_available,
)
from core.publishing.publish_jobs import (
    PUBLISH_JOB_STATUSES,
    PublishJob,
    PublishJobStore,
)

__all__ = [
    "PLATFORM_NOTE",
    "PLATFORM_X",
    "PLATFORM_WORDPRESS",
    "SUPPORTED_PLATFORMS",
    "PublishContent",
    "PublishResult",
    "PublishTarget",
    "playwright_available",
    "PUBLISH_JOB_STATUSES",
    "PublishJob",
    "PublishJobStore",
]
