# トラブルシューティング（I7）

## LLM が応答しない / スタブのまま

- APIキーが解決できていない可能性。`GET /api/health` の `has_llm` を確認。
- 既定クライアントは GUI 設定（`~/.repocorp/gui_settings.json`）> 環境変数の順で provider+key を解決します（`core.llm.get_default_llm_client`）。キーが無いと `None`＝従来のテンプレート動作。
- provider 別の環境変数: `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GROQ_API_KEY` / `GITHUB_TOKEN` / `GOOGLE_API_KEY`。
- レート制限/一時障害は `call_with_retry`（指数バックオフ）で自動再試行。恒久エラーは `LLMError` として正規化され UI に表示。

## 外部 CLI ツールが「未検出」になる（実行モード=CLI）

- `GET /api/execution/modes` で各 CLI（claude/codex/gemini/aider/opencode）の可用性を確認。
- PATH に実体が無いと未検出。インストール手順は [`docs/cli_tools.md`](cli_tools.md) を参照。
- コマンド名を上書きするには `gui_settings.cli_commands`（例: `{"claude": "claude-x"}`）。

## 埋め込みターミナルが開かない / すぐ消える

- PTY は **POSIX 専用**。Windows では未対応の明示エラーになります（C5。ConPTY は将来対応）。
- 同時セッション上限（既定 20）に達していないか。アイドル/終了セッションは自動 GC されます（C1）。
- `cwd が存在しません` エラー: 指定ディレクトリが存在するか確認。

## WebSocket がつながらない（chat/updates/terminal）

- localhost からのみ接続可。リバースプロキシ経由などで `Origin` が許可外だと 4403 で拒否（A4, CSWSH 対策）。
- LAN 公開時は `REPOCORP_ALLOWED_HOSTS` / `REPOCORP_CORS_ORIGINS` の設定を確認。

## API が 401 / 413 を返す

- 401: トークン認証が有効（`REPOCORP_API_TOKEN` か `api_auth_token`）。`X-RepoCorp-Token` か `Authorization: Bearer` を送る（A2）。
- 413: リクエストボディが上限超過（A8）。`REPOCORP_MAX_BODY_BYTES` を確認。

## フロントエンドが「未ビルド」になる

- `web/dist` が無いと案内ページ（503）。`npm --prefix web/frontend install && npm --prefix web/frontend run build` を実行。

## ログを詳しく見たい

- `REPOCORP_LOG_FORMAT=json` で構造化ログ（相関ID `request_id` 付き, J2/J3）。`REPOCORP_LOG_LEVEL=DEBUG` でレベル変更。
