"""Convert high-scoring trends into actionable, human-gated proposals.

Two outputs, both behind the existing approval gate (nothing auto-publishes):

* **ContentJob draft** — a one-shot content brief seeded from the trend, added
  disabled so a human enables it (covers the "現状売れているものを真似る" angle:
  ride a hot topic immediately).
* **ImprovementProposal** — a "模倣候補" new-business idea recorded as a
  ``proposed`` proposal on the meta org (covers the originality + business
  expansion angle: a structured idea to evaluate later).

Conversion is idempotent via the trend hash so re-running never duplicates.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from uuid import NAMESPACE_URL, uuid5

from core.trends.models import TrendItem
from core.trends.store import TrendStore

logger = logging.getLogger(__name__)

# 安定 review_id 用の名前空間（dedupe_key 毎に決定論的な UUID を作り、再生成で
# 提案が重複しないようにする — hq_interventions.py と同じ思想）。
_TREND_NS = uuid5(NAMESPACE_URL, "pantheon.trends")

DEFAULT_MIN_SCORE = 7.0
DEFAULT_MAX_PER_RUN = 5
PROCESSED_FILENAME = "trends_processed.json"


def _processed_path(platform_home):
    from pathlib import Path

    return Path(platform_home) / "trends" / PROCESSED_FILENAME


def _load_processed(platform_home) -> set[str]:
    import json

    try:
        data = json.loads(_processed_path(platform_home).read_text(encoding="utf-8"))
        return set(data) if isinstance(data, list) else set()
    except (OSError, ValueError):
        return set()


def _save_processed(platform_home, hashes: set[str]) -> None:
    import json
    import os

    path = _processed_path(platform_home)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(sorted(hashes), ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)  # atomic: クラッシュで processed 集合が壊れない
    except OSError as exc:  # pragma: no cover
        logger.debug("failed to persist processed trends: %s", exc)


def _existing_dedupe_keys(sm) -> set[str]:
    """既存提案の dedupe_key 集合（再生成で提案を重複させないための突合用）。"""
    keys: set[str] = set()
    try:
        for p in sm.get_all_improvement_proposals(limit=2000):
            key = p.get("dedupe_key")
            if key:
                keys.add(str(key))
    except Exception:  # noqa: BLE001
        pass
    return keys


def _content_job_for(trend: TrendItem, org_name: str):
    from core.content.content_jobs import ContentJob

    theme = f"トレンド「{trend.title}」を題材にしたコンテンツ（出典: {trend.url}）"
    return ContentJob(
        org_name=org_name,
        kind="content_brief",
        theme=theme[:500],
        enabled=False,  # 人間が有効化するまで自動実行しない（承認ゲート）
    )


def _imitation_proposal(trend: TrendItem, org_name: str):
    from core.models.organization import ImprovementProposal

    title = f"[新規事業候補] {trend.title}"[:120]
    description = (
        f"高スコアトレンド（{trend.score:.1f}）を起点とする新規事業/コンテンツ候補。\n\n"
        f"出典: {trend.url}\n"
        f"ジャンル: {trend.genre or '(未分類)'}\n"
        f"要約: {trend.summary[:600]}\n\n"
        "売れている事例の模倣＋オリジナリティ付与の観点で評価し、承認なら "
        "Organization/コンテンツ施策へ展開する。"
    )
    return ImprovementProposal(
        # dedupe_key から決定論的に導出 → 再生成でも同一 id（重複排除が効く）
        review_id=uuid5(_TREND_NS, f"trend:{trend.hash}"),
        priority="high" if trend.score >= 8.5 else "medium",
        category="new_business",
        title=title,
        description=description,
        expected_impact=f"trend-score {trend.score:.1f} / {trend.source}",
        status="proposed",
        is_meta=True,  # file_path 無しの meta 提案
        dedupe_key=f"trend:{trend.hash}",
        target_kind="content_asset",
        source_org_name="TrendIntelligence",
    )


def convert_trends(
    *,
    platform_home=None,
    min_score: float = DEFAULT_MIN_SCORE,
    max_per_run: int = DEFAULT_MAX_PER_RUN,
    org_name: Optional[str] = None,
) -> Dict[str, Any]:
    """未処理の高スコアトレンドを ContentJob ドラフト＋提案へ変換する（承認ゲート経由）。

    冪等: trend hash で処理済みを記録し、再実行で重複生成しない。
    戻り値: {"converted": int, "content_jobs": int, "proposals": int, "skipped": int}
    """
    if platform_home is None:
        from core.platform.state import get_platform_home

        platform_home = get_platform_home()

    from core.platform.state import PlatformStateManager

    psm = PlatformStateManager(platform_home)

    # 受け手 org: 明示指定 → 既存の content 系 org → Meta org → 先頭 org
    org = _resolve_target_org(psm, org_name)
    if org is None:
        return {"converted": 0, "content_jobs": 0, "proposals": 0, "skipped": 0, "reason": "no_org"}

    processed = _load_processed(platform_home)
    store = TrendStore(platform_home)
    candidates: List[TrendItem] = [
        t for t in store.list(limit=200, min_score=min_score) if t.hash not in processed
    ]

    from core.content.content_jobs import ContentJobStore

    job_store = ContentJobStore(platform_home)
    sm = psm.get_org_state_manager(org)

    # アーティファクト単位の冪等化: ContentJob は既存 theme に出典 URL が含まれるかで、
    # 提案は dedupe_key で重複判定する。これにより processed.json はあくまで最適化であり、
    # 部分失敗（job 成功・proposal 失敗等）でも二重生成しない。
    existing_job_themes = [j.theme for j in job_store.list_jobs()]
    existing_dedupe = _existing_dedupe_keys(sm)

    content_jobs = 0
    proposals = 0
    for trend in candidates[:max_per_run]:
        marker = f"trend:{trend.hash}"
        # ContentJob ドラフト（出典 URL 既出なら成功扱いでスキップ）
        job_ok = bool(trend.url) and any(trend.url in theme for theme in existing_job_themes)
        if trend.url and not job_ok:
            try:
                job = _content_job_for(trend, org.name)
                job_store.add_job(job)
                existing_job_themes.append(job.theme)
                content_jobs += 1
                job_ok = True
            except Exception as exc:  # noqa: BLE001
                logger.info("trend job creation failed for %s: %s", trend.hash, exc)
        elif not trend.url:
            job_ok = True  # URL 無しは job 対象外（提案のみ）
        # 模倣候補 ImprovementProposal（dedupe_key 既出なら成功扱いでスキップ）
        proposal_ok = marker in existing_dedupe
        if not proposal_ok:
            try:
                sm.save_improvement_proposal(_imitation_proposal(trend, org.name))
                existing_dedupe.add(marker)
                proposals += 1
                proposal_ok = True
            except Exception as exc:  # noqa: BLE001
                logger.info("trend proposal creation failed for %s: %s", trend.hash, exc)
        # 両アーティファクトが揃ったトレンドだけ processed に記録する（部分失敗は次回
        # 再試行され、URL/dedupe_key の冪等チェックが二重生成を防ぐ）。
        if job_ok and proposal_ok:
            processed.add(trend.hash)

    _save_processed(platform_home, processed)
    return {
        "converted": content_jobs,
        "content_jobs": content_jobs,
        "proposals": proposals,
        "skipped": max(0, len(candidates) - max_per_run),
    }


def propose_claude_code_updates(*, platform_home=None, max_per_run: int = 3) -> Dict[str, Any]:
    """``claude_code`` ジャンルの新トレンドを ``.claude/`` 設定更新提案へ変換する。

    Anthropic/Claude Code 自体の進化（新機能・新モデル・ベストプラクティス）を拾い、
    リポジトリの Claude Code 設定を見直す meta 提案を承認ゲート付きで起票する。
    トレンド監視 daemon の週次相当ステップ。冪等（trend hash で処理済み記録）。
    """
    if platform_home is None:
        from core.platform.state import get_platform_home

        platform_home = get_platform_home()

    from core.models.organization import ImprovementProposal
    from core.platform.state import PlatformStateManager

    psm = PlatformStateManager(platform_home)
    org = _resolve_target_org(psm, None)
    if org is None:
        return {"proposals": 0, "reason": "no_org"}

    processed = _load_processed(platform_home)
    store = TrendStore(platform_home)
    candidates = [
        t for t in store.list(limit=100, genre="claude_code") if f"cc:{t.hash}" not in processed
    ]

    sm = psm.get_org_state_manager(org)
    existing_dedupe = _existing_dedupe_keys(sm)
    made = 0
    for trend in candidates[:max_per_run]:
        dedupe_key = f"cc-trend:{trend.hash}"
        if dedupe_key in existing_dedupe:  # 既存提案と重複しない（再生成耐性）
            processed.add(f"cc:{trend.hash}")
            continue
        try:
            proposal = ImprovementProposal(
                review_id=uuid5(_TREND_NS, dedupe_key),
                priority="medium",
                category="claude_code_config",
                title=f"[CC設定見直し] {trend.title}"[:120],
                description=(
                    "Claude Code / Anthropic の新トレンドを受けて、リポジトリの "
                    "`.claude/` 設定（agents/skills/commands/hooks/MCP/モデルティア）の"
                    "見直しを検討する。\n\n"
                    f"出典: {trend.url}\n要約: {trend.summary[:600]}"
                ),
                expected_impact="開発体験・自動化の最新化",
                status="proposed",
                is_meta=True,
                dedupe_key=dedupe_key,
                target_kind="org_structure",
                source_org_name="TrendIntelligence",
            )
            sm.save_improvement_proposal(proposal)
            existing_dedupe.add(dedupe_key)
            processed.add(f"cc:{trend.hash}")
            made += 1
        except Exception as exc:  # noqa: BLE001
            logger.info("cc trend proposal failed for %s: %s", trend.hash, exc)

    _save_processed(platform_home, processed)
    return {"proposals": made}


def _resolve_target_org(psm, org_name: Optional[str]):
    if org_name:
        org = psm.load_organization_by_name(org_name)
        if org is not None:
            return org
    orgs = psm.load_organizations()
    if not orgs:
        return None
    # content/メタ系を優先、無ければ先頭
    for org in orgs:
        if "content" in (org.name or "").lower() or "meta" in (org.name or "").lower():
            return org
    return orgs[0]
