"""
CapabilityGapAnalyzer — 能力ギャップ分析器 (L-02)

OperationPatternDetector が検出した繰り返しパターンと
CapabilityRegistry の現有能力リストを照合し、
「このパターンを自動化・高速化する能力が不足している」を LLM で判断する。

システムが自分の能力不足を文章で説明できる状態を作る。
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 優先度の表示順ランク（high > medium > low）。文字列の辞書順では 'low' < 'medium'
# となり medium より low が先に並んでしまうため、明示ランクで並べ替える。
_PRIORITY_RANK = {"high": 0, "medium": 1, "low": 2}


@dataclass
class CapabilityGap:
    """検出された能力ギャップ。"""

    gap_id: str
    pattern_key: str  # どの繰り返しパターンから検出されたか
    description: str  # ギャップの説明
    suggested_type: str  # "agent" | "skill" | "tool" | "mcp_tool"
    suggested_name: str  # 提案する能力名
    rationale: str  # なぜこの能力が必要か
    priority: str = "medium"  # "high" | "medium" | "low"
    estimated_token_savings: int = 0
    detected_at: str = ""
    implemented: bool = False

    def __post_init__(self):
        if not self.detected_at:
            self.detected_at = datetime.now(timezone.utc).isoformat()
        if not self.gap_id:
            self.gap_id = (
                f"gap:{self.pattern_key}:{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
            )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "CapabilityGap":
        allowed = {k for k in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in allowed})


class CapabilityGapAnalyzer:
    """
    繰り返しパターン + 現有能力リストから能力ギャップを分析する。

    LLM を使う場合（analyze_with_llm）と、
    ルールベースのヒューリスティック（analyze_heuristic）の2モードを持つ。
    ヒューリスティックはトークンゼロで動作するため、常に先に実行する。
    """

    GAP_FILE = "capability_gaps.json"

    # ヒューリスティックルール: 繰り返し操作 → 不足能力の推定
    HEURISTIC_RULES = [
        {
            "operation_type": "codebase_scan",
            "suggested_type": "agent",
            "suggested_name": "CodebaseExplorerAgent",
            "description": "コードベース全スキャンが毎回実行されている — キャッシュ付き高速調査エージェントが不足",
            "rationale": "毎回生ファイルを読み込むと大量のトークンを消費する。インデックスキャッシュを使ったCodebaseExplorerAgentで解決できる。",
            "priority": "high",
        },
        {
            "operation_type": "code_review",
            "suggested_type": "skill",
            "suggested_name": "CODEBASE_EXPLORATION",
            "description": "コードレビューが繰り返し実行されている — コードベース調査スキルの統合が不足",
            "rationale": "CodeReviewAgentがCodebaseExplorerAgentを使えれば、毎回のファイル読み込みコストを削減できる。",
            "priority": "medium",
        },
        {
            "operation_type": "security_audit",
            "suggested_type": "skill",
            "suggested_name": "SECURITY_AUDIT",
            "description": "セキュリティ監査が繰り返し実行されている — 専用スキルが不足",
            "rationale": "SECURITY_AUDITスキルを定義することで、監査に特化したプロンプトとファイル選択ロジックを適用できる。",
            "priority": "medium",
        },
        {
            "operation_type": "dependency_analysis",
            "suggested_type": "tool",
            "suggested_name": "DependencyGraphBuilder",
            "description": "依存関係分析が繰り返し実行されている — 依存グラフキャッシュツールが不足",
            "rationale": "依存グラフを一度構築してキャッシュすることで、繰り返し計算コストを削減できる。",
            "priority": "medium",
        },
    ]

    def __init__(
        self,
        pattern_detector=None,
        capability_registry=None,
        platform_home: Optional[Path] = None,
        llm_client: Optional[Any] = None,
    ):
        self._detector = pattern_detector
        self._registry = capability_registry
        self._llm = llm_client

        from core.platform.state import get_platform_home

        home = platform_home or get_platform_home()
        self._gap_file = home / self.GAP_FILE

        self._gaps: List[CapabilityGap] = []
        self._load_gaps()

    # ------------------------------------------------------------------ #
    # 分析                                                                 #
    # ------------------------------------------------------------------ #

    def analyze(self, use_llm: bool = False) -> List[CapabilityGap]:
        """
        ギャップ分析を実行する。
        - まずヒューリスティックでゼロトークン分析
        - use_llm=True の場合は LLM で補完
        """
        patterns = self._detector.get_repeated_patterns() if self._detector else []

        new_gaps: List[CapabilityGap] = []

        # 1. ヒューリスティック分析（トークン不要）
        new_gaps += self._analyze_heuristic(patterns)

        # 2. LLM 分析（オプション）
        if use_llm and self._llm and patterns:
            llm_gaps = self._analyze_with_llm(patterns)
            # 重複除外
            existing_names = {g.suggested_name for g in new_gaps}
            new_gaps += [g for g in llm_gaps if g.suggested_name not in existing_names]

        # 保存
        for gap in new_gaps:
            self._gaps.append(gap)
        self._save_gaps()

        return new_gaps

    def get_all_gaps(self, include_implemented: bool = False) -> List[CapabilityGap]:
        """検出済みギャップを返す。"""
        if include_implemented:
            return list(self._gaps)
        return [g for g in self._gaps if not g.implemented]

    def mark_implemented(self, gap_id: str) -> bool:
        """ギャップを実装済みにマークする。"""
        for gap in self._gaps:
            if gap.gap_id == gap_id:
                gap.implemented = True
                self._save_gaps()
                return True
        return False

    def format_for_agent(self) -> str:
        """エージェントのプロンプトに埋め込める形式でギャップを返す。"""
        active = self.get_all_gaps()
        if not active:
            return "【能力ギャップ】なし（現在のシステム能力は十分です）"
        lines = ["【検出された能力ギャップ】"]
        for gap in sorted(active, key=lambda g: _PRIORITY_RANK.get(g.priority, 99)):
            lines.append(
                f"  [{gap.priority.upper()}] {gap.suggested_name} ({gap.suggested_type})\n"
                f"    理由: {gap.description}"
            )
        return "\n".join(lines)

    def get_summary(self) -> Dict[str, Any]:
        active = self.get_all_gaps()
        return {
            "total_gaps": len(active),
            "high_priority": len([g for g in active if g.priority == "high"]),
            "suggested_agents": [g.suggested_name for g in active if g.suggested_type == "agent"],
            "suggested_skills": [g.suggested_name for g in active if g.suggested_type == "skill"],
        }

    def should_run_analysis(self, last_run_path: Path) -> bool:
        """Return True when the last analysis is older than seven days."""
        path = Path(last_run_path)
        if not path.exists():
            return True
        try:
            last_run = datetime.fromisoformat(path.read_text(encoding="utf-8").strip())
            return datetime.now(timezone.utc) - last_run > timedelta(days=7)
        except Exception:  # 破損/naive-tz は「要再実行」に倒す
            return True

    def mark_analysis_run(self, last_run_path: Path) -> None:
        """Persist the current analysis timestamp."""
        path = Path(last_run_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(datetime.now(timezone.utc).isoformat(), encoding="utf-8")

    # ------------------------------------------------------------------ #
    # 内部実装                                                             #
    # ------------------------------------------------------------------ #

    def _analyze_heuristic(self, patterns) -> List[CapabilityGap]:
        """ルールベースのヒューリスティック分析。"""
        existing_names = {g.suggested_name for g in self._gaps}
        new_gaps = []
        existing_cap_names: set = set()
        if self._registry:
            existing_cap_names = {e.name for e in self._registry.list_all()}

        for pattern in patterns:
            for rule in self.HEURISTIC_RULES:
                if rule["operation_type"] != pattern.operation_type:
                    continue
                if rule["suggested_name"] in existing_names:
                    continue
                if rule["suggested_name"] in existing_cap_names:
                    continue
                gap = CapabilityGap(
                    gap_id=f"gap:{pattern.pattern_key}:{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
                    pattern_key=pattern.pattern_key,
                    description=rule["description"],
                    suggested_type=rule["suggested_type"],
                    suggested_name=rule["suggested_name"],
                    rationale=rule["rationale"],
                    priority=rule["priority"],
                    estimated_token_savings=int(pattern.total_tokens * 0.5),
                )
                new_gaps.append(gap)

        return new_gaps

    def _analyze_with_llm(self, patterns) -> List[CapabilityGap]:
        """LLM を使ったギャップ分析（トークンコストあり）。"""
        try:
            cap_summary = ""
            if self._registry:
                cap_summary = self._registry.format_for_agent()

            patterns_text = "\n".join(
                f"  - {p.operation_type}: {p.repeat_count}回繰り返し, "
                f"合計{p.total_tokens}トークン消費"
                for p in patterns
            )

            prompt = f"""以下の繰り返し操作パターンと現在のシステム能力を分析し、
