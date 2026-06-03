# GitHub Copilot Instructions

> **このリポジトリの正典は [`../AGENTS.md`](../AGENTS.md) です。**
> GitHub Copilot を含むすべての外部AIコーディングエージェントは、まず `AGENTS.md` を読んでから
> 作業してください。本ファイルは指示を二重管理しないために最小限に留めています。

## 最初に読むもの

1. `AGENTS.md`（リポジトリ直下）— プロジェクト概要・ディレクトリ構造・開発規約・テスト手順
2. `docs/architecture.md` — アーキテクチャと「エージェントの2つの平面」

## 絶対に守る要点（詳細は AGENTS.md）

- 新規 `.py` は `from __future__ import annotations` で開始する
- `datetime.utcnow()` 禁止 → `datetime.now(timezone.utc)`
- テストは `tests/` に追加し、`python -m pytest tests/ -q` を常に緑に保つ
- Web/API 変更時は 404 系挙動を壊さない（`web/server.py`）
- LLM 呼び出しは必ず `core/llm`（プロバイダー非依存）経由にする

## 注意

リポジトリ直下の `skills/` `agents/` `commands/` は RepoCorp の実行時概念であり、
特定のAIツールの設定とは無関係です（AGENTS.md の「エージェントの2つの平面」を参照）。
