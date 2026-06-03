# RepoCorp AI — LLM非依存基盤 → WebGUI → 自己改善ランタイム

## Context（なぜやるか）

RepoCorp AI は「開発者が自己成長型AI組織を作り、CLI / WebGUI / 自律デーモンでコード分析→改善提案→承認→自己改善を回す」プラットフォーム。最終ゴールは **WebGUI からユーザーが契約している任意のLLM（APIキーさえあれば誰でも）で Core 自身を改善できる** こと。今回は人間が外部AIエージェント（Claude Code 等）でその**基盤を構築**する。

調査で判明した根本問題（＝ユーザーが「困っている」点の正体）:

1. **LLMアクセス経路が二重化している。** 一部は provider 非依存の [`core/llm.get_llm_provider`](core/llm/__init__.py)（async, 5社対応）を使うが、`tool_design_agent` / `self_code_writer` / `orchestrator_agent` / `codebase_explorer_agent` / `agent_factory` および `core/` 多数（`goal_parser` `goal_decomposer` `pre_task_orchestrator` `capability_gap_analyzer` `org_designer` `meta_improvement_analyzer` `goal_verifier`）は **LangChain風 `llm_client.invoke(prompt)` 前提**。この `llm_client` を CLI/WebGUI から配線する箇所が無く、未注入時は**雛形/stub にサイレント degrade**する。→「どのAIでも全機能」は現状成立していない。
2. **エージェント設定が2つの異質な層で混ざって認識されている。**「ビルド時＝外部AIツールがCoreを開発する層（ツール毎に設定が違う）」と「実行時＝RepoCorp自身が任意LLMで動く層」。両者に単一の真実が無い。リポジトリ直下の `skills/` `commands/` `agents/` が Claude Code の `.claude/` と紛らわしいことも一因。
3. **プロバイダ差の正規化層が無い。** [`AnthropicProvider`](core/llm/anthropic_provider.py) は tool スキーマを正規化せず素通し、[`OpenAIProvider`](core/llm/openai_provider.py) だけ `_normalize_tools` を持つ。構造化出力（JSON）は各エージェントが素の `json.loads` で受けており（例 [`improvement_executor_agent.py:182`](agents/improvement_executor_agent.py)）壊れやすい。プロバイダ毎の能力差（tools / JSONモード / streaming+tools / reasoning_effort / context長）がモデル化されていない。
4. **自己改善（自己拡張）チェーンが休眠＆stub。** [`self_extension_pipeline`](core/intelligence/self_extension_pipeline.py)（ToolDesign→SelfCodeWriter）はどこからも呼ばれず、[`SelfCodeWriter`](agents/self_code_writer.py) は TODO 雛形生成止まり。「編集→テスト→反復→PR」の実ループとWebGUIからの起動口が無い。

**確定した方針（ユーザー回答）:** ①基盤 → ②WebGUI → ③自己改善 の**段階実行**。自己改善は**内蔵・プロバイダ非依存エンジン**（外部CLI非依存）。プロバイダは**設計のみ（5社の実機検証は後続）**。UIは **React を正典・出荷品質**（旧 `web/static/index.html` は撤去/隔離）。

---

## 中核メンタルモデル：2つの平面を分離し、各々に単一の真実を置く

| | 平面A：ビルド時 / 外部エージェント | 平面B：実行時 / 内部エージェント |
|---|---|---|
| いつ | 人間が外部AIツールで RepoCorp を**開発**する時 | WebGUIからユーザーのLLMが Core を**自律改善**する時 |
| ツール | Claude Code / Codex / Cursor / Copilot / Gemini CLI | RepoCorp 自身（外部ツール非依存） |
| 単一の真実 | **`AGENTS.md`**（＋各ツール用は薄いリダイレクト） | **`skills/*.yaml` + `agents/definitions/*.yaml` + `core/llm`** |
| 「設定がLLM毎に違う」問題 | AGENTS.md に集約し各ツールは参照だけ | そもそも RepoCorp の YAML に統一済（プロバイダ差は正規化層で吸収） |

この分離を**コードと文書の両方で**確立するのが Phase 1 の目的。

---

## Phase 1 — 基盤（今回の主成果）

### 1A. LLMアクセスを `core/llm` に一本化（最重要）

