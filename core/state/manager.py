"""
Pantheon - Repo-Centric State Manager

すべての状態・決定・成果物をOrganizationのリポジトリ内にgit管理で残す。
これにより、複数のセッション（人間・AI）が非同期で協調可能になる。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from core.models.organization import is_active_improvement_proposal_status


class RepoStateManager:
    """
    各OrganizationのリポジトリRoot内に .pantheon/ ディレクトリを作り、
    状態を永続化する。
    """

    def __init__(self, repo_path: Path | str, org_name: str):
        self.repo_path = Path(repo_path)
        self.org_name = org_name
        self.state_dir = self.repo_path / ".pantheon"
        self.state_dir.mkdir(parents=True, exist_ok=True)

        # 主要ディレクトリ
        self.current_state_file = self.state_dir / "current_state.json"
        self.decisions_dir = self.state_dir / "decisions"
        self.workflows_dir = self.state_dir / "workflows"
        self.knowledge_dir = self.state_dir / "knowledge"
        self.artifacts_dir = self.state_dir / "artifacts"
        self.organizations_dir = self.state_dir / "organizations"
        self.sessions_dir = self.state_dir / "sessions"

        for d in [
            self.decisions_dir, self.workflows_dir, self.knowledge_dir,
            self.artifacts_dir, self.organizations_dir, self.sessions_dir,
        ]:
            d.mkdir(exist_ok=True)

    def save_current_state(self, state: Dict[str, Any]) -> None:
        """現在の全体状態を保存"""
        payload = dict(state)
        payload["last_updated"] = datetime.now(timezone.utc).isoformat()
        with open(self.current_state_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    def load_current_state(self) -> Dict[str, Any]:
        if self.current_state_file.exists():
            with open(self.current_state_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"organization": self.org_name, "status": "initialized"}

    def record_decision(
        self,
        decision_id: str,
        title: str,
        content: str,
        made_by: str,
        tags: Optional[list[str]] = None,
    ) -> Path:
        """重要な決定を記録"""
        decision = {
            "id": decision_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "title": title,
            "content": content,
            "made_by": made_by,
            "tags": tags or [],
        }
        path = self.decisions_dir / f"{decision_id}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(decision, f, ensure_ascii=False, indent=2)
        return path

    def get_recent_decisions(self, limit: int = 10) -> list[Dict[str, Any]]:
        """最近の決定を取得（他のセッションが参照するため）"""
        decisions = []
        for f in self.decisions_dir.glob("*.json"):
            with open(f, "r", encoding="utf-8") as fp:
                decisions.append(json.load(fp))

        def sort_key(decision: Dict[str, Any]) -> datetime:
            timestamp = str(decision.get("timestamp", ""))
            try:
                return datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            except ValueError:
                return datetime.min.replace(tzinfo=timezone.utc)

        return sorted(decisions, key=sort_key, reverse=True)[:limit]

    # ============================================================
    # Quality Review & Improvement Proposal 永続化
    # ============================================================

    def save_quality_review(self, review: "QualityReview") -> Path:
        """QualityReviewを .pantheon/reviews/ に保存"""
        reviews_dir = self.state_dir / "reviews"
        reviews_dir.mkdir(exist_ok=True)
        path = reviews_dir / f"{review.id}.json"
        with open(path, "w", encoding="utf-8") as f:
            f.write(review.model_dump_json(indent=2))
        return path

    def save_improvement_proposal(self, proposal: "ImprovementProposal") -> Path:
        """ImprovementProposalを .pantheon/improvements/ に保存"""
        improvements_dir = self.state_dir / "improvements"
        improvements_dir.mkdir(exist_ok=True)
        path = improvements_dir / f"{proposal.id}.json"
        with open(path, "w", encoding="utf-8") as f:
            f.write(proposal.model_dump_json(indent=2))
        return path

    def get_pending_improvement_proposals(self, limit: int = 20) -> list[Dict[str, Any]]:
        """未完了の改善提案を取得（Meta-Improvement Organizationが拾う用）"""
        improvements_dir = self.state_dir / "improvements"
        if not improvements_dir.exists():
            return []
        proposals = []
        for f in sorted(improvements_dir.glob("*.json"), reverse=True):
            with open(f, "r", encoding="utf-8") as fp:
                data = json.load(fp)
            if is_active_improvement_proposal_status(data.get("status")):
                proposals.append(data)
            if len(proposals) >= limit:
                break
        return proposals

    def save_proposal(self, proposal: "ImprovementProposal") -> bool:
        """Sprint 2 alias: ImprovementProposal を保存して成功可否を返す。"""
        self.save_improvement_proposal(proposal)
        return True

    def get_pending_proposals(self, limit: int = 20) -> list["ImprovementProposal"]:
        """Sprint 2 alias: 未対応 ImprovementProposal をモデルとして返す。"""
        from core.models.organization import ImprovementProposal

        proposals = []
        for data in self.get_pending_improvement_proposals(limit=limit):
            try:
                proposals.append(ImprovementProposal.model_validate(data))
            except Exception:
                continue
        return proposals

    def update_proposal_fields(self, proposal_id: str, **updates: Any) -> bool:
        """改善提案の任意フィールドを更新する。Returns True if successful."""
        improvements_dir = self.state_dir / "improvements"
        if not improvements_dir.exists():
            return False
        for f in improvements_dir.glob("*.json"):
            if f.stem == proposal_id:
                with open(f, "r", encoding="utf-8") as fp:
                    data = json.load(fp)
                data.update(updates)
                data["last_updated"] = datetime.now(timezone.utc).isoformat()
                with open(f, "w", encoding="utf-8") as fp:
                    json.dump(data, fp, ensure_ascii=False, indent=2)
                return True
        return False

    def update_proposal_status(self, proposal_id: str, status: str) -> bool:
        """改善提案のステータスを更新する。Returns True if successful."""
        return self.update_proposal_fields(proposal_id, status=status)

    # ============================================================
    # Organization 永続化
    # ============================================================

    def save_organization(self, org: "Organization") -> Path:
        """Organization を .pantheon/organizations/<id>.json に保存"""
        path = self.organizations_dir / f"{org.id}.json"
        path.write_text(org.model_dump_json(indent=2), encoding="utf-8")
        return path

    def load_organizations(self) -> list["Organization"]:
        """保存済みの全 Organization を読み込む"""
        from core.models.organization import Organization
        result = []
        for f in sorted(self.organizations_dir.glob("*.json")):
            try:
                result.append(Organization.model_validate_json(f.read_text(encoding="utf-8")))
            except Exception:
                continue
        return result

    def load_organization_by_name(self, name: str) -> "Organization | None":
        """名前で Organization を検索する"""
        for org in self.load_organizations():
            if org.name == name:
                return org
        return None

    def save_session_context(self, session_id: str, context: Dict[str, Any]) -> None:
        """セッション間で共有するコンテキストを保存する。"""
        path = self.sessions_dir / f"{session_id}.json"
        payload = dict(context)
        payload["session_id"] = session_id
        payload["saved_at"] = datetime.now(timezone.utc).isoformat()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    def load_session_context(self, session_id: str) -> Dict[str, Any] | None:
        """セッション間コンテキストを読み込む。"""
        path = self.sessions_dir / f"{session_id}.json"
        if not path.exists():
            return None
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def list_session_contexts(self) -> list[Dict[str, Any]]:
        """保存済みセッションコンテキストの一覧を返す。"""
        results = []
        for path in sorted(self.sessions_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                with open(path, encoding="utf-8") as f:
                    ctx = json.load(f)
                results.append({
                    "session_id": ctx.get("session_id", path.stem),
                    "saved_at": ctx.get("saved_at", ""),
                    "summary": ctx.get("summary", ""),
                })
            except Exception:
                continue
        return results

    def get_cross_org_state(self) -> Dict[str, Any]:
        """全組織をまたぐ共有状態を返す（タスクキューの概要等）。"""
        from core.orchestration.task_queue import TaskQueue

        queue = TaskQueue()
        return {
            "pending_tasks": len(queue.get_pending_tasks(limit=None)),
            "recent_tasks": queue.list_tasks(limit=5),
        }
