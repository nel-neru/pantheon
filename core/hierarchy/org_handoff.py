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
    # 承認時に自動生成した受け手 org の content_asset ブリーフ提案 id（マテリアライズ）。
    materialized_ref: str = ""
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

    def record_materialization(self, handoff_id: str, proposal_id: str) -> OrgHandoff:
        """承認時に自動生成した受け手 org のブリーフ提案 id を記録（状態は変えない）。"""
        handoffs = self._load()
        for handoff in handoffs:
            if handoff.handoff_id != handoff_id:
                continue
            handoff.materialized_ref = proposal_id
            self._save(handoffs)
            return handoff
        raise KeyError(f"引き渡しが見つかりません: {handoff_id}")

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


# ---------------------------------------------------------------------------
# マテリアライズ（承認 → 受け手 org の content_asset ブリーフ提案を自動生成）
# ---------------------------------------------------------------------------
#
# 「承認ボタンを押すだけで次の org の草稿が出てくる」橋渡し。検証済みの『型』
# （無料エリア3要素・500円入口+3倍刻みティア・A8.net X不可/PR表記・相互送客）を
# 決定論的にブリーフ化する。実記事の本文生成は後段（既存の content_asset 適用 / LLM）に委ねる。


def _brief_for(handoff: OrgHandoff) -> tuple[str, str, str]:
    """handoff.kind から受け手向け content_asset ブリーフ (file_path, title, content) を決定論生成する。"""
    payload = handoff.payload or {}
    short = handoff.handoff_id.split(":")[-1][:8]
    kind = handoff.kind
    src = handoff.source_org
    prov = f"> 出所: handoff `{handoff.handoff_id}`（{src} → {handoff.target_org} / {kind}）\n"

    def fmt_payload() -> str:
        if not payload:
            return "（ペイロードなし）"
        return "\n".join(f"- {k}: {v}" for k, v in payload.items())

    if kind == "audience_signal":
        theme = str(payload.get("theme") or handoff.title)
        file_path = f"content/brief-note-{short}.md"
        title = f"有料note企画ブリーフ: {theme}"
        content = (
            f"# 有料note企画ブリーフ — {theme}\n\n{prov}\n"
            f"## 引き渡しペイロード\n{fmt_payload()}\n\n"
            "## 無料エリア（試食）— 3要素（note公式・有料記事100件分析の型）\n"
            "- ①共感・問いかけ: 読者の悩みを言語化（TODO: 具体化）\n"
            "- ②変化の物語: Before/After（TODO）\n"
            "- ③ベネフィット提示: 読んで得られる価値（TODO）\n\n"
            "## 有料エリア（フルコース）\n"
            "- 無料では絶対に出さない一段深い内容（生ログ・プロンプト全文・裏側）で差別化\n\n"
            "## 値付け（note公式・約3,000件分析の型）\n"
            "- 単発note: 専門ノウハウ 1,000円〜 / +1対1相談権 5,000円〜\n"
            "- メンバーシップ: 入口500円、複数ティアは3倍刻み（500 → 1,500 → 5,000円）\n\n"
            "## 次アクション\n"
            "- このブリーフを承認・適用 → 本文を執筆/生成 → 公開・価格設定（運用者）\n"
            "- 物販化できる箇所は `monetization_lead` でアフィリ組織へ handoff\n"
        )
    elif kind == "monetization_lead":
        offer = str(payload.get("offer") or handoff.title)
        file_path = f"content/brief-affiliate-{short}.md"
        title = f"物販導線ブリーフ: {offer}"
        content = (
            f"# 物販導線ブリーフ — {offer}\n\n{prov}\n"
            f"## 引き渡しペイロード\n{fmt_payload()}\n\n"
            "## 規約・コンプライアンス（必須・検証済み）\n"
            "- ステマ規制（景表法 告示第19号, 2023-10-01施行）: 明瞭な PR 表記（「広告」「PR」等）を付す\n"
            "- A8.net: **X(旧Twitter)でアフィリリンク不可** → 掲出面は note本文 / YouTube概要欄 / リンク集\n"
            "- 許可SNS（A8.net）: Instagram / YouTube / TikTok / Pinterest\n\n"
            "## CV導線\n"
            "- オファー: " + offer + "（intent: " + str(payload.get("intent") or "未設定") + "）\n"
            "- 掲出面: " + str(payload.get("placement") or "note本文/YouTube概要欄") + "\n"
            "- ASP: " + str(payload.get("asp") or "A8.net 等（料率/Cookie/ToS を一次ページで再確認）") + "\n\n"
            "## 次アクション\n"
            "- このブリーフを承認・適用 → PR表記つき物販導線を執筆 → 概要欄/note本文へ反映（運用者）\n"
        )
    elif kind == "content_brief":
        topic = str(payload.get("topic") or handoff.title)
        file_path = f"content/brief-sns-{short}.md"
        title = f"集客テーマブリーフ: {topic}"
        content = (
            f"# 集客テーマブリーフ — {topic}\n\n{prov}\n"
            f"## 引き渡しペイロード\n{fmt_payload()}\n\n"
            "## 投稿設計（相互送客）\n"
            "- X: 短文×頻度で実用ノウハウを小出し → 固定ポスト/リンク集から note へ（物販リンクは置かない）\n"
            "- YouTube: 概要欄 CTA / 動画内 CTA で note・メンバーシップへ\n"
            "- 一貫テーマ: 「多くの人がいる X/YouTube から少しずつ自分の note へ」\n\n"
            "## 次アクション\n"
            "- このブリーフを承認・適用 → 投稿/台本を執筆 → 運用者が手動公開\n"
        )
    else:
        file_path = f"content/brief-{short}.md"
        title = f"引き渡しブリーフ: {handoff.title}"
        content = (
            f"# 引き渡しブリーフ — {handoff.title}\n\n{prov}\n"
            f"## 引き渡しペイロード\n{fmt_payload()}\n\n"
            "## 次アクション\n- このブリーフを承認・適用して着手する\n"
        )
    return file_path, title, content