- **`LLMProvider` に同期ブリッジ＆構造化出力を追加**（`core/llm/base.py`）:
  - `invoke(prompt: str | list[LLMMessage]) -> LLMResponse` … 既存の無数の `llm_client.invoke()` 呼出をそのまま活かす互換アダプタ。内部は `generate()` をイベントループ安全に実行（実行中ループ検出→`run_coroutine_threadsafe`、無ければ `asyncio.run`）。
  - `generate_json(messages, schema=None) -> dict` … プロバイダの JSON/tool-forcing を使える場合は使い、使えない場合は**堅牢抽出**にフォールバック。抽出ロジックは既存の [`ToolDesignAgent._extract_json_object`](agents/tool_design_agent.py) を `core/llm/json_extract.py` に切り出して共用化（素の `json.loads` 箇所を順次置換）。
- **既定クライアントの解決を1箇所に集約**（`core/llm/__init__.py` に `get_default_llm_client()`）: GUI設定 `~/.repocorp/gui_settings.json`（[`_load_gui_settings`](web/server.py)）→ 環境変数の優先順で provider+key を解決し、`get_llm_provider()` を返す。CLI/WebGUI から各エージェント生成時にこれを注入し、**未注入＝stub degrade を撲滅**。
  - 注入口: [`agents/agent_factory.py`](agents/agent_factory.py)、[`agents/orchestrator_agent.py`](agents/orchestrator_agent.py)（`OrchestratorAgent.create()`）、[`main.py`](main.py) `_get_orchestrator`、`web/server.py` のエージェント生成箇所。
- **`.invoke()` 利用箇所はインターフェース互換のまま**（戻り値 `.content`）にして、まず「実LLMで動く」状態を作る。個別リファクタは段階的に。

### 1B. プロバイダ能力＋正規化層（設計を実装、5社の実機検証は後続）

- **`core/llm/capabilities.py`**: `ProviderCapabilities`（`supports_tools` / `supports_json_mode` / `supports_streaming` / `supports_streaming_tools` / `supports_reasoning_effort` / `context_window` / `default_models`）を provider 毎に定義。`LLMProvider.capabilities` プロパティで公開。
- **`core/llm/model_registry.py`**: いま `web/server.py` の `FALLBACK_MODELS` / 各 provider の `DEFAULT_MODELS` / `get_model_name` に散在するモデル情報を集約（provider→models＋メタ）。`web/server.py` と各 provider はここを参照。
- **tool スキーマの中立化**: 中立 tool 表現（`name`/`description`/`input_schema`）を正と定め、[`AnthropicProvider`](core/llm/anthropic_provider.py) にも `_normalize_tools` 相当を実装（現状 OpenAI だけ持つ非対称を解消）。
- **API/Settings へ能力を公開**: `GET /api/settings` 応答（[`SettingsResponse`](web/server.py)）と `GET /api/providers/{provider}/models` に capabilities を載せ、WebGUI が「この provider で何ができるか」を表示できる土台に（UI 反映は Phase 2）。

### 1C. 2平面の設定ファイルを確立

- **平面A（外部ツール）**: `AGENTS.md` を唯一の正典に保ち、薄いリダイレクトを追加—
  - `CLAUDE.md`, `GEMINI.md`, `.github/copilot-instructions.md`, `.cursor/rules/repocorp.mdc`（または `.cursorrules`）… いずれも「正典は `AGENTS.md`。まずそれを読め」と最小記述＋重要規約の要点のみ。
  - （任意）`.mcp.json` は MCP 利用方針が固まってから。今回はスコープ外として AGENTS.md に方針メモのみ。
- **平面B（内部）**: 既存 `skills/*.yaml` / `agents/definitions/*.yaml` を維持。
- **命名衝突の明文化**: `docs/architecture.md` に「2平面」節を追加し、`skills/`・`agents/`・`commands/` が **RepoCorp 実行時概念であり Claude Code の `.claude/` ではない**ことを明記。物理リネームは import/テスト破壊リスクが高いため**今回はしない**（文書で解消）。

### Phase 1 完了の定義
- 任意の1プロバイダの API キーだけで、stub に落ちず実LLMで主要フロー（chat / analyze / goal / orchestration）が動く。
- `generate_json` 経由で JSON 取得が堅牢化。`capabilities` / `model_registry` が API で取得できる。
- 外部ツール用リダイレクト群と「2平面」ドキュメントが揃う。
- `pytest tests/ -q` 全件グリーン（新規ユーティリティのテストを追加）。

---

