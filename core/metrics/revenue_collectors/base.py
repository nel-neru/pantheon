"""REV-COLLECT: 収益コレクタの基底（アダプタ契約）。

各プラットフォーム（note / X / ASP 等）のアダプタは :class:`RevenueCollector` を実装し、
資格情報が接続済みか（:meth:`is_configured`）と、接続済みなら売上の取得
（:meth:`fetch`）を返す。資格情報は ``~/.pantheon/revenue_credentials/<source>.json``
に置く前提（接続は human-gate）。実 API 連携が入るまで ``fetch`` は空を返してよい
（枠組みのみ）。

決定論・冪等を旨とし、``fetch`` が返す :class:`CollectedRevenue.source` は **レコード単位で
安定な一意キー**（例 ``"note:2026-06:article123"``）にする — ``OutcomeStore`` 側の
``dedupe_on_source`` がこれで二重計上を防ぐ。
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass
class CollectedRevenue:
    """1 件の収益レコード（アダプタが返す中立表現）。"""

    org_name: str
    amount: float
    source: str  # レコード単位で安定な一意キー（dedupe_on_source 用）
    occurred_at: str = ""  # ISO 文字列（空可・OutcomeStore 側で補完）
    note: str = ""


def credentials_path(source: str, platform_home: Path) -> Path:
    """``~/.pantheon/revenue_credentials/<source>.json`` のパス（接続情報の置き場所）。"""
    return Path(platform_home) / "revenue_credentials" / f"{source}.json"


class RevenueCollector(ABC):
    """収益コレクタの基底。サブクラスは ``source`` と :meth:`fetch` を実装する。"""

    #: プラットフォーム識別子（"note" / "x" / "asp" など）。
    source: str = "base"

    #: 人間が接続するときの表示名。
    label: str = "収益ソース"

    def is_configured(self, platform_home: Path) -> bool:
        """資格情報が接続済みか（既定: ``revenue_credentials/<source>.json`` の存在）。"""
        return credentials_path(self.source, platform_home).exists()

    def _load_credentials(self, platform_home: Path) -> Optional[dict]:
        try:
            return json.loads(
                credentials_path(self.source, platform_home).read_text(encoding="utf-8")
            )
        except (OSError, ValueError):
            return None

    @abstractmethod
    def fetch(self, platform_home: Path) -> List[CollectedRevenue]:
        """接続済み時に売上を取得して返す（未接続では呼ばれない）。"""
        raise NotImplementedError