def materialize_handoff(handoff: OrgHandoff, *, psm: Any) -> Any:
    """承認済み handoff から受け手 org の content_asset ブリーフ提案を生成・保存する。

    受け手 org の正準ストア（``<repo>/.pantheon/improvements/``）に保存され、PolicyEngine 上
    content_asset は human_required。受け手側は通常の ``pantheon proposal apply`` で承認・適用する。
    受け手 org が未登録 / target_repo_path 未設定なら ``None`` を返す（マテリアライズ不可）。
    """
    from core.orchestration.asset_application import build_content_asset_proposal

    target = psm.load_organization_by_name(handoff.target_org)
    if target is None or not target.target_repo_path:
        return None

    file_path, title, content = _brief_for(handoff)
    proposal = build_content_asset_proposal(
        title=title,
        description=(
            f"handoff {handoff.handoff_id}（{handoff.source_org} → {handoff.target_org} / "
            f"{handoff.kind}）から自動生成したブリーフ。承認・適用でワークスペースに草稿が入る。"
        ),
        file_path=file_path,
        content=content,
        mode="create",
        target_repo=str(target.target_repo_path),
        priority=handoff.priority,
    )
    sm = psm.get_org_state_manager(target)
    sm.save_improvement_proposal(proposal)
    return proposal


# ---------------------------------------------------------------------------
# 本文ドラフトの自動執筆（承認ボタン → ほぼ完成原稿）
# ---------------------------------------------------------------------------
#
# materialize_handoff の「ブリーフ（型のスケルトン）」を一段進めて、本文ドラフトを生成する。
# 生成は Pantheon 標準どおり claude CLI（ClaudeCodeProvider）経由・API キーなし。
# claude が使えない（テスト/オフライン）ときは決定論テンプレート（型に沿った充填版）に
# フォールバックするので、常に何かしらの使えるドラフトが返る。


def _draft_system_prompt(kind: str) -> str:
    """受け手の kind 別に、検証済みの型・コンプラを織り込んだ system プロンプトを返す。"""
    base = (
        "あなたは日本市場の収益化に長けた日本語の編集者です。検証済みの『型』に厳密に従い、"
        "誇大表現・収益保証・虚偽は一切書かないでください。事実が不明な箇所は推測で埋めず "
        "`TODO:` で明示します。出力は記事に使える markdown 本文のみ。"
    )
    if kind == "audience_signal":
        return base + (
            "\n対象は note の有料記事ドラフト。構成: (1) タイトル案、(2) 無料エリア=試食 に必ず "
            "「①共感・問いかけ ②変化の物語(Before/After) ③ベネフィット提示」の3要素、"
            "(3) 有料エリア=フルコース の見出し構成（生ログ・プロンプト全文など一段深い差別化）、"
            "(4) 値付け案（入口500円＋3倍刻み 500/1500/5000円を前提）。"
        )
    if kind == "monetization_lead":
        return base + (
            "\n対象は物販レビュー/紹介セクション。必ず冒頭に明瞭な PR 表記（例『# PR』）を置く"
            "（ステマ規制 景表法）。A8.net 規約上 X にアフィリリンクは置かず note本文/YouTube概要欄 前提。"
            "構成: PR表記 / 誰におすすめか / 特徴 / メリット・デメリット（正直に）/ CTA。"
        )
    if kind == "content_brief":
        return base + (
            "\n対象は SNS 集客。構成: X の短文ポスト案を3〜5本（相互送客で note へ誘導、"
            "X には物販リンクを置かない）＋ YouTube 動画の構成案（概要欄CTA含む）。"
        )
    return base + "\n対象の引き渡しブリーフをもとに、実務で使えるドラフトを書いてください。"


