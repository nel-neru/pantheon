# 2階層プラグイン + マーケットプレイス — キックオフ / 段階分割メモ

**日付**: 2026-06-13 / **対応**: Master Plan v1.1 §4.1 残タスク③（P1-2）

## 背景（実態を踏まえた再定義）

実コード分析で判明したこと:
- **会社プラグイン相当は既に存在**: `pantheon org create --genre --persona --design`
  （`commands/org.py` + `core/orchestration/org_template_designer.py`）が、ジャンル別に
  Division 構成を設計して**新しい収益モデル会社（Organization）を1コマンドで量産**する。
- **欠けているのは「事業部プラグイン」**: 既存 Organization に Division（事業部）を**追加**する
  仕組みが無い。`core/org_factory.py` の `_build_division(dept: dict) -> Division` という
  再利用可能な部品はあるが、org 全体生成からしか呼ばれていない。
- **GUI マーケットプレイス**が無い（プラグインを一覧・追加する画面）。

## このMVPで実装する範囲（1 work ブランチ）

1. **事業部プラグインのカタログ**: `config/division_plugins.yaml`（id / label / category /
   department〔=`_build_division` が食べる dict〕）。Audience / Monetization / Operations の代表を同梱。
2. **backend**: `core/orchestration/division_plugins.py`
   - `load_division_plugins()` / `get_division_plugin(id)`
   - `add_division_plugin(org, plugin_id) -> Division`（`org_factory._build_division` を再利用し
     `org.add_division`）
   - `load_company_plugins()`（`config/departments/*.yaml` を会社プラグインのアーキタイプとして列挙）
3. **API**（`web/server.py`）: `GET /api/division-plugins` / `GET /api/company-plugins` /
   `POST /api/organizations/{org_name}/divisions`（プラグイン install → Division 追加 → save）。
4. **CLI**（`commands/plugin.py`）: `pantheon plugin list` / `pantheon plugin add-division --org --plugin`。
5. **frontend**: `MarketplacePage`（`/marketplace`）— 会社/事業部プラグインを分けて一覧し、
   事業部プラグインを既存 org に追加。co-located vitest。
6. **テスト**: backend（カタログ/追加/API）+ frontend。

## 段階的な次ステップ（このMVPに含めない）

- **会社プラグインの manifest 正式化**: 現状は genre/template を会社プラグインとして「ラベル付け」
  するだけ。将来は plugin manifest（依存・初期 KPI・Human タスク・週次レビュー種）を持つ正式形へ。
- **Meta-Overseer による自動提案**: トレンドから「この会社にこの事業部を足すと良い」を提案ゲート化。
- **GUI マーケットプレイスの強化**: カテゴリ絞り込み・おすすめ組合せ・プレビュー。
- **auto 公開 / WordPress 本文流し込み**（Publishing 側 Phase 2、別タスク）。

## 設計判断

- 事業部プラグイン = 既存テンプレ機構（`_build_division`）の再利用。新しい構造は導入しない（§13-4）。
- 「共有は極力避ける」（§13-3）に従い、追加した Division はその org 専用（横断共有しない）。
- SpecialistAgent の skills 2〜3 制約は `_build_team` の既存正規化に委ねる（仕様維持）。
