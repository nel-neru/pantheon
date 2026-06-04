# Development Conventions

このドキュメントは、Pantheon の既存コードとテストから読み取れる実装慣習をまとめたものです。

## Python 実装パターン

### 1. `from __future__ import annotations`

新規Pythonファイルでは `from __future__ import annotations` を先頭付近に置く前提で統一します。
既存コードのコア実装でも広く採用されています。

### 2. Path ベースのファイル操作

- `pathlib.Path` を基本とする
- 文字列パスより `Path` を優先
- `expanduser()`, `resolve()` を必要に応じて使う

### 3. UTF-8 JSON 永続化

永続化はおおむね以下の形です。

- `json.dumps(..., ensure_ascii=False, indent=2)`
- `Path.write_text(..., encoding="utf-8")`
- Pydanticモデルは `model_dump_json(indent=2)` / `model_validate_json(...)`

### 4. dataclass と Pydantic の使い分け

- **Pydantic (`BaseModel`)**
  - 永続化される中核モデル
  - バリデーションが必要なモデル
  - 例: `Organization`, `SpecialistAgent`, `ImprovementProposal`
- **dataclass**
  - 軽量DTO、計画オブジェクト、実行進捗、CapabilityやPattern統計
  - 例: `AgentTask`, `AgentResult`, `TaskAnalysis`, `PatternRecord`

### 5. logging + print の二層

- 内部診断は `logging.getLogger(__name__)`
- CLIユーザー向け出力は `print()`
- つまり「内部観測」と「日本語の操作メッセージ」を分離している

## Datetime 取り扱い

### 基本ルール

- `datetime.utcnow()` は使わない
- **常に `datetime.now(timezone.utc)`** を使う
- 永続化時は `.isoformat()` を使う

### 理由

- `PlatformStateManager`, `RepoStateManager`, `KnowledgeManager`, `PatternStore`, `Goal` 系などで
  すべてUTCベースのタイムスタンプを使っている
- naive datetime を混ぜると比較や永続化で事故りやすい

## Pydantic モデルのパターン

代表例: `core/models/organization.py`

- `Field(default_factory=...)` で UUID / datetime / list を初期化
- 数値制約は `ge`, `le` を使う
- Enum を明示的に型に含める
- 生成/復元は `model_dump_json`, `model_validate`, `model_validate_json`

例:

- `SpecialistAgent.skills`: `Field(..., min_length=2, max_length=3)`
- `Organization.autonomy_score`: `Field(40.0, ge=0, le=100)`

## テストパターン

テストフレームワークは `pytest` + `pytest-asyncio` です。
`python -m pytest tests/ --collect-only -q` で現在の収集数を確認できます。

### よく使うパターン

#### 1. `tmp_path`

状態管理・JSON永続化・policyファイル・knowledge保存のテストでは `tmp_path` を使います。

例:

- `RepoStateManager(tmp_path, "StateOrg")`
- `KnowledgeManager(tmp_path)`
- `policy_path = tmp_path / "policy.yaml"`

#### 2. `patch("core.platform.state.get_platform_home", return_value=tmp_path)`

グローバルストアを汚さないため、CLI / Platform 系テストではこのパターンを多用します。

代表例:

- `tests/test_orchestration_cli.py`
- `tests/test_abstract_goal_pipeline.py`

#### 3. `capsys`

CLI出力を検証するため、`capsys.readouterr().out` を使います。

#### 4. pre-commit フック

`bash scripts/install_hooks.sh` で pre-commit フックを導入できます。
このフックは GUI ページのテスト不足と HelpPage の更新漏れを早期に知らせます。

#### 5. 非同期ヘルパー

テストでは `_run(coro)` や `asyncio.run(coro)` で非同期関数を同期的に呼ぶパターンがあります。

#### 6. 安定APIの回帰テスト

`tests/test_regression.py` では dict schema / rule名 / JSON構造の安定性を守っています。
キー名や出力形式の変更は要注意です。

### 404 に関する注意

Web API では `web/server.py` が Organization未発見時に `HTTPException(status_code=404)` を返します。
Webエンドポイント変更時はこの挙動を壊さないでください。

## CLI コマンドのパターン

`main.py` に統一された構造があります。

1. `async def cmd_xxx(args: argparse.Namespace)` で処理を書く
2. `main()` の parser セクションで subparser を追加
3. dispatch または `if/elif` で配線する

### 実装上の慣習

- CLIメッセージは日本語主体
- エラー時は `sys.exit(1)` を使う場合がある
- helper 関数 (`_make_code_review_agent`, `_get_psm`) で構築をまとめる

## 状態保存の配置規約

### グローバル

`~/.pantheon/`（または `PANTHEON_HOME`）

- `platform.json`
- `organizations/`
- `knowledge/`
- `policy.yaml`
- `orchestration_patterns.json`
- `capability_registry.json`
- `capability_gaps.json`

### リポジトリ単位

`<target_repo>/.pantheon/`

- `current_state.json`
- `decisions/`
- `reviews/`
- `improvements/`
- `knowledge/`
- `artifacts/`
- `organizations/`

## 変更時の注意点

- 中核モデルのスキーマ変更は回帰テスト影響が大きい
- `main.py`, `core/models`, `core/platform`, `tests/` は `PolicyEngine` 上も慎重変更対象
- 新しいSkillやAgentを追加するなら、実装・ルーティング・テストをまとめて更新する
