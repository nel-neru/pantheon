"""アフィリエイト商材レジストリ — 案件・料率・recurring の台帳。

正準は ``~/.pantheon/affiliate_programs.json``（JSON）。``config/affiliate_programs/*.yaml`` を
``seed_from_config()`` で取り込む（``program_id`` がスラッグなので再シードは冪等＝重複しない）。
台本生成は ``has_affiliate=True`` を優先してツールを割り当てる。
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

VALID_TIERS = ("a", "b", "c")
VALID_CATEGORIES = (
    "video",
    "voice",
    "writing",
    "design",
    "automation",
    "research",
    "general",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def slugify(name: str) -> str:
    """名前を安定スラッグへ（再シードの冪等キー）。英数以外は ``-`` に畳む。"""
    s = re.sub(r"[^a-z0-9]+", "-", str(name).strip().lower()).strip("-")
    return s or "program"


@dataclass
class AffiliateProgram:
    """アフィリエイト案件 1 件。"""

    name: str
    category: str = "general"
    network: str = "none"
    url: str = ""
    commission: str = ""
    recurring: bool = False
    has_affiliate: bool = True
    japan_ok: str = "partial"  # "true" / "partial" / "false"（yaml の bool も str 化して保持）
    tier: str = "b"  # a=主力 / b=補完 / c=集客ネタ
    topics: List[str] = field(default_factory=list)
    notes: str = ""
    program_id: str = ""
    created_at: str = ""

    def __post_init__(self) -> None:
        self.name = str(self.name)
        self.category = str(self.category).strip().lower() or "general"
        if self.category not in VALID_CATEGORIES:
            self.category = "general"
        self.network = str(self.network)
        self.recurring = bool(self.recurring)
        self.has_affiliate = bool(self.has_affiliate)
        # yaml では true/false が bool、partial が str で来るため一律 str 化。
        self.japan_ok = str(self.japan_ok).strip().lower()
        self.tier = str(self.tier).strip().lower()
        if self.tier not in VALID_TIERS:
            self.tier = "b"
        if not isinstance(self.topics, list):
            self.topics = []
        self.topics = [str(t) for t in self.topics if isinstance(t, (str, int, float))]
        if not self.program_id:
            self.program_id = f"aff:{slugify(self.name)}"
        if not self.created_at:
            self.created_at = _now_iso()

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "AffiliateProgram":
        known = {f for f in cls.__dataclass_fields__}  # noqa: C416
        return cls(**{k: v for k, v in d.items() if k in known})


class AffiliateProgramStore:
    """商材レジストリの永続ストア（``~/.pantheon/affiliate_programs.json``）。"""

    def __init__(self, platform_home: Optional[Path] = None):
        if platform_home is None:
            from core.platform.state import get_platform_home

            platform_home = get_platform_home()
        self.platform_home = Path(platform_home)
        self.platform_home.mkdir(parents=True, exist_ok=True)
        self.path = self.platform_home / "affiliate_programs.json"

    # ---- 低レベル read/write（破損耐性・非 list ガード・原子的書き込み）----
    def _load_raw(self) -> List[Dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        return data if isinstance(data, list) else []

    def _save_raw(self, items: List[Dict[str, Any]]) -> None:
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    # ---- 公開 API ----
    def list_programs(self) -> List[AffiliateProgram]:
        out: List[AffiliateProgram] = []
        for d in self._load_raw():
            if not isinstance(d, dict):
                continue
            try:
                out.append(AffiliateProgram.from_dict(d))
            except (TypeError, ValueError):
                continue  # 壊れた/不完全なレコードはスキップ
        return out

    def get_program(self, program_id: str) -> Optional[AffiliateProgram]:
        for p in self.list_programs():
            if p.program_id == program_id:
                return p
        return None

    def get_by_name(self, name: str) -> Optional[AffiliateProgram]:
        target = f"aff:{slugify(name)}"
        return self.get_program(target)

    def upsert(self, program: AffiliateProgram) -> AffiliateProgram:
        """program_id 一致なら上書き、無ければ追加（冪等シードの土台）。"""
        items = self._load_raw()
        for i, d in enumerate(items):
            if isinstance(d, dict) and d.get("program_id") == program.program_id:
                items[i] = program.to_dict()
                break
        else:
            items.append(program.to_dict())
        self._save_raw(items)
        return program

    def add_program(self, program: AffiliateProgram) -> AffiliateProgram:
        return self.upsert(program)

    def affiliate_enabled(self) -> List[AffiliateProgram]:
        """収益源になる（has_affiliate=True）案件のみ。tier a→b→c 順で安定ソート。"""
        order = {"a": 0, "b": 1, "c": 2}
        progs = [p for p in self.list_programs() if p.has_affiliate]
        return sorted(progs, key=lambda p: (order.get(p.tier, 3), p.name))

    def seed_from_config(self, config_path: Optional[Path] = None) -> int:
        """``config/affiliate_programs/ai_tools.yaml`` を読み込んで upsert する。

        取り込めた件数を返す。yaml/ファイルが無い・壊れている場合は 0（例外を投げない）。
        """
        import yaml

        if config_path is None:
            from core.paths import resource_path

            config_path = resource_path("config", "affiliate_programs", "ai_tools.yaml")
        config_path = Path(config_path)
        if not config_path.exists():
            return 0
        try:
            payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        except (OSError, ValueError):
            return 0
        if not isinstance(payload, dict):
            return 0
        rows = payload.get("programs", [])
        if not isinstance(rows, list):
            return 0
        count = 0
        for row in rows:
            if not isinstance(row, dict) or not row.get("name"):
                continue
            try:
                self.upsert(AffiliateProgram.from_dict(row))
                count += 1
            except (TypeError, ValueError):
                continue
        return count
