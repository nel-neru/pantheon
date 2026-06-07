# Group Structure & Monetization — Design & Decision Record

**種別**: 恒久ドキュメント（実装済みアーキテクチャ＋設計判断＋残存する将来課題の記録）。
計画段階の一時ドキュメント（kickoff / inspiration / roadmap）は実装完了に伴い
`docs/archive/plans/` へアーカイブした（git 履歴に推論過程は保全）。
**最終更新**: 2026-06（Phase 5 Slice A ＋ Phase 6/7/8 初期スライス完了・main 反映済み）

このドキュメントは「Pantheon を HQ（本社）＝Meta-Improvement Organization が、収益志向を含む
複数の子 Organization を設計・強化・進化させる group company」にするという方針の、**現時点で
実装され main にマージ済みの内容**と、その**設計判断**、そして**意図的に未着手の将来課題**を
恒久的に記録する。

## ビジョン（恒久）

Pantheon（Meta-Improvement Organization + Platform）が **本社 / メタ組織** として、目的志向の
子 Organization（アフィリエイト運用、SNS グロース、Note/コンテンツ販売など収益組織を含む）を
設計・強化・継続進化させる。子組織はドメインに特化し、HQ は次に集中する:

- 組織設計と進化
- 能力・スキルの開発
- cross-org の学習とパターン伝播
- システム全体・ツール群の自己改善

これにより **再帰的フライホイール**（より良い HQ → より良い子組織と自動化 → 実成果と
フィードバック → さらに強い HQ/Platform）が回る。

### 不変の指針

1. **信頼できる substrate が先**。野心的な group/収益機能は、一貫した Policy・学習ループ・
   安全な実行の上にのみ載せる。
2. **HQ はまず設計と substrate を強化し、収益アクションを（当初は）自ら実行しない**。価値は
   外部アカウントの直接操作ではなく、収益組織が使う組織構造・ワークフロー・プロンプト・ツールの
   改善から生まれる。
3. **flat な multi-org より再帰的フライホイール**。HQ 層が能動的に子組織を診断・介入・進化させる。
4. **コア改善コントラクトを一般化する**（並行システムを作らない）。
   analyze → proposal → PolicyEngine → execute + 学習 を拡張する。
5. **安全性と監査可能性は非交渉**。新しい経路（他組織への構造介入・コンテンツ資産変更・外部行為）は
   すべて universal PreTaskOrchestrator + PolicyEngine を通す。バイパス禁止。
6. **状態と成果物の規律**。グローバルは `~/.pantheon`、子組織固有は `<target>/.pantheon`。
   新しい主要フローは `core/atlas/data/flows.json` に必ず登録。

## 実装済みアーキテクチャ（main 反映済み）

### 1. 構造的介入コントラクト（Phase 5 Slice A）

コードファイル変更専用だった改善ループを「組織モデル変更」へ一般化した。

- **モデル** (`core/models/organization.py`): `ImprovementProposal` に cross-org 介入フィールドを
  *additive・Optional* で追加（既存 JSON は後方互換でロード可）:
  `target_org_id` / `target_org_name` / `source_org_name` / `intervention_type` /
  `target_kind` / `target_ref` / `intervention_spec`。
  `StructuralInterventionType` enum（ADD_DIVISION / ADD_TEAM / ADD_AGENT / INJECT_SKILLS /
  SET_GOAL）、`STRUCTURAL_INTERVENTION_CATEGORY`、`is_structural_intervention()` /
  `is_structural_intervention_dict()`。
- **ポリシー** (`core/policy/engine.py`): `_check_intervention()` で **cross-org 介入は必ず
  HUMAN_REQUIRED**（rule `intervention.cross_org`）。auto_reject の carve-out を介入にも拡張し、
  `structural_intervention` を human_required カテゴリへ。auto_approve には決して落ちない。
- **適用** (`core/orchestration/structural_intervention.py`): 純粋・冪等な
  `apply_intervention_to_org`、ロード→system 組織拒否→変更→永続化の
  `apply_structural_intervention`、PreTask 経由の `execute_structural_intervention`、安定
  dedupe（uuid5）の `build_intervention_proposal`。専用 `StructuralInterventionExecutorAgent`
  （**LLM 不使用・決定論的**）＋ `agents/definitions/structural_intervention_executor.yaml`。
- **HQ** (`core/hierarchy/hq_interventions.py`): `HQInterventionProposer` が子 org を診断し、
  弱み→介入のヒューリスティックで提案を生成、子 org の `.pantheon` に保存・dedupe。
- **面**: CLI `pantheon hq diagnose | propose | apply`。既存の `pantheon proposal apply` と
  Web `POST /api/proposals/{org}/{id}/approve` は、空 file_path 棄却の **前に** 構造介入を
  専用 executor へ自動委任（通常提案・通常 meta 提案の挙動は不変）。

### 2. 収益ドメイン substrate（Phase 6）

