# Agents Overview

RepoCorp AI には、CLIから直接使うエージェントと、自己拡張/内部支援に使うエージェントの両方が存在します。
すべての実行型エージェントの基底契約は `agents/base.py` にあります。

## 共通契約

- 入力: `AgentTask(task_type, description, input)`
- 出力: `AgentResult(success, output, thinking_process, execution_log, error)`
- 基底クラス: `BaseAgent`
- SpecialistAgent を持つ場合、スキルは 2〜3 個に制約される

## エージェント一覧

| Agent / Class | 主な役割 | 代表スキル | 主な利用箇所 | 備考 |
| --- | --- | --- | --- | --- |
| `CodeReviewAgent` | 対象リポジトリを分析して改善提案を生成 | `DEEP_RESEARCH`, `PERFORMANCE_ANALYSIS` | `repocorp analyze`, Web `/api/analyze` | `apply_skills_to_prompt()` を使う代表例 |
| `ImprovementExecutorAgent` | 承認済み提案をコードへ反映し、PR/ローカルブランチを作成 | `PROMPT_ENGINEERING`, `TOOL_INTEGRATION` | `repocorp approve`, `SelfImprovementLoop` | GitHub token がなければローカル適用。git 操作は `to_thread`（E9） |
| `CoreImprovementAgent` | RepoCorp 自身（Core）を LLM で改善。編集→`SafeChangeExecutor`でテスト検証→反復→検証済み差分 | （内蔵コーディングエージェント） | `POST /api/core/improve`, `components/CoreImprovePanel.tsx` | 既定 validate_only。Core 変更は `PolicyEngine` で human_required。LLM 未設定なら明確に失敗（stub 生成しない） |
| `CodebaseExplorerAgent` | コードベース探索を索引/スナップショットで軽量化 | `CODEBASE_EXPLORATION`, `DEEP_RESEARCH` | 内部探索、将来の review/exploration 強化 | `CodebaseIndexer` と `CodebaseSnapshot` を利用 |
| `ToolDesignAgent` | 能力ギャップから新能力の実装仕様を作る | `STRATEGIC_PLANNING`, `AGENT_WORKFLOW_DESIGN` | 自己拡張フロー、tests | `ImplementationSpec` を返す |
| `SelfCodeWriter` | 実装仕様から Python コード雛形を生成 | `PROMPT_ENGINEERING`, `TOOL_INTEGRATION` | 自己拡張フロー、tests | import 推定や雛形生成を担当 |
| `ConversationAgent` | knowledge・提案・組織状態に基づく自然言語回答 | なし（`BaseAgent` 継承ではない） | 内部会話/将来の対話UI | platform state / knowledge を横断参照 |
| `SpecialistAgent` (model) | Organization 配下の汎用専門担当 | YAMLや動的生成に依存 | `org_factory`, `DynamicAgentSpawner` | データモデルであり、そのままでは `run()` を持たない |

## CLIから直接見えるフロー

### 1. Analyze flow

- `main._make_code_review_agent()` が `CodeReviewAgent` を構築
- `cmd_analyze()` が `AgentTask(task_type="code_review")` を作成
- 結果は `ImprovementProposal` として保存される

### 2. Approve flow

- `main._make_improvement_executor()` が `ImprovementExecutorAgent` を構築
- `cmd_approve()` が対象提案を `improvement_execution` タスクとして実行
- GitHub連携があればPR、なければローカルブランチ作成

### 3. Self-improvement flow

- `SelfImprovementLoop` が `.repocorp/improvements/` から提案を取得
- 組織内Agentの先頭を `ImprovementExecutorAgent` に渡して改善を実行

## 内部支援フロー

- `CodebaseExplorerAgent`
  - フルスキャンを繰り返さず、インデックスを再利用するための探索専用役
- `ToolDesignAgent` + `SelfCodeWriter`
  - `CapabilityGapAnalyzer` が見つけた不足能力を「仕様→コード」に落とし込む自己拡張ライン
- `ConversationAgent`
  - 提案件数、既知課題、組織健康度などの要約回答を返す

## SpecialistAgent の供給源

### YAMLテンプレート由来

`core/org_factory.py` は `config/departments/*.yaml` を読み取り、各Teamごとに1つの `SpecialistAgent` を生成します。
スキル数が1個しかない場合は `STRATEGIC_PLANNING` を補完し、0個なら
`STRATEGIC_PLANNING + DEEP_RESEARCH` を使います。

### 動的生成由来

`core/orchestration/dynamic_agent_spawner.py` は、TaskRouter で十分なマッチが得られなかった場合に
`SpawnRequest(required_skills, purpose, task_type, suggested_name)` から新しい SpecialistAgent を生成します。

## Agentを追加する場合

1. `agents/<name>.py` を追加
2. `BaseAgent` を継承し `async def run(...)` を実装
3. デフォルトの `SpecialistAgent` を用意する場合は 2〜3 スキルにする
4. 必要に応じて `CapabilityRegistry.scan_and_register_all()` で検出されるように配置する
5. CLIで使うなら `main.py` に生成ヘルパー + コマンド経路を追加する
