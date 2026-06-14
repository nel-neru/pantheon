"""REV-COLLECT: プラットフォーム別アダプタ（note / X / ASP）。

枠組み段階のため、各アダプタの ``fetch`` は **実 API 連携が入るまで空を返す**
（資格情報の接続＝human-gate が済むまで自動収集はしない）。接続済みの判定は基底の
``is_configured``（``revenue_credentials/<source>.json`` の存在）に従う。

実 API 実装はここに差し込む（例: note の売上ページ/CSV、X の収益、ASP のレポート API）。
それまでは手動入力（``POST /api/outcomes``）/CSV 取り込みが収益記録の正規経路。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List

from core.metrics.revenue_collectors.base import CollectedRevenue, RevenueCollector

logger = logging.getLogger(__name__)


class NoteRevenueCollector(RevenueCollector):
    source = "note"
    label = "note（有料記事の売上）"

    def fetch(self, platform_home: Path) -> List[CollectedRevenue]:
        # TODO(human-gate): note の売上取得を実装（接続済み資格情報を使う）。
        logger.info("note revenue fetch: 実 API 連携は未実装（Phase 2・接続後に有効化）")
        return []


class XRevenueCollector(RevenueCollector):
    source = "x"
    label = "X（クリエイター収益）"

    def fetch(self, platform_home: Path) -> List[CollectedRevenue]:
        # TODO(human-gate): X の収益取得を実装。
        logger.info("x revenue fetch: 実 API 連携は未実装（Phase 2・接続後に有効化）")
        return []


class AspRevenueCollector(RevenueCollector):
    source = "asp"
    label = "ASP（アフィリエイト報酬）"

    def fetch(self, platform_home: Path) -> List[CollectedRevenue]:
        # TODO(human-gate): ASP レポート API から確定報酬を取得。
        logger.info("asp revenue fetch: 実 API 連携は未実装（Phase 2・接続後に有効化）")
        return []
