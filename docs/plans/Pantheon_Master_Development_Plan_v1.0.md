# Pantheon Master Development Plan v1.1
**Version**: 1.1 (Re-baselined against actual codebase)  
**Date**: 2026-06-13（初版 1.0 = 2026-06-12）  
**Status**: 再ベースライン済（Re-baselined） — §2 を実コード分析で充填し、Phase 0 を「実際に欠けている少数」へ絞り直した  
**Purpose**: Pantheonリポジトリ内でClaude Codeとペアプロするための**単一の生きている計画書**。理想のビジョン（Grand Vision）を最上位ゴールとして完全に保持し、Phase 0の実行可能な仕組み構築を最優先で進めるための統合版。  
**Target**: Phase 0（仕組み構築期）を最優先で完了させ、Pantheonが「自分で計画を回せる状態」になること。その上で、長期的に「AIネイティブ自律組織OS」として完成させる。

> **v1.1 の要点**: 計画書 v1.0 は「初期状態」を前提に書かれていたが、実分析の結果、**Phase 0
> インフラの 7〜9割は既に実装済み**（daemon群+watchdog、rate-limit gate、model routing、quota
> governor、PyInstaller spec、2つの GUI、収益サブストレート、content→承認→公開フロー）であることが
> 判明した。真の残ギャップは少数（収益GUI入力／`_publish_live`／2階層プラグイン）。詳細は §2。

---

## 0. このドキュメントの使い方（Claude Code向け）

このドキュメントをClaude Codeに読み込ませて、以下の指示を出すことで一貫した開発を進められるようにする。

**推奨の使い方**:
- セッション開始時にこのファイル全体をコンテキストとして渡す
- 「この計画に基づいて、次にやるべきタスクを提案して」と指示
- 実装時は「この計画の[該当セクション]に従って実装して」と具体的に指定
- 重要な決定は必ずこの計画に反映させる（自己更新を促す）
- 計画に矛盾が生じたら、すぐに指摘して計画の更新を提案する

**更新ルール**:
- この計画は **Version 1.0（初期状態）** から開始する
- 重要な設計判断・実装完了・新しい知見が出たら、**必ずこのファイルに反映**し、バージョン番号を上げる（例: 1.1, 2.0 など）
- 「この計画を最新の状態に更新して」と指示すると良い
- 変更履歴は簡潔に冒頭または末尾に追記

---

## 1. 究極のビジョン（Grand Vision） — 私のゴールとして完全に保持

**Pantheon = 「個人/小規模事業者が持つ、24時間365日自律経営するAIネイティブ組織OS」**

- **Pantheonが主役**：組織の戦略立案・実行・改善・成長をほぼ全てAIが担う。
- **人間は組織の一員**：人間は「Human Specialist Member」として、**人間しかできないタスク**（初回アカウント作成、高リスク承認、創造的判断、外部交渉など）だけを任される。
- **成長しながらスケール**：副業1つから始め、収益データに基づいて新事業（新org）を自律的に立ち上げ、ポートフォリオ全体を最適化・拡大していく。副業モデルプラグインを選んで追加するだけで、即座に事業部が完成し、ユーザー好みに勝手に成長する。
- **究極のゴール**：ユーザーが「Pantheon、今年の副業全体で月100万円目指して最適に運用して」と言うだけで、**複数のAI事業部が24時間動き、収益を最大化し、自動で改善・新事業創出**してくれる状態。

Pantheonは単なるツールではなく、**ユーザーの「AI経営会社そのもの」**になる。

### 1.1 コア原則（Core Principles）

1. **Pantheon First（Pantheon主導）**  
   意思決定・実行のデフォルトはPantheon。人間は例外的に介入。

2. **Human-as-Member（人間は組織メンバー）**  
   人間はorg chart上に「Human Specialist」として位置づけられ、タスクをアサインされる。

3. **24/7 Autonomous Operation（完全自律24時間運用）**  
   デーモン + 永続メモリ + Fable級長時間実行で、ユーザーが寝ている間も改善を続ける。

4. **Self-Evolving & Self-Expanding（自己進化・自己拡大）**  
   収益データ・トレンドから新スキル・新orgを自律提案・作成。

5. **Revenue as First-Class Citizen（収益を一級市民扱い）**  
   収益トラッキング・分析・予測・最適化・再投資判断を自動化。

6. **Human Gate for High-Risk Only（高リスクのみ人間ゲート）**  
   低〜中リスクは自動実行。高リスク・人間しかできないことのみ人間承認。

7. **Packaging as Real App（本物のアプリとして提供）**  
   Pantheon.exeを「AI経営OSアプリ」として洗練。インストール → 即組織起動。

### 1.2 理想の最終アーキテクチャ（Ideal Final Architecture）

ユーザーの提案を採用して、**Pantheonを「グループ会社の経営層」**として設計する形に進化させた。

