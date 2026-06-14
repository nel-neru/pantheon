# Pantheon — Agent Instructions

このファイルはAIエージェント（GitHub Copilot, Claude等）がこのリポジトリで作業する際に
最初に読むべきコンテキストファイルです。

## プロジェクト概要

Pantheonは「個人開発者が自分専用の自己成長型AI組織を立ち上げ、共に進化させる」プラットフォームです。
CLI / Web UI / 自律実行パイプラインを通じて、Organizationの作成、コード分析、改善提案、承認、自己改善を支援します。

## ディレクトリ構造

- `main.py` — `pantheon` CLI エントリーポイント。全サブコマンドを定義
- `agents/` — 実行可能なエージェント実装（レビュー、改善適用、探索、自己拡張系）
- `core/` — 中核ロジック
  - `models/` — Pydanticデータモデル（Organization, Division, Team, SpecialistAgent, ImprovementProposal）
  - `platform/` — グローバル状態 (`~/.pantheon`) 管理
  - `state/` — 各リポジトリ内 `.pantheon/` 状態管理
  - `goals/` — 抽象ゴール→計画→実行→検証パイプライン
  - `orchestration/` — Pre-Task分析、ルーティング、動的エージェント生成、実行パターン学習
  - `intelligence/` — スキルエンジン、CapabilityRegistry、ギャップ分析、コードベース索引
  - `quality/` — SelfImprovementLoop、内部コンサル、品質改善ループ
  - `metrics/` — 組織健康度・バランス・成長指標
  - `policy/` — Human-in-the-Loop承認ポリシー
  - `ui/` — ダッシュボード/ドキュメント生成などCLI支援UI
  - `llm/` — LLM メッセージ/レスポンスの値オブジェクト（ホスト型プロバイダ抽象は廃止 / F1）
  - `runtime/` — **Claude Code 実行バックエンド**（`claude_code.py` の `ClaudeCodeProvider`＝唯一の生成経路）＋ wmux マルチプレクサ連携
- `config/` — YAMLテンプレート、設定、ペルソナ
- `github_integration/` — GitHub PR作成・リポジトリ連携
- `web/` — FastAPIベースのWeb GUI/API
- `tests/` — pytestテスト群
- `docs/` — 人間/AI向け補足ドキュメント

## 主要コンポーネントと責務

- `core/models/organization.py` — 組織モデルと品質レビュー/改善提案モデル
- `core/bootstrap.py` — プラットフォーム初期化とMeta-Improvement Organizationの作成
- `core/platform/state.py` — グローバルOrganization管理、共有知識保存
- `core/state/manager.py` — 各対象リポジトリ内 `.pantheon/` の状態・提案・決定管理
- `core/orchestration/pre_task_orchestrator.py` — 実行前メタ分析、推奨パターン選択、学習記録
- `core/orchestration/task_router.py` — タスク種別×スキル重みで最適エージェント選定
- `core/orchestration/orchestration_pattern_store.py` — 実行実績の永続化と推奨パターン学習
- `core/goals/abstract_goal_pipeline.py` — 自然言語ゴールからOrganization生成・実行・検証までの統合パイプライン
- `core/intelligence/capability_registry.py` — Agent/Skill の能力レジストリ
- `core/intelligence/capability_gap_analyzer.py` — 不足能力の検出
- `core/intelligence/agent_skill_engine.py` — スキルをプロンプト/知識タグへ変換
- `agents/code_review_agent.py` — リポジトリ分析と改善提案生成
- `agents/improvement_executor_agent.py` — 承認済み提案の適用、ローカルブランチ/PR作成
- `agents/codebase_explorer_agent.py` — インデックス/スナップショットベースのコード探索

## 開発規約

- 新規Pythonファイルは `from __future__ import annotations` で始める
- 日本語を含む PowerShell スクリプト（`scripts/*.ps1`）は **UTF-8 BOM 付き**で保存する
  （Windows PowerShell 5.1 は BOM 無しを cp932 誤読しパースが壊れる）
- PS5.1 の `Start-Process -ArgumentList` は**空白を含む配列要素を自動クォートしない**
  （実証済み・引数が分割される）。空白を含む引数は手動クォートした1本の文字列で渡す
