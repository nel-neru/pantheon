"""REV-COLLECT: プラットフォーム別アダプタ（note / X / ASP）。

各アダプタは :class:`~core.metrics.revenue_collectors.csv_import.CsvBackedRevenueCollector` を継承し、
``~/.pantheon/revenue_imports/<source>.csv`` を置くと **CSV から自動収集する**（P15）。
公式 API 連携（Phase 2）は :meth:`_fetch_via_api` をオーバーライドして差し込む。
それまでは CSV 取り込み / 手動入力（``POST /api/outcomes``）が収益記録の経路。
"""

from __future__ import annotations

from core.metrics.revenue_collectors.csv_import import CsvBackedRevenueCollector


class NoteRevenueCollector(CsvBackedRevenueCollector):
    source = "note"
    label = "note（有料記事の売上）"


class XRevenueCollector(CsvBackedRevenueCollector):
    source = "x"
    label = "X（クリエイター収益）"


class AspRevenueCollector(CsvBackedRevenueCollector):
    source = "asp"
    label = "ASP（アフィリエイト報酬）"
