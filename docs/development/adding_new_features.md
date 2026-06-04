# Adding New Features

Pantheon に新機能を追加する際の、実際のコード構造に基づく手順です。

## 0. まず追加先を決める

| 追加したいもの | 主な配置先 |
| --- | --- |
| 新しいCLIコマンド | `main.py` |
| 新しいAgent | `agents/` |
| 新しい組織/状態モデル | `core/models/` |
| 新しい知能・索引・能力管理 | `core/intelligence/` |
| 新しいオーケストレーション部品 | `core/orchestration/` |
| 新しい品質/自己改善ロジック | `core/quality/` |
| Web API | `web/server.py` または `web/` 配下 |
| GitHub連携 | `github_integration/` |
| YAMLベースの組織テンプレート | `config/departments/` |

## 1. 実装場所を切る

例:

- 新しい探索Agent → `agents/my_explorer_agent.py`
- 新しい能力分析器 → `core/intelligence/my_analyzer.py`
- 新しい指標計算 → `core/metrics/...`

新規Pythonファイルは `from __future__ import annotations` を含め、`Path` / `timezone.utc` / UTF-8 JSON の既存パターンに揃えます。

## 2. Agent を追加する場合

### 最低限必要な形

1. `BaseAgent` を継承
2. `async def run(self, task: AgentTask) -> AgentResult` を実装
3. デフォルトの `SpecialistAgent` を持たせるなら 2〜3 スキルにする

### 参考にすべき実装

- `agents/code_review_agent.py`
- `agents/codebase_explorer_agent.py`
- `agents/tool_design_agent.py`

### スキルを新設する場合

次をまとめて更新します。

- `core/models/organization.py` の `AgentSkill`
- `core/intelligence/agent_skill_engine.py` の `SKILL_DEFINITIONS`
- `core/orchestration/task_router.py` の `TASK_SKILL_REQUIREMENTS`（必要に応じて）
- 組織テンプレート (`config/departments/*.yaml`) やテスト

## 3. CapabilityRegistry に登録する

`CapabilityRegistry` は現状、**agentsディレクトリ内のAgent** と **AgentSkill enum** を自動スキャンします。

### 自動で載るケース

- `agents/*.py` に新しいAgentを追加した
- `AgentSkill` に新スキルを追加した

この場合は `CapabilityRegistry.scan_and_register_all()` で検出されます。

### 手動登録が必要なケース

- `tool` / `mcp_tool` を独自管理したい
- 自動スキャン対象外の能力をレジストリ化したい

その場合は次のように `CapabilityEntry` を `register()` します。

```python
from core.intelligence.capability_registry import CapabilityEntry, CapabilityRegistry

registry = CapabilityRegistry()
registry.register(CapabilityEntry(
    id="tool:my_feature",
    name="MyFeatureTool",
    capability_type="tool",
    description="...",
))
```

## 4. 新しい CLI コマンドを追加する

`main.py` では次の3点を必ず揃えます。

### A. 実処理関数を追加

```python
async def cmd_my_feature(args: argparse.Namespace) -> None:
    ...
```

### B. parser を追加

`main()` 内の `subparsers` または既存サブコマンド配下に `add_parser()` を追加します。

### C. dispatch / if-elif に接続

`dispatch` dict または `args.command` 分岐に接続しないと呼ばれません。

### 参考例

- 単独コマンド: `analyze`, `proposals`, `approve`
- ネストあり: `org`, `platform`, `goal`, `daemon`, `agent`, `orchestration`

## 5. Web API を追加する場合

`web/server.py` の既存パターンに合わせます。

- request body は `BaseModel` を定義
- `PlatformStateManager` で Organization を解決
- 未発見時は `HTTPException(status_code=404, ...)`
- レスポンスは JSON dict / list

## 6. 組織テンプレートを追加する場合

`config/departments/*.yaml` を追加し、`org add --template <name>` で選べる形にします。

YAMLでは:

- `departments`
- `type`
- `mission`
- `teams`
- `required_skills`

を定義します。

`core/org_factory.py` が Team ごとに1体の `SpecialistAgent` を生成します。

## 7. テストを追加する

### テスト配置

- 基本は `tests/test_<module_or_feature>.py`
- 既存機能拡張なら関連テストファイルに追加でもよい

### よく使うパターン

- `tmp_path` でファイルシステム隔離
- `patch("core.platform.state.get_platform_home", return_value=tmp_path)`
- `capsys` でCLI出力検証
- `SimpleNamespace(...)` で `cmd_*` 関数へ引数注入

### 守るべきこと

- 全件テストの収集・実行を壊さない
- 出力フォーマットや schema を変える場合は回帰テストを更新する

## 8. 最低限の検証

変更後は少なくとも次を意識します。

```bash
python -m pytest tests/ --collect-only -q
python -m pytest tests/ -q
```

すべての変更で全件テストが必要とは限りませんが、
破壊的変更・中核モデル・CLI・状態管理の変更では広めに確認するのが安全です。

## 9. 実務的な追加順序（推奨）

1. モデル/実装を追加
2. Agent / Registry / Router / Policy の必要箇所を接続
3. CLIやWebの入口を追加
4. テストを書く
5. ドキュメント（`AGENTS.md`, `docs/`）を更新

## 変更例

### 例1: 新しいセキュリティ監査Agentを追加

1. `agents/security_audit_agent.py` を作成
2. `AgentSkill` に必要スキルが足りなければ追加
3. `TaskRouter.TASK_SKILL_REQUIREMENTS["security_audit"]` を確認・調整
4. `CapabilityRegistry.scan_and_register_all()` で見える状態にする
5. `main.py` に必要なら CLI 導線を追加
6. `tests/` にAgentテストとCLIテストを追加

### 例2: 新しい `pantheon foo` コマンドを追加

1. `cmd_foo(args)` を作る
2. parser に `foo` を追加
3. dispatch に接続
4. `capsys` でCLIテストを書く
5. `docs/api/cli_reference.md` も更新する