def _draft_user_prompt(handoff: OrgHandoff) -> str:
    payload_lines = (
        "\n".join(f"- {k}: {v}" for k, v in (handoff.payload or {}).items()) or "（なし）"
    )
    return (
        f"# 引き渡し: {handoff.title}\n"
        f"種別: {handoff.kind}\n"
        f"送り手→受け手: {handoff.source_org} → {handoff.target_org}\n\n"
        f"## ペイロード\n{payload_lines}\n\n"
        "上記をもとに、指定の構成・型に沿った本文ドラフトを markdown で書いてください。"
    )


def _deterministic_draft(handoff: OrgHandoff, title: str) -> str:
    """claude が使えないときのフォールバック本文（型に沿った充填テンプレート）。"""
    _, _, skeleton = _brief_for(handoff)
    return (
        f"# {title}（本文ドラフト）\n\n"
        "> 注: claude CLI 不在のため決定論テンプレートで生成。`pantheon` を claude にログインさせると"
        " LLM が本文を執筆します。\n\n"
        + skeleton
    )


async def generate_draft_body(handoff: OrgHandoff) -> tuple[str, str]:
    """引き渡しから本文ドラフト (title, markdown) を生成する。

    claude CLI が使えれば LLM 生成、使えなければ決定論テンプレートにフォールバックする。
    例外時も決定論版を返す（best-effort・呼び出し側を失敗させない）。
    """
    _, title, _ = _brief_for(handoff)

    from core.runtime.claude_code import claude_available

    if not claude_available():
        return title, _deterministic_draft(handoff, title)

    try:
        from core.llm import LLMMessage, get_llm_provider

        provider = get_llm_provider()
        response = await provider.generate(
            messages=[
                LLMMessage(role="system", content=_draft_system_prompt(handoff.kind)),
                LLMMessage(role="user", content=_draft_user_prompt(handoff)),
            ],
            temperature=0.6,
            max_tokens=2500,
        )
        body = (getattr(response, "content", "") or "").strip()
        return (title, body) if body else (title, _deterministic_draft(handoff, title))
    except Exception:  # noqa: BLE001 - 生成失敗時は決定論版にフォールバック
        return title, _deterministic_draft(handoff, title)


async def draft_handoff(handoff: OrgHandoff, *, psm: Any) -> Any:
    """承認済み handoff から本文ドラフトの content_asset 提案を生成・保存する。

    materialize_handoff（ブリーフ）の一段先。受け手 org の正準ストアに保存され、PolicyEngine 上
    content_asset は human_required。受け手は通常の ``pantheon proposal apply`` で適用する。
    受け手 org が未登録 / target_repo_path 未設定なら ``None`` を返す。
    """
    from core.orchestration.asset_application import build_content_asset_proposal
    from core.runtime.claude_code import claude_available

    target = psm.load_organization_by_name(handoff.target_org)
    if target is None or not target.target_repo_path:
        return None

    title, body = await generate_draft_body(handoff)
    short = handoff.handoff_id.split(":")[-1][:8]
    engine = "LLM(claude)" if claude_available() else "決定論テンプレート"
    proposal = build_content_asset_proposal(
        title=f"本文ドラフト: {title}",
        description=(
            f"handoff {handoff.handoff_id}（{handoff.source_org} → {handoff.target_org} / "
            f"{handoff.kind}）から生成した本文ドラフト（{engine}）。承認・適用でワークスペースに入る。"
        ),
        file_path=f"content/draft-{short}.md",
        content=body,
        mode="create",
        target_repo=str(target.target_repo_path),
        priority=handoff.priority,
    )
    sm = psm.get_org_state_manager(target)
    sm.save_improvement_proposal(proposal)
    return proposal
