# 組織分離境界の汎用enforce — 設計メモ

**種別**: 計画/設計段階の一時ドキュメント（Planning Hygiene に基づき `docs/plans/` に配置）。
実装完了後、恒久的な内容は `docs/architecture/organization_boundaries.md` の
「実装済みの境界enforce」セクションへ統合済み。本メモは設計判断の経緯を残すために置く。
**作成**: 2026-06-07

## 背景・課題

Pantheon は複数の Organization を同一プラットフォーム上で共存させる。中でも**外部目的を持つ
Organization**（収益志向の子組織など）が、自分のワークスペースの外（特に Pantheon core）を
変更する提案を出す可能性がある。`organization_boundaries.md` は原則4「ポリシーで境界を
enforce する」を掲げていたが、PolicyEngine は**全組織共通の `file_patterns`**（core を全員に
対して人間確認にする）しか持たず、**組織単位のスコープ強制が存在しなかった**。

ゴール: 特定ドメイン（アフィリエイト等）の知識を core に持ち込まずに、すべての外部目的
Organization に等しく効く**汎用の境界ガード**を最小実装する。

## 設計判断

1. **軽量な分類フィールドを Organization に additive 追加**
   `isolation_level: str = "standard"`（`core | standard | external`）と
   `allowed_path_scope: List[str] = []`。Phase 5 の cross-org フィールドと同じ additive/Optional/
   デフォルトの後方互換パターン。既存 JSON は新フィールドなしでロード可能。
   不正な `isolation_level` は `field_validator` で `standard` に寄せ、旧データ/手書き JSON を壊さない。

2. **PolicyEngine に純粋なパススコープ判定を追加（ドメイン知識ゼロ）**
   `OrgBoundaryContext`（engine.py 内 dataclass。`organization.py` を import しないので循環なし）と
   `_check_org_boundary`。`evaluate` に**オプショナルキーワード `org_context=None`** を追加し、
   None なら完全に従来挙動（既存の全呼び出しは無改修で挙動不変）。

3. **`external` 限定でのみ作動**:
   - 絶対パス／`..`（ワークスペース外脱出）→ **REJECT**（`org_boundary.escape`）。強い境界。
   - `allowed_path_scope` 宣言時、その接頭辞外 → **HUMAN_REQUIRED**（`org_boundary.out_of_scope`）。
   - 区切りは `\`/`/` 双方を正規化し、セグメント境界一致で判定（Windows対応。`content` が
     `contentious/` に誤一致しない）。

4. **挿入位置**: `_check_content_asset`（1.6）の後・`_check_human_required`（2）の前（= 1.7）。
   構造介入・content_asset の専用判定を先に通し、残った通常 code_file 提案にだけ境界ガードを当てる。
   優先順位 `auto_reject > human_required > auto_approve` と整合（早期 REJECT は最高severity）。

5. **配線**: 提案元組織を既にロードしている2経路でコンテキストを構築して渡す。
   - CLI: `commands/org.py` `cmd_proposal_apply`
   - Web: `web/server.py` `_approve_proposal_internal`
   - **据え置き（意図的に `org_context=None` のまま）**: reject 経路（却下は常に許可で無害）、
     `commands/hq.py`（cross-org 構造介入＝空 file_path で no-op）、`core/scheduler.py`
     （自律ループ。blast radius を広げないため次回フォローアップ）。

## 非汚染の確認

- 追加コード（フィールド名・enum 値・ルール名・コメント）に**アフィリエイト語彙は一切ない**。
- すべての external 組織に等しく適用される汎用機構であり、将来どんな外部目的Organizationを
  追加してもそのまま効く。
- アフィリエイト固有の知識・戦略・プロンプトは Pantheon リポジトリ外の独立ワークスペースに
  閉じ込める（core/docs/config には置かない）。

## テスト

`tests/test_policy_org_boundary.py`: external の絶対パス/`..`→REJECT、scope外→HUMAN_REQUIRED、
scope内/未宣言→通過、空 file_path→境界 no-op、standard/core/None→従来挙動。

## フォローアップ（未着手）

- `core/scheduler.py` 自律適用への `org_context` 配線。
- 知識ネームスペース単位の共有許可/禁止（原則2の機械的enforce）。