```
┌─────────────────────────────────────────────────────────────────┐
│  Pantheon Group HQ（グループ経営層）                               │
│  Meta-Overseer（究極のCEO Agent）                                 │
│  - 複数収益モデル会社の統括・資源配分・グループ全体最適化           │
│  - トレンド監視・新収益モデル会社立ち上げ・共有事業部の管理        │
│  - Fable 5級長時間自律実行 + 大規模Sub-Agent生成                   │
└──────────────────────────┬──────────────────────────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        ▼                  ▼                  ▼
┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
│ 収益モデル会社A   │ │ 収益モデル会社B   │ │ 収益モデル会社C   │ ...（無限拡張）
│ (例: Note販売会社) │ │ (例: アフィ会社)  │ │ (例: YouTube会社) │
│                  │ │                  │ │                  │
│ - X集客事業部     │ │ - X集客事業部     │ │ - X集客事業部     │
│ - note販売事業部  │ │ - アフィ事業部    │ │ - 動画作成事業部   │
│                  │ │                  │ │ - 収益化事業部    │
└──────────────────┘ └──────────────────┘ └──────────────────┘
        │                  │                  │
        └──────────────────┼──────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  Persistent Runtime Layer（永続実行基盤）                         │
│  - Layered Memory + Group-wide Knowledge共有                     │
│  - Daemon群（24/7） + Watchdog + Checkpoint/Resume               │
│  - Revenue Intelligence Engine（グループ全体収益最適化）         │
│  - Self-Evolution Engine（会社横断の改善ループ）                 │
└─────────────────────────────────────────────────────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        ▼                  ▼                  ▼
   Human Member     GUI Observatory     External Tools
   (タスク受領)       (監視・承認)         (API/ブラウザ)
```

**この構造のメリット**:
- 管理のシンプルさ：原則として各収益モデル会社は**独立した事業部を持つ**（共有は極力避ける）。
- 明確な責任範囲とスケーラビリティ。
- 現実の会社組織に近い感覚。

### 1.3 主要モジュール（Key Modules）

**A. Meta-Overseer / HQ Agent**  
Pantheon全体の「CEO Agent」。毎日/毎週の経営会議を自律開催。収益レポート自動生成 → 改善提案 → 実行。新org設計・立ち上げ。

**B. Revenue Intelligence Engine（最重要新機能）**  
自動収集・分析・改善・再投資判断を自動化。

**C. Specialized Organizations（事業部）**  
Meta-Overseerが自律的に新orgを作成。各orgは独立しつつHQと連携。

**D. Persistent Runtime & Daemons**  
24/7常時稼働。Trend Monitor、Self-Evolution、Revenue Daemonなど。

**E. Human Member Management**  
人間をorg chart上に登録し、Human-onlyタスクを自動アサイン。

**F. Packaging & Distribution（アプリ化）**  
最終的に「Workspaceモデル」へ移行（gitリポジトリ管理から脱却）。PyInstallerをメインとし、Dockerは上級者向けオプション。

**G. 副業モデルプラグインシステム（2階層）** ★詳細は後述セクションで統合

---

## 2. 現在のPantheon状態分析（**最重要・新規追加セクション**）

**このセクションはPhase 0開始時点で必ず埋めること。**

Claude Codeに対する最初の指示:
1. 現在のPantheonのコードベースを**詳細に分析**せよ
2. 以下の観点で現状をまとめてこのセクションに反映せよ
3. 不足している部分を明確にリストアップせよ

**分析すべき観点（最低限）**:
- 現在のディレクトリ構造と主要ファイル
- 既存のDaemon・Agent構成
- Memory層の実装状況（Layered Memory / Playbookなど）
- GUIの現状（組織管理・プラグイン追加周り）
- データ永続化の現状（gitベース？ .pantheon/ など）
- pyproject.toml / 依存関係の状況
- Fable 5対応状況
- 既存のプラグイン機構の有無
- 収益トラッキングの実装状況
- 全体の技術的負債とボトルネック

**現状サマリー（2026-06-13 実コード分析で充填）**:

リポジトリは **Python 3.12 CLI + FastAPI + React 19/Vite/TS/Tailwind v4** のフラット構成。
全生成は**ローカル `claude` CLI 経由**（`core/runtime/claude_code.py`、ホスト型 API キーは無し）。
状態は **JSON 正準**（グローバル `~/.pantheon`／リポジトリ固有 `<repo>/.pantheon`）で、SQLite は
クエリ用ミラーのみ。

