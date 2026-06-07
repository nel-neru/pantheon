"""
Asset Application — 収益 Organization 等のコンテンツ資産を *ワークスペース内に安全に*
生成/更新する経路（Phase 6 の非コード提案 + Phase 7 の制御された行為面）。

設計思想:
- コードファイル改善（LLM 書換 / git ブランチ・PR）とは別経路。記事・コピー・スクリプト等を
  対象 Organization の ``target_repo`` ワークスペース *内部にだけ* 書き込む。
- **外部投稿・公開は一切行わない**（Phase 7 はワークスペース内アーティファクト生成までに限定）。
  生成物は git で版管理され、外部スケジューラ/ランナーが別途実行する前提。
- 適用は **PolicyEngine 承認後** にのみ呼ばれる（content_asset は publishing 近接のため
  human_required）。書き込みは repo ルート外へ絶対に出ない（パストラバーサル防止）。
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict
from uuid import UUID, uuid5

from core.models.organization import (
    CONTENT_ASSET_CATEGORY,
    CONTENT_ASSET_TARGET_KIND,
    ImprovementProposal,
)

if TYPE_CHECKING:
    pass

_REVIEW_NAMESPACE = UUID("b2e2a0de-7c20-4f3b-8d44-1a6f6f6f6f6f")
_VALID_MODES = ("create", "overwrite", "append")

# Asset executor の capability id（routing の最終フォールバックに使う）。
ASSET_APPLICATION_AGENT_ID = "agent:asset_executor"


class AssetApplicationError(ValueError):
    """ワークスペース資産を適用できないときに送出する（呼び出し側で 4xx/失敗に変換）。"""


def _as_field(proposal: ImprovementProposal | Dict[str, Any], key: str) -> Any:
    if isinstance(proposal, ImprovementProposal):
        return getattr(proposal, key, None)
    return proposal.get(key)


def _proposal_as_dict(proposal: ImprovementProposal | Dict[str, Any]) -> Dict[str, Any]:
    if isinstance(proposal, ImprovementProposal):
        return proposal.model_dump(mode="json")
    return dict(proposal)


def _resolve_workspace_path(repo_root: Path, rel: str) -> Path:
    """ワークスペース内の安全な絶対パスへ解決する（root 外への脱出を拒否）。"""
    candidate = Path(rel)
    if candidate.is_absolute():
        raise AssetApplicationError("絶対パスは指定できません（ワークスペース相対パスのみ）。")
    if any(part == ".." for part in candidate.parts):
        raise AssetApplicationError("パストラバーサル（..）は許可されません。")
    resolved_root = Path(repo_root).resolve()
    resolved = (resolved_root / candidate).resolve(strict=False)
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise AssetApplicationError("ワークスペース外への書き込みは許可されません。") from exc
    return resolved


def apply_content_asset(
    proposal: ImprovementProposal | Dict[str, Any],
    *,
    repo_root: Path | str,
) -> Dict[str, Any]:
    """承認済みの content_asset 提案をワークスペース内に安全適用する（永続=ファイル書込）。

    提案の形:
      file_path: ワークスペース相対パス（例 "articles/foo.md"）
      intervention_spec: {"content": <str>, "mode": "create"|"overwrite"|"append"}
    """
    root = Path(repo_root)
    if not root.exists() or not root.is_dir():
        raise AssetApplicationError(f"ワークスペースが存在しません: {root}")

    file_path = _as_field(proposal, "file_path") or ""
    spec = _as_field(proposal, "intervention_spec") or {}
    content = spec.get("content")
    mode = str(spec.get("mode") or "create").lower()

    if not file_path:
        raise AssetApplicationError("content_asset: file_path が必要です。")
    if content is None:
        raise AssetApplicationError("content_asset: intervention_spec.content が必要です。")
    if mode not in _VALID_MODES:
        raise AssetApplicationError(
            f"content_asset: 不正な mode '{mode}'（許可: {', '.join(_VALID_MODES)}）。"
        )

    content = str(content)
    target = _resolve_workspace_path(root, file_path)
    rel = str(target.relative_to(root.resolve()))

    if mode == "create" and target.exists():
        return {
            "applied": False,
            "file_path": rel,
            "mode": mode,
            "reason": "既に存在します（mode=create のためスキップ）。",
        }

    target.parent.mkdir(parents=True, exist_ok=True)
    if mode == "append" and target.exists():
        existing = target.read_text(encoding="utf-8")
        target.write_text(existing + content, encoding="utf-8")
    else:
        target.write_text(content, encoding="utf-8")

    return {
        "applied": True,
        "file_path": rel,
        "mode": mode,
        "bytes_written": len(content.encode("utf-8")),
    }


def _dedupe_key(target_repo: str, file_path: str, title: str) -> str:
    raw = f"{target_repo}|{file_path}|{title}".encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:16]


def build_content_asset_proposal(
    *,
    title: str,
    description: str,
    file_path: str,
    content: str,
    mode: str = "create",
    target_repo: str = "",
    priority: str = "medium",
) -> ImprovementProposal:
    """ワークスペース資産（content_asset）提案を組み立てる（安定 dedupe_key / review_id）。"""
    dedupe_key = _dedupe_key(target_repo, file_path, title)
    review_id = uuid5(_REVIEW_NAMESPACE, dedupe_key)
    return ImprovementProposal(
        review_id=review_id,
        title=title,
        description=description,
        priority=priority,
        category=CONTENT_ASSET_CATEGORY,
        file_path=file_path,
        dedupe_key=dedupe_key,
        target_kind=CONTENT_ASSET_TARGET_KIND,
        intervention_spec={"content": content, "mode": mode},
    )


async def execute_content_asset(
    proposal: ImprovementProposal | Dict[str, Any],
    *,
    repo_path: Path | str,
    record: bool = True,
) -> Any:
    """承認済み content_asset を **PreTaskOrchestrator 経由** で適用する（no-bypass）。"""
    from agents.base import AgentTask
    from core.intelligence.capability_registry import CapabilityRegistry
    from core.orchestration.orchestration_pattern_store import OrchestrationPatternStore
    from core.orchestration.pre_task_orchestrator import PreTaskOrchestrator
    from core.platform.state import get_platform_home

    platform_home = get_platform_home()
    registry = CapabilityRegistry(platform_home=platform_home)
    try:
        if not registry.has_capability(ASSET_APPLICATION_AGENT_ID):
            registry.scan_and_register_all()
    except Exception:  # noqa: BLE001 - スキャン不能でもフォールバックで実行できる
        pass

    store = OrchestrationPatternStore(platform_home=platform_home)
    orchestrator = PreTaskOrchestrator(capability_registry=registry, pattern_store=store)

    title = _as_field(proposal, "title") or "content asset"
    description = f"ワークスペース資産の適用: {title}"
    analysis = orchestrator.analyze("content_asset_application", description)
    others = [a for a in (analysis.recommended_agent_ids or []) if a != ASSET_APPLICATION_AGENT_ID]
    analysis.recommended_agent_ids = [ASSET_APPLICATION_AGENT_ID, *others]

    task = AgentTask(
        task_type="content_asset_application",
        description=description,
        input={"proposal": _proposal_as_dict(proposal), "repo_path": str(repo_path)},
    )
    return await orchestrator.execute(task, analysis, record=record)
