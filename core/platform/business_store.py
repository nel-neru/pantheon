"""BusinessStore — Business（会社の合成）の永続ストア（``~/.pantheon/businesses.json``）。

OutcomeStore / PublishJobStore と同じ規約（破損耐性・非 list ガード・原子的書き込み）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.models.business import Business
from core.persistence import atomic_write_text


class BusinessStore:
    def __init__(self, platform_home: Optional[Path] = None):
        if platform_home is None:
            from core.platform.state import get_platform_home

            platform_home = get_platform_home()
        self.platform_home = Path(platform_home)
        self.platform_home.mkdir(parents=True, exist_ok=True)
        self.path = self.platform_home / "businesses.json"

    def _load_raw(self) -> List[Dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        return data if isinstance(data, list) else []

    def _save_raw(self, items: List[Dict[str, Any]]) -> None:
        atomic_write_text(self.path, json.dumps(items, ensure_ascii=False, indent=2))

    def list_businesses(self) -> List[Business]:
        out: List[Business] = []
        for d in self._load_raw():
            if not isinstance(d, dict):
                continue
            try:
                out.append(Business.model_validate(d))
            except Exception:  # noqa: BLE001 — 壊れた/旧スキーマのレコードはスキップ
                continue
        return out

    def get(self, key: str) -> Optional[Business]:
        """id（文字列）または name で検索する。"""
        key = (key or "").strip()
        for b in self.list_businesses():
            if str(b.id) == key or b.name == key:
                return b
        return None

    def save(self, business: Business) -> Business:
        """id 一致なら上書き、無ければ追加。"""
        items = self._load_raw()
        bid = str(business.id)
        payload = business.model_dump(mode="json")
        for i, d in enumerate(items):
            if isinstance(d, dict) and str(d.get("id")) == bid:
                items[i] = payload
                break
        else:
            items.append(payload)
        self._save_raw(items)
        return business

    def delete(self, key: str) -> bool:
        target = self.get(key)
        if target is None:
            return False
        bid = str(target.id)
        items = [
            d for d in self._load_raw() if not (isinstance(d, dict) and str(d.get("id")) == bid)
        ]
        self._save_raw(items)
        return True

    def compose_handoffs(self, business: Business, *, psm: Any = None) -> List[Any]:
        """Business の handoff_routes から保留中の OrgHandoff を作成する（合成の実体化）。

        既存のクロス Org ハンドオフ基盤を再利用する（新規プロトコルは作らない）。
        作成できた OrgHandoff のリストを返す。source==target など不正なルートはスキップ。
        """
        from core.hierarchy.org_handoff import OrgHandoffStore

        home = (
            self.platform_home if psm is None else getattr(psm, "platform_home", self.platform_home)
        )
        store = OrgHandoffStore(platform_home=home)
        created: List[Any] = []
        for route in business.handoff_routes:
            if not route.from_org or not route.to_org or route.from_org == route.to_org:
                continue
            try:
                handoff = store.create(
                    route.from_org,
                    route.to_org,
                    route.kind,
                    title=f"[{business.name}] {route.from_org}→{route.to_org} ({route.kind})",
                    note=f"business:{business.id}",
                )
                created.append(handoff)
            except ValueError:
                continue  # ポリシー棄却・不正ルートはスキップ
        return created
