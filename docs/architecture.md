# RepoCorp AI アーキテクチャ

 ## システム概要

 RepoCorp AI は、開発者の自然言語ゴールや対象リポジトリを入力として、
 Organization生成・コード分析・改善提案・承認・自己改善までを扱うマルチレイヤー型のAI支援基盤です。

 ## エージェントの2つの平面（重要）

 RepoCorp には性質の異なる2つの「エージェント平面」があり、これを混同しないことが設計の要です。
 それぞれに**単一の真実 (Single Source of Truth)** を置きます。

 | | 平面A：ビルド時 / 外部エージェント | 平面B：実行時 / 内部エージェント |
 |---|---|---|
 | いつ使うか | 人間が外部AIツールで RepoCorp 自身を**開発**するとき | WebGUI/CLI からユーザーのLLMが Core を**自律実行/改善**するとき |
 | 担い手 | Claude Code / Codex / Cursor / Copilot / Gemini CLI | RepoCorp 自身（外部ツールに非依存） |
 | 単一の真実 | **`AGENTS.md`**（各ツール用は薄いリダイレクト） | **`skills/*.yaml` + `agents/definitions/*.yaml` + `core/llm`** |
 | 「LLM毎に設定が違う」問題 | `AGENTS.md` に集約し、各ツール設定はそれを参照するだけ | YAML に統一済。プロバイダー差は `core/llm` の正規化層で吸収 |

 - **平面A**: `AGENTS.md` を正典とし、`CLAUDE.md` / `GEMINI.md` / `.github/copilot-instructions.md`
   / `.cursor/rules/repocorp.mdc` は「まず `AGENTS.md` を読め」と促す薄いリダイレクトに留める。
   これにより、どの外部AIツールを使っても指示が一つに揃う。
 - **平面B**: 内部エージェント/スキルは YAML で宣言し、`core/llm` のプロバイダー抽象を通すため、
   ユーザーが契約している任意のLLM（APIキーさえあれば）で全機能が動く。

 ### 命名の衝突に注意

 リポジトリ直下の `skills/` `agents/` `commands/` は **RepoCorp の実行時概念**
 （内部スキル定義 / 内部エージェント実装・定義 / `repocorp` CLI サブコマンド）であり、
 Claude Code の `.claude/skills`・`.claude/agents`・`.claude/commands` とは**無関係**です。
 偶然名前が似ているだけなので、外部ツールの設定ディレクトリと混同しないこと。

 ## LLM アクセス（プロバイダー非依存）

 すべての LLM 呼び出しは `core/llm` を唯一の経路とします。

 - `core/llm/base.py` — `LLMProvider` 抽象基底（`generate` / `stream` / `generate_json` / `capabilities`）
 - プロバイダー実装 — `anthropic` / `openai` / `groq` / `github_models` / `gemini`
 - `core/llm/client.py` — 同期ブリッジ `LLMClient`（`.invoke` / `.complete` / `.generate_json`）と、
   GUI設定/環境変数からキーを解決する `get_default_llm_client()` / `get_configured_llm_provider()`。
   **キーが解決できない場合は None を返し**、各エージェントは従来のテンプレート/ヒューリスティック
   動作にフォールバックする（＝キー未設定でも壊れない）。
 - `core/llm/tool_schema.py` — tool(function calling) スキーマの中立表現と各プロバイダー形への相互変換
 - `core/llm/json_extract.py` — 出力からの堅牢な JSON 抽出（コードフェンス/前置き文を許容）
 - `core/llm/capabilities.py` — プロバイダー能力（tools/JSON/streaming/文脈長 等）の宣言レジストリ
 - `core/llm/model_registry.py` — モデル一覧・既定モデル・タスク別モデルの集約（API/UIが参照）

 CLI（`main._get_orchestrator`）と Web（`web/server.py` の goal/analyze/approve 実行口）は
 `get_default_llm_client()` を注入し、APIキーがあればスタブに落ちず実 LLM で動作する。

 ## 全体図（text-based）

 ```text
 Developer / Operator
         │
         ├─ repocorp CLI (main.py)
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
   (.repocorp, GitHub, LLM providers, config YAML)
 ```

 ## レイヤー構成

 ### 1. Interface Layer

 - `main.py`
   - `repocorp` CLI の全サブコマンドを定義
   - Organization管理、分析、承認、goal実行、daemon、orchestration分析を提供
 - `web/server.py`
   - FastAPI によるプラットフォームAPI
   - Organization一覧、分析、提案参照、platform status を公開

 ### 2. Platform / State Layer

 - `core/bootstrap.py`
   - 初回起動時に Meta-Improvement Organization を自動作成
   - デフォルトポリシー生成も担当
 - `core/platform/state.py`
   - `~/.repocorp` 以下に platform 情報と Organization 定義を保存
 - `core/state/manager.py`
   - 各対象リポジトリ内の `.repocorp/` を管理
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
   - 過去実行知識・ベストプラクティスを `.repocorp/knowledge/` に保存

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

 ### A. `repocorp analyze`

 1. `main.py` が対象Organizationを取得
 2. `RepoStateManager` で対象リポジトリの `.repocorp` を開く
 3. `CodeReviewAgent` がコード収集 → LLM分析
 4. 生成された `ImprovementProposal` を `.repocorp/improvements/` に保存

 ### B. `repocorp approve`

 1. 未対応提案からID一致の提案を取得
 2. `ImprovementExecutorAgent` が対象ファイルを変更
 3. GitHub token があれば PR、なければローカルブランチ/コミットを作成
 4. 提案ステータスを `done` / `failed` に更新

 ### C. `repocorp goal run`

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
    - 組織一覧や共有ポリシーは `~/.repocorp`
    - 対象リポジトリ固有の提案・知識・決定は `<repo>/.repocorp`

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
 - **テスト**: pytest, pytest-asyncio, vitest
 - **Lint**: Ruff
 - **ターミナル**: PTY (pty/termios) + xterm.js + WebSocket

 ## 追加コンポーネント（Phase 2–5）

 ### Web/UI
 - `web/frontend/`（React+Vite, dist が正典）。旧 `web/static` は `web/legacy/` へ退避。
 - 主要画面に「ターミナル」を追加。Settings に provider capabilities / モデル / 実行モード(API/CLI) / トークン使用量。

 ### LLM 信頼性・可観測性
 - `core/llm/retry.py` — `LLMError`（provider/status/retryable 正規化）と `call_with_retry`（タイムアウト＋指数バックオフ）。全 provider の `generate` をラップ。
 - `core/llm/usage.py` — `UsageTracker`（provider/model 別トークン集計）。`GET/DELETE /api/usage`。
 - `core/llm/capabilities.py` / `model_registry.py` / `tool_schema.py` / `json_extract.py` / `client.py`（同期ブリッジ＋既定/構成クライアント解決）。

 ### 自己改善ランタイム
 - `agents/core_improvement_agent.py` — LLM編集→`SafeChangeExecutor`でテスト検証/反復/複数ファイル原子適用→検証済み diff（既定 validate_only）。
 - `POST /api/core/improve` → `ImprovementProposal`（`PolicyEngine` で Core 変更は human_required）→ 承認は既存フロー（検証済み content をサイドカーから直接適用）。

 ### 実行モード（API / CLI）
 - `core/execution/cli_registry.py` — 外部CLI(claude/codex/gemini/aider/opencode) の定義と PATH 可用性検出。`GET /api/execution/modes`。
 - API=内蔵エージェント / CLI=埋め込みターミナルのワークスペースで外部CLIを起動。

 ### 埋め込みターミナル（cmux 風）
 - `web/terminal.py` — PTY セッション管理（localhost 限定 + Host 許可リスト + WS Origin 検証 + atexit 終了 + BEL 通知 + git ブランチ）。
 - `/api/terminal/sessions`（REST）+ `/ws/terminal/{id}`（WebSocket）+ `web/frontend/src/components/TerminalView.tsx` + `pages/TerminalPage.tsx`（縦タブ・状態・青リング・CLI起動）。

 ### セキュリティ / 運用
 - 既定バインド `127.0.0.1`（公開は `--host`/`REPOCORP_HOST` 明示）。`TrustedHostMiddleware`（DNS リバインディング対策）。秘匿値マスキング・ログフィルタ。原子的 JSON 書込（`_atomic_write_text`）。`/api/health`。
 - CI: `.github/workflows/ci.yml`（ruff/pytest, build/vitest, audit）。`Makefile`（`make verify`）。
 - 改善バックログ: `docs/improvement_backlog.md`（100件チェックリスト）。
