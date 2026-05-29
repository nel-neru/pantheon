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

### WebSocket

- `WS /ws/chat`
- `WS /ws/updates`

## エラー方針

- 未発見リソースは `404`
- 入力不正は `422`
- 依存サービス未設定や内部失敗は `400/500` 系

## 実装メモ

- Organization 未発見時の `404` は壊さないこと
- ルートや設定変更時は `tests/test_web_server.py` を更新すること
