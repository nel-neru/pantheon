"""
ConversationAgent — 開発者との自然言語会話エージェント (I-01)

開発者の質問を受け取り、蓄積データ（KnowledgeManager・提案・組織状態）を
参照して自然言語で回答する。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from core.platform.state import get_platform_home


@dataclass
class ConversationResponse:
    question: str
    answer: str
    confidence: float
    sources: list[str] = field(default_factory=list)
    suggested_actions: list[str] = field(default_factory=list)


class ConversationAgent:
    def __init__(self, knowledge_manager=None, platform_home: Path = None):
        self.knowledge_manager = knowledge_manager
        self.platform_home = Path(platform_home) if platform_home else get_platform_home()
        self.platform_home.mkdir(parents=True, exist_ok=True)
        self._history: list[dict[str, str]] = []

    def ask(self, question: str, context: dict = None) -> ConversationResponse:
        context = context or {}
        keywords = self._parse_keywords(question)
        knowledge_hits = self._search_knowledge(keywords)
        sources = self._build_sources(knowledge_hits)

        pending_count = int(context.get("pending_proposals", self._count_pending_proposals()))
        known_issue_count = int(
            context.get("known_issue_count", self._count_known_issues(knowledge_hits))
        )
        health_summary = context.get("health_summary") or self._describe_health()

        answer = (
            "データを参照しましたが、具体的な回答を生成できませんでした。"
            "`repocorp analyze`を実行してみてください。"
        )
        confidence = 0.3
        suggested_actions = ["repocorp analyze"]

        if any(token in question for token in ("危険", "リスク", "問題")):
            answer = (
                f"既知の問題は{known_issue_count}件あります。"
                "追加の状況確認には `repocorp analyze` を実行してください。"
            )
            confidence = 0.8 if known_issue_count or sources else 0.55
            suggested_actions = ["repocorp analyze"]
            if "platform:pending_proposals" not in sources and pending_count:
                sources.append("platform:pending_proposals")
        elif any(token in question for token in ("提案", "改善")):
            answer = f"現在の未処理提案は{pending_count}件です。優先順位を確認して改善を進められます。"
            confidence = 0.85 if pending_count or sources else 0.5
            suggested_actions = ["repocorp proposals list", "repocorp analyze"]
            if "platform:pending_proposals" not in sources:
                sources.append("platform:pending_proposals")
        elif any(token in question for token in ("状態", "健康")):
            answer = health_summary
            confidence = 0.75
            suggested_actions = ["repocorp analyze"]
            if "platform:organizations" not in sources:
                sources.append("platform:organizations")

        response = ConversationResponse(
            question=question,
            answer=answer,
            confidence=max(0.0, min(1.0, confidence)),
            sources=self._dedupe(sources),
            suggested_actions=self._dedupe(suggested_actions),
        )
        self._history.append(
            {
                "question": question,
                "answer": response.answer,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
        return response

    def get_conversation_history(self) -> list[dict]:
        return [dict(item) for item in self._history]

    def _parse_keywords(self, question: str) -> list[str]:
        keywords = set(re.findall(r"[A-Za-z0-9_]+", question.lower()))
        for token in ("危険", "リスク", "問題", "提案", "改善", "状態", "健康"):
            if token in question:
                keywords.add(token)
        return sorted(keywords)

    def _search_knowledge(self, keywords: list[str]) -> list[Any]:
        if not self.knowledge_manager or not keywords:
            return []

        search = getattr(self.knowledge_manager, "search", None)
        if callable(search):
            try:
                result = search(keywords)
                return list(result) if result else []
            except Exception:
                return []

        get_insights = getattr(self.knowledge_manager, "get_insights", None)
        if callable(get_insights):
            try:
                return list(get_insights(tags=keywords, limit=10))
            except Exception:
                return []
        return []

    def _build_sources(self, knowledge_hits: list[Any]) -> list[str]:
        sources: list[str] = []
        for hit in knowledge_hits:
            if isinstance(hit, dict):
                source = hit.get("title") or hit.get("id") or hit.get("source")
                if source:
                    sources.append(str(source))
            elif isinstance(hit, str):
                sources.append(hit)
        return sources

    def _count_known_issues(self, knowledge_hits: list[Any]) -> int:
        if knowledge_hits:
            return len(knowledge_hits)
        recent = [
            notice
            for notice in self._load_notifications()
            if notice.get("level") in {"warn", "critical"}
        ]
        return len(recent)

    def _count_pending_proposals(self) -> int:
        count = 0
        for proposal in self._iter_pending_proposals():
            if proposal.get("status", "proposed") == "proposed":
                count += 1
        return count

    def _describe_health(self) -> str:
        orgs = self._load_organizations()
        if not orgs:
            return "組織状態データはまだ十分ではありません。`repocorp analyze` で状態を更新してください。"

        scores = [float(org.get("autonomy_score", 50.0)) for org in orgs]
        avg_score = sum(scores) / len(scores)
        if avg_score >= 70:
            label = "概ね健康"
        elif avg_score >= 40:
            label = "やや注意"
        else:
            label = "要改善"
        return (
            f"現在は{len(orgs)}組織が登録され、平均自律スコアは{avg_score:.1f}です。"
            f"全体状態は{label}です。"
        )

    def _load_organizations(self) -> list[dict[str, Any]]:
        orgs_dir = self.platform_home / "organizations"
        if not orgs_dir.exists():
            return []
        results: list[dict[str, Any]] = []
        for path in sorted(orgs_dir.glob("*.json")):
            try:
                results.append(json.loads(path.read_text(encoding="utf-8")))
            except Exception:
                continue
        return results

    def _iter_pending_proposals(self) -> Iterable[dict[str, Any]]:
        seen_dirs: set[Path] = set()

        direct_dir = self.platform_home / ".repocorp" / "improvements"
        if direct_dir.exists():
            seen_dirs.add(direct_dir)

        for org in self._load_organizations():
            repo_path = org.get("target_repo_path")
            if not repo_path:
                continue
            improvements_dir = Path(repo_path) / ".repocorp" / "improvements"
            if improvements_dir.exists():
                seen_dirs.add(improvements_dir)

        for directory in seen_dirs:
            for path in sorted(directory.glob("*.json")):
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    continue
                if data.get("status", "proposed") == "proposed":
                    yield data

    def _load_notifications(self) -> list[dict[str, Any]]:
        path = self.platform_home / "notifications.jsonl"
        if not path.exists():
            return []
        results: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                results.append(json.loads(line))
            except Exception:
                continue
        return results

    def _dedupe(self, items: list[str]) -> list[str]:
        seen = set()
        result = []
        for item in items:
            if item not in seen:
                seen.add(item)
                result.append(item)
        return result
