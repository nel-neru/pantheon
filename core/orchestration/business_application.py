"""承認済み new_business 提案 → ライブな Organization + Business への自動組成（拡張: フライホイール actuate）。

トレンド→新規会社候補提案（``category=new_business``）が承認インボックスで止まりがちな摩擦を解消し、
「承認したら 1 アクションで会社（Organization）と事業（Business）が立ち上がる」までを開通する。

HITL 安全性: 提案は **人手承認後** に明示操作（CLI/Web ボタン）で呼ばれる前提。生成物は
external/workspace の INCUBATING な Organization と Business エンティティのみで、外部送信・課金は伴わない。
決定論・LLM 非依存（事業部は既存の plugin_templates プリセットから組み立てる）。
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

# new_business 提案の suggested_divisions（DivisionType 値）→ plugin_templates カテゴリ。
_TYPE_TO_CATEGORY: Dict[str, str] = {
    "audience_development": "audience",
    "content_production": "content",
    "monetization": "monetization",
    "org_evolution": "operations",
}

# 事業部の日本語ラベル（表示名）。
_TYPE_LABEL: Dict[str, str] = {
    "audience_development": "集客事業部",
    "content_production": "コンテンツ制作事業部",
    "monetization": "収益化事業部",
    "org_evolution": "改善・運用事業部",
}


def _proposal_field(proposal: Any, key: str, default: Any = None) -> Any:
    """提案（dict か ImprovementProposal）から属性/キーを安全に取り出す。"""
    if isinstance(proposal, dict):
        value = proposal.get(key, default)
    else:
        value = getattr(proposal, key, default)
    return value if value is not None else default


def _workspace_dir(psm: Any, org_name: str):
    """install_company_plugin と同じ規約で会社のワークスペース dir を用意する（非 ASCII 衝突回避）。"""
    import hashlib
    from pathlib import Path

    root = getattr(psm, "get_workspaces_root", lambda: None)() or (psm.platform_home / "workspaces")
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", org_name).strip("-")
    if not org_name.isascii() or not slug:
        digest = hashlib.sha1(org_name.encode("utf-8")).hexdigest()[:8]
        slug = f"{slug}-{digest}" if slug else f"company-{digest}"
    ws = Path(root) / slug
    try:
        ws.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return ws


def scaffold_business_from_proposal(proposal: Any, *, psm: Any) -> Dict[str, Any]:
    """承認済み new_business 提案から Organization と Business を組成する。

    提案の ``intervention_spec``（kind=new_business, name, genre, divisions）を読み、
    workspace/external の Organization を起動し、suggested_divisions を正しい型の事業部として
    取り付け、それを member とする Business を保存する。同名 org は再利用（冪等）。

    未知/非 new_business 提案は ValueError。戻り値:
    ``{"ok", "org_name", "business_name", "divisions", "reused_org"}``。
    """
    from core.models.business import Business
    from core.models.organization import Organization, OrganizationStatus
    from core.orchestration.plugin_templates import scaffold_division_plugin
    from core.org_factory import _build_division
    from core.platform.business_store import BusinessStore

    if str(_proposal_field(proposal, "category", "")) != "new_business":
        raise ValueError("new_business カテゴリの提案ではありません")

    spec = _proposal_field(proposal, "intervention_spec", {}) or {}
    if not isinstance(spec, dict):
        spec = {}
    title = str(_proposal_field(proposal, "title", "") or "")
    # 構造化 spec を優先。古い提案（spec 無し）は title から会社名を復元する。
    name = str(spec.get("name") or "").strip()
    if not name:
        name = title.replace("[新規会社候補]", "").strip() or "新規事業"
    genre = str(spec.get("genre") or "").strip()
    div_types: List[str] = [str(d) for d in (spec.get("divisions") or []) if str(d).strip()]

    reused = psm.load_organization_by_name(name)
    if reused is not None:
        org = reused
        reused_org = True
    else:
        ws = _workspace_dir(psm, name)
        org = Organization(
            name=name,
            purpose=f"{name}（トレンド由来の新規収益モデル会社）",
            management_mode="workspace",
            workspace_path=str(ws),
            status=OrganizationStatus.INCUBATING,
            isolation_level="external",
        )
        if genre:
            org.industry_genre = genre
        for div_type in div_types:
            category = _TYPE_TO_CATEGORY.get(div_type, "operations")
            label = _TYPE_LABEL.get(div_type, f"{div_type}事業部")
            dept = scaffold_division_plugin(div_type, label, category)["department"]
            org.add_division(_build_division(dept))
        psm.save_organization(org)
        reused_org = False

    # member 1 社の Business を作る（提案 1 件＝事業 1 つ）。同名は再利用（冪等）。
    store = BusinessStore(platform_home=psm.platform_home)
    business = store.get(name)
    if business is None:
        business = Business(
            name=name,
            purpose=genre or "トレンド由来の新規事業",
            member_orgs=[org.name],
        )
        store.save(business)

    return {
        "ok": True,
        "org_name": org.name,
        "business_name": business.name,
        "divisions": [d.name for d in org.divisions],
        "reused_org": reused_org,
    }


def find_new_business_proposal(
    psm: Any, org_name: str, proposal_id: str
) -> Optional[Dict[str, Any]]:
    """対象 org の状態から new_business 提案（id 先頭一致）を探す。無ければ None。"""
    org = psm.load_organization_by_name(org_name)
    if org is None:
        return None
    sm = psm.get_org_state_manager(org)
    for p in sm.get_all_improvement_proposals(limit=500):
        if str(p.get("id", "")).startswith(proposal_id) and p.get("category") == "new_business":
            return p
    return None
