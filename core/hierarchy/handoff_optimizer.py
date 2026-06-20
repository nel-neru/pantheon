"""
HandoffOptimizer — 集客 org（リーチ有・収益弱）→ 収益化 org への handoff を推奨する純粋関数
（P2.4 連携最適化 / 収益フライホイールの結合提案）。

設計思想:
- ``OrgHandoff`` ストア（``core/hierarchy/org_handoff.py``）が «どの引き渡しを記録/承認したか»
  を扱うのに対し、ここは «どの org からどの org へ引き渡すべきか» の **推奨**だけを返す。
  永続化・LLM 呼び出し・外部 API には一切依存しない、決定論的で冪等な純粋関数。
- 「リーチはあるが収益が弱い org（audience）」の関心を、「収益化できる org（monetization）」へ
  橋渡しすると収益フライホイールが回る、というドメイン仮説をコード化したもの。
- 役割（role）が入力で与えられていればそれを尊重し、未指定なら reach/revenue から推定する。
  実際の引き渡し配線（kind・payload・承認）は ``OrgHandoff`` 側 / 各組織の運用が定義する。
"""

from __future__ import annotations

from typing import Any, Dict, List

from core.persistence import coerce_float

# 役割ラベル。audience = リーチ源（集客）、monetization = 収益化先。
ROLE_AUDIENCE = "audience"
ROLE_MONETIZATION = "monetization"


def _classify_role(role: Any, reach: float, revenue: float) -> str:
    """role を正規化/推定する。

    明示 role（audience/monetization）はそのまま尊重。未指定/空/不明な値のときは
    reach>0 かつ revenue<=0 を audience、revenue>0 を monetization と推定する。
    どちらにも当てはまらない（例: reach も revenue も 0）場合は空文字（=対象外）。
    """
    normalized = str(role).strip().lower() if role is not None else ""
    if normalized in (ROLE_AUDIENCE, ROLE_MONETIZATION):
        return normalized
    # 推定: 収益が出ていれば収益化、収益が無くリーチがあれば集客。
    if revenue > 0:
        return ROLE_MONETIZATION
    if reach > 0:
        return ROLE_AUDIENCE
    return ""


def recommend_handoffs(org_stats: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """集客 org → 収益化 org の handoff 推奨を生成する（純粋・決定論・冪等）。

    Args:
        org_stats: 各 org の統計 dict のリスト。各要素は以下のキーを持つ:
            - ``org_name`` (str): 組織名（必須）。
            - ``reach`` (number): リーチ規模（インプレッション/フォロワー等の合算指標）。
            - ``revenue`` (number): 収益額。
            - ``role`` (str, 任意): ``"audience"`` / ``"monetization"`` / ``""``。
              未指定なら reach/revenue から推定する。

    Returns:
        ``{"from_org", "to_org", "reason", "priority"}`` の dict リスト。
        各 audience org に対し、最も revenue の高い monetization org を 1 件だけ宛先にする。
        並び順は audience org の reach 降順（同 reach は入力順で安定）。
        monetization org が無い、または audience org が無い場合は空リスト。

    決定論性:
        同 revenue の monetization が複数あるときは入力順で先勝ち。
        同 reach の audience は入力順を保つ（安定ソート）。ゼロ除算は発生しない。
    """
    audiences: List[Dict[str, Any]] = []
    monetizers: List[Dict[str, Any]] = []

    # 入力を 1 度走査し、役割ごとに分類する（入力順を保持）。
    for raw in org_stats or []:
        if not isinstance(raw, dict):
            continue
        name = raw.get("org_name")
        if not name:
            continue
        reach = coerce_float(raw.get("reach"))
        revenue = coerce_float(raw.get("revenue"))
        role = _classify_role(raw.get("role"), reach, revenue)
        entry = {"org_name": str(name), "reach": reach, "revenue": revenue}
        if role == ROLE_AUDIENCE:
            audiences.append(entry)
        elif role == ROLE_MONETIZATION:
            monetizers.append(entry)

    # どちらかが欠ければ推奨は成立しない。
    if not audiences or not monetizers:
        return []

    # 宛先は «最も収益の高い» 収益化 org 1 件。max は安定（同値は先勝ち）。
    target = max(monetizers, key=lambda m: m["revenue"])

    # audience を reach 降順で安定ソート（同 reach は元の入力順を維持）。
    ordered_audiences = sorted(audiences, key=lambda a: a["reach"], reverse=True)

    recommendations: List[Dict[str, Any]] = []
    for audience in ordered_audiences:
        reason = (
            f"{audience['org_name']} はリーチ {audience['reach']:.0f} を持つが収益が弱い。"
            f" 最も収益化できる {target['org_name']}（収益 {target['revenue']:.0f}）へ"
            f" 関心を引き渡すと収益フライホイールが回る。"
        )
        recommendations.append(
            {
                "from_org": audience["org_name"],
                "to_org": target["org_name"],
                "reason": reason,
                # priority: リーチが大きいほど引き渡し効果が大きいと見なし高くする。
                "priority": audience["reach"],
            }
        )
    return recommendations
