"""
Atlas → ImprovementProposal generator

Repository Atlas が把握している各フローの ``known_issues`` を、安定 ID（dedupe_key）付きの
**meta-level** ``ImprovementProposal`` に変換する。Meta-Improvement Organization の
``<repo>/.pantheon/improvements/`` に保存することで、自己改善ループ（platform run-all 等）が
拾えるようになる ＝ 「Atlas を自己改善の燃料にする」。

純粋・オフライン（生成系に非依存）。再実行しても dedupe_key により重複を作らない。
"""

from __future__ import annotations

import hashlib
import uuid
from typing import TYPE_CHECKING, Any

from core.models.organization import ImprovementProposal

if TYPE_CHECKING:  # pragma: no cover - 型ヒントのみ（実行時 import 回避）
    from core.state.manager import RepoStateManager

# Atlas issue の severity → 提案 priority
_SEVERITY_TO_PRIORITY = {"high": "high", "medium": "medium", "low": "low"}
# dedupe_key 由来の安定 review_id を作るための名前空間
_REVIEW_NAMESPACE = uuid.UUID("a7c0ffee-a7c0-4a7c-8a7c-a7c0ffeea7c0")


def _normalize_file(raw: str | None) -> str:
    """issue の file をリポジトリ相対パスへ正規化する（絶対 Windows パスが混じっても安全）。"""
    if not raw:
        return ""
    path = str(raw).replace("\\", "/").strip()
    # 絶対パスが紛れ込んだ場合はリポジトリ名以降に丸める（best-effort）
    for marker in ("/pantheon/", "/Pantheon/"):
        if marker in path:
            path = path.split(marker, 1)[1]
            break
    return path


def _dedupe_key(flow_id: str, title: str, file_path: str) -> str:
    raw = f"{flow_id}|{title}|{file_path}".encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:16]


def build_atlas_proposals(atlas: dict[str, Any]) -> list[ImprovementProposal]:
    """Atlas モデルの known_issues を ImprovementProposal のリストへ変換する（純粋関数）。"""
    proposals: list[ImprovementProposal] = []
    for flow in atlas.get("flows", []):
        flow_id = str(flow.get("id", ""))
        flow_name = str(flow.get("name", flow_id))
        for issue in flow.get("known_issues", []) or []:
            title = str(issue.get("title", "")).strip()
            if not title:
                continue
            file_path = _normalize_file(issue.get("file"))
            dedupe_key = _dedupe_key(flow_id, title, file_path)
            severity = str(issue.get("severity", "medium")).lower()
            priority = _SEVERITY_TO_PRIORITY.get(severity, "medium")
            detail = str(issue.get("detail", "")).strip()
            description = (
                f"[Atlas/{flow_name}] {detail}\n\n"
                f"このフローの既知の問題から自動生成された meta 提案です（severity={severity}）。"
            )
            proposals.append(
                ImprovementProposal(
                    review_id=uuid.uuid5(_REVIEW_NAMESPACE, dedupe_key),
                    title=f"[meta] {title}",
                    description=description,
                    priority=priority,
                    category="meta",
                    file_path=file_path,
                    expected_impact=f"フロー『{flow_name}』の信頼性向上",
                    is_meta=True,
                    dedupe_key=dedupe_key,
                )
            )
    return proposals


def _existing_dedupe_keys(state_manager: "RepoStateManager") -> set[str]:
    """保存済み（terminal 含む全件）提案の dedupe_key 集合を返す。"""
    keys: set[str] = set()
    improvements_dir = state_manager.state_dir / "improvements"
    if not improvements_dir.exists():
        return keys
    import json

    for path in improvements_dir.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        key = data.get("dedupe_key")
        if key:
            keys.add(str(key))
    return keys


def generate_atlas_proposals(
    atlas: dict[str, Any],
    state_manager: "RepoStateManager",
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Atlas から meta 提案を生成し、重複を除いて state_manager に保存する。

    Returns: {"created": [...titles], "skipped": [...titles], "total": int, "dry_run": bool}
    """
    proposals = build_atlas_proposals(atlas)
    existing = _existing_dedupe_keys(state_manager)
    created: list[str] = []
    skipped: list[str] = []
    seen_this_run: set[str] = set()

    for proposal in proposals:
        key = proposal.dedupe_key
        if key in existing or key in seen_this_run:
            skipped.append(proposal.title)
            continue
        seen_this_run.add(key)
        if not dry_run:
            state_manager.save_improvement_proposal(proposal)
        created.append(proposal.title)

    return {
        "created": created,
        "skipped": skipped,
        "total": len(proposals),
        "dry_run": dry_run,
    }
