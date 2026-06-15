# Pantheonにおける組織境界と分離の原則

## 目的

Pantheonは複数のOrganizationを安全に共存させ、それぞれが独立して自己改善できるプラットフォームを目指しています。
そのためには、**core（メタ基盤）と外部目的を持つOrganizationの境界を明確に保つ**ことが極めて重要です。

本ドキュメントでは、特定のユースケース（アフィリエイトなど）に引きずられることなく、汎用的に組織を分離するための原則を定義します。

## 背景と問題意識

- Pantheonのcoreは「すべてのOrganizationを支えるためのメタプラットフォーム」である
- 特定の目的（例: アフィリエイト収益化、PC自作支援、ゲームmodding）を持つOrganizationをcoreに最適化すると、拡張性が損なわれる
- 将来的に多様なOrganizationを追加した際に、毎回個別の分離ルールを記述するのは保守性・拡張性の観点で問題がある

したがって、分離の考え方は「特定の組織向け」ではなく、「外部目的を持つOrganization全般」に適用可能な**一般原則**として定義する必要があります。

## 基本原則

### 1. coreは中立であること
- coreのコード、ポリシー、知識、プロンプトは、特定の外部目的に最適化されてはならない
- 改善提案や新機能は、「すべてのOrganizationに恩恵があるか」を第一に判断する

### 2. 知識のスコープを明確に分離する
- 各Organization固有の知識（ドメイン知識、運用ノウハウ、評価基準など）は、当該Organizationの `.pantheon/knowledge/` または `knowledge/<org-name>/` 配下に閉じ込める
- coreの `core/knowledge/` やグローバル知識には、組織横断で再利用可能な**抽象化された知見**のみを保持する

### 3. 改善提案の影響範囲を制限する
- 外部目的を持つOrganizationから発生した改善提案が、coreのファイル（`core/` 配下、`main.py`、ポリシー定義など）に影響を与えることは原則として避ける
- 高リスクな変更（coreファイルへの変更）は、PolicyEngineで強制的に人間承認を必須とする

### 4. ポリシーで境界をenforceする
- `core/policy/engine.py` を拡張し、組織の**分離レベル**に基づいた境界チェックを行う
- ファイルパスやカテゴリ判定に加えて、**組織スコープを意識した汎用ガード**を実装済み
  （`_check_org_boundary` / `OrgBoundaryContext`。下記「実装済みの境界enforce」参照）

### 5. 状態管理の分離を維持する
- グローバル状態（`~/.pantheon`）とリポジトリ固有状態（`<repo>/.pantheon`）の分離はすでに良い設計
- 各Organizationの状態・知識・提案履歴は、対象リポジトリの `.pantheon/` 内に閉じ込める

## 実践的な運用指針

### 新しい外部目的Organizationを追加するとき
1. まず一般原則（本ドキュメント）に従っているかを確認する
2. 組織固有の知識・Division構成・運用ルールは、当該組織の運用ドキュメントや `config/` / `knowledge/` 内に閉じ込める
3. core側には「この組織がどのように分離されているか」の抽象的な記述のみを残す
4. 具体例（アフィリエイト組織など）は、原則の「適用例」として軽く触れる程度に留める

### ドキュメント作成時の注意
- `docs/architecture/` に置くドキュメントは、常に汎用原則として記述する
- 「アフィリエイト組織向けのDivision構成」や「アフィリエイト特化の分離ルール」のような記述は避ける
- 将来的に他のOrganizationを追加したときも同じ原則が適用できるかを意識する

## 実装済みの境界enforce（汎用）

原則4・5を実コードで担保する**汎用機構**（特定ドメイン非依存）:

- **組織の分離レベル**: `Organization.isolation_level`（`"core" | "standard" | "external"`）と
  `Organization.allowed_path_scope`（external 組織が変更してよいワークスペース相対パス接頭辞）。
  いずれも additive・デフォルト付きで、既存の永続化済み JSON を後方互換でロードできる。
  `pantheon org add --isolation-level external` で外部目的Organizationを external として登録する。