| 観点 | 実装状況 | 根拠（file:line） |
|------|---------|------------------|
| ディレクトリ構造 | フラット（`main.py`/`core/`/`agents/`/`commands/`/`web/` がルート） | `pyproject.toml` `[tool.setuptools.packages.find] where=["."]` |
| Daemon 構成 | ✅ improvement/content/trend/watchdog の4種が永続サービス化 | `core/runtime/daemon_registry.py:60-97`、`core/runtime/watchdog.py`、`scripts/install_watchdog_task.ps1`（Task Scheduler 常駐） |
| レート制限／クォータ／モデルティア | ✅ 全実装（A-1/A-2/A-5） | `core/runtime/usage_gate.py`、`model_router.py`+`config/model_tiers.yaml`、`quota_governor.py`+`config/token_quota.yaml` |
| Memory 層（Layered/Playbook） | ⚠️ パターン蓄積はあるが統一 "Playbook" 抽象は無し | `core/intelligence/agent_knowledge.py`、`core/intelligence/*`、`core/quality/*` |
| GUI | ✅ 2フロント並走 | `web/frontend/`（14画面: dashboard/inbox/orgs/proposals/handoffs/studio/content/revenue/agents/atlas/sessions/board/data/settings）、`web/atelier/`（6画面: observatory/pantheon/atelier/signals/inbox/handbook）。`web/server.py:215-234` が `PANTHEON_UI` で dist 切替 |
| データ永続化 | JSON 正準、SQLite はミラー | `core/platform/state.py:78-242`、`core/state/manager.py`、`core/state/sqlite_manager.py:24-27`（「副ミラー」明記） |
| pyproject/依存 | ✅ prod/dev/web の3分割 | `pyproject.toml` `[project.dependencies]` + `[project.optional-dependencies]`（dev/web）。ホスト型LLM SDK 無し |
| Fable 5 対応 | ❌ 未配線（ただし runtime はモデル非依存） | `config/model_tiers.yaml` は heavy→opus/standard→sonnet/light→haiku。`claude_code.py` は `--model` 委譲のみ → config 追記で対応可 |
| プラグイン機構 | ⚠️ genre ベースの org 量産（会社プラグイン相当）はあるが2階層化されていない | `commands/org.py`（`org create --genre --persona --design`）、`core/orchestration/org_template_designer.py`、`config/departments/` |
| 収益トラッキング | ⚠️ 記録・集計の土台はあるが GUI 単件入力と簡易レポートが無い | `core/metrics/outcomes.py`（`OutcomeStore.record`/`summary_for_org`/`REVENUE_METRICS`）、`GET /api/metrics/revenue`（`web/server.py:2512`）、`POST /api/outcomes/import`（一括, `:3842`）。**単件 POST 無し** |
| グループ会社構造／Meta-Overseer | ✅ Meta-Improvement Org=HQ、複数org管理、横断介入 | `core/bootstrap.py:23-76`、`core/platform/state.py`、`core/hierarchy/hq_interventions.py`、外部org実体3つ（affiliate/note/sns, `isolation_level=external`） |
| content→公開フロー | ⚠️ draft→承認→公開の骨格・dry-run は完成、実投稿は未実装 | `core/content/content_runner.py`、`core/publishing/`、全アダプタの `_publish_live` が `NotImplementedError`（`core/publishing/adapters/base.py:46-50`） |
| 技術的負債/ボトルネック | 収益→実投稿の「最後の1mile」未接続、プラグインの2階層化未了、Playbook 抽象の不在 | 上記参照 |

**Phase 0で最も不足している部分（2026-06-13 特定）**:

Phase 0 インフラの大半は既に存在する。**実際に欠けているのは少数**：

1. **収益の GUI 単件入力＋簡易レポート**（P2-8）— `OutcomeStore.record()` は存在するが
   HTTP 単件 POST と入力フォーム・期間集計レポートが無い。Phase 0 成功指標に明記された項目。
2. **`_publish_live` の実装**（追加発見）— content→承認→公開フローは完成しているが、全アダプタの
   実投稿が `NotImplementedError`。自律ループが「実際に出力する」ための最後の1mile。
3. **2階層プラグイン＋GUIマーケットプレイス**（P1-2）— 会社プラグイン相当（org量産）はあるが、
   事業部プラグイン（既存orgへ事業部追加）とマーケットプレイス UI が無い。
4. **Fable 5 の config 配線**（自明）— `config/model_tiers.yaml` への追記のみ。
5. **`src/` 移行は実施非推奨**（P1-4）— フラット配置は daemon の `python -m` entry point と
   PyInstaller spec が依存。移行は破壊的で価値が薄い → 計画から凍結（§13 参照）。

---

## 3. Phase 0 の最優先目標

Phase 0終了時点で達成すべき状態（File 1の目標を基盤に、ビジョンを意識して統合）:

- グループ会社構造（Pantheon Group HQ + 複数収益モデル会社）が動作している
- 会社プラグイン / 事業部プラグインの基本システムが動く
- Meta-Overseerが「新しい収益モデル会社を作る → 運用する → 改善する」という一連の流れを提案・実行できる
- 初期テンプレート作成のフレームワークが整っている
- 収益トラッキングの最低限の仕組みがある
- GUIで組織管理と提案確認がやりやすい状態になっている
- **長期ビジョンに沿った基盤**が整い、Phase 1以降でRevenue Intelligence Engineや自己拡大機能へスムーズに移行できる状態

---

## 4. Phase 0 で優先的に実装すべきもの（優先度順・統合版）

**優先度ルール**:
- **P1（最優先）**: Phase 0の根幹に関わるもの。後回しにすると全体が遅れる。
- **P2**: 重要だがP1の後で進めても大きな問題にならない。
- **P3**: あった方が良いが、Phase 0後半〜Phase 1に回しても問題ない。

