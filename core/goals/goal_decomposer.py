"""
GoalDecomposer — 目標分解エンジン (M-02)

StructuredGoal を、実行可能な Epic / Story / Task の階層に分解する。
各 Task は「担当可能な Agent 種別・必要スキル・依存関係・成功基準」を持つ。
既存の AgentSkill と CapabilityRegistry を参照して実行可能性を確認する。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.goals.goal_parser import GoalType, StructuredGoal
from core.llm.json_extract import extract_json_object

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────── #
# データモデル                                                         #
# ────────────────────────────────────────────────────────────────── #


@dataclass
class TaskSpec:
    """実行可能な最小単位のタスク。"""

    task_id: str
    title: str
    description: str
    required_skills: List[str]  # AgentSkill.value のリスト
    agent_type: str = "specialist"  # "specialist" | "codebase_explorer" | "code_reviewer"
    dependencies: List[str] = field(default_factory=list)  # 先行 task_id のリスト
    success_criteria: str = ""
    estimated_tokens: int = 2000
    is_executable: bool = True  # CapabilityRegistry に対応するエージェントがあるか

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "title": self.title,
            "description": self.description,
            "required_skills": self.required_skills,
            "agent_type": self.agent_type,
            "dependencies": self.dependencies,
            "success_criteria": self.success_criteria,
            "estimated_tokens": self.estimated_tokens,
            "is_executable": self.is_executable,
        }


@dataclass
class StorySpec:
    """タスクの集まり — Sprint サイズの実行単位。"""

    story_id: str
    title: str
    description: str
    tasks: List[TaskSpec] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "story_id": self.story_id,
            "title": self.title,
            "description": self.description,
            "tasks": [t.to_dict() for t in self.tasks],
        }


@dataclass
class EpicSpec:
    """大きな機能単位 — 複数の Story を含む。"""

    epic_id: str
    title: str
    description: str
    stories: List[StorySpec] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "epic_id": self.epic_id,
            "title": self.title,
            "description": self.description,
            "stories": [s.to_dict() for s in self.stories],
        }


@dataclass
class GoalPlan:
    """目標分解の結果 — Epic/Story/Task 階層の実行計画。"""

    plan_id: str
    goal_id: str
    goal_description: str
    epics: List[EpicSpec] = field(default_factory=list)
    total_tasks: int = 0
    executable_tasks: int = 0
    created_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()
        self._recalculate()

    def _recalculate(self) -> None:
        all_tasks = self.get_all_tasks()
        self.total_tasks = len(all_tasks)
        self.executable_tasks = sum(1 for t in all_tasks if t.is_executable)

    def get_all_tasks(self) -> List[TaskSpec]:
        tasks = []
        for epic in self.epics:
            for story in epic.stories:
                tasks.extend(story.tasks)
        return tasks

    def get_executable_tasks(self) -> List[TaskSpec]:
        return [t for t in self.get_all_tasks() if t.is_executable]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "goal_id": self.goal_id,
            "goal_description": self.goal_description,
            "epics": [e.to_dict() for e in self.epics],
            "total_tasks": self.total_tasks,
            "executable_tasks": self.executable_tasks,
            "created_at": self.created_at,
        }


# ────────────────────────────────────────────────────────────────── #
# 目標種別ごとのテンプレート化されたタスクツリー                         #
# ────────────────────────────────────────────────────────────────── #


def _make_id(prefix: str) -> str:
    return f"{prefix}:{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"


# 各目標種別の標準タスクテンプレート定義
_TEMPLATES: Dict[str, List[Dict[str, Any]]] = {
    GoalType.SECURITY: [
        {
            "epic": "セキュリティ調査・分析",
            "stories": [
                {
                    "story": "コードベース調査",
                    "tasks": [
                        {
                            "title": "コードベース全体のセキュリティリスクを調査",
                            "skills": ["codebase_exploration", "deep_research"],
                            "tokens": 3000,
                        },
                    ],
                },
                {
                    "story": "脆弱性の特定",
                    "tasks": [
                        {
                            "title": "認証・認可の実装を確認",
                            "skills": ["deep_research", "tool_integration"],
                            "tokens": 2000,
                        },
                        {
                            "title": "入力バリデーションの確認",
                            "skills": ["deep_research", "tool_integration"],
                            "tokens": 2000,
                        },
                    ],
                },
            ],
        },
        {
            "epic": "セキュリティ改善の実施",
            "stories": [
                {
                    "story": "改善提案の生成",
                    "tasks": [
                        {
                            "title": "セキュリティ改善提案を生成",
                            "skills": ["tool_integration", "prompt_engineering"],
                            "tokens": 3000,
                            "depends_on_prev": True,
                        },
                    ],
                },
                {
                    "story": "テストと検証",
                    "tasks": [
                        {
                            "title": "セキュリティテストを実行して改善を確認",
                            "skills": ["tool_integration"],
                            "tokens": 2000,
                            "depends_on_prev": True,
                        },
                    ],
                },
            ],
        },
    ],
    GoalType.TEST_COVERAGE: [
        {
            "epic": "テスト現状の把握",
            "stories": [
                {
                    "story": "カバレッジ計測",
                    "tasks": [
                        {
                            "title": "現在のテストカバレッジを計測",
                            "skills": ["codebase_exploration", "performance_analysis"],
                            "tokens": 2000,
                        },
                        {
                            "title": "テストが不足しているモジュールを特定",
                            "skills": ["deep_research", "performance_analysis"],
                            "tokens": 2000,
                        },
                    ],
                },
            ],
        },
        {
            "epic": "テストの追加",
            "stories": [
                {
                    "story": "ユニットテスト追加",
                    "tasks": [
                        {
                            "title": "優先度の高いモジュールのユニットテストを作成",
                            "skills": ["prompt_engineering", "tool_integration"],
                            "tokens": 4000,
                            "depends_on_prev": True,
                        },
                    ],
                },
                {
                    "story": "統合テスト追加",
                    "tasks": [
                        {
                            "title": "主要フローの統合テストを作成",
                            "skills": ["prompt_engineering", "agent_workflow_design"],
                            "tokens": 4000,
                            "depends_on_prev": True,
                        },
                    ],
                },
            ],
        },
    ],
    GoalType.PERFORMANCE: [
        {
            "epic": "パフォーマンス計測",
            "stories": [
                {
                    "story": "ボトルネック特定",
                    "tasks": [
                        {
                            "title": "処理時間・メモリ使用量を計測",
                            "skills": ["performance_analysis", "deep_research"],
                            "tokens": 3000,
                        },
                        {
                            "title": "ボトルネックの根本原因を分析",
                            "skills": ["performance_analysis", "codebase_exploration"],
                            "tokens": 3000,
                        },
                    ],
                },
            ],
        },
        {
            "epic": "最適化の実施",
            "stories": [
                {
                    "story": "コード最適化",
                    "tasks": [
                        {
                            "title": "ボトルネック箇所の最適化実装",
                            "skills": ["prompt_engineering", "tool_integration"],
                            "tokens": 4000,
                            "depends_on_prev": True,
                        },
                        {
                            "title": "キャッシュ・非同期処理の導入を検討",
                            "skills": ["strategic_planning", "tool_integration"],
                            "tokens": 3000,
                            "depends_on_prev": True,
                        },
                    ],
                },
            ],
        },
    ],
    GoalType.REFACTORING: [
        {
            "epic": "コード品質分析",
            "stories": [
                {
                    "story": "現状把握",
                    "tasks": [
                        {
                            "title": "コードの複雑度・重複を分析",
                            "skills": ["codebase_exploration", "performance_analysis"],
                            "tokens": 3000,
                        },
                    ],
                },
            ],
        },
        {
            "epic": "リファクタリング実施",
            "stories": [
                {
                    "story": "構造改善",
                    "tasks": [
                        {
                            "title": "重複コードを抽出・共通化",
                            "skills": ["prompt_engineering", "tool_integration"],
                            "tokens": 4000,
                            "depends_on_prev": True,
                        },
                        {
                            "title": "命名・関数分割を改善",
                            "skills": ["prompt_engineering", "knowledge_curation"],
                            "tokens": 3000,
                            "depends_on_prev": True,
                        },
                    ],
                },
            ],
        },
    ],
    GoalType.NEW_SERVICE: [
        {
            "epic": "設計・計画",
            "stories": [
                {
                    "story": "アーキテクチャ設計",
                    "tasks": [
                        {
                            "title": "システムアーキテクチャを設計",
                            "skills": ["strategic_planning", "org_design"],
                            "tokens": 4000,
                        },
                        {
                            "title": "APIインターフェースを設計",
                            "skills": ["agent_workflow_design", "strategic_planning"],
                            "tokens": 3000,
                        },
                    ],
                },
            ],
        },
        {
            "epic": "実装",
            "stories": [
                {
                    "story": "コア機能実装",
                    "tasks": [
                        {
                            "title": "データモデルを実装",
                            "skills": ["prompt_engineering", "tool_integration"],
                            "tokens": 4000,
                            "depends_on_prev": True,
                        },
                        {
                            "title": "ビジネスロジックを実装",
                            "skills": ["prompt_engineering", "tool_integration"],
                            "tokens": 5000,
                            "depends_on_prev": True,
                        },
                        {
                            "title": "APIエンドポイントを実装",
                            "skills": ["prompt_engineering", "tool_integration"],
                            "tokens": 4000,
                            "depends_on_prev": True,
                        },
                    ],
                },
                {
                    "story": "テスト",
                    "tasks": [
                        {
                            "title": "ユニットテスト・統合テストを作成",
                            "skills": ["prompt_engineering", "agent_workflow_design"],
                            "tokens": 4000,
                            "depends_on_prev": True,
                        },
                    ],
                },
            ],
        },
    ],
    GoalType.DOCUMENTATION: [
        {
            "epic": "ドキュメント作成",
            "stories": [
                {
                    "story": "コード分析",
                    "tasks": [
                        {
                            "title": "既存コードからdocstringを収集",
                            "skills": ["codebase_exploration", "knowledge_curation"],
                            "tokens": 3000,
                        },
                    ],
                },
                {
                    "story": "ドキュメント生成",
                    "tasks": [
                        {
                            "title": "READMEを更新",
                            "skills": ["knowledge_curation", "prompt_engineering"],
                            "tokens": 3000,
                            "depends_on_prev": True,
                        },
                        {
                            "title": "API仕様書を生成",
                            "skills": ["prompt_engineering", "knowledge_curation"],
                            "tokens": 4000,
                            "depends_on_prev": True,
                        },
                    ],
                },
            ],
        },
    ],
    GoalType.IMPROVEMENT: [
        {
            "epic": "品質分析",
            "stories": [
                {
                    "story": "コードレビュー",
                    "tasks": [
                        {
                            "title": "コードレビューで改善点を特定",
                            "skills": ["codebase_exploration", "deep_research"],
                            "tokens": 4000,
                        },
                    ],
                },
            ],
        },
        {
            "epic": "改善実施",
            "stories": [
                {
                    "story": "改善適用",
                    "tasks": [
                        {
                            "title": "優先度の高い改善を適用",
                            "skills": ["prompt_engineering", "tool_integration"],
                            "tokens": 4000,
                            "depends_on_prev": True,
                        },
                    ],
                },
            ],
        },
    ],
}

# 未知の目標種別用デフォルト
_DEFAULT_TEMPLATE = [
    {
        "epic": "現状分析",
        "stories": [
            {
                "story": "調査",
                "tasks": [
                    {
                        "title": "目標達成に必要なコンテキストを調査",
                        "skills": ["deep_research", "codebase_exploration"],
                        "tokens": 3000,
                    },
                ],
            },
        ],
    },
    {
        "epic": "実施",
        "stories": [
            {
                "story": "実行",
                "tasks": [
                    {
                        "title": "目標に向けた主要タスクを実行",
                        "skills": ["prompt_engineering", "tool_integration"],
                        "tokens": 4000,
                        "depends_on_prev": True,
                    },
                ],
            },
        ],
    },
]


# ────────────────────────────────────────────────────────────────── #
# GoalDecomposer クラス                                               #
# ────────────────────────────────────────────────────────────────── #


class GoalDecomposer:
    """
    StructuredGoal を Epic / Story / Task の階層に分解するエンジン。

    LLM なしでもテンプレートベースで実用的なタスクツリーを生成する。
    CapabilityRegistry と照合して実行可能性を確認する。
    """

    def __init__(
        self,
        capability_registry: Optional[Any] = None,
        llm_client: Optional[Any] = None,
    ):
        self._registry = capability_registry
        self._llm = llm_client

    def decompose(self, goal: StructuredGoal, use_llm: bool = False) -> GoalPlan:
        """
        StructuredGoal を GoalPlan（Epic/Story/Task ツリー）に分解する。

        Args:
            goal: パース済みの構造化された目標
            use_llm: True の場合 LLM でより詳細な分解を行う

        Returns:
            GoalPlan
        """
        if use_llm and self._llm:
            try:
                return self._decompose_with_llm(goal)
            except Exception as e:
                logger.warning("LLM decomposition failed, using template: %s", e)

        return self._decompose_with_template(goal)

    # ------------------------------------------------------------------ #
    # テンプレートベース分解                                               #
    # ------------------------------------------------------------------ #

    def _decompose_with_template(self, goal: StructuredGoal) -> GoalPlan:
        """テンプレートから Epic/Story/Task ツリーを生成する。"""
        template = _TEMPLATES.get(goal.goal_type, _DEFAULT_TEMPLATE)

        available_skills = self._get_available_skills()
        epics: List[EpicSpec] = []
        prev_task_ids: List[str] = []

        for epic_def in template:
            epic = EpicSpec(
                epic_id=_make_id("epic"),
                title=epic_def["epic"],
                description=f"{goal.goal_type} - {epic_def['epic']}",
            )

            for story_def in epic_def.get("stories", []):
                story = StorySpec(
                    story_id=_make_id("story"),
                    title=story_def["story"],
                    description=story_def["story"],
                )

                for task_def in story_def.get("tasks", []):
                    task_id = _make_id("task")
                    deps = (
                        list(prev_task_ids)
                        if task_def.get("depends_on_prev") and prev_task_ids
                        else []
                    )
                    skills = task_def.get("skills", ["deep_research"])
                    is_executable = (
                        any(s in available_skills for s in skills) if available_skills else True
                    )

                    task = TaskSpec(
                        task_id=task_id,
                        title=task_def["title"],
                        description=f"{goal.description} — {task_def['title']}",
                        required_skills=skills,
                        agent_type="specialist",
                        dependencies=deps,
                        success_criteria=goal.success_criteria[0] if goal.success_criteria else "",
                        estimated_tokens=task_def.get("tokens", 2000),
                        is_executable=is_executable,
                    )
                    story.tasks.append(task)
                    prev_task_ids = [task_id]

                epic.stories.append(story)
            epics.append(epic)

        ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        plan = GoalPlan(
            plan_id=f"plan:{goal.goal_type}:{ts}",
            goal_id=goal.goal_id,
            goal_description=goal.description,
            epics=epics,
        )
        return plan

    def _get_available_skills(self) -> List[str]:
        """CapabilityRegistry から利用可能なスキルのリストを返す。"""
        if self._registry is None:
            return []
        try:
            entries = self._registry.list_all()
            skills = set()
            for e in entries:
                skills.update(e.skills if hasattr(e, "skills") else [])
            return list(skills)
        except Exception as e:
            logger.warning("Failed to get available skills: %s", e)
            return []

    # ------------------------------------------------------------------ #
    # LLM 分解                                                             #
    # ------------------------------------------------------------------ #

    def _decompose_with_llm(self, goal: StructuredGoal) -> GoalPlan:
        """LLM を使って詳細なタスクツリーを生成する。"""
        prompt = f"""以下の目標を実行可能なタスクに分解してください。

