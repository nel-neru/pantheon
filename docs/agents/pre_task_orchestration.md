# Pre-Task Orchestration

`core/orchestration/pre_task_orchestrator.py` は、
**「タスクが来たら即実行」ではなく、まず最善の実行方法を考える** ための層です。

## なぜ必要か

従来の問題設定はシンプルです。

- タスクが発生する
- 固定Agentがそのまま実行する
- 「誰が・どういう並びで・どの程度レビュー付きで」やるべきかを考えない

Pantheon ではこれを避けるため、全実行を原則として次の5段階で扱います。

1. **ANALYZE** — タスク種別・複雑度・要求スキルを整理
2. **RESEARCH** — 過去の知識・パターン統計・静的ベストプラクティスを参照
3. **SELECT / SPAWN** — 既存Agentを選ぶ、足りなければ作る
4. **EXECUTE** — 適切な実行パターンで走らせる
5. **LEARN** — 結果をパターンストアとknowledgeへ戻す

## 構成要素

- `PreTaskOrchestrator`
- `TaskRouter`
- `BestPracticeAdvisor`
- `DynamicAgentSpawner`
- `OrchestrationPatternStore`

## Analyze フェーズ

`TASK_ORCHESTRATION_PROFILES` によって、タスク種別ごとの標準設定が定義されています。

例:

- `code_review` → `review_loop`
- `improvement_execution` → `sequential_pipeline`
- `codebase_exploration` → `single_agent`
- `meta_improvement` → `hierarchical`
- `security_audit` → `review_loop`

`TaskAnalysis` には以下が入ります。

- `task_type`
- `complexity`
- `recommended_pattern`
- `recommended_agent_ids`
- `spawn_new_agent`
- `research_notes`
- `estimated_tokens`
- `confidence`

## 5つの実行パターン

### 1. Single Agent

- 定数: `single_agent`
- 向いているタスク: 単純な探索、知識整理、軽い単発作業
- 実装状態: `execute()` で明示実装済み

### 2. Sequential Pipeline

- 定数: `sequential_pipeline`
- 向いているタスク: 「前工程の出力が次工程の入力になる」作業
- 実装内容:
  - 各Agentの `result.output` を `previous_output` として次の `AgentTask.input` に渡す
- 典型例: 改善実行前後の段階処理

### 3. Review Loop

- 定数: `review_loop`
- 向いているタスク: 品質重視、レビュー付き実行
- 実装内容:
  - 先頭Agentが実行
  - 2番目のAgentがいれば `review_target` としてレビュー
- 典型例: `code_review`, `security_audit`

### 4. Parallel Then Merge

- 定数: `parallel_then_merge`
- 向いているタスク: 独立サブタスクが並列実行できる場面
- 実装内容:
  - `asyncio.gather()` で複数Agentを並列実行
  - 現在は「最初の成功結果」を代表結果として返す
- 注意: マージロジックはまだ簡易的

### 5. Hierarchical

- 定数: `hierarchical`
- 向いているタスク: 複雑で長期的、マネージャーがワーカーを束ねる仕事
- プロファイル上の利用: `meta_improvement`
- **現在の実装注意**:
  - `execute()` は hierarchical 専用処理をまだ持たず、未対応パターンは実質 `single_agent` にフォールバックする
  - つまり「分析上は推奨される」が、「実行エンジンが完全対応済み」とは言えない

> 補足: コードには `best_of_n` も定義されていますが、現在の主要プロファイルでは使われていません。

## TaskRouter はどう選ぶか

`core/orchestration/task_router.py` では、タスク種別ごとに重み付きスキル要求を持ちます。

例: `code_review`

- `CODEBASE_EXPLORATION`: 0.9
- `PERFORMANCE_ANALYSIS`: 0.7
- `TOOL_INTEGRATION`: 0.6
- `DEEP_RESEARCH`: 0.4

### 選定アルゴリズム

1. `CapabilityRegistry.list_agents()` から候補を取得
2. Agentごとに「持っているスキル」と要求スキルの一致度を計算
3. `usage_count` に応じて小さな利用実績ボーナスを加算
4. スコア上位 `max_agents` 件を返す
5. 正規化スコアが `SPAWN_THRESHOLD = 0.3` 未満なら `fallback_used=True`

### 出力

`RoutingDecision`:

- `selected_agent_ids`
- `routing_reason`
- `skill_match_scores`
- `fallback_used`

## DynamicAgentSpawner の役割

`routing.fallback_used` かつ推奨Agent不足のとき、
`PreTaskOrchestrator` は `spawn_spec` を組み立てます。

`DynamicAgentSpawner` 側では:

- 既存Agentの再利用を先に試す
- 文字列スキル名を `AgentSkill` に解決
- 必要ならエイリアス（`research`, `security`, `docs`, `workflow` など）で補完
- 2スキル未満なら `DEEP_RESEARCH` を補助で追加
- CapabilityRegistry へ新Agentを登録

## BestPracticeAdvisor の役割

`RESEARCH` フェーズでは次の順序で助言を作ります。

1. `KnowledgeManager` から関連知識を取得
2. `OrchestrationPatternStore` の統計を表示
3. 静的ベストプラクティスへフォールバック

これにより `TaskAnalysis.research_notes` に、「この種のタスクでは何が効いたか」を埋め込めます。

## OrchestrationPatternStore はどう学習するか

`core/orchestration/orchestration_pattern_store.py` は `PatternRecord` を `orchestration_patterns.json` に保存します。

### 保存される情報

- `task_type`
- `pattern`
- `agent_ids`
- `success`
- `execution_time_ms`
- `quality_score`
- `notes`
- `timestamp`

### 学習ロジック

- `task_type × pattern` ごとに集計
- 成功率と平均品質を計算
- **3件未満の履歴では推奨を返さない**
- 3件以上なら「成功率 → 平均品質」の順でベストパターンを返す

つまり、初期は静的プロファイル中心、履歴が溜まると実績ベースで最適化されます。

## 実行後に何が保存されるか

`PreTaskOrchestrator._record_execution()` は成功/失敗を次に送ります。

- in-memory execution log
- `OrchestrationPatternStore`
- `OperationPatternDetector`（あれば）
- `KnowledgeManager`（成功時のみ）

## CLIからの観測方法

- `pantheon orchestration analyze <task_type>`
- `pantheon orchestration history`
- `pantheon orchestration capabilities`
- `pantheon orchestration self-review`

## 現時点で押さえるべきポイント

- ルーターは**スキル重みベース**で選ぶ
- 実行パターンは**静的プロファイル + 学習結果**で決まる
- 履歴が3件以上で初めて PatternStore の推薦が効き始める
- Hierarchical は概念として重要だが、実行器はまだ完全実装ではない
- 学習は knowledge と統計の二本立てで蓄積される