> **【v1.1 現況早見表】**（各項目に ✅ 実装済 / ⚠️ 一部 / ❌ 未実装 を付与。詳細は §2）
> | # | 項目 | 現況 |
> |---|------|------|
> | P1-1 | グループ会社構造の基盤整備 | ✅ |
> | P1-2 | 2階層プラグインシステムの基本実装 | ❌（残タスク③） |
> | P1-3 | Meta-Overseer の基本能力強化 | ✅ |
> | P1-4 | `src/` レイアウトへの移行 | ❌ → **凍結提案**（§13） |
> | P2-5 | 実行設定の柔軟性基盤 | ⚠️ |
> | P2-6 | PyInstaller `.spec` のベース | ✅ |
> | P2-7 | 初期テンプレート作成フレームワーク | ✅ |
> | P2-8 | 収益トラッキングの最低限 | ⚠️（残タスク①） |
> | P3-9 | GUI の改善 | ✅ |
> | P3-10 | データ永続化（Workspace/SQLite） | ⚠️ → Phase 2 送り |
> | P3-11 | 依存関係整理 | ✅ |
> | P3-12 | 高度な共有事業部機能 | ⏸ 後回し |
> | 追加 | content→公開の実投稿（`_publish_live`） | ❌（残タスク②） |
> | 追加 | Fable 5 の config 配線 | ❌（残タスク④・自明） |

### P1（最優先）
1. **グループ会社構造の基盤整備**　〔✅ 実装済〕
   - Pantheon Group HQ（Meta-Overseer）の役割明確化
   - 収益モデル会社を追加できる仕組み
   - 事業部を各社に追加できる仕組み
   - 組織間の関係性管理（共有は極力避ける設計）

2. **2階層プラグインシステムの基本実装**　〔❌ 未実装 = 残タスク③〕
   - 会社プラグインを追加すると収益モデル会社が作成される仕組み（※ genre ベース org 量産が相当機能として既存）
   - 事業部プラグインを追加すると既存会社に事業部が追加される仕組み（※ 未実装）
   - GUIマーケットプレイスの基本UI（※ 未実装）

3. **Meta-Overseerの基本能力強化**　〔✅ 実装済〕
   - 現在の状態を分析して改善提案ができる
   - 「新しい収益モデル会社を作って」と指示されたら計画を立てて実行できる

4. **`src/` レイアウトへの移行**　〔❌ → 凍結提案。フラット配置は daemon の `python -m` entry point と PyInstaller spec が依存。§13 参照〕
   - 本番コードと開発用コードの明確な分離
   - `pyproject.toml` の `packages.find` 更新

### P2
5. **実行設定の柔軟性基盤（Execution Configurability）**　〔⚠️ 一部: daemon間隔/モデル/prompt/policy は GUI可変、token上限・承認閾値・通知は未露出〕
   - Daemon実行間隔のGUI設定対応
   - モデル選択・トークン上限などのリソース制御をアプリ設定で変更可能に

6. **PyInstaller `.spec` のベース作成**　〔✅ 実装済: `packaging/pantheon.spec`（本番品質）〕
   - 本番に含めるファイルと除外するファイルの明確化
   - 簡単なビルドテストの実施

7. **初期テンプレート作成フレームワーク**　〔✅ 実装済: `org_template_designer.py` + `config/departments/` + `org_factory.py`〕
   - 会社プラグイン・事業部プラグインの初期状態生成仕組み（詳細はセクション6参照）

8. **収益トラッキングの最低限の仕組み**　〔⚠️ 一部 = 残タスク①: 記録/集計/CSV import はあるが GUI 単件入力と簡易レポートが無い〕
   - 手動入力でも売上データを記録・集計できる状態にする
   - 後から自動収集に置き換えやすい設計にする

### P3
9. **GUIの改善（組織管理・プラグイン追加周り）**　〔✅ 実装済: 2フロント・org階層・承認・inbox〕
   - 組織の階層構造が見やすい
   - 提案の確認・承認がやりやすい
   - プラグイン追加が直感的にできる

10. **データ永続化部分の設計（Workspaceモデル）**　〔⚠️ JSON正準・SQLiteミラーのみ → 計画書通り Phase 2 送り〕
    - exeとDocker両対応を意識した抽象化レイヤーのプロトタイプ
    - SQLiteを中心としたテーブル設計（セクション5.2参照）

11. **`pyproject.toml` の依存関係整理**　〔✅ 実装済: prod/dev/web の3分割〕
    - dev依存と本番依存の明確な分離

12. **高度な共有事業部機能**（後回し推奨）　〔⏸ 後回し（一部は P2-5 と重複）〕
    - 定期実行系（Daemon）の間隔をGUI設定で変更可能にする
    - モデル選択・フォールバック、トークン使用上限などのリソース制御をアプリ設定で調整可能にする
    - Meta-Overseerの提案積極性や承認閾値をユーザー設定で変えられるようにする
    - 通知頻度や時間帯制御も設定可能にする

### 4.1 再ベースライン後の「真の Phase 0 残タスク」（v1.1 で新設）

上記マーカーの通り、Phase 0 インフラの大半は実装済み。**残る実装ギャップは以下に集約**する。
推奨順（ユーザー合意「全部やる」前提）：

| 順 | 残タスク | 対応する旧項目 | 規模/リスク | 中核ファイル |
|----|----------|----------------|-------------|--------------|
| ① | **収益 手動入力GUI + 簡易レポート** | P2-8 | 小・低 | `web/server.py`（`POST /api/outcomes` 追加）, `core/metrics/outcomes.py`（期間集計）, `web/frontend/.../RevenuePage.tsx`, `web/atelier` |
| ② | **`_publish_live` 実装（note を1st）** | 追加発見 | 中・中 | `core/publishing/adapters/note.py`, `core/publishing/runner.py` |
| ③ | **2階層プラグイン + マーケットプレイス MVP** | P1-2 | 大・中 | `core/org_factory.py`, `org_template_designer.py`, `commands/org.py`, 両フロント新画面 |
| ④ | **Fable 5 の config 配線**（即・横断） | ロードマップ | 極小・極小 | `config/model_tiers.yaml` |