- **PolicyEngine の境界ガード**: `core/policy/engine.py` の `OrgBoundaryContext` と
  `_check_org_boundary`。`evaluate(proposal, *, org_context=...)` に提案元組織の分離コンテキストを
  渡すと、`isolation_level == "external"` の組織についてのみ:
  - 提案の `file_path` が絶対パス／`..` を含む（ワークスペース外への脱出）→ **REJECT**
    （`org_boundary.escape`）。
  - `allowed_path_scope` を宣言していてその接頭辞外を触る → **HUMAN_REQUIRED**
    （`org_boundary.out_of_scope`）。
  `org_context` を渡さない既存呼び出しは完全に従来挙動（チェック不作動）。承認/適用の全経路
  （CLI `proposal apply` / Web `approve` / 自律スケジューラ `core/scheduler.py` の自動適用）が
  提案元組織からコンテキストを構築して渡す。特に自律適用は人間確認を挟まないため、ここでの境界ガードが
  external 組織のワークスペース外脱出を silent に自動適用させない最後の砦になる。
- この機構は**特定の外部組織（アフィリエイト等）の知識を一切含まず**、すべての external 組織に
  等しく適用される。新しい外部目的Organizationを追加しても同じガードがそのまま効く。

## 厳格ルール（2026-06-15 強化 — 仕組み化）

GUI/CLI/エージェントで挙動が割れると管理が破綻するため、以下を**厳格ルール**として固定する。

1. **新規事業＝外部 Organization。業務一式は兄弟リポジトリへ。**
   新しい「事業/ビジネス」を始めるとき、その**業務データ・戦略・コンテンツ**（商材リスト・収益化
   ロードマップ・生成済みコンテンツ等）を **`core/` `config/` `docs/` `content/` に置いてはならない**。
   外部目的 Organization（`isolation_level="external"`）を作り、業務一式は pantheon の**兄弟 git
   リポジトリ**（例 `C:\Users\neoma\NEL\<org>-org`）に置く。core が持つのは**汎用 capability のみ**
   （例: `core/content` のコンテンツ生成、`core/metrics/outcomes` の成果記録）。
   *アンチパターン（2026-06-15 是正済）*: `core/affiliate/` ＋ `config/affiliate_programs/` ＋
   `docs/plans/...roadmap.md` ＋ `content/shortvideo_affiliate/` を本体に直書きしたこと。

2. **組織生成は単一経路（OrgService）を通す。**
   Organization の作成は **`core/org_service.py:create_org`** を唯一の入口とし、CLI（`commands/org.py`）・
   Web API（`web/server.py:api_create_organization`）・自律パイプライン（`core/goals/org_instantiator.py`）
   が全てここを通る。各所で `org_factory` を直叩き＋個別 `save_organization` する実装を増やさない
   （経路差＝管理破綻の温床）。

3. **`isolation_level` は全経路で第一級。GUI でも設定可能。**
   CLI（`--isolation-level`）／GUI（`OrgCreateRequest.isolation_level`）／エージェント（自律生成は
   既定 external）のいずれでも明示的に扱う。GUI で作った「外部Org」が standard 化して境界が効かない、
   という経路差を作らない。

4. **事業部（Division）の追加は `add_division_plugin` のみ。**
   GUI（`POST /api/organizations/{org}/divisions`）も CLI（`plugin add-division`）も
   `core/orchestration/division_plugins.py:add_division_plugin` を通す。新経路で `org.add_division` を
   直接呼ぶ実装を増やさない。

5. **再発防止ガード**: `scripts/check_core_neutrality.py` が `core/`/`config/`/`content/`/`docs/` への
   業務固有アーティファクト混入を検査し、`.claude/hooks` の PostToolUse 統合フックから実行する。

## 関連する既存コンポーネント

- `core/models/organization.py`: `Organization` の `purpose`/`target_repo_path` で外部目的を表現し、
  `isolation_level`/`allowed_path_scope` で分離境界を表現
- `core/policy/engine.py`: 改善提案の承認判定 ＋ 組織分離境界チェック（`_check_org_boundary`）
- `core/state/manager.py`: リポジトリごとの状態分離
- `core/platform/state.py`: GroupHQStateによる複数Organization管理

## 今後の拡張方向

- `allowed_path_scope` を超えた、知識ネームスペース単位の共有許可/禁止の明示制御
- 組織横断の知識共有を明示的に許可/禁止する仕組み（原則2の機械的enforce）
- external 組織の `target_repo_path` 自体の検証（登録時に他組織/coreのパスと重ならないことを保証）

この原則を守ることで、Pantheonは特定のユースケースに最適化されることなく、長期的に拡張可能なプラットフォームであり続けられます。