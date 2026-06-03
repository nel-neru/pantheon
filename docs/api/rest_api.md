# REST API Reference

RepoCorp AI の Web API は `web/server.py` の FastAPI アプリです。
起動後は `http://localhost:7860/docs` で Swagger UI、`/openapi.json` で OpenAPI を確認できます。

## 起動

```bash
repocorp serve
```

## 主要エンドポイント

### Platform / settings

- `GET /api/settings`
- `PUT /api/settings`
- `GET /api/storage/info`
- `GET /api/providers/{provider}/models`

### Organizations

- `GET /api/organizations`
- `POST /api/organizations`
- `GET /api/organizations/{org_name}`
- `PUT /api/organizations/{org_name}`
- `DELETE /api/organizations/{org_name}`
- `GET /api/organizations/{org_name}/icon`
- `PUT /api/organizations/{org_name}/icon`
- `DELETE /api/organizations/{org_name}/icon`

### Analysis / proposals

- `POST /api/analyze`
- `POST /api/analyze/stream`
- `GET /api/organizations/{org_name}/proposals`
- `POST /api/proposals/{org_name}/{proposal_id}/approve`
- `POST /api/proposals/{org_name}/{proposal_id}/reject`
- `POST /api/proposals/{org_name}/batch`

### Goals / orchestration / agents

- `GET /api/goals/history`
- `DELETE /api/goals/history`
- `POST /api/goals/stream`
- `GET /api/orchestration/analyze/{task_type}`
- `GET /api/agents`
- `GET /api/agents/runtime`
- `GET /api/skills`
- `GET /api/execution-history`

### Knowledge / tasks / chat

- `GET /api/knowledge/files`
- `POST /api/knowledge/files`
- `GET /api/knowledge/files/{file_path:path}`
- `PUT /api/knowledge/files/{file_path:path}`
- `DELETE /api/knowledge/files/{file_path:path}`
- `GET /api/tasks`
- `POST /api/tasks`
- `GET /api/tasks/{task_id}`
- `DELETE /api/tasks/{task_id}`
- `POST /api/chat`
- `GET /api/chat/sessions`
- `POST /api/chat/sessions`
- `GET /api/chat/sessions/{session_id}`
- `PUT /api/chat/sessions/{session_id}`
- `DELETE /api/chat/sessions/{session_id}`
- `POST /api/chat/sessions/{session_id}/messages`

### システム / 可観測性

- `GET /api/health` — liveness/readiness（version, has_llm, frontend_built, terminal_sessions）
- `GET /api/usage` — LLM トークン使用量の集計（provider/model 別 + 合計）
- `DELETE /api/usage` — 使用量カウンタのリセット
- `GET /api/metrics` — HTTP リクエストメトリクス（requests / errors / avg_duration_ms / by_status, J4）
- `DELETE /api/metrics` — メトリクスのリセット
- 全レスポンスに `X-Request-ID`（相関ID, J3）。受信した同名ヘッダがあれば踏襲。
- 構造化ログ（J2）: `REPOCORP_LOG_FORMAT=json` で1行1JSON、`REPOCORP_LOG_LEVEL` でレベル指定。
- 認証（任意, A2）: `REPOCORP_API_TOKEN` か `gui_settings.api_auth_token` を設定すると `/api/*`（health 除く）に `X-RepoCorp-Token` か `Authorization: Bearer` を要求。
- ボディ上限（A8）: `REPOCORP_MAX_BODY_BYTES`（既定 10MiB）超過は 413。

### 実行モード（API / CLI）

- `GET /api/execution/modes` — 実行モード一覧と外部CLIツールの可用性（claude/codex/gemini/aider/opencode）

### Core 自己改善

- `POST /api/core/improve` — RepoCorp 自身のコードを LLM で改善・テスト検証し、人間承認待ちの提案として登録（作業ツリーへ自動適用しない）。`{instruction, file_path | files, org_name?, max_iterations?}`

### ターミナル（localhost 限定）

- `GET /api/terminal/sessions` — ワークスペース一覧
- `POST /api/terminal/sessions` — ワークスペース作成（`{name?, cwd?, command? | cli_tool?}`）
- `DELETE /api/terminal/sessions/{session_id}` — 終了

### プロバイダー設定

- `GET /api/providers/{provider}/models` — モデル一覧 + capabilities

### WebSocket

- `WS /ws/chat`
- `WS /ws/updates`
- `WS /ws/terminal/{session_id}` — PTY 双方向（Origin 検証あり）

## エラー方針

- 未発見リソースは `404`
- 入力不正は `422`
- 依存サービス未設定や内部失敗は `400/500` 系

## 実装メモ

- Organization 未発見時の `404` は壊さないこと
- ルートや設定変更時は `tests/test_web_server.py` を更新すること
