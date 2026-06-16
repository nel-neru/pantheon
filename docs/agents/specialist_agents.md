# SpecialistAgent パターン

`SpecialistAgent` は Pantheon の組織モデルにおける最小の専門実行単位です。
`core/models/organization.py` では Pydantic モデルとして定義され、次の制約を持ちます。

- `name: str`
- `skills: List[AgentSkill]`（**最低2個、最大3個**）
- `description`
- `current_task`
- `performance_score`
- `created_at`

## 良い SpecialistAgent とは

良い SpecialistAgent は「何でもできるAgent」ではなく、**狭く深い責務**を持ちます。

### 条件

1. **役割が明確**
   - 例: コード探索、改善適用、能力設計
2. **スキルの相乗効果がある**
   - 2〜3スキルの組み合わせで行動原理が強化される
3. **プロンプトへ反映できる**
   - `AgentSkillEngine` が persona / focus / output_hint を注入できる
4. **ナレッジ再利用しやすい**
   - スキル値が knowledge tag にそのまま使われる
5. **組織上の配置先が自然**
   - Team mission や task_type と結びついている

## スキルの意味

`AgentSkill` は現在次の10種類です。

| Skill | 役割の要点 |
| --- | --- |
| `STRATEGIC_PLANNING` | 長期視点、優先順位、将来価値 |
| `CORPORATE_RESEARCH` | 競合/業界調査、ベストプラクティス参照 |
| `ORG_DESIGN` | 責務分離、モジュール構造、設計整理 |
| `AGENT_WORKFLOW_DESIGN` | エージェント協調、状態管理、ワークフロー設計 |
| `PROMPT_ENGINEERING` | LLM入出力品質、トークン効率 |
| `TOOL_INTEGRATION` | 外部API/GitHub/安全性/認証の扱い |
| `DEEP_RESEARCH` | 根本原因分析、証拠重視の調査 |
| `PERFORMANCE_ANALYSIS` | 計算量、I/O、スケーリング |
| `KNOWLEDGE_CURATION` | ドキュメント化、再利用しやすさ |
| `CODEBASE_EXPLORATION` | コードベース全体把握、依存関係俯瞰 |

## よく使われるスキル組み合わせ

| 組み合わせ | 効果 | コード例 |
| --- | --- | --- |
| `DEEP_RESEARCH` + `PERFORMANCE_ANALYSIS` | 表面的な不具合ではなく、原因とコストの両方を見る | `main._make_code_review_agent()` |
| `PROMPT_ENGINEERING` + `TOOL_INTEGRATION` | LLM生成物を実際のファイル変更やGitHub操作に接続しやすい | `main._make_improvement_executor()`, `SelfCodeWriter` |
| `CODEBASE_EXPLORATION` + `DEEP_RESEARCH` | 広く見てから深く掘る探索型エージェントになる | `CodebaseExplorerAgent` |
| `STRATEGIC_PLANNING` + `AGENT_WORKFLOW_DESIGN` | 不足能力をどの形で組み込むべきか設計しやすい | `ToolDesignAgent` |
| `CORPORATE_RESEARCH` + `ORG_DESIGN` + `STRATEGIC_PLANNING` | 組織構造テンプレートの初期設計に向く | `meta_improvement.yaml` 内 Org Research Team |
| `DEEP_RESEARCH` + `TOOL_INTEGRATION` + `PERFORMANCE_ANALYSIS` | ツール導入と実効性評価を両立できる | `meta_improvement.yaml` 内 Tool Adoption Team |

## AgentSkillEngine はどうスキルを使うか

`core/intelligence/agent_skill_engine.py` は各スキルを以下の3要素に変換します。

- `persona` — どんな専門家として振る舞うか
- `focus` — 何を重視して見るか
- `output_hint` — どんな形式・観点で出力するか

`apply_skills_to_prompt(base_prompt, skills)` はこれらを `===【あなたの専門スキル】===` ブロックとして追記します。

### 実際の挙動

- `BaseAgent.apply_skills_to_prompt()` から利用可能
- `BaseAgent.get_skill_tags()` で knowledge 検索タグにも転用される
- `CodeReviewAgent` は実際に `apply_skills_to_prompt()` を使用している
- ほかのAgentでも `BaseAgent` を通じて利用可能だが、全クラスでまだ完全統一はされていない

## コードベース内の具体例

### 1. CodeReviewAgent

- 実体: `agents/code_review_agent.py`
- スキル: `DEEP_RESEARCH`, `PERFORMANCE_ANALYSIS`
- 目的: コードの問題を「根本原因」と「性能/保守性」の両軸で提案化
- 特徴: `REVIEW_SYSTEM_PROMPT` にスキル注入を行う

### 2. ImprovementExecutorAgent

- 実体: `agents/improvement_executor_agent.py`
- スキル: `PROMPT_ENGINEERING`, `TOOL_INTEGRATION`
- 目的: 改善提案を正確なファイル変更へ落とし込み、GitHubまたはローカルgitへ接続
- 特徴: PR作成 / ローカルブランチ作成を切り替える

### 3. CodebaseExplorerAgent

- 実体: `agents/codebase_explorer_agent.py`
- スキル: `CODEBASE_EXPLORATION`, `DEEP_RESEARCH`
- 目的: 全体把握 → 必要箇所だけ詳細調査、という探索プロトコルを提供
- 特徴: `CodebaseIndexer` と `CodebaseSnapshot` を使ってトークンを節約

### 4. YAMLから生成される SpecialistAgent

- 実体: `core/org_factory.py`
- 目的: Team定義から1体の SpecialistAgent を自動生成
- 特徴:
  - 3スキル超は先頭3個に正規化
  - 1スキルなら `STRATEGIC_PLANNING` を補完
  - 0スキルなら `STRATEGIC_PLANNING + DEEP_RESEARCH`

### 5. DynamicAgentSpawner

- 実体: `core/orchestration/dynamic_agent_spawner.py`
- 目的: 適任Agent不在時に新しい SpecialistAgent を生成
- 特徴: `research`, `security`, `docs`, `workflow` などの別名から `AgentSkill` にファジーマッチする

## 設計上の注意点

1. 3スキルを超えない
2. スキルは「並べるだけ」でなく、実際のプロンプトや選定ロジックに効く組み合わせにする
3. 新しいスキルを増やす場合は次もセットで更新する
   - `core/models/organization.py` の `AgentSkill`（enum メンバー）
   - `skills/<value>.yaml`（`SkillLoader` が読み込む定義。`id` は enum 値と一致。`SKILL_DEFINITIONS` 辞書は廃止）
   - `core/orchestration/task_router.py` の `TASK_SKILL_REQUIREMENTS`（必要なら）
   - 組織テンプレートやテスト
4. 役割が広すぎる場合は新Agentに分割する

## 推奨パターン

- **調査系**: `CODEBASE_EXPLORATION` + `DEEP_RESEARCH`
- **実装系**: `PROMPT_ENGINEERING` + `TOOL_INTEGRATION`
- **設計系**: `STRATEGIC_PLANNING` + `ORG_DESIGN` or `AGENT_WORKFLOW_DESIGN`
- **知識系**: `KNOWLEDGE_CURATION` + `DEEP_RESEARCH` or `STRATEGIC_PLANNING`