**設計判断（§13 と整合）**：
- 各実装は **1サイクル=1 work ブランチ**で小さく出荷（`new_work_branch.mjs` → 実装 → test-triage → `merge_to_main.mjs`）。
- 既存資産を最大限再利用し新規実装を避ける（`OutcomeStore.record`、publishing の dry-run/未導入分岐、org テンプレ適用、policy/承認ゲート）。
- ②は Playwright・プラットフォーム固有・セッション認証で①より高リスクのため、確実な①を先に出す。

### 4.2 直近1〜2週間でやる 3〜5 タスク（v1.1 で新設）

1. **計画書 v1.1 への再ベースライン**（本更新）— §2 充填・現況マーカー・残タスク整理。【完了】
2. **Fable 5 の config 配線**（残タスク④）— `config/model_tiers.yaml` に追記し `claude --model` で smoke 確認。即着手。
3. **収益 手動入力GUI + 簡易レポート**（残タスク①）— `POST /api/outcomes` + RevenuePage 入力フォーム + 月次集計。Phase 0 成功指標を1つ確実にクローズ。
4. **`_publish_live`（note）の実装**（残タスク②）— content→承認→公開ループが実際に出力するようにする。
5. （バッファ）**2階層プラグイン MVP のキックオフメモ**（残タスク③）— `docs/plans/` に段階分割設計を起こす。

---

## 5. アーキテクチャ・データ設計（統合版）

### 5.1 ワークスペースデータ構造設計方針

将来的にアプリ化する際は、**gitリポジトリ管理から脱却**し、アプリが管理する「ワークスペース」モデルに移行する予定。

**基本コンセプト**:
- **Workspace** = Pantheonアプリが管理する1つのデータコンテナ（ローカルフォルダ or 将来的にクラウド）
- Workspaceの中に複数の**Organization（収益モデル会社）**を内包
- 各Organizationは独立したデータ領域を持つ
- Git連携は「上級者向けオプション」として残し、デフォルトはアプリ内完結とする

**データの永続化方針**:
| データ種別 | 保存方式 | 理由 |
|------------|----------|------|
| 組織構造・設定 | SQLite（またはJSON + インデックス） | 高速検索・整合性が必要 |
| Agent記憶・Playbook | SQLite + ファイル（大容量データ） | 検索性と容量のバランス |
| 記事・投稿ドラフト・履歴 | ファイルシステム（Markdownなど） | 人間が直接見やすい・編集しやすい |
| 収益データ・分析結果 | SQLite | 集計・クエリがしやすい |
| 実行ログ・提案履歴 | SQLite（時系列） | 検索・分析しやすい |
| 設定・ユーザー設定 | JSON or SQLite | 読み書きが簡単 |

**重要な設計原則**:
- Organization単位でのデータ分離を徹底
- 人間が読み書きしやすい形式を優先
- バージョン管理はアプリ内で独自に実装（スナップショット + 差分）
- バックアップはWorkspace単位で簡単に取れるようにする
- 移行性を確保

**現在のGitモデルからの移行パス**:
- Phase 0〜1では現在の「外部リポジトリ + `.pantheon/`」方式を継続
- Phase 2以降で「ワークスペースモデル」への移行を本格検討
- 移行ツールを用意して、既存の組織データをワークスペースに取り込めるようにする

### 5.2 ワークスペース用具体的なテーブル設計案（SQLite中心）

