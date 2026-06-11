# Security Policy

## 設計上のセキュリティ特性

- **API キーを保存・送信しません。** 全生成はローカルの `claude` CLI を経由し、
  認証は Claude Code 自身が管理します。
- **ローカルファースト。** Web GUI / API はローカル利用が前提です
  （既定バインドは `127.0.0.1`）。
- **API トークン（任意）。** 環境変数 `PANTHEON_API_TOKEN` を設定すると、
  `/api/*` への全リクエストに `Authorization: Bearer <token>` を要求します。
  LAN 公開（`--host 0.0.0.0`）する場合は必ず設定してください。
- **外部 Organization の隔離。** `isolation_level=external` の組織はポリシー
  エンジンによりワークスペース外への変更を遮断されます。

## 脆弱性の報告

セキュリティ上の問題を発見した場合は、公開 Issue ではなく
GitHub の **Private vulnerability reporting**（Security タブ）からご報告ください。

## サポート対象

最新の `main` ブランチのみを対象とします。
