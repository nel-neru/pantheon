"""Business — 複数の Organization（会社）を合成した「事業」を表す第一級モデル。

恒久原則（``docs/architecture/organization_boundaries.md``）に基づき、**会社/能力（Organization）と
事業（Business）を分離**する。会社は再利用可能な構成部品（例: 動画制作社・アフィリエイト社）であり、
Business はそれらを ``handoff_routes``（集客→制作→収益化）で合成したものを指す。

合成の実体は既存のクロス Org ハンドオフ（``core/hierarchy/org_handoff.py``）を再利用する
（新しい合成プロトコルは作らない）。成果は member 会社の Outcome を Business 単位でロールアップする。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

# 会社の役割（合成上の意味付け。自由文字列も可）。
KNOWN_ROLES = ("audience", "producer", "monetizer", "operations")


class HandoffRoute(BaseModel):
    """Business 内の会社間ルート（合成の経路テンプレート）。"""

    from_org: str
    to_org: str
    kind: str = "content_brief"  # org_handoff の KNOWN_HANDOFF_KINDS と整合


class Business(BaseModel):
    """複数会社を合成した事業。member は Organization 名で参照する
    （``OrgHandoff``/``OutcomeStore`` が org 名キーのため整合する）。"""

    id: UUID = Field(default_factory=uuid4)
    name: str
    purpose: str = ""
    member_orgs: List[str] = Field(default_factory=list)
    roles: Dict[str, str] = Field(default_factory=dict)  # org_name -> role
    handoff_routes: List[HandoffRoute] = Field(default_factory=list)
    kpis: List[str] = Field(default_factory=list)
    status: str = "active"  # active / paused / archived
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