```sql
-- ワークスペース
CREATE TABLE workspaces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    path TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 組織（収益モデル会社）
CREATE TABLE organizations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    type TEXT,
    description TEXT,
    status TEXT DEFAULT 'active',
    config JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (workspace_id) REFERENCES workspaces(id)
);

-- 事業部
CREATE TABLE divisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    organization_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    type TEXT,
    parent_division_id INTEGER,
    config JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (organization_id) REFERENCES organizations(id)
);

-- Agent
CREATE TABLE agents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    division_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    role TEXT,
    model_preference TEXT,
    system_prompt TEXT,
    config JSON,
    last_active_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (division_id) REFERENCES divisions(id)
);

-- Playbook / Memory
CREATE TABLE playbooks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id INTEGER NOT NULL,
    category TEXT,
    title TEXT,
    content TEXT,
    usefulness_score INTEGER DEFAULT 0,
    usage_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (agent_id) REFERENCES agents(id)
);

-- コンテンツ（メタデータのみ。本文はファイル管理）
CREATE TABLE contents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    division_id INTEGER NOT NULL,
    type TEXT,
    title TEXT,
    file_path TEXT,
    status TEXT DEFAULT 'draft',
    metadata JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (division_id) REFERENCES divisions(id)
);

-- 収益データ
CREATE TABLE revenue_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    organization_id INTEGER NOT NULL,
    division_id INTEGER,
    date DATE NOT NULL,
    amount INTEGER NOT NULL,
    currency TEXT DEFAULT 'JPY',
    source TEXT,
    metadata JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (organization_id) REFERENCES organizations(id)
);

-- 実行ログ
CREATE TABLE execution_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    organization_id INTEGER,
    agent_id INTEGER,
    action_type TEXT,
    status TEXT,
    input_summary TEXT,
    output_summary TEXT,
    duration_seconds INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (organization_id) REFERENCES organizations(id),
    FOREIGN KEY (agent_id) REFERENCES agents(id)
);

-- アプリ設定
CREATE TABLE app_settings (
    key TEXT PRIMARY KEY,
    value JSON,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

この設計は「Organization単位での分離」「人間が扱いやすいコンテンツ管理」「後からのクラウド移行」を意識している。

---

## 6. 初期テンプレート設計方針（Phase 0で意識すること・統合版）

テンプレート作成時に必ず守るべき原則（File 1 + File 2を統合）:

**全体原則**:
1. **「すぐに使える + 自己改善可能」** を最優先
2. **過剰に作り込まない**（育てる余地を残す）
3. **自己進化の種を最初から入れる**（レビューAgent、playbook蓄積など）
4. **Human Memberの役割を明確に定義**
5. **Fable 5の長時間自律性を活かしたAgent構成にする**

### 6.1 会社プラグインの初期テンプレート構成
- Meta-Overseer配下の専用HQ Agent（その会社の戦略立案・KPI管理）
- 推奨事業部の初期セット（例: Note販売会社なら X集客事業部 + note販売事業部）
- グループ全体との連携設定（収益レポートの自動集約、資源配分ルール）
- 初期収益KPIダッシュボード（売上、ROAS、LTVなどの基本指標）
- Human Member向けタスクリスト（初回設定項目）
- 自己改善ループの種（週次レビューAgent + playbook更新仕組み）

### 6.2 事業部プラグインの初期テンプレート構成（カテゴリ別）

**Audience系（X集客事業部など）**:
- 投稿生成Agent + エンゲージメント分析Agent
- プロフィール最適化Skill + 固定ポスト生成Skill
- トレンド収集 + ハッシュタグ最適化の仕組み
- 集客→他事業部へのハンドオフ設計
- 初期KPI: フォロワー増加率、エンゲージメント率、インプレッション

**Monetization系（note販売事業部 / アフィ事業部）**:
- コンテンツ生成 + セールスライティングAgent
- 価格最適化 + A/Bテスト自動実行の仕組み
- 売上トラッキング + ファン化施策Agent
- PR表記・コンプライアンスチェックSkill
- 初期KPI: 売上、コンバージョン率、客単価、リピート率

**Full Funnel系**:
- 上記Audience + Monetizationの主要Agentを統合
- ファネル全体のKPI管理Agent
- 自動改善提案Agent
- 初期KPI: ファネル全体のLTV、CAC、ROAS

**Operations系**:
- 分析・レポート自動生成Agent
- スケジューラー + 通知Agent
- 競合・トレンド監視Agent
- 複数事業部横断のデータ集約仕組み

**成長を促すための仕組み（全テンプレート共通）**:
- 週次/月次自己レビューAgentの標準搭載
- Playbook自動蓄積の仕組み
- ユーザー指示受付の明確なインターフェース
- Meta-Overseerへのエスカレーションルール

---

## 7. 副業モデルプラグインシステム（2階層・詳細版）

グループ会社構造に合わせて、**プラグインを2階層**に設計。

### 7.1 会社プラグイン（Company Plugin）
- 一つの「収益モデル会社」全体をパッケージ化。
- 例: 「Note販売会社プラグイン」「アフィリエイト会社プラグイン」「YouTube会社プラグイン」など。
- 追加すると、**新しい収益モデル会社が即座に立ち上がり**、Pantheon Group HQの下にぶら下がる。
- Meta-Overseerがトレンドを見て自律的に会社プラグインを提案・作成。

### 7.2 事業部プラグイン（Division Plugin）
- 既存の収益モデル会社の中に、特定の事業部を追加。
- 例: 「X集客事業部プラグイン」「note販売事業部プラグイン」「アフィ事業部プラグイン」など。
- 原則として**各収益モデル会社に専用**で追加（共有は管理が煩雑になるため基本的に避ける）。

### 7.3 プラグイン追加の体験
- GUIの「副業マーケットプレイス」で会社プラグインと事業部プラグインを明確に分けて表示。
- Meta-Overseerが賢く組み合わせを提案。

### 7.4 初期搭載おすすめプラグイン一覧（2026年トレンドベース）

**1. Audience / Traffic Plugins（集客手段）**
- X（Twitter）集客特化プラグイン
- YouTubeショート/長尺集客プラグイン
- TikTok / Instagram Reels集客プラグイン
- SEOブログ / note無料記事集客プラグイン
- Newsletter集客プラグイン

**2. Content & Product Plugins（商品・コンテンツ作成）**
- note有料記事作成特化プラグイン
- デジタルプロダクト作成プラグイン
- AIツール / プロンプトパック販売プラグイン
- オンライン講座 / メンバーシップコンテンツ作成プラグイン
- 電子書籍 / レポート自動生成プラグイン

**3. Monetization Plugins（直接収益化）**
- アフィリエイト特化プラグイン
- note有料記事販売最適化プラグイン
- メンバーシップ / サブスク収益化プラグイン
- デジタル商品販売プラグイン
- 広告収益化プラグイン

**4. Full Funnel / Ecosystem Plugins（複合モデル・一番おすすめ）**
- 「X集客 → note販売 → アフィリエイト」完全ファネルプラグイン
- 「短尺動画集客 → デジタル商品販売」ファネルプラグイン
- 「コンテンツ作成 → 複数プラットフォーム同時収益化」ハイブリッドプラグイン
- 「AI活用コンテンツ自動生成 → note + アフィ複合販売」プラグイン

**5. Operations & Analytics Plugins（運用支援）**
- 収益ダッシュボード & 分析強化プラグイン
- 投稿・記事スケジューラー自動化プラグイン
- 競合・トレンド監視プラグイン
- A/Bテスト自動実行プラグイン
- 顧客管理・CRM簡易版プラグイン

---

## 8. 壮大かつ具体的な実装ロードマップ（Ambitious Roadmap）

### Phase 0: 基盤強化（即時〜1ヶ月）
- Fable 5対応（runtime更新）
- 既存daemonの永続サービス化 + watchdog
- Layered Memory基盤実装
- Revenue Intelligence Engineのプロトタイプ（手動データ入力から開始）
- グループ会社構造基盤 + 2階層プラグイン基本実装（P1タスク）
- `src/` レイアウト移行 + PyInstaller specベース作成
- 初期テンプレートフレームワーク + 収益トラッキング最低限

### Phase 1: 収益ループ完成（1〜3ヶ月）
- Revenue Intelligence Engine本格化（API連携 + 自動分析）
- Meta-Overseerの基本実装（収益分析 → 改善提案）
- GUI Observatory大幅強化（収益ダッシュボード + 提案キュー）
- Human Memberタスク管理機能

### Phase 2: 自己拡大機能（3〜6ヶ月）
- 新org自動設計・作成機能（Meta-Overseer主導）
- 副業モデルプラグインシステムの本格実装（大量テンプレート + GUIマーケットプレイス + 自動追加フロー）
- Trend Monitor Daemonの本格運用
- Self-Evolution Engine（playbook自動生成・適用）
- 複数org間連携最適化

### Phase 3: アプリ化・ユーザビリティ爆上げ（6〜9ヶ月）
- Pantheon.exeを「AI経営OSアプリ」として完成
  - 美しいインストーラー
  - 初回ウィザードで「副業ポートフォリオ自動構築」
  - Always-Onモード + 通知
- クラウド版Pantheon（オプション）

### Phase 4: 究極形態（9ヶ月〜1年+）
- 完全自律経営デモ（「月XX円目標で最適運用して」と言うだけで動く）
- 新事業ジャンル自動発見・立ち上げ
- コミュニティ機能
- 税務・会計補助（将来的に外部ツール連携）

---

## 9. 技術的基盤（Technical Foundations）

- **LLM**: Fable 5（長時間・自律実行最強）をメイン。必要に応じてモデルルーティング。
- **Orchestration**: 既存 + LangGraph風stateful graphのハイブリッド。
- **Memory**: Persistent Playbook + Memory Bank + File-based memory（Fable 5活用）。
- **Runtime**: Python + FastAPI + React GUI。Daemonは永続プロセス化。
- **Packaging**: PyInstaller（現行） + 将来的により洗練されたインストーラー/ラッパー。
- **Governance**: 既存PolicyEngineをさらに強化（Human Gate + 完全監査ログ）。
- **外部連携**: MCP風ツール統合、ASP API、note API、X APIなど（可能な限り自動化）。

---

## 10. 人間の役割の明確化（Human Role Definition）

**Pantheonがやる（95%以上）**:
- 戦略立案・実行・分析・改善
- 新事業創出
- 日常運用・コンテンツ生成・最適化
- 収益管理・予測

**人間がやる（残り5%）**:
- 人間しかできない初回設定（アカウント作成など）
- 高リスク承認（大きな契約、法的判断）
- 創造的・感情的な判断
- Pantheonへの高レベル指示（「もっと攻めたポートフォリオにして」）

人間は「Pantheonという会社の優秀な社員」として、タスクをこなすイメージ。

---

## 11. リスクと対策（Risks & Mitigations）

- **コスト爆増** → クォータ管理 + モデルティアリング + 効率化ループ
- **安全性・暴走** → 強力なPolicyEngine + Human Gate + 定期監査
- **完全自動の限界** → 人間ゲートを明確に残す
- **アプリ化の難易度** → 段階的（まずは現行exe強化 → 本格ラッパー）
- **計画の陳腐化** → 定期的なレビューと自己更新プロセスの徹底

---

## 12. 成功指標（Success Metrics）

**Phase 0終了時点の具体的な指標**（v1.1 現況注記つき）:
- Meta-Overseerが「新しい収益モデル会社を1つ提案・計画立案・基本実行できる」状態　〔✅ 概ね達成〕
- 会社プラグインを追加すると即座に新しいOrganizationが作成され、基本的なAgentが動作する　〔✅ `org create --genre` で達成。2階層化（事業部プラグイン）は残タスク③〕
- 手動入力で収益データを記録・集計でき、簡単なレポートが出力できる　〔⚠️ CLI/CSV は可。GUI 単件入力＋レポートが残タスク①〕
- GUIで組織階層と提案確認が直感的に操作できる　〔✅ 達成〕
- ~~`src/` レイアウトへの移行が完了し、ビルドが安定している~~　〔❌ → **凍結（§13-6）**。フラット配置を維持し「ビルド安定」は `packaging/pantheon.spec` で既に達成済とみなす〕

**長期的な成功指標**:
- ユーザーが「Pantheonに任せておけば収益が勝手に伸びる」と感じる状態
- 新orgがMeta-Overseer主導で複数立ち上がっている
- 収益改善ループが完全に自動化されている
- 24時間運用で「寝てる間に改善が進んでた」体験が日常化

---

## 13. 開発時の判断基準

実装時に迷ったら以下の優先順位で判断する:

1. **Phase 0の目標達成に寄与するか**
2. **長期ビジョン（Grand Vision）に沿っているか**
3. **管理のシンプルさを損なわないか**（共有は極力避ける）
4. **後から改善しやすい設計になっているか**
5. **Meta-Overseerが理解・改善しやすい構造か**

**v1.1 で確定した設計判断**:

6. **`src/` レイアウト移行は凍結（実施しない）**　— 現状のフラット配置は daemon の
   `python -m core._daemon_runner`（及び `_content_daemon_runner`/`_trend_daemon_runner`/`_watchdog_runner`）
   entry point と `packaging/pantheon.spec` のバンドル設定が依存している。移行は高リスク・低価値で、
   §13-3「管理のシンプルさ」「後から改善しやすさ」に反するため、明示的に凍結する（P1-4・§12 を更新済）。
   将来 Workspace モデル（§5）へ移行する際に layout も併せて再検討する。

---

## 14. Claude Codeとのペアプロで意識してほしいこと

- この計画を常に意識しながらタスクを進めてほしい
- 重要な設計判断は必ず理由とともに提案する
- 「この変更はPhase 0のどの目標に寄与するのか」「長期ビジョンのどの部分に繋がるのか」を意識する
- 実装後は「この変更によって何ができるようになったか」を簡潔にまとめる
- 計画に矛盾が生じたら、すぐに指摘して計画の更新を提案する

---

## 15. 次のアクション（この計画を読み込んだ直後）

**v1.1 で 1〜4 を実施済**（このセクションの当初指示は完了した）:

1. ✅ 現在のコードベースを分析して **Phase 0で最も不足している部分** を特定し §2 に反映した
2. ✅ 不足を埋める **具体的なタスクリスト** を優先度順に提案した（§4.1）
3. ✅ 最初の1〜2週間でやる 3〜5 タスクに絞った（§4.2）
4. ✅ 計画を v1.1 に更新した（src/ 凍結・版数矛盾の解消を含む）

**次の実行アクション**（§4.2 の順）: Fable 5 config 配線 → 収益GUI入力+レポート → `_publish_live`(note)。

---

**このドキュメントは生きている計画書です。**

開発を進める中で重要な決定が出たら、必ずこのファイルに反映させてください。  
**バージョンは 1.0 を出発点とし、大きな変更ごとにインクリメントしてください**（現在 v1.1）。
〔v1.0 の本文に「3.0から開始」とあったのはヘッダ「Version 1.0」との矛盾であり、v1.1 で 1.x 系に統一して解消した〕

**理想のビジョンは私のゴールとして完全に保持した。**  
Phase 0の実行計画も、長期ビジョンと矛盾なく整合させた。

これでClaude Codeに渡して本格的に開発を進められるはずだ。

（Claude Code使用時は「この計画を最新の状態に更新して」と指示すると良い）

---

**作成者注記（v1.0 初期状態）**:
- 以前の2つの計画ファイル（実践計画 + 究極ビジョン）を1つに統合して作成した**初期バージョン**
- 理想のGrand Vision（私のゴール）を冒頭に完全に保持
- Phase 0の実践タスク・プラグインシステム・テンプレート設計・データ構造など、両方の主要情報を欠落なく統合
- 重複を解消し、セクション番号を整理
- 「現在の状態分析」セクションを新規追加（これを最初に埋めること）
- Version 1.0として出発点に設定。以降は開発の進捗に合わせてバージョンアップしていく

**次のステップ**: このv1.0ファイルをClaude Codeに渡し、**セクション2の「現在のPantheon状態分析」から開始せよ**。分析結果を埋めたら計画を更新しながらPhase 0を進めていく。

---

**変更履歴**:

- **v1.1（2026-06-13）**: §2「現在の状態分析」を実コード分析で充填（10観点の EXISTS/PARTIAL/MISSING 表＋根拠）。
  Phase 0 の大半（daemon群+watchdog / rate-limit gate / model routing / quota / PyInstaller spec /
  2 GUI / 収益サブストレート / content→承認→公開骨格）が実装済と判明。§4 に現況早見表＋項目マーカーを追加。
  §4.1「真の残タスク」（①収益GUI ②`_publish_live` ③2階層プラグイン ④Fable配線）と §4.2「直近3〜5タスク」を新設。
  §13-6 で `src/` 移行を**凍結**（daemon entry point / PyInstaller spec が依存）。§12 成功指標と版数記述の矛盾を修正。
- **v1.0（2026-06-12）**: 2つの計画ファイル（実践計画＋究極ビジョン）を統合した初期版。