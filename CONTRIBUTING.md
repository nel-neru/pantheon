# CONTRIBUTING — RepoCorp AI

開発に参加いただきありがとうございます。**正典は [`AGENTS.md`](AGENTS.md)** です。まずそちらを読んでください。本書は開発セットアップと日常の手順をまとめた補助文書です。

## セットアップ

```bash
# Python (editable + dev/web extras) と frontend 依存をまとめて
make install
# または個別に:
python -m pip install -e ".[dev,web]" ruff
npm --prefix web/frontend ci

# git フック（ruff lint / GUI テスト存在チェック / HelpPage 更新喚起）
bash scripts/install_hooks.sh
```

## 日常コマンド（Makefile）

| コマンド | 内容 |
|---|---|
| `make test` | pytest（バックエンド） |
| `make cov` | pytest + カバレッジゲート（`--cov-fail-under=70`, F7） |
| `make lint` / `make fix` | `ruff check .` / `ruff check --fix .` |
| `make build` | frontend ビルド（tsc + vite） |
| `make fe-test` | vitest（フロントエンド） |
| `make verify` | lint + test + build + fe-test を一括（**CI 同等**） |
| `make audit` | 依存脆弱性スキャン（pip-audit / npm audit） |
| `make serve` | Web GUI を localhost で起動 |

PR を出す前に **`make verify` が緑**であることを確認してください。

## コーディング規約（要点・詳細は AGENTS.md）

- 新規 `.py` は `from __future__ import annotations` で開始する。
- `datetime.utcnow()` 禁止 → `datetime.now(timezone.utc)`。
- **LLM 呼び出しは必ず `core/llm` 経由**（特定プロバイダー SDK に直結しない）。既定クライアントは `core.llm.get_default_llm_client()`、構造化出力は `generate_json`。
- テストは `tests/` に追加し、`python -m pytest tests/ -q` を常に緑に保つ。
- Web/API 変更時は 404/SPA 挙動を壊さない（`web/server.py` の catch-all は未知の `/api/*`・`/ws/*` に 404 を返す）。UI ページ追加時は `HelpPage.tsx` と vitest を更新する。
- `skills/` `agents/` `commands/` は **RepoCorp の実行時概念**であり Claude Code の `.claude/` とは無関係（`docs/architecture.md` の「2平面」を参照）。

## 改善バックログ

横断監査で見つかった改善課題は [`docs/improvement_backlog.md`](docs/improvement_backlog.md) にカテゴリ別・優先度つきでまとまっています。各イテレーションは「調査 → 実装 → pytest/vitest/ruff 緑 → チェック」で進めます。

## PR フロー

1. `main` から作業ブランチを作成。
2. 変更 + テスト追加。`make verify` を緑に。
3. PR を作成（関連するバックログ項目があれば記載）。CI（ruff + pytest + coverage、frontend build + vitest、依存 audit）が走ります。