- `datetime.utcnow()` は使用禁止 → `datetime.now(timezone.utc)` を使用
- タイムゾーン付き datetime を使用する
- データモデルは Pydantic / dataclass の既存パターンに合わせる
- テストは `tests/` 配下に追加し、pytestを使う
- 全件テストの収集・実行を壊さないこと
- Web/API変更時は 404 系挙動を壊さないこと（`web/server.py` に明示的な404ハンドリングあり）
- SpecialistAgent の `skills` は最低2個、最大3個
- 状態はグローバルなら `~/.pantheon`、対象リポジトリ固有なら `<repo>/.pantheon` に保存する
- **ブランチ運用（命名規約・ライフサイクル）**: 作業は必ず `work/` プレフィックスのブランチで行い、
  `main` へ直接コミットしない。命名は `work/<slug>-<YYYYMMDD>`（slug は kebab-case のトピック。
  作成は `node scripts/new_work_branch.mjs <slug>`）。auto-commit フックの自動分岐は
  `work/auto-<timestamp>`。「完了」の判別は **origin/main にマージ済みか** が基準で、
  `node scripts/branch_status.mjs`（done/active/stale 分類、`--prune` で done 掃除）で確認する。
  完了した作業ブランチは `node scripts/merge_to_main.mjs`（テストゲート付き）で main へ統合する。
- **計画ドキュメントの取り扱い（Planning Document Hygiene）**: キックオフ・調査メモ・
  ロードマップ・フェーズ別の実装計画など **一時的な計画段階ドキュメントは `docs/plans/` に置く**。
  恒久ドキュメントフォルダ（`docs/design/`, `docs/architecture.md` 等）を計画ファイルで汚さない。
  実装完了後に重要な決定を恒久ドキュメントへ統合し、計画ファイルはアーカイブ/削除する
  （詳細は `docs/plans/README.md`）。検証は `python scripts/check_planning_docs.py`
  （`docs/` の .md を編集すると PostToolUse の統合フック `post-edit-checks.mjs` が自動実行）。

## 24時間自律基盤・トレンド・Org量産（運用サブシステム）

- **デーモン群**（`core/runtime/daemon_registry.py`）: improvement / content / trend / watchdog / revenue。
  `pantheon daemons status|start|stop <name|all>` で管理。`pantheon daemons watchdog install` で
  Windows タスクスケジューラに常駐登録（PC 再起動後も自動復帰）。状態は `~/.pantheon/daemons/`。
- **レート制限自動再開**（`core/runtime/usage_gate.py`）: 制限を全プロセス共有し、検知したら
  pause→reset 時刻に自動 resume。制限中は subprocess を起動しない（トークン浪費ゼロ）。
- **モデルティアリング**（`core/runtime/model_router.py` + `config/model_tiers.yaml`）: task_type で
  fable/sonnet/haiku を自動選択（heavy=長時間自律は Fable 5）。生成呼び出しに `task_type=` を渡すと有効（opt-in）。
- **トークンクォータ**（`core/runtime/quota_governor.py` + `config/token_quota.yaml`）: 5h 窓の実測消費で
  逼迫時に低優先タスクを自動スキップ＋light 降格。`GET /api/usage/summary`。
- **トレンド収集**（`core/trends/`）: `pantheon trends collect|list`。web/RSS+YouTube を収集・採点・
  重複排除し、高スコアを ContentJob/新規事業提案へ承認ゲート付きで変換（trend daemon）。
- **Org 量産**（`core/orchestration/org_template_designer.py`）: `pantheon org create --genre --persona
  --design` で LLM がジャンル別構成を設計→外部 Organization を1コマンド生成。ペルソナ/デザインは
  `config/personas/`・`config/design_styles/`。

## テスト実行

```bash
python -m pytest tests/ -q
```

テスト件数確認だけなら:

```bash
python -m pytest tests/ --collect-only -q
```

## 新機能追加時の基本パターン

1. 追加先レイヤーを決める（`core/`, `agents/`, `web/`, `github_integration/` など）
2. 必要なら `tests/test_<feature>.py` を追加し、`tmp_path` / `patch(get_platform_home, ...)` パターンに合わせる
3. 新しいAgentを追加したら `agents/` に配置し、`BaseAgent` 契約に従う
4. 新しいSkillを追加したら `AgentSkill` と `AgentSkillEngine.SKILL_DEFINITIONS` を更新する
5. 新CLI機能なら `main.py` に `cmd_*` 関数、parser定義、dispatch追加を行う
6. Capabilityとして公開したい場合は `CapabilityRegistry.scan_and_register_all()` か `register()` で扱える形にする
7. 既存テストが通ることを確認する

## 重要なファイル

- `core/models/organization.py` — データモデル（Organization, Division, Team, SpecialistAgent等）
- `core/orchestration/pre_task_orchestrator.py` — タスク実行前のメタ分析
- `core/goals/abstract_goal_pipeline.py` — 抽象目標→自律実行パイプライン
- `core/intelligence/capability_gap_analyzer.py` — 能力ギャップ自動検出
- `core/intelligence/capability_registry.py` — 現有能力の一覧化と利用実績管理
- `core/platform/state.py` — グローバルプラットフォーム状態
- `core/state/manager.py` — 各リポジトリ内の `.pantheon` 永続化
- `main.py` — CLIエントリーポイント
- `web/server.py` — FastAPIベースのWeb API
