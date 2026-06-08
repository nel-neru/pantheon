"""
OrgHandoff — ピア Organization 間の引き渡し（cross-org collaboration / 収益フライホイールの結合組織）。

設計思想:
- HQ→子の構造介入（``structural_intervention``）とは別軸。対等な org 同士で、ある org の
  成果物（集客シグナル・購買意図・原稿）を別 org の入力（有料コンテンツ生成・収益化導線）へ
  橋渡しする。「SNS 集客 → note 販売 → アフィリ収益化」のフライホイールはこの引き渡しの連鎖。
- ``OutcomeStore`` と同じく **JSON を正準**（``~/.pantheon/org_handoffs.json``）とする軽量ストア。
  外部 API 連携は持たない（イベントは org / 自動化が record する）。
- すべての引き渡しは **PolicyEngine を通る**。``cross_org_handoff`` カテゴリは常に
  HUMAN_REQUIRED（= 承認ボタン）。別 org の作業キューに仕事を生むため auto 適用しない。
- ライフサイクル: ``pending`` →（人間が承認）``approved`` →（受け手 org が消費）``consumed``。
  却下は ``rejected``。`payload` は自由 dict で、ニッチ固有の構造（検証済み需要・原稿参照・
  購買意図セグメント等）を後方互換のまま載せられる。

このモジュール自身は «どの org がどの kind を流すか» を知らない（特定ドメイン非依存）。
具体的な funnel（集客→販売→収益化）の配線は各組織の charter / 運用が定義する。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from core.models.organization import CROSS_ORG_HANDOFF_CATEGORY


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# 引き渡しのライフサイクル状態。
HANDOFF_PENDING = "pending"  # 承認待ち（承認ボタン前）
HANDOFF_APPROVED = "approved"  # 人間が承認済み（受け手 org が消費可能）
HANDOFF_CONSUMED = "consumed"  # 受け手 org が消費（例: content_asset 提案を生成）
HANDOFF_REJECTED = "rejected"  # 却下

ACTIVE_HANDOFF_STATUSES = (HANDOFF_PENDING, HANDOFF_APPROVED)

# 代表的な引き渡し種別（自由文字列も可。集計/ルーティングの意味付けに使う）。
# audience_signal: 検証済みの需要/関心セグメント（SNS 運用 → note 販売 / アフィリ）
# content_brief:   有料コンテンツ/記事の企画ブリーフ（note 販売 / アフィリ → コンテンツ制作）
# monetization_lead: 購買意図のある導線（note 販売 / SNS → アフィリ収益化）
KNOWN_HANDOFF_KINDS = ("audience_signal", "content_brief", "monetization_lead")


@dataclass
class OrgHandoff:
    """ピア org 間の 1 件の引き渡しアーティファクト。"""

    source_org: str
    target_org: str
    kind: str
    title: str
    payload: Dict[str, Any] = field(default_factory=dict)
    status: str = HANDOFF_PENDING
    priority: str = "medium"
    note: str = ""
    # 監査用: 作成時の PolicyEngine 判定を記録（常に human_required になる想定）。
    policy_decision: str = ""
    policy_reason: str = ""
    # 受け手 org が消費した結果の参照（例: 生成した content_asset 提案 id）。
    consumed_ref: str = ""
    handoff_id: str = ""
    created_at: str = ""
    decided_at: str = ""
    consumed_at: str = ""

    def __post_init__(self):
        self.kind = str(self.kind).strip()
        if not isinstance(self.payload, dict):
            self.payload = {}
        if not self.handoff_id:
            self.handoff_id = f"handoff:{uuid4()}"
        if not self.created_at:
            self.created_at = _now_iso()

    def as_policy_dict(self) -> Dict[str, Any]:
        """PolicyEngine.evaluate に渡す提案ライクな dict。

        重要: ``target_org_name`` 等の構造介入キーは **入れない**（介入と誤判定されるため）。
        引き渡しは category だけで識別し、専用の ``_check_handoff`` ゲートに載せる。
        """
        return {
            "category": CROSS_ORG_HANDOFF_CATEGORY,
            "priority": self.priority,
            "file_path": "",
            "title": self.title,
        }


class OrgHandoffStore:
    """引き渡しの永続ストア（``~/.pantheon/org_handoffs.json``）。"""

    def __init__(self, platform_home: Optional[Path] = None):
        if platform_home is None:
            from core.platform.state import get_platform_home

            platform_home = get_platform_home()
        self.platform_home = Path(platform_home)
        self.platform_home.mkdir(parents=True, exist_ok=True)
        self.handoffs_path = self.platform_home / "org_handoffs.json"

    # ---- 作成（PolicyEngine ゲートを通す） ----

    def create(
        self,
        source_org: str,
        target_org: str,
        kind: str,
        title: str,
        payload: Optional[Dict[str, Any]] = None,
        *,
        priority: str = "medium",
        note: str = "",
        policy: Any = None,
    ) -> OrgHandoff:
        """引き渡しを作成して永続化する。

        PolicyEngine を通し判定を記録する（``cross_org_handoff`` は常に human_required）。
        判定が REJECT（運用者が kill-switch でカテゴリ無効化した場合等）なら作成しない。
        ``policy`` を渡さなければデフォルトの ``PolicyEngine()`` を使う（テストで差し替え可能）。
        """
        if source_org == target_org:
            raise ValueError("引き渡しの source_org と target_org は異なる必要があります。")

        handoff = OrgHandoff(
            source_org=source_org,
            target_org=target_org,
            kind=kind,
            title=title,
            payload=dict(payload or {}),
            priority=priority,
            note=note,
        )

        from core.policy.engine import ApprovalDecision, PolicyEngine

        engine = policy or PolicyEngine()
        verdict = engine.evaluate(handoff.as_policy_dict())
        handoff.policy_decision = verdict.decision.value
        handoff.policy_reason = verdict.reason
        if verdict.decision == ApprovalDecision.REJECT:
            raise ValueError(
                f"引き渡しはポリシーにより棄却されました: {verdict.reason}（rule={verdict.rule_name}）"
            )

        handoffs = self._load()
        handoffs.append(handoff)
        self._save(handoffs)
        return handoff

    # ---- 参照 ----

    def get(self, handoff_id: str) -> Optional[OrgHandoff]:
        return next((h for h in self._load() if h.handoff_id == handoff_id), None)

    def list_handoffs(
        self,
        *,
        source_org: Optional[str] = None,
        target_org: Optional[str] = None,
        status: Optional[str] = None,
        kind: Optional[str] = None,
    ) -> List[OrgHandoff]:
        result = self._load()
        if source_org is not None:
            result = [h for h in result if h.source_org == source_org]
        if target_org is not None:
            result = [h for h in result if h.target_org == target_org]
        if status is not None:
            result = [h for h in result if h.status == status]
        if kind is not None:
            result = [h for h in result if h.kind == kind]
        return result

    def pending_for(self, target_org: str) -> List[OrgHandoff]:
        """承認待ち（``pending``）の引き渡し＝受け手 org の「承認ボタン」キュー。"""
        return self.list_handoffs(target_org=target_org, status=HANDOFF_PENDING)

    def ready_for(self, target_org: str) -> List[OrgHandoff]:
        """承認済みで未消費（``approved``）の引き渡し＝受け手 org が着手できる仕事。"""
        return self.list_handoffs(target_org=target_org, status=HANDOFF_APPROVED)

    # ---- 状態遷移 ----

    def approve(self, handoff_id: str) -> OrgHandoff:
        """承認ボタン: ``pending`` → ``approved``。"""
        return self._transition(
            handoff_id,
            allowed_from=(HANDOFF_PENDING,),
            new_status=HANDOFF_APPROVED,
            stamp="decided_at",
        )

    def reject(self, handoff_id: str) -> OrgHandoff:
        """却下: ``pending`` → ``rejected``。"""
        return self._transition(
            handoff_id,
            allowed_from=(HANDOFF_PENDING,),
            new_status=HANDOFF_REJECTED,
            stamp="decided_at",
        )

    def mark_consumed(self, handoff_id: str, consumed_ref: str = "") -> OrgHandoff:
        """受け手 org が消費したと記録: ``approved`` → ``consumed``。"""
        return self._transition(
            handoff_id,
            allowed_from=(HANDOFF_APPROVED,),
            new_status=HANDOFF_CONSUMED,
            stamp="consumed_at",
            consumed_ref=consumed_ref,
        )

    def _transition(
        self,
        handoff_id: str,
        *,
        allowed_from: tuple[str, ...],
        new_status: str,
        stamp: str,
        consumed_ref: str = "",
    ) -> OrgHandoff:
        handoffs = self._load()
        for handoff in handoffs:
            if handoff.handoff_id != handoff_id:
                continue
            if handoff.status not in allowed_from:
                raise ValueError(
                    f"引き渡し {handoff_id} は状態 '{handoff.status}' のため "
                    f"'{new_status}' に遷移できません（許可: {', '.join(allowed_from)}）。"
                )
            handoff.status = new_status
            setattr(handoff, stamp, _now_iso())
            if consumed_ref:
                handoff.consumed_ref = consumed_ref
            self._save(handoffs)
            return handoff
        raise KeyError(f"引き渡しが見つかりません: {handoff_id}")

    # ---- 内部 ----

    def _load(self) -> List[OrgHandoff]:
        if not self.handoffs_path.exists():
            return []
        try:
            payload = json.loads(self.handoffs_path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return []
        handoffs: List[OrgHandoff] = []
        for item in payload:
            try:
                handoffs.append(OrgHandoff(**item))
            except (TypeError, ValueError):
                # 未知キー/不正な item はスキップして全体を壊さない（前方/後方互換）。
                continue
        return handoffs

    def _save(self, handoffs: List[OrgHandoff]) -> None:
        self.handoffs_path.write_text(
            json.dumps([asdict(h) for h in handoffs], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