## Phase 2 — WebGUI（React 正典・出荷品質）※次段

- **旧UIの撤去/隔離**: [`web/server.py`](web/server.py) の serve 経路を React `dist/` 専用に整理し、`web/static/index.html`（81KB単一HTML）は `web/legacy/` へ退避。AGENTS.md 規約の **404 系挙動は維持**（[`@app.get("/{full_path:path}")`](web/server.py) の SPA フォールバックを保全）。
- **全10画面を実機監査**（サーバ起動＋Preview/ブラウザMCP）。出荷品質ルーブリックで採点し、下回る要素を改善:
  - 一貫したデザインシステム（[`web/frontend/src/index.css`](web/frontend/src/index.css) のトークンを正とする）、空状態 / ローディング / エラー状態、フォーム検証フィードバック、トースト、リアルタイム（[`useWebSocket`](web/frontend/src/hooks/useWebSocket.ts) / `/ws/updates`）UX。
  - アクセシビリティ（ラベル / フォーカス可視 / コントラスト / キーボード操作）、レスポンシブ、ダーク/ライト両対応の整合、日本語コピーの統一。
  - 対象: `ChatPage` `OrgsPage` `AnalyzePage` `GoalsPage` `ProposalsPage` `AgentsPage` `DashboardPage` `DataPage` `SettingsPage` `HelpPage`（[`web/frontend/src/pages/`](web/frontend/src/pages)）。
  - **Phase 1 の capabilities/model_registry を Settings へ反映**（provider 毎の対応機能・モデル一覧の動的表示）。
- **規約遵守**: UI 変更時 `HelpPage.tsx` 更新、新規ページにテスト追加（pre-commit `scripts/install_hooks.sh`）。`web/frontend` の vitest（`npm run test`）と `pytest` を維持。

## Phase 3 — 自己改善ランタイム（内蔵・プロバイダ非依存）※次段

- **自己拡張チェーンを `core/llm` に統一**: [`ToolDesignAgent`](agents/tool_design_agent.py) / [`SelfCodeWriter`](agents/self_code_writer.py) の `llm_client.invoke` を Phase 1 の既定クライアントで充足（stub 脱却）。
- **`CoreImprovementAgent`（新規 `agents/core_improvement_agent.py`）**= 内蔵コーディングエージェント:
  - 計画 → 編集（差分 or 全文＋ガード）→ **対象 pytest 実行** → 失敗ならエラーを文脈に戻して**反復（上限付き）** → ブランチ/PR。
  - 適用/PR は既存 [`ImprovementExecutorAgent`](agents/improvement_executor_agent.py) と [`github_integration/pr_creator.py`](github_integration/pr_creator.py) を再利用。検証ゲートとして [`core/policy/engine.py`](core/policy/engine.py)（Core 変更は human_required）を通す。
- **WebGUIからの起動口**: 既存 [`TaskQueue`](core/orchestration/task_queue.py)＋`POST /api/tasks` に `core_improvement` タイプを追加し、ワーカーが `CoreImprovementAgent` を駆動。進捗は既存 `/ws/updates`＋`execution_history` で配信。→「Core 改善を WebGUI から」の基盤完成。

---

## 主要な再利用（新規作成より優先）

- 堅牢JSON抽出: [`ToolDesignAgent._extract_json_object`](agents/tool_design_agent.py) を共通化。
- 適用/ブランチ/PR: [`ImprovementExecutorAgent`](agents/improvement_executor_agent.py) ＋ `github_integration/pr_creator.py`。
- 設定解決: [`_load_gui_settings` / `_PROVIDER_KEY_MAPPING`](web/server.py)（CLI 側 [`main.py`](main.py) にも同等あり→共通化候補）。
- 起動/進捗: [`TaskQueue`](core/orchestration/task_queue.py)、`UpdateHub` / `/ws/updates`、`execution_history`（`web/server.py`）。
- ガード: [`PolicyEngine`](core/policy/engine.py)（`DEFAULT_POLICY`）。
- デザイントークン: [`web/frontend/src/index.css`](web/frontend/src/index.css)。

## リスク / 留意

- `.invoke()` の同期ブリッジは**実行中イベントループ**（FastAPI async 文脈）での `asyncio.run` 二重起動に注意 → ループ検出して別スレッド実行。
- 全文書き換え方式は `max_tokens`（現状 8000）で大ファイル truncate の恐れ → Phase 3 で差分編集を検討。
- ディレクトリ物理リネームはしない（テスト/インポート破壊回避、文書で命名整理）。
- プロバイダ実機検証は今回スコープ外（設計と正規化層まで）。`capabilities` は保守的な既定値で開始。

