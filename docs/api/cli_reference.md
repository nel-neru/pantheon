# CLI Reference

このドキュメントは `main.py` と実際の `--help` 出力に基づく `pantheon` CLI リファレンスです。
エントリーポイントは `pyproject.toml` の `pantheon = "main:main"` です。

## トップレベルコマンド

```text
pantheon {init,org,analyze,proposals,approve,query,platform,goal,serve,daemon,agent,orchestration}
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

## `pantheon init`

```bash
pantheon init
```

- `~/.pantheon` の初期化
- Meta-Improvement Organization の作成
- デフォルトポリシー生成

## `pantheon org`

### `pantheon org add`

```bash
pantheon org add --name NAME [--repo REPO] [--purpose PURPOSE] [--template TEMPLATE]
```

| Option | 説明 |
| --- | --- |
| `--name` | Organization 名（必須） |
| `--repo` | 担当リポジトリの絶対パス |
| `--purpose` | Organization の目的・ゴール |
| `--template` | テンプレート名（例: `meta_improvement`） |

### `pantheon org list`

```bash
pantheon org list
```

登録済み Organization の一覧を表示します。

### `pantheon org remove`

```bash
pantheon org remove --name NAME
```

| Option | 説明 |
| --- | --- |
| `--name` | 削除する Organization 名（必須） |

## `pantheon analyze`

```bash
pantheon analyze --org-name ORG_NAME [--max-files MAX_FILES]
```

| Option | 説明 |
| --- | --- |
| `--org-name` | 対象 Organization 名（必須） |
| `--max-files` | 分析する最大ファイル数（default: `15`） |

実装: `cmd_analyze()` → `CodeReviewAgent`

## `pantheon proposals`

```bash
pantheon proposals --org-name ORG_NAME
```

| Option | 説明 |
| --- | --- |
| `--org-name` | 対象 Organization 名（必須） |

未対応提案を `実行可能` / `Meta-level` に分けて表示します。

## `pantheon approve`

```bash
pantheon approve PROPOSAL_ID --org-name ORG_NAME [--github-repo GITHUB_REPO] [--github-token GITHUB_TOKEN]
```

| 引数 / Option | 説明 |
| --- | --- |
| `proposal_id` | 承認する提案ID（先頭8文字以上） |
| `--org-name` | 対象 Organization 名（必須） |
| `--github-repo` | GitHub リポジトリ (`owner/repo`) |
| `--github-token` | GitHub トークン |

実装: `cmd_approve()` → `ImprovementExecutorAgent`

## `pantheon query`

```bash
pantheon query [--filter FILTER] [--limit LIMIT] [--db-path DB_PATH]
```

| Option | 説明 |
| --- | --- |
| `--filter` | SQL filter clause（例: `WHERE priority='high'`） |
| `--limit` | 最大件数（default: `50`） |
| `--db-path` | 対象 SQLite DB パス |

## `pantheon platform`

### `pantheon platform status`

```bash
pantheon platform status
```

全 Organization 横断の健康度・バランス・未対応提案数を表示します。

### `pantheon platform run-all`

```bash
pantheon platform run-all [--max-orgs MAX_ORGS]
```

| Option | 説明 |
| --- | --- |
| `--max-orgs` | 最大実行 Org 数（default: `5`） |

実装: 優先度順に `SelfImprovementLoop` を実行

## `pantheon goal`

### `pantheon goal status`

```bash
pantheon goal status
```

保存されたゴール履歴を表示します。

### `pantheon goal run`

```bash
pantheon goal run GOAL_TEXT
```

| 引数 | 説明 |
| --- | --- |
| `goal_text` | 実行するゴール文 |

実装: `AbstractGoalPipeline` を実行

## `pantheon serve`

```bash
pantheon serve [--host HOST] [--port PORT]
```

| Option | 説明 |
| --- | --- |
| `--host` | バインドホスト（default: `127.0.0.1`=ローカルのみ） |
| `--port` | ポート番号（default: `7860`） |

`fastapi` / `uvicorn` が必要です。

LAN に公開する場合は `--host 0.0.0.0` とし、併せて環境変数 `PANTHEON_API_TOKEN`
を設定してください（設定すると `/api/*` と `/ws/*` に Bearer 認証を要求します）。
GUI には `http://<host>:<port>/?token=<TOKEN>` でアクセスすると以降トークンが
保存され、API/WS リクエストへ自動付与されます。

## `pantheon daemon`

### `pantheon daemon start`

```bash
pantheon daemon start [--interval INTERVAL] [--max-files MAX_FILES]
```

| Option | 説明 |
| --- | --- |
| `--interval` | 実行間隔（秒, default: `3600`） |
| `--max-files` | 1 Organization あたり最大分析ファイル数 |

### `pantheon daemon stop`

```bash
pantheon daemon stop
```

### `pantheon daemon status`

```bash
pantheon daemon status
```

PID、schedulerログ、起動方法を表示します。

## `pantheon agent`

### `pantheon agent status`

```bash
pantheon agent status --org-name ORG_NAME
```

| Option | 説明 |
| --- | --- |
| `--org-name` | 対象 Organization 名（必須） |

`SkillProficiencyManager` のデータを表形式で表示します。

## `pantheon orchestration`

### `pantheon orchestration analyze`

```bash
pantheon orchestration analyze TASK_TYPE
```

| 引数 | 説明 |
| --- | --- |
| `task_type` | タスク種別（例: `code_review`, `meta_improvement`, `security_audit`） |

`PreTaskOrchestrator.analyze()` の結果を表示します。

### `pantheon orchestration history`

```bash
pantheon orchestration history
```

`OrchestrationPatternStore` の履歴を集計表示します。

### `pantheon orchestration capabilities`

```bash
pantheon orchestration capabilities
```

Capability Registry と検出済み能力ギャップを表示します。

### `pantheon orchestration self-review`

```bash
pantheon orchestration self-review
```

実行履歴から失敗率・品質の悪いパターンを検出し、改善必要箇所を表示します。

## 実用例

```bash
pantheon init
pantheon org add --name "MyApp" --repo /path/to/app --purpose "ECサイト開発"
pantheon proposals --org-name "MyApp"
pantheon platform status
pantheon goal run "セキュリティを改善したい"
pantheon orchestration analyze code_review
```
