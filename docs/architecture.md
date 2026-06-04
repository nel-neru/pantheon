# Pantheon アーキテクチャ

 ## システム概要

 Pantheon は、開発者の自然言語ゴールや対象リポジトリを入力として、
 Organization生成・コード分析・改善提案・承認・自己改善までを扱うマルチレイヤー型のAI支援基盤です。

 ## 全体図（text-based）

 ```text
 Developer / Operator
         │
         ├─ pantheon CLI (main.py)
         └─ FastAPI Web UI (web/server.py)
                  │
                  ▼
       Platform / Application Layer
   (core/bootstrap.py, core/platform/state.py)
                  │
     ┌────────────┼────────────┐
     ▼            ▼            ▼
 Goal Layer   Orchestration   Quality / Policy
(core/goals)   (core/orchestration) (core/quality, core/policy)
     │            │            │
     └──────┬─────┴─────┬──────┘
            ▼           ▼
     Agent Layer   Intelligence Layer
       (agents/)   (core/intelligence, core/knowledge)
            │           │
            └──────┬────┘
                   ▼
         Repo / State / Integrations
   (.pantheon, GitHub, LLM providers, config YAML)
 ```

 ## レイヤー構成

 ### 1. Interface Layer

 - `main.py`
   - `pantheon` CLI の全サブコマンドを定義
   - Organization管理、分析、承認、goal実行、daemon、orchestration分析を提供
 - `web/server.py`
   - FastAPI によるプラットフォームAPI
   - Organization一覧、分析、提案参照、platform status を公開

 ### 2. Platform / State Layer

 - `core/bootstrap.py`
   - 初回起動時に Meta-Improvement Organization を自動作成
   - デフォルトポリシー生成も担当
 - `core/platform/state.py`
   - `~/.pantheon` 以下に platform 情報と Organization 定義を保存
 - `core/state/manager.py`
   - 各対象リポジトリ内の `.pantheon/` を管理
   - 改善提案、レビュー結果、決定履歴、knowledge を永続化

 ### 3. Domain / Organization Layer

 - `core/models/organization.py`
   - `Organization`, `Division`, `Team`, `SpecialistAgent`, `ImprovementProposal` 等の中核モデル
   - Pydantic v2 を使って制約（例: SpecialistAgent skills は2〜3個）を表現
 - `core/org_factory.py`
   - YAMLテンプレートから組織構造を構築
   - `config/departments/meta_improvement.yaml` を初期組織のソースとして利用

 ### 4. Agent Layer

 - `agents/base.py`
   - `AgentTask` / `AgentResult` / `BaseAgent` を定義
 - 代表的な実装
   - `CodeReviewAgent`: リポジトリ分析と改善提案生成
   - `ImprovementExecutorAgent`: 提案のコード反映とPR/ブランチ作成
   - `CodebaseExplorerAgent`: コード探索のトークン削減
   - `ToolDesignAgent`: 能力ギャップから実装仕様生成
   - `SelfCodeWriter`: 実装仕様からコード雛形生成
   - `ConversationAgent`: knowledge・提案・組織状態に基づく回答

 ### 5. Intelligence Layer

 - `core/intelligence/agent_skill_engine.py`
   - `AgentSkill` をプロンプト強化用の persona / focus / output_hint に変換
 - `core/intelligence/capability_registry.py`
   - 既存Agent/Skillをレジストリ化
 - `core/intelligence/capability_gap_analyzer.py`
   - 繰り返し操作から不足能力を検出
 - `core/intelligence/codebase_indexer.py`
   - ASTベースのコードベース索引
 - `core/intelligence/codebase_snapshot.py`
   - 目的別の最小トークン表現を生成
 - `core/knowledge/manager.py`
   - 過去実行知識・ベストプラクティスを `.pantheon/knowledge/` に保存

 ### 6. Orchestration Layer

 - `core/orchestration/pre_task_orchestrator.py`
   - ANALYZE → RESEARCH → SELECT/SPAWN → EXECUTE → LEARN の流れを統括
 - `core/orchestration/task_router.py`
   - タスク種別ごとのスキル重みをもとにエージェントを選定
 - `core/orchestration/dynamic_agent_spawner.py`
   - 適任Agentがいない場合に SpecialistAgent を動的生成
 - `core/orchestration/orchestration_pattern_store.py`
   - 実行結果を蓄積し、3件以上の履歴で推奨パターンを返す
 - `core/orchestration/best_practice_advisor.py`
   - Knowledge + PatternStore から事前アドバイスを作る

 ### 7. Goal / Quality / Policy Layer

 - `core/goals/abstract_goal_pipeline.py`
   - 自然言語ゴールを構造化し、計画・組織生成・実行・検証まで一気通貫で扱う
 - `core/goals/execution_coordinator.py`
   - GoalPlan の依存関係をトポロジカル順に実行
 - `core/quality/self_improvement_loop.py`
   - Meta-Improvement Organization が改善提案を拾って適用
 - `core/policy/engine.py`
   - `auto_reject > human_required > auto_approve` の優先順位で承認方針を決定

 ### 8. Integration Layer

 - `core/llm/`
   - OpenAI / Anthropic の抽象化レイヤー
 - `github_integration/pr_creator.py`
   - PyGithub でブランチ作成・ファイル更新・PR作成
 - `config/`
   - YAMLテンプレートや設定、persona定義

 ## 主要データフロー

 ### A. `pantheon analyze`

 1. `main.py` が対象Organizationを取得
 2. `RepoStateManager` で対象リポジトリの `.pantheon` を開く
 3. `CodeReviewAgent` がコード収集 → LLM分析
 4. 生成された `ImprovementProposal` を `.pantheon/improvements/` に保存

 ### B. `pantheon approve`

 1. 未対応提案からID一致の提案を取得
 2. `ImprovementExecutorAgent` が対象ファイルを変更
 3. GitHub token があれば PR、なければローカルブランチ/コミットを作成
 4. 提案ステータスを `done` / `failed` に更新

 ### C. `pantheon goal run`

 1. `GoalParser` が自然言語を `StructuredGoal` に変換
 2. `GoalDecomposer` が Epic/Story/Task へ分解
 3. `OrgInstantiator` が適切な Organization を新規作成または再利用
 4. `ExecutionCoordinator` が依存関係順に実行
 5. `GoalVerifier` が達成率と推奨事項を返す

 ### D. Pre-Task Orchestration

 1. `PreTaskOrchestrator.analyze()` がタスク種別を解析
 2. `BestPracticeAdvisor` が過去知識/統計を調査
 3. `TaskRouter` がスキル重みに応じてエージェント候補を選ぶ
 4. 必要なら `DynamicAgentSpawner` が新しい SpecialistAgent を作る
 5. 実行結果は `OrchestrationPatternStore` と `KnowledgeManager` に保存される

 ## 主要な設計判断

 1. **グローバル状態とリポジトリ状態を分離**
    - 組織一覧や共有ポリシーは `~/.pantheon`
    - 対象リポジトリ固有の提案・知識・決定は `<repo>/.pantheon`

 2. **SpecialistAgent は 2〜3 スキルに限定**
    - ジェネラリスト化を避け、役割を明確にする
    - `AgentSkillEngine` によりスキルが実際のプロンプトへ反映される

 3. **YAMLテンプレートで組織を外部化**
    - `config/departments/*.yaml` により組織構造を変更可能

 4. **Human-in-the-Loop をポリシー化**
    - `PolicyEngine` で高リスクカテゴリや重要ファイルを人間承認へ回す

 5. **学習ループを分散保持**
    - KnowledgeManager: テキスト知見
    - OrchestrationPatternStore: 実行統計
    - CapabilityRegistry / GapAnalyzer: 自己拡張の材料

 ## 現状の実装上の注意点

 - `PreTaskOrchestrator` は `hierarchical` と `best_of_n` を定義しているが、
   `execute()` 実装は `single / sequential / review_loop / parallel` を直接分岐し、
   未実装パターンは現在 `single_agent` 相当へフォールバックする
 - `CodeReviewAgent` は `apply_skills_to_prompt()` を使っているが、すべてのAgentがまだ同水準で
   スキル注入を使っているわけではない
 - `CapabilityRegistry.scan_and_register_all()` は現状 `agents/` と `AgentSkill` を中心にスキャンする

 ## 技術スタック

 - **言語**: Python 3.11+
 - **CLI**: argparse
 - **Web**: FastAPI, Uvicorn（optional `web` extra）
 - **モデル**: Pydantic v2, dataclasses
 - **設定**: PyYAML, `.env` / 環境変数
 - **LLM**: Anthropic, OpenAI（抽象化レイヤーあり）
 - **Git/GitHub**: GitPython, PyGithub
 - **ワークフロー**: LangGraph（依存として導入、周辺機能でも参照）
 - **テスト**: pytest, pytest-asyncio
 - **Lint**: Ruff