## 検証

- **Phase 1**: `python -m pytest tests/ -q --tb=short`（624件＋新規グリーン）。1プロバイダのキーのみ設定し、`repocorp chat` / `analyze` / `goal run` が stub でなく実LLM応答することを確認。`GET /api/settings`・`/api/providers/*/models` に capabilities が載ることを確認。
- **Phase 2**: `repocorp serve` 起動 → Preview/ブラウザMCP で 10画面を巡回し、ルーブリック項目（空/ローディング/エラー/A11y/レスポンシブ/ダークライト）を実機確認。`npm run test`（vitest）＋`pytest` グリーン。
- **Phase 3**: WebGUI から `core_improvement` タスクを投入 → 編集→pytest→（失敗時）反復→ブランチ/PR、PolicyEngine の human_required ゲートが効くことを確認。

## 段階実行の順序

1. **Phase 1（今回着手）** → 2. Phase 2 → 3. Phase 3。各 Phase 完了時に `pytest` 全件グリーンと該当 Phase の検証を必須ゲートにする。

---

## 実装状況

### ✅ Phase 1 完了（2026-05-29）

- **新規**: `core/llm/json_extract.py`（堅牢JSON抽出）, `client.py`（同期ブリッジ `LLMClient` + `get_default_llm_client` / `get_configured_llm_provider` + provider/key/model 解決）, `capabilities.py`（`ProviderCapabilities` レジストリ）, `tool_schema.py`（tool中立化）, `model_registry.py`（モデル集約）。
- **基底拡張**: `core/llm/base.py` に `generate_json`（async）と `capabilities` プロパティ。
- **provider統一**: OpenAI/GitHubModels/Anthropic を `tool_schema` 経由に統一（Anthropic/GitHubModels の tool 正規化を新設、GitHubModels の tool_calls 引数パースのバグ修正）。
- **注入（クラス既定は不変）**: `main._get_orchestrator`・`web/server.py`（goal/analyze/approve 実行口）で `get_default_llm_client(settings=...)` を明示注入。`AbstractGoalPipeline(llm_client=...)` と `CodeReviewAgent(llm_provider=...)` を追加。`AbstractGoalPipeline.run` はクライアント有りで `use_llm` 自動有効化。
- **API公開**: `GET /api/settings` に `provider_capabilities`、`/api/providers/{provider}/models` に `capabilities`。`web/server.py` の `FALLBACK_MODELS` は `model_registry` 参照に移管。
- **2平面の確立**: `AGENTS.md` を正典化＋`CLAUDE.md` / `GEMINI.md` / `.github/copilot-instructions.md` / `.cursor/rules/repocorp.mdc` をリダイレクト追加。`docs/architecture.md` に「2平面」「LLMアクセス」節と命名注記。
- **テスト**: `test_llm_client` / `test_llm_capabilities` / `test_model_registry` / `test_tool_schema` / `test_llm_wiring`（stub撲滅の実証含む） / `test_api_capabilities` を追加。**全 699 件グリーン**。新規ファイルは ruff クリーン。

**設計上の安全則（重要・引き継ぎ）**: エージェントの `__init__` 既定は一切変えていない（`llm_client=None` のスタブ経路を保持＝既存テスト不破壊）。注入は呼び出し側のみ。`get_default_llm_client()` はキー未解決で `None` を返す。サーバは必ず `settings=_load_gui_settings()` を渡す（テストの monkeypatch と整合）。

**Phase 1 の既知フォロー（一部 Phase 3 で対応済み）**:
- `LLMConfig.from_env()` は env のみ参照（gui_settings を読まない）。グローバルに変えると provider 単体テスト（キー無し→ValueError 期待）を壊すため、`get_configured_llm_provider` 経由で個別解決する方針を維持。
- 既存 lint 債務（私の変更外）: `agents/conversation_agent.py` F401、`core/goals/goal_verifier.py`・`main.py`・`web/server.py` の import 並び I001。スコープ外のため未修整。

### ✅ Phase 2 完了（WebGUI: React 正典・出荷品質）