目標: {goal.description}
種別: {goal.goal_type}
スコープ: {goal.scope}
成功基準: {", ".join(goal.success_criteria)}

以下のJSON形式で分解してください:
{{
  "epics": [
    {{
      "title": "Epic名",
      "description": "Epic説明",
      "stories": [
        {{
          "title": "Story名",
          "tasks": [
            {{
              "title": "タスク名",
              "description": "タスクの詳細",
              "required_skills": ["skill1", "skill2"],
              "estimated_tokens": 2000,
              "depends_on_prev": false
            }}
          ]
        }}
      ]
    }}
  ]
}}

利用可能なスキル: codebase_exploration, deep_research, strategic_planning,
prompt_engineering, tool_integration, performance_analysis,
knowledge_curation, agent_workflow_design, org_design, corporate_research"""

        response = self._llm.invoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)

        data = extract_json_object(content)
        if not isinstance(data, dict):
            return self._decompose_with_template(goal)
        available_skills = self._get_available_skills()
        epics: List[EpicSpec] = []
        prev_task_ids: List[str] = []

        for epic_data in data.get("epics", []):
            epic = EpicSpec(
                epic_id=_make_id("epic"),
                title=epic_data.get("title", "Epic"),
                description=epic_data.get("description", ""),
            )
            for story_data in epic_data.get("stories", []):
                story = StorySpec(
                    story_id=_make_id("story"),
                    title=story_data.get("title", "Story"),
                    description=story_data.get("title", ""),
                )
                for task_data in story_data.get("tasks", []):
                    task_id = _make_id("task")
                    skills = task_data.get("required_skills", ["deep_research"])
                    deps = (
                        list(prev_task_ids)
                        if task_data.get("depends_on_prev") and prev_task_ids
                        else []
                    )
                    is_executable = (
                        any(s in available_skills for s in skills) if available_skills else True
                    )
                    task = TaskSpec(
                        task_id=task_id,
                        title=task_data.get("title", "Task"),
                        description=task_data.get("description", ""),
                        required_skills=skills,
                        dependencies=deps,
                        estimated_tokens=task_data.get("estimated_tokens", 2000),
                        is_executable=is_executable,
                    )
                    story.tasks.append(task)
                    prev_task_ids = [task_id]
                epic.stories.append(story)
            epics.append(epic)

        ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        plan = GoalPlan(
            plan_id=f"plan:{goal.goal_type}:{ts}",
            goal_id=goal.goal_id,
            goal_description=goal.description,
            epics=epics,
        )
        return plan