- **スキル**: `AgentSkill` に `content_strategy` / `audience_growth` / `performance_marketing`
  （＋ `skills/*.yaml`。YAML `id` == enum 値）。`DivisionType` に `content_production` /
  `audience_development` / `monetization`。
- **テンプレート**: `config/departments/content_operations.yaml`
  （`pantheon org add --template content_operations`。3 division 構成）。
- **非コード提案**: `content_asset`（`is_content_asset_dict` / `build_content_asset_proposal`）。

### 3. 制御された行為面（Phase 7・ワークスペース内に限定）

- `core/orchestration/asset_application.py` がワークスペース **内部にだけ** 記事/コピー/
  スクリプトを安全書込（絶対パス・`..`・root 脱出を拒否、create/overwrite/append、冪等。
  dir/空白パスは `AssetApplicationError`）。専用 `AssetExecutorAgent`（LLM 不使用）＋ PreTask
  routing。PolicyEngine は `content_asset` / `external_action` を必ず human_required に。
  CLI/Web の approve は content_asset を file ベース executor の前に専用経路へ委任。
- **外部投稿/公開は未実装（意図的ゲート）** — 実 SNS/広告アカウントへの posting は導入していない。

### 4. 成果フィードバック / フライホイール（Phase 8）

- `core/metrics/outcomes.py`（`OutcomeStore` = `~/.pantheon/outcomes.json`、reach/revenue 集計。
  `OutcomeEvent.__post_init__` で value=float / metric=lower 正規化）。
  CLI `pantheon hq outcomes record | list`。
- `HQInterventionProposer` が「リーチありで収益 0」を検知し収益化 SET_GOAL を自動提案 →
  **成果 → HQ → 介入 → 成果 の輪が閉じた**。

### 5. 横断（Atlas / ブランチ運用 / 規約）

- `flows.json`: `hq-intervention` / `revenue-content-asset` / `outcome-feedback` を追加（計 18）。
- ブランチ運用の仕組み化: 命名 `work/<slug>-<YYYYMMDD>`（`scripts/new_work_branch.mjs`）、
  完了判別＝origin/main マージ済み（`scripts/branch_status.mjs`、`--prune`）、統合は
  `scripts/merge_to_main.mjs`（テストゲート付き・`--force` 不使用）。`/new-work-branch` /
  `/branch-status` / `/merge-to-main`。`CLAUDE.md` / `AGENTS.md` に明文化。
- Planning Document Hygiene: `scripts/check_planning_docs.py` ＋ PostToolUse フック
  `check-planning-docs.mjs` ＋ `AGENTS.md` 規約。

## 主要な設計判断

- **並行システムを作らず既存ループを一般化**: コードファイル変更を「組織モデル変更」「コンテンツ
  資産変更」へ拡張。新フィールドはすべて additive・Optional で後方互換。
- **executor は決定論的（LLM 不使用）**: 構造介入・資産適用の executor は生成を行わず、検証済み
  proposal を安全・冪等に適用するだけ。生成と適用を分離し監査可能性を担保。
- **cross-org / 収益 / 外部行為は常に HUMAN_REQUIRED**: auto_approve に落ちる経路を作らない。
  実外部投稿は意図的に未実装のゲートとして残す。
- **安全な書込境界**: 資産適用はワークスペース root 内に限定（絶対パス・`..`・脱出を拒否）。
- **後方互換**: 既存 proposal JSON は新フィールドなしでロード可能。

## 残存する将来課題（意図的に未着手）

「キックオフが定義した中核スライス」は完了・main 反映済みだが、ロードマップの以下の後続スライスは
**意図的に未実装**である（必要になった時点で `docs/plans/` に新規キックオフを作成して着手）:

- 介入/収益ヒューリスティックの **LLM 化**（現状は決定論的ヒューリスティック）。
- **実外部投稿アクション**（Phase 7 後半）— 実 SNS/広告/Note への posting。強い Policy・
  human gate・監査が前提。
- **外部分析の自動取り込み**（Note 売上・アフィリエイト・SNS インサイトの puller）→ OutcomeStore へ。
- **cross-org 学習伝播**の強化（org-to-org タグ、類似 org タイプでのパターン/能力履歴クエリ）。
- **group ダッシュボード拡張**（GroupHQState + 子 org 健康度 + pending 介入の可視化、cross-org メトリクス）。

## 関連

- 実装の一次情報: `core/orchestration/structural_intervention.py`,
  `core/orchestration/asset_application.py`, `core/hierarchy/hq_interventions.py`,
  `core/metrics/outcomes.py`, `core/policy/engine.py`, `commands/hq.py`。
- テスト: `tests/test_hq_intervention.py`, `tests/test_revenue_substrate.py`,
  `tests/test_check_planning_docs.py`。
- アーカイブ済み計画ドキュメント（推論過程・研究シード）: `docs/archive/plans/`。
