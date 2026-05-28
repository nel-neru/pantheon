# CLI Reference

このドキュメントは `main.py` と実際の `--help` 出力に基づく `repocorp` CLI リファレンスです。
エントリーポイントは `pyproject.toml` の `repocorp = "main:main"` です。

## トップレベルコマンド

```text
repocorp {init,org,analyze,proposals,approve,query,platform,goal,serve,daemon,agent,orchestration}
```

| Command | 説明 |
| --- | --- |
| `init` | グローバルプラットフォームを初期化する |
| `org` | Organization の作成・一覧・削除 |
| `analyze` | 対象Organizationのリポジトリを分析して改善提案を生成 |
| `proposals` | 未対応の改善提案を一覧表示 |
| `approve` | 改善提案を承認してコードへ適用 |
| `query` | SQLite proposals を条件付き検索 |
| `platform` | プラットフォーム横断操作 |
| `goal` | 抽象ゴールの履歴表示と実行 |
| `serve` | Web GUI を起動 |
| `daemon` | 自律改善デーモンの管理 |
| `agent` | エージェント状態・実績を表示 |
| `orchestration` | Pre-Task Orchestration の分析・履歴・能力表示 |

## `repocorp init`

```bash
repocorp init
```

- `~/.repocorp` の初期化
- Meta-Improvement Organization の作成
- デフォルトポリシー生成

## `repocorp org`

### `repocorp org add`

```bash
repocorp org add --name NAME [--repo REPO] [--purpose PURPOSE] [--template TEMPLATE]
```

| Option | 説明 |
| --- | --- |
| `--name` | Organization 名（必須） |
| `--repo` | 担当リポジトリの絶対パス |
| `--purpose` | Organization の目的・ゴール |
| `--template` | テンプレート名（例: `meta_improvement`） |

### `repocorp org list`

```bash
repocorp org list
```

登録済み Organization の一覧を表示します。

### `repocorp org remove`

```bash
repocorp org remove --name NAME
```

| Option | 説明 |
| --- | --- |
| `--name` | 削除する Organization 名（必須） |

## `repocorp analyze`

```bash
repocorp analyze --org-name ORG_NAME [--max-files MAX_FILES]
```

| Option | 説明 |
| --- | --- |
| `--org-name` | 対象 Organization 名（必須） |
| `--max-files` | 分析する最大ファイル数（default: `15`） |

実装: `cmd_analyze()` → `CodeReviewAgent`

## `repocorp proposals`

```bash
repocorp proposals --org-name ORG_NAME
```

| Option | 説明 |
| --- | --- |
| `--org-name` | 対象 Organization 名（必須） |

未対応提案を `実行可能` / `Meta-level` に分けて表示します。

## `repocorp approve`

```bash
repocorp approve PROPOSAL_ID --org-name ORG_NAME [--github-repo GITHUB_REPO] [--github-token GITHUB_TOKEN]
```

| 引数 / Option | 説明 |
| --- | --- |
| `proposal_id` | 承認する提案ID（先頭8文字以上） |
| `--org-name` | 対象 Organization 名（必須） |
| `--github-repo` | GitHub リポジトリ (`owner/repo`) |
| `--github-token` | GitHub トークン |

実装: `cmd_approve()` → `ImprovementExecutorAgent`

## `repocorp query`

```bash
repocorp query [--filter FILTER] [--limit LIMIT] [--db-path DB_PATH]
```

| Option | 説明 |
| --- | --- |
| `--filter` | SQL filter clause（例: `WHERE priority='high'`） |
| `--limit` | 最大件数（default: `50`） |
| `--db-path` | 対象 SQLite DB パス |

## `repocorp platform`

### `repocorp platform status`

```bash
repocorp platform status
```

全 Organization 横断の健康度・バランス・未対応提案数を表示します。

### `repocorp platform run-all`

```bash
repocorp platform run-all [--max-orgs MAX_ORGS]
```

| Option | 説明 |
| --- | --- |
| `--max-orgs` | 最大実行 Org 数（default: `5`） |

実装: 優先度順に `SelfImprovementLoop` を実行

## `repocorp goal`

### `repocorp goal status`

```bash
repocorp goal status
```

保存されたゴール履歴を表示します。

### `repocorp goal run`

```bash
repocorp goal run GOAL_TEXT
```

| 引数 | 説明 |
| --- | --- |
| `goal_text` | 実行するゴール文 |

実装: `AbstractGoalPipeline` を実行

## `repocorp serve`

```bash
repocorp serve [--host HOST] [--port PORT]
```

| Option | 説明 |
| --- | --- |
| `--host` | バインドホスト（default: `0.0.0.0`） |
| `--port` | ポート番号（default: `7860`） |

`fastapi` / `uvicorn` が必要です。

## `repocorp daemon`

### `repocorp daemon start`

```bash
repocorp daemon start [--interval INTERVAL] [--max-files MAX_FILES]
```

| Option | 説明 |
| --- | --- |
| `--interval` | 実行間隔（秒, default: `3600`） |
| `--max-files` | 1 Organization あたり最大分析ファイル数 |

### `repocorp daemon stop`

```bash
repocorp daemon stop
```

### `repocorp daemon status`

```bash
repocorp daemon status
```

PID、schedulerログ、起動方法を表示します。

## `repocorp agent`

### `repocorp agent status`

```bash
repocorp agent status --org-name ORG_NAME
```

| Option | 説明 |
| --- | --- |
| `--org-name` | 対象 Organization 名（必須） |

`SkillProficiencyManager` のデータを表形式で表示します。

## `repocorp orchestration`

### `repocorp orchestration analyze`

```bash
repocorp orchestration analyze TASK_TYPE
```

| 引数 | 説明 |
| --- | --- |
| `task_type` | タスク種別（例: `code_review`, `meta_improvement`, `security_audit`） |

`PreTaskOrchestrator.analyze()` の結果を表示します。

### `repocorp orchestration history`

```bash
repocorp orchestration history
```

`OrchestrationPatternStore` の履歴を集計表示します。

### `repocorp orchestration capabilities`

```bash
repocorp orchestration capabilities
```

Capability Registry と検出済み能力ギャップを表示します。

### `repocorp orchestration self-review`

```bash
repocorp orchestration self-review
```

実行履歴から失敗率・品質の悪いパターンを検出し、改善必要箇所を表示します。

## 実用例

```bash
repocorp init
repocorp org add --name "MyApp" --repo /path/to/app --purpose "ECサイト開発"
repocorp proposals --org-name "MyApp"
repocorp platform status
repocorp goal run "セキュリティを改善したい"
repocorp orchestration analyze code_review
```
