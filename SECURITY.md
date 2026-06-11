# Security Policy

## 設計上のセキュリティ特性

- **API キーを保存・送信しません。** 全生成はローカルの `claude` CLI を経由し、
  認証は Claude Code 自身が管理します。
- **ローカルファースト。** Web GUI / API はローカル利用が前提です
  （既定バインドは `127.0.0.1`）。
- **API トークン（任意）。** 環境変数 `PANTHEON_API_TOKEN` を設定すると、
  `/api/*`（Bearer ヘッダ）と `/ws/*`（`?token=` クエリ）の両方に認証を要求します。
  LAN 公開（`--host 0.0.0.0`）する場合は必ず設定してください。
  Web GUI からは `http://<host>:<port>/?token=<TOKEN>` でアクセスすると、
  トークンが保存され以降の API/WS リクエストへ自動付与されます。
- **外部 Organization の隔離。** `isolation_level=external` の組織はポリシー
  エンジンによりワークスペース外への変更を遮断されます。

## 脆弱性の報告

セキュリティ上の問題を発見した場合は、公開 Issue ではなく
GitHub の **Private vulnerability reporting**（Security タブ）からご報告ください。
この機能はリポジトリの Settings → Code security で有効化されている必要があります
（公開前のチェックリスト項目）。有効でない場合は、メンテナへ直接ご連絡ください。

## サポート対象

最新の `main` ブランチのみを対象とします。