- **旧UI撤去**: `web/static/index.html` → `web/legacy/` へ git mv（`web/legacy/README.md` 追加）。`web/server.py` の配信を `dist/` 専用に整理、`STATIC_DIR` 定数を削除、未ビルド時は案内ページ(503)。
- **/api/* の404修正**: SPA catch-all が未知の `/api/*`・`/ws/*` を握りつぶしていた（200 HTML）のを **404 を返す**よう修正。
- **Settings に capabilities 反映**: `ProviderCapabilityRow`（ツール/JSON/ストリーミング/推論強度/文脈長チップ）を追加し、`/api/providers/{p}/models` の capabilities を表示。
- **実機監査**: `repocorp serve` + Preview MCP で全画面をダーク/ライト/モバイル巡回。コンソールエラー無し、既存UIは既に高品質と確認。
- 追加テスト: `tests/test_spa_serving.py`。vitest（SettingsPage capabilities）拡張。

### ✅ Phase 3 完了（自己改善ランタイム: 内蔵・プロバイダ非依存）

- **`agents/core_improvement_agent.py`（新規）**: LLM編集→`SafeChangeExecutor`でバックアップ/テスト検証/自動ロールバック→失敗時はエラーを文脈に戻して反復→検証済み差分。既定は validate_only（作業ツリーを元に戻す）。LLM未設定ならスタブ生成せず明確に失敗。
- **WebGUI起動口**: `POST /api/core/improve`（`web/server.py`）。`get_default_llm_client(settings=...)` 注入、`_resolve_self_improvement_org` で保存先解決、`PolicyEngine` で判定（Core変更→human_required）、検証済み変更を `ImprovementProposal`（category=`core_self_improvement`, status=`proposed`）として登録。承認は**既存の承認→ImprovementExecutor→PR フローを再利用**。
- **UI**: `web/frontend/src/components/CoreImprovePanel.tsx`（改善提案画面の最上部）。HelpPage に手順を追記。
- 追加テスト: `tests/test_core_improvement_agent.py`(8), `tests/test_core_improve_api.py`(4), `CoreImprovePanel.test.tsx`(3)。

**最終検証**: `pytest` **715 passed** / `vitest` **76 passed** / frontend build OK / 新規ファイル ruff クリーン / 実機で `/api/core/improve`(422 validation) と Core改善パネル描画を確認。

### ✅ Phase 4 完了（残課題 + API/CLI実行モード + cmux再現ターミナル）

**残課題**: ①`ImprovementExecutorAgent` を `get_configured_llm_provider` 経由に（GUI保存キー単独で動作）。②`CoreImprovementAgent` 複数ファイル対応＋検証済み変更をサイドカー保存し承認時に直接適用（`SafeChangeExecutor.apply_changes` 追加、再生成回避）。④ **repo 全体を ruff クリーン化**（142 自動修正＋手動修正、`pre_task_orchestrator` の `import asyncio` 欠落という潜在バグも修正）。

**実行モード(API/CLI)**: `core/execution/cli_registry.py`（claude/codex/gemini/aider/opencode, PATH 可用性検出, コマンド上書き可）。gui_settings に `execution_mode`/`cli_tool`/`cli_commands`。`GET /api/execution/modes` ＋ Settings に「実行モード」カード。API=内蔵 / CLI=ターミナルで外部CLI起動。

**cmux 再現ターミナル**: `web/terminal.py`（PTY セッション/スクロールバック/BEL通知/git ブランチ, localhost限定）＋ REST(`/api/terminal/sessions`)＋ WS(`/ws/terminal/{id}`)。フロント: `components/TerminalView.tsx`(xterm.js)＋`pages/TerminalPage.tsx`（縦タブ・ワークスペース、git ブランチ/cwd/状態、エージェント待ちの青リング、CLI起動メニュー）。nav/route/HelpPage 追加。

**最終検証**: `pytest` **736 passed** / `vitest` **80 passed** / build OK / **ruff 0 errors(repo全体)** / 実機で埋め込みターミナル(実シェル prompt 表示)・CLI可用性検出(Gemini検出)・実行モードUI を確認。

**残課題（次ラウンド候補）**: ③ 5プロバイダ実機検証。CLIモードと内蔵エージェント実行の更なる統合（CLIワークスペースの出力をタスク結果として取り込む）。ターミナルのフル cmux 機能（分割ペイン・埋め込みブラウザ・socket API）。JS バンドル分割（xterm で 500KB 超の警告）。
