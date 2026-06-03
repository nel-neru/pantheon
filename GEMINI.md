# GEMINI.md

> **このリポジトリの正典は [`AGENTS.md`](AGENTS.md) です。**
> Gemini / Gemini CLI を含むすべての外部AIコーディングエージェントは、まず `AGENTS.md` を
> 読んでから作業してください。本ファイルは Gemini 用の入口で、指示を二重管理しないために
> 最小限に留めています（＝単一の真実は AGENTS.md）。

## 最初に読むもの

1. [`AGENTS.md`](AGENTS.md) — プロジェクト概要・ディレクトリ構造・開発規約・テスト手順
2. [`docs/architecture.md`](docs/architecture.md) — アーキテクチャと「エージェントの2つの平面」

## 絶対に守る要点（詳細は AGENTS.md）

- 新規 `.py` は `from __future__ import annotations` で開始する
- `datetime.utcnow()` 禁止 → `datetime.now(timezone.utc)`
- テストは `tests/` に追加し、`python -m pytest tests/ -q` を常に緑に保つ
- Web/API 変更時は 404 系挙動を壊さない（`web/server.py`）
- **LLM 呼び出しは必ず `core/llm`（プロバイダー非依存）経由**。特定プロバイダーに直結しない。
  既定クライアントは `core.llm.get_default_llm_client()`、構造化出力は `generate_json` を使う

## 注意: 命名の衝突に惑わされない

リポジトリ直下の `skills/` `agents/` `commands/` は **RepoCorp の実行時概念**であり、
特定のAIツールの設定ディレクトリとは無関係です。詳細は AGENTS.md と
`docs/architecture.md` の「エージェントの2つの平面」を参照。
