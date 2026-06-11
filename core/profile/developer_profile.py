"""
DeveloperProfileManager — 開発者プロファイル (D-01~D-06)

開発者の好み・スタイル・優先事項を学習して提案を個人化する。
~/.pantheon/developer_profile.json に永続化する。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Dict, Optional

from core.platform.state import get_platform_home


class CommunicationStyle(str, Enum):
    VERBOSE = "verbose"
    BALANCED = "balanced"
    CONCISE = "concise"


@dataclass
class ApprovalPattern:
    category: str
    approved_count: int = 0
    rejected_count: int = 0

    @property
    def approval_rate(self) -> float:
        total = self.approved_count + self.rejected_count
        return self.approved_count / total if total > 0 else 0.5


@dataclass
class DeveloperProfile:
    user_id: str = "default"
    approval_patterns: dict[str, ApprovalPattern] = field(default_factory=dict)
    focus_areas: list[str] = field(default_factory=list)
    communication_style: str = CommunicationStyle.BALANCED.value
    preferred_categories: list[str] = field(default_factory=list)
    avoided_categories: list[str] = field(default_factory=list)
    weak_categories: list[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()
        if not self.updated_at:
            self.updated_at = self.created_at


class DeveloperProfileManager:
    """Approval / rejection patterns から開発者プロファイルを学習する。"""

    def __init__(self, platform_home: Optional[Path] = None):
        self.platform_home = Path(platform_home) if platform_home else get_platform_home()
        self.profiles_dir = self.platform_home / "developer_profiles"
        self.profiles_dir.mkdir(parents=True, exist_ok=True)

    def get_profile(self, user_id: str = "default") -> DeveloperProfile:
        return self._load(user_id)

    def record_approval(self, category: str, approved: bool, user_id: str = "default") -> None:
        profile = self._load(user_id)
        pattern = profile.approval_patterns.get(category)
        if pattern is None:
            pattern = ApprovalPattern(category=category)
            profile.approval_patterns[category] = pattern

        if approved:
            pattern.approved_count += 1
        else:
            pattern.rejected_count += 1

        self._refresh_profile(profile)
        self.save(profile)

    def update_communication_style(self, style: str) -> None:
        profile = self._load("default")
        profile.communication_style = self._normalize_style(style).value
        self.save(profile)

    def get_description_length_hint(self, profile: DeveloperProfile) -> str:
        style = self._normalize_style(profile.communication_style)
        if style == CommunicationStyle.VERBOSE:
            return "詳細な説明と根拠を含めてください（500文字以上）"
        if style == CommunicationStyle.CONCISE:
            return "簡潔に要点のみ記載してください（100文字以内）"
        return "適度な説明を提供してください（200-300文字）"

    def update_weakness_detection(self, profile: DeveloperProfile) -> list[str]:
        previous = set(profile.weak_categories)
        weak_categories: set[str] = set()

        for category, pattern in profile.approval_patterns.items():
            total = pattern.approved_count + pattern.rejected_count
            rejection_rate = pattern.rejected_count / total if total > 0 else 0.0
            if total >= 3 and rejection_rate > 0.6:
                weak_categories.add(category)

        profile.weak_categories = sorted(weak_categories)
        return sorted(weak_categories - previous)

    def get_personalization_context(self, user_id: str = "default") -> str:
        profile = self._load(user_id)
        preferred = (
            ", ".join(profile.preferred_categories) if profile.preferred_categories else "なし"
        )
        avoided = ", ".join(profile.avoided_categories) if profile.avoided_categories else "なし"
        parts = [f"好む変更: {preferred}", f"避ける変更: {avoided}"]
        if profile.focus_areas:
            parts.append(f"注力領域: {', '.join(profile.focus_areas)}")
        parts.append(f"説明スタイル: {profile.communication_style}")
        return "【開発者の好み】" + " / ".join(parts)

    def save(self, profile: DeveloperProfile) -> None:
        profile.updated_at = datetime.now(timezone.utc).isoformat()
        path = self.profiles_dir / f"{profile.user_id}.json"
        path.write_text(
            json.dumps(asdict(profile), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _load(self, user_id: str) -> DeveloperProfile:
        path = self.profiles_dir / f"{user_id}.json"
        if not path.exists():
            return DeveloperProfile(user_id=user_id)

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return DeveloperProfile(user_id=user_id)

        patterns: Dict[str, ApprovalPattern] = {}
        for category, raw_pattern in data.get("approval_patterns", {}).items():
            if isinstance(raw_pattern, ApprovalPattern):
                patterns[category] = raw_pattern
            else:
                patterns[category] = ApprovalPattern(
                    category=raw_pattern.get("category", category),
                    approved_count=raw_pattern.get("approved_count", 0),
                    rejected_count=raw_pattern.get("rejected_count", 0),
                )

        profile = DeveloperProfile(
            user_id=data.get("user_id", user_id),
            approval_patterns=patterns,
            focus_areas=list(data.get("focus_areas", [])),
            communication_style=self._normalize_style(
                data.get("communication_style", "balanced")
            ).value,
            preferred_categories=list(data.get("preferred_categories", [])),
            avoided_categories=list(data.get("avoided_categories", [])),
            weak_categories=list(data.get("weak_categories", [])),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )
        self._refresh_profile(profile)
        return profile

    def _refresh_profile(self, profile: DeveloperProfile) -> None:
        preferred: list[str] = []
        avoided: list[str] = []

        for category, pattern in profile.approval_patterns.items():
            if pattern.approved_count >= 3 and pattern.approval_rate > 0.6:
                preferred.append(category)
            if pattern.rejected_count >= 3 and pattern.approval_rate < 0.4:
                avoided.append(category)

        eligible_focus = [
            pattern
            for pattern in profile.approval_patterns.values()
            if pattern.approved_count + pattern.rejected_count >= 2
        ]
        eligible_focus.sort(
            key=lambda pattern: (
                -pattern.approval_rate,
                -(pattern.approved_count + pattern.rejected_count),
                pattern.category,
            )
        )

        profile.communication_style = self._normalize_style(profile.communication_style).value
        profile.preferred_categories = sorted(preferred)
        profile.avoided_categories = sorted(avoided)
        profile.focus_areas = [pattern.category for pattern in eligible_focus[:3]]
        self.update_weakness_detection(profile)

    def personalize_message(self, message: str, user_id: str = "default") -> str:
        profile = self._load(user_id)
        style = self._normalize_style(profile.communication_style)
        if style == CommunicationStyle.CONCISE:
            return f"簡潔に提案してください: {message}"
        if style == CommunicationStyle.VERBOSE:
            return f"詳細な根拠つきで提案してください: {message}"
        return f"バランス良く提案してください: {message}"

    def _normalize_style(self, style: str) -> CommunicationStyle:
        normalized = (style or "").strip().lower()
        if normalized == "detailed":
            normalized = CommunicationStyle.VERBOSE.value
        return (
            CommunicationStyle(normalized)
            if normalized in CommunicationStyle._value2member_map_
            else CommunicationStyle.BALANCED
        )