不足している能力（Agent/Skill/Tool）を特定してください。

繰り返し操作パターン:
{patterns_text}

{cap_summary}

各能力ギャップについて以下のJSON形式で出力してください:
[
  {{
    "suggested_type": "agent|skill|tool",
    "suggested_name": "クラス名",
    "description": "ギャップの説明（日本語）",
    "rationale": "なぜ必要か（日本語）",
    "priority": "high|medium|low"
  }}
]
"""
            response = self._llm.invoke(prompt)
            content = response.content if hasattr(response, "content") else str(response)

            import re

            json_match = re.search(r"\[.*?\]", content, re.DOTALL)
            if not json_match:
                return []

            raw_gaps = json.loads(json_match.group())
            result = []
            for i, raw in enumerate(raw_gaps):
                result.append(
                    CapabilityGap(
                        gap_id=f"gap:llm:{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}:{i}",
                        pattern_key="llm_analysis",
                        description=raw.get("description", ""),
                        suggested_type=raw.get("suggested_type", "agent"),
                        suggested_name=raw.get("suggested_name", f"UnknownCapability_{i}"),
                        rationale=raw.get("rationale", ""),
                        priority=raw.get("priority", "medium"),
                    )
                )
            return result
        except Exception as e:
            logger.warning("LLM gap analysis failed: %s", e)
            return []

    def _load_gaps(self) -> None:
        if not self._gap_file.exists():
            return
        try:
            data = json.loads(self._gap_file.read_text(encoding="utf-8"))
            for d in data.get("gaps", []):
                self._gaps.append(CapabilityGap.from_dict(d))
        except Exception as e:
            logger.warning("CapabilityGapAnalyzer load failed: %s", e)

    def _save_gaps(self) -> None:
        self._gap_file.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version": "1.0.0",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "gaps": [g.to_dict() for g in self._gaps],
        }
        self._gap_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
