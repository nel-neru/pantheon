"""REV-COLLECT: 汎用 CSV 取り込みコレクタ（P15 — stub だった fetch() を実装する）。

実 API 連携（note/X/ASP の公式 API）が入るまでの **現実的な自動収集経路**として、各ソースの
売上 CSV（プラットフォームのダウンロード/エクスポート）を取り込めるようにする。
``~/.pantheon/revenue_imports/<source>.csv`` を置くと、そのソースは「接続済み」とみなされ、
収集サイクルで自動的に OutcomeStore へ記録される（``dedupe_on_source`` で再取り込みしても二重計上しない）。

CSV 形式（ヘッダ行・列名は大文字小文字を無視）::

    org_name,amount,occurred_at,id,note
    動画制作社,1200,2026-06-10,note-art-1,有料記事

- ``org_name``（別名 ``org``）と ``amount``（別名 ``revenue``）は必須。
- ``occurred_at``（別名 ``date``）/ ``id`` / ``note`` は任意。
- レコード単位の安定キー ``source`` は ``<source>:<id>``（id が無ければ行内容の sha1）。
  再取り込みで同じ行は同じキー → ``dedupe_on_source`` が二重計上を防ぐ。

堅牢性（silent-drop-observability 規約）: 壊れた行は **例外を投げず skip し、件数を warn ログ**に出す。
1 行の不正で収集全体を落とさない。
"""

from __future__ import annotations

import csv
import hashlib
import logging
from pathlib import Path
from typing import List, Optional

from core.metrics.revenue_collectors.base import CollectedRevenue, RevenueCollector

logger = logging.getLogger(__name__)

# 取り込み CSV の置き場所（接続=このファイルを置くこと）。
REVENUE_IMPORTS_DIR = "revenue_imports"

_ORG_KEYS = ("org_name", "org", "organization")
_AMOUNT_KEYS = ("amount", "revenue", "売上", "金額")
_DATE_KEYS = ("occurred_at", "date", "日付")
_ID_KEYS = ("id", "record_id", "transaction_id")
_NOTE_KEYS = ("note", "memo", "備考")


def revenue_csv_path(source: str, platform_home: Path) -> Path:
    """``~/.pantheon/revenue_imports/<source>.csv`` のパス（CSV 取り込みの置き場所）。"""
    return Path(platform_home) / REVENUE_IMPORTS_DIR / f"{source}.csv"


def _pick(row: dict, keys: tuple) -> str:
    """row（小文字化済みキー）から最初に見つかった列の値を返す（無ければ空文字）。"""
    for k in keys:
        if k in row and row[k] is not None:
            return str(row[k]).strip()
    return ""


def _stable_source_key(source: str, rec_id: str, org: str, amount: str, occurred_at: str) -> str:
    """レコード単位で安定な一意キーを返す（dedupe_on_source 用）。

    明示 ``id`` があればそれを使い、無ければ行内容（org|amount|date）の sha1 で安定化する。
    """
    if rec_id:
        return f"{source}:{rec_id}"
    digest = hashlib.sha1(f"{org}|{amount}|{occurred_at}".encode()).hexdigest()[:12]
    return f"{source}:{digest}"


def parse_revenue_csv(path: Path, source: str) -> List[CollectedRevenue]:
    """売上 CSV を ``CollectedRevenue`` のリストへ変換する（壊れた行は skip + warn）。"""
    try:
        text = Path(path).read_text(encoding="utf-8-sig")  # BOM 付きエクスポートにも耐える
    except OSError as exc:
        logger.warning("revenue CSV %s の読み込みに失敗: %s", path, exc)
        return []

    records: List[CollectedRevenue] = []
    skipped = 0
    reader = csv.DictReader(text.splitlines())
    for raw in reader:
        # キーを小文字化して列名のゆれ（大文字/前後空白）を吸収する。
        row = {(k or "").strip().lower(): (v or "") for k, v in raw.items() if k is not None}
        org = _pick(row, _ORG_KEYS)
        amount_str = _pick(row, _AMOUNT_KEYS).replace(",", "")
        if not org or not amount_str:
            skipped += 1
            continue
        try:
            amount = float(amount_str)
        except (TypeError, ValueError):
            skipped += 1
            continue
        occurred_at = _pick(row, _DATE_KEYS)
        rec_id = _pick(row, _ID_KEYS)
        note = _pick(row, _NOTE_KEYS)
        records.append(
            CollectedRevenue(
                org_name=org,
                amount=amount,
                source=_stable_source_key(source, rec_id, org, amount_str, occurred_at),
                occurred_at=occurred_at,
                note=note,
            )
        )
    if skipped:
        logger.warning("revenue CSV %s: %d 行を不正としてスキップしました", path, skipped)
    return records


class CsvBackedRevenueCollector(RevenueCollector):
    """資格情報 JSON か CSV 取り込みファイルのどちらかで「接続済み」とみなすコレクタ基底。

    実 API（``revenue_credentials/<source>.json`` を使う公式連携）が未実装の段階でも、
    ``revenue_imports/<source>.csv`` を置けば CSV から自動収集できる（P15）。
    実 API を実装する際は :meth:`_fetch_via_api` をオーバーライドする。
    """

    def is_configured(self, platform_home: Path) -> bool:
        # 資格情報 JSON（実 API 用）か CSV 取り込みファイルのいずれかがあれば接続済み扱い。
        return (
            super().is_configured(platform_home)
            or revenue_csv_path(self.source, platform_home).exists()
        )

    def _fetch_via_api(self, platform_home: Path) -> List[CollectedRevenue]:
        """実 API 連携（Phase 2）。既定は未実装で空を返す。サブクラスで差し込む。"""
        logger.info("%s revenue API fetch: 未実装（Phase 2・CSV 取り込みを使用）", self.source)
        return []

    def fetch(self, platform_home: Path) -> List[CollectedRevenue]:
        csv_path = revenue_csv_path(self.source, platform_home)
        if csv_path.exists():
            return parse_revenue_csv(csv_path, self.source)
        return self._fetch_via_api(platform_home)


def collected_revenue_from_path(
    path: Path, source: str, *, platform_home: Optional[Path] = None
) -> List[CollectedRevenue]:
    """任意パスの CSV を取り込む補助（CLI の ``revenue import`` 等から再利用可能）。"""
    return parse_revenue_csv(Path(path), source)
