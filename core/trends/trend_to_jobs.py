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

from core.persistence import atomic_write_text
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

    path = _processed_path(platform_home)
    try:
        # atomic_write_text: クラッシュ/並行書き込みで processed 集合が壊れない（torn write 防止）
        atomic_write_text(path, json.dumps(sorted(hashes), ensure_ascii=False))
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

    # タイトルを先に切り詰めてから URL を付与する（全体切り詰めで出典が消えないように）。
    title = (trend.title or "")[:300]
    theme = f"トレンド「{title}」を題材にしたコンテンツ（出典: {trend.url}）"
    return ContentJob(
        org_name=org_name,
        kind="content_brief",
        theme=theme,
        enabled=False,  # 人間が有効化するまで自動実行しない（承認ゲート）
        source_trend_hash=trend.hash,  # 重複排除は theme ではなくこの hash で行う
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
        # review_id を dedupe_key から決定論化（来歴の安定化）。実際の重複排除は
        # 呼び出し側の dedupe_key 突合で行う（id は uuid4 のまま）。
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
    戻り値: {"converted": int, "content_jobs": int, "proposals": int,
             "failed": int, "skipped": int}

    ``failed`` は max_per_run 内で「両アーティファクトが揃わなかった」トレンド数
    （job/proposal 生成例外などの部分・全失敗）。これを surface しないと呼び出し側
    （trend daemon の summary）が「新規ゼロ」と「全件失敗」を区別できず、健全な無変換
    サイクルと壊れたサイクルが同じ ``proposals:0`` に潰れる（メトリクス母数の黙殺）。
    """
    if platform_home is None:
        from core.platform.state import get_platform_home

        platform_home = get_platform_home()

    from core.platform.state import PlatformStateManager

    psm = PlatformStateManager(platform_home)

    # 受け手 org: 明示指定 → 既存の content 系 org → Meta org → 先頭 org
    org = _resolve_target_org(psm, org_name)
    if org is None:
        return {
            "converted": 0,
            "content_jobs": 0,
            "proposals": 0,
            "failed": 0,
            "skipped": 0,
            "reason": "no_org",
        }

    processed = _load_processed(platform_home)
    store = TrendStore(platform_home)
    candidates: List[TrendItem] = [
        t for t in store.list(limit=200, min_score=min_score) if t.hash not in processed
    ]

    from core.content.content_jobs import ContentJobStore

    job_store = ContentJobStore(platform_home)
    sm = psm.get_org_state_manager(org)

    # アーティファクト単位の冪等化: ContentJob は source_trend_hash の完全一致で、
    # 提案は dedupe_key で重複判定する（theme の部分一致や切り詰めに依存しない）。
    # これにより processed.json はあくまで最適化であり、部分失敗でも二重生成しない。
    existing_job_hashes = {
        h for j in job_store.list_jobs() if (h := getattr(j, "source_trend_hash", ""))
    }
    existing_dedupe = _existing_dedupe_keys(sm)

    content_jobs = 0
    proposals = 0
    failed = 0
    for trend in candidates[:max_per_run]:
        marker = f"trend:{trend.hash}"
        # ContentJob ドラフト（同 trend hash の job が既存なら成功扱いでスキップ）
        job_ok = trend.hash in existing_job_hashes
        if not job_ok:
            try:
                job_store.add_job(_content_job_for(trend, org.name))
                existing_job_hashes.add(trend.hash)
                content_jobs += 1
                job_ok = True
            except Exception as exc:  # noqa: BLE001
                logger.info("trend job creation failed for %s: %s", trend.hash, exc)
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
        # 再試行され、hash/dedupe_key の冪等チェックが二重生成を防ぐ）。揃わなかった
        # トレンドは failed に計上し、無変換と失敗を区別可能にする（観測化）。
        if job_ok and proposal_ok:
            processed.add(trend.hash)
        else:
            failed += 1

    _save_processed(platform_home, processed)
    return {
        "converted": content_jobs,
        "content_jobs": content_jobs,
        "proposals": proposals,
        "failed": failed,
        "skipped": max(0, len(candidates) - max_per_run),
    }


def propose_claude_code_updates(*, platform_home=None, max_per_run: int = 3) -> Dict[str, Any]:
    """``claude_code`` ジャンルの新トレンドを ``.claude/`` 設定更新提案へ変換する。

    Anthropic/Claude Code 自体の進化（新機能・新モデル・ベストプラクティス）を拾い、
    リポジトリの Claude Code 設定を見直す meta 提案を承認ゲート付きで起票する。
    トレンド監視 daemon の週次相当ステップ。冪等（trend hash で処理済み記録）。
    戻り値: {"proposals": int, "failed": int}（``failed`` は提案生成で例外を出した件数）。
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
    failed = 0
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
            failed += 1
            logger.info("cc trend proposal failed for %s: %s", trend.hash, exc)

    _save_processed(platform_home, processed)
    return {"proposals": made, "failed": failed}


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
