# セキュリティ運用ガイド（I5）

RepoCorp AI は **ローカル開発ツール**として設計されており、既定では `127.0.0.1` のみで待ち受けます。
埋め込みターミナルは実シェルを起動できるため、公開設定には特に注意してください。

## ネットワーク公開

| 項目 | 既定 | 公開時の注意 |
|---|---|---|
| バインドアドレス | `127.0.0.1`（A1） | `REPOCORP_HOST=0.0.0.0` で全 IF 公開。信頼できる LAN のみ。 |
| Host ヘッダ許可リスト | localhost 系のみ（A4, `TrustedHostMiddleware`） | LAN 公開時は `REPOCORP_ALLOWED_HOSTS=host1,host2` で明示追加。DNS リバインディング対策。 |
| CORS | `http://localhost:5173`（A3） | `REPOCORP_CORS_ORIGINS=...` で明示。`*` は使わない。 |
| WebSocket | localhost + Origin 検証（A4） | CSWSH 対策。`/ws/*` は loopback クライアント + 許可 Origin のみ。 |

> ⚠ `REPOCORP_HOST` で公開すると、埋め込みターミナル（実シェル）も到達可能になります。

## 認証（任意, A2）

既定では API 認証は **無効**です。有効化するには次のいずれかを設定します。

- 環境変数 `REPOCORP_API_TOKEN=<token>`
- `~/.repocorp/gui_settings.json` の `"api_auth_token": "<token>"`

有効化すると `/api/*`（`/api/health` を除く）にトークンが必要です。クライアントは
`X-RepoCorp-Token: <token>` か `Authorization: Bearer <token>` を送ります。比較は
`hmac.compare_digest`（定数時間）。WebSocket は別途 Origin 検証で保護されます。

## APIキー管理

- プロバイダーのキーは `~/.repocorp/gui_settings.json` に保存され、ファイル権限は `0600` に設定されます（権限が緩い場合は警告ログ）。
- ログ出力時はキー/トークンらしき文字列を `***REDACTED***` にマスクします（A6, `core/logging_config.py`）。
- **推奨**: 可能なら環境変数でキーを渡す。OS ネイティブのキーチェーン保存（keyring, A5）は将来対応予定。
- GitHub トークンは最小権限（リポジトリへの PR 作成に必要な範囲）に絞ってください。

## 環境変数と `.env`（A10）

- `.env.example` がテンプレート。`cp .env.example .env` して値を埋める。**`.env` 実体はコミットしない**（`.gitignore` 済み）。
- `.env.example` の鍵名は provider 解決（`PROVIDER_KEY_MAPPING`）と一致: `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GROQ_API_KEY` / `GITHUB_TOKEN` / `GOOGLE_API_KEY`。加えて運用系: `REPOCORP_HOST` / `REPOCORP_ALLOWED_HOSTS` / `REPOCORP_CORS_ORIGINS` / `REPOCORP_API_TOKEN` / `REPOCORP_MAX_BODY_BYTES` / `REPOCORP_LOG_FORMAT` / `REPOCORP_LOG_LEVEL` / `REPOCORP_WS_MAX_CONNECTIONS` / `REPOCORP_TERMINAL_IDLE_TTL` / `REPOCORP_TERMINAL_EXITED_TTL`。
- GUI から保存したキーは `~/.repocorp/gui_settings.json`（`0600`）。env と GUI のどちらか一方で十分（解決順は env > settings）。

## GitHub トークンの最小権限（A11）

PR 作成（`ImprovementExecutorAgent` / `github_integration`）に使う `GITHUB_TOKEN` は最小権限で発行する。

- **Fine-grained PAT（推奨）**: 対象リポジトリのみに絞り、`Contents: Read and write`（ブランチ作成/コミット）と `Pull requests: Read and write`（PR 作成）のみ付与。
- **Classic PAT**: プライベートリポジトリなら `repo` スコープ。公開のみなら `public_repo`。`workflow` 等の不要スコープは付けない。
- トークン未設定時は PR を作らずローカルブランチに適用（degrade）。トークンはログに出さない（A6 マスキング対象）。

## 入力・リソース保護

- リクエストボディ上限（A8）: 既定 10MiB。`REPOCORP_MAX_BODY_BYTES` で調整。超過は 413。
- WebSocket 同時接続上限（A9）: `/ws/updates` 既定 50。`REPOCORP_WS_MAX_CONNECTIONS`（0 で無制限）。超過は 1013 で拒否。
- 埋め込みターミナルはアイドル/終了セッションを自動 GC（C1）。`REPOCORP_TERMINAL_IDLE_TTL` / `REPOCORP_TERMINAL_EXITED_TTL` で調整。

## 監査・観測

- Core 改善/承認/組織操作は `execution_history` に `actor`（system/user）を記録（A7/J7）。
- 相関ID `X-Request-ID`（J3）と構造化ログ `REPOCORP_LOG_FORMAT=json`（J2）で追跡可能。

## チェックリスト（公開前）

- [ ] 本当に LAN 公開が必要か。不要なら `127.0.0.1` のまま。
- [ ] `REPOCORP_ALLOWED_HOSTS` と `REPOCORP_CORS_ORIGINS` を明示。
- [ ] `REPOCORP_API_TOKEN` を設定。
- [ ] APIキーの権限・スコープを最小化。
- [ ] 信頼できるネットワークか（埋め込みターミナル＝実シェル到達可）。
