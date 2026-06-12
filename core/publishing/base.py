"""投稿エンジンの抽象（プラットフォーム非依存の値オブジェクトと Publisher 契約）。

ここには重い依存（Playwright 等）を持ち込まない。``playwright_available()`` は遅延 import で
存在判定だけを行い、実ブラウザは各アダプタが必要時にのみ起動する。
"""

from __future__ import annotations

import importlib.util
import os
from dataclasses import dataclass, field
from typing import List, Optional, Protocol, runtime_checkable

# 対応プラットフォーム（ユーザー確定: note / X / アフィリ記事CMS）。
PLATFORM_NOTE = "note"
PLATFORM_X = "x"
PLATFORM_WORDPRESS = "wordpress"
SUPPORTED_PLATFORMS = (PLATFORM_NOTE, PLATFORM_X, PLATFORM_WORDPRESS)

# 投稿モード:
#   assisted = 投稿画面まで自動で開き、本文を流し込むが最終送信は人間（Phase 1 / 既定・最も安全）
#   auto     = 承認済みを予約時刻に完全自動送信（Phase 2）
PUBLISH_MODE_ASSISTED = "assisted"
PUBLISH_MODE_AUTO = "auto"
PUBLISH_MODES = (PUBLISH_MODE_ASSISTED, PUBLISH_MODE_AUTO)


def playwright_available() -> bool:
    """Playwright が import 可能か（実ブラウザ投稿が可能か）を遅延判定する。

    ``content_runner`` の ``claude_available()`` と同じ思想で、未導入環境でも本パッケージの
    import と dry-run を壊さない。``PANTHEON_NO_BROWSER=1`` で明示的に無効化できる（テスト用）。
    """
    if os.environ.get("PANTHEON_NO_BROWSER") == "1":
        return False
    return importlib.util.find_spec("playwright") is not None


@dataclass
class PublishContent:
    """投稿する中身（プラットフォーム非依存のスナップショット）。"""

    title: str = ""
    body: str = ""
    tags: List[str] = field(default_factory=list)
    # 媒体固有の補助情報（例: WordPress の status=draft/publish、note のマガジン等）。
    extra: dict = field(default_factory=dict)


@dataclass
class PublishTarget:
    """どこへ・いつ・どのモードで投稿するか。"""

    platform: str
    account: str = ""
    scheduled_at: Optional[str] = None
    mode: str = PUBLISH_MODE_ASSISTED


@dataclass
class PublishResult:
    """投稿の結果。``ok`` が False のときは ``error`` に理由を入れる。

    ``handed_off=True`` は「自動化パート（下書き流し込み）は成功したが、最終公開は
    人間に引き渡した」状態。公開済み（published）とは区別され、成果指標にも数えない。
    """

    ok: bool
    platform: str
    url: str = ""
    error: str = ""
    dry_run: bool = False
    mode: str = PUBLISH_MODE_ASSISTED
    detail: str = ""
    handed_off: bool = False


@runtime_checkable
class Publisher(Protocol):
    """各プラットフォーム投稿アダプタの契約。

    ``dry_run=True`` のときは外部へ一切作用せず、検証用の ``PublishResult`` を返さねばならない。
    実投稿は Playwright を必要時に起動して行う（``dry_run=False`` かつ接続済みセッションが前提）。
    """

    platform: str

    async def publish(
        self,
        content: PublishContent,
        target: PublishTarget,
        *,
        dry_run: bool = False,
    ) -> PublishResult: ...
