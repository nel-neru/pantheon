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
  - `llm/` — OpenAI / Anthropic 抽象化レイヤー
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
- `datetime.utcnow()` は使用禁止 → `datetime.now(timezone.utc)` を使用
- タイムゾーン付き datetime を使用する
- データモデルは Pydantic / dataclass の既存パターンに合わせる
- テストは `tests/` 配下に追加し、pytestを使う
- 全件テストの収集・実行を壊さないこと
- Web/API変更時は 404 系挙動を壊さないこと（`web/server.py` に明示的な404ハンドリングあり）
- SpecialistAgent の `skills` は最低2個、最大3個
- 状態はグローバルなら `~/.pantheon`、対象リポジトリ固有なら `<repo>/.pantheon` に保存する

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
