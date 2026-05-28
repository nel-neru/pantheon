"""
RepoCorp AI - Codebase Intelligence Layer

コードベース知性層。毎回の生ファイル読み込みを廃止し、
圧縮インデックス・スナップショット・MCPツールを通じて
エージェントのトークン消費を最小化しながら理解精度を向上させる。

含まれるモジュール:
  - CodebaseIndexer          : ASTベース圧縮インデックス (K-01, K-02)
  - CodebaseSnapshot         : 目的別最小トークン表現 (K-03)
  - TokenBudgetManager       : トークン予算管理 (K-11)
  - AgentSkillEngine         : スキル→動作変換エンジン (A-01~A-03)
  - SkillProficiencyManager  : スキル習熟度管理 (A-04)
  - AgentKnowledgeAccumulator: 成功パターン蓄積 (A-06)
  - SkillPropagator          : スキル継承・伝播 (A-07)
  - SkillGapDetector         : 動的スキルギャップ検出 (A-08)
  - PersonaLoader            : Persona YAML 読み込み (A-09)
  - AgentSelfEvaluator       : 出力自己評価 (A-10)
  - CapabilityRegistry       : システム能力レジストリ (L-03)
  - OperationPatternDetector : 繰り返し操作検出 (L-01)
  - CapabilityGapAnalyzer    : 能力ギャップ分析 (L-02)
"""

from .codebase_indexer import CodebaseIndexer
from .codebase_snapshot import CodebaseSnapshot
from .token_budget_manager import TokenBudgetManager
from .agent_skill_engine import AgentSkillEngine
from .skill_proficiency import SkillProficiencyManager, SkillProficiencyRecord
from .agent_knowledge import AgentKnowledgeAccumulator, SuccessPattern
from .skill_propagator import SkillPropagator
from .skill_gap_detector import SkillGapDetector, SkillGap
from .persona_loader import PersonaLoader
from .self_evaluator import AgentSelfEvaluator, EvaluationResult
from .capability_registry import CapabilityRegistry
from .pattern_detector import OperationPatternDetector
from .capability_gap_analyzer import CapabilityGapAnalyzer

__all__ = [
    "CodebaseIndexer",
    "CodebaseSnapshot",
    "TokenBudgetManager",
    "AgentSkillEngine",
    "SkillProficiencyManager",
    "SkillProficiencyRecord",
    "AgentKnowledgeAccumulator",
    "SuccessPattern",
    "SkillPropagator",
    "SkillGapDetector",
    "SkillGap",
    "PersonaLoader",
    "AgentSelfEvaluator",
    "EvaluationResult",
    "CapabilityRegistry",
    "OperationPatternDetector",
    "CapabilityGapAnalyzer",
]
