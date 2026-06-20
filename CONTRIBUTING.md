# Contributing to Pantheon

Pantheon への貢献に興味を持っていただきありがとうございます。

## 開発環境のセットアップ

前提: Python 3.11+ / Node.js 22+ / ローカルの `claude` CLI（認証済み）

```bash
# バックエンド
python -m venv .venv
.venv/Scripts/pip install -e ".[dev,web]"     # Windows
# .venv/bin/pip install -e ".[dev,web]"       # macOS/Linux

# フロントエンド
cd web/frontend && npm ci
```

Pantheon は **API キーを一切使いません**。全生成はローカルの `claude` CLI
（Claude Code）を経由します。`claude` で一度ログインしてください。

## ブランチ運用

- 作業は必ず `work/<slug>-<YYYYMMDD>` ブランチで行います（`main` 直コミット禁止）。
  `node scripts/new_work_branch.mjs <slug>` で最新 main から作成できます。
- 完了したブランチは `node scripts/merge_to_main.mjs`（テストゲート付き）で
  main へ統合します。

## テスト

```bash
.venv/Scripts/python -m pytest tests/ -q     # バックエンド
.venv/Scripts/python -m ruff check .         # lint
cd web/frontend && npm test                  # フロントエンド (vitest)
```

- 新機能・修正には必ず `tests/` にテストを追加してください
  （`tmp_path` + `get_platform_home` monkeypatch パターン推奨）。
- **Windows では既知失敗は 0 件**です。chmod 0o600 由来の 2 件のテストは
  Windows では skip され、Linux CI では実行されて pass します。
  したがって、いかなる失敗も回帰です（詳細は CLAUDE.md）。

## コーディング規約

- 新規 Python ファイルは `from __future__ import annotations` で開始
- `datetime.utcnow()` 禁止 → `datetime.now(timezone.utc)`（常に timezone-aware）
- ruff（select = E,F,I / line-length 100）でフォーマット・lint
- 状態の保存先: グローバル → `~/.pantheon`、対象リポジトリ固有 → `<repo>/.pantheon`
- 詳細は [AGENTS.md](AGENTS.md) と `docs/development/conventions.md` を参照

## Pull Request

1. work ブランチで変更し、テストを全件グリーンにする（既知ベースライン除く）
2. 変更内容・動機・テスト方法を PR 説明に記載
3. CI（GitHub Actions）が通ることを確認
