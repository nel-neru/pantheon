# plans/

このディレクトリは **実装前の計画段階ドキュメント** を置く場所です。

**ルール（Group & Monetization Roadmap に明文化済み）**:
- 進行中の計画・調査・キックオフなどの一時的ドキュメントは `docs/plans/` に集約する。
- `docs/design/` などの恒久ドキュメントフォルダを汚さない。
- 各 plans/ エリアには必ず README を置き、「これは一時的である」ことを明記する。
- 実装完了後:
  1. 重要な決定・設計は `docs/design/`、`docs/architecture.md` など恒久ドキュメントに統合する。
  2. このディレクトリ内のファイルは削除するか `docs/archive/plans/` 等へアーカイブする（ゴミを残さない）。
- Claude Code などのエージェント作業では、主に `phase5-kickoff.md` を指定して「始めて」と伝える。

## 現在の主なファイル

- `phase5-kickoff.md` — エージェント起動用の単一エントリポイントファイル（Claude指定推奨）
- `phase5-inspiration-trending-agents-2026.md` — トレンド調査の種
- `group-monetization-implementation-plan.md` — 詳細なフェーズ別実装計画（Planning Document Hygiene ルールや現在のタスクを含む）
- `group-monetization-vision.md` — この取り組み向けの高レベルビジョン（実装後アーカイブ/統合の対象になる可能性あり）
- （必要に応じて他の計画メモを追加）

実装が終わったらこのREADMEも含めて掃除してください。計画の成果は恒久ドキュメントに残す。

検証: `python scripts/check_planning_docs.py` を実行すると、設計フォルダへの計画ドキュメントの誤配置を検知します。Phase 4 の精神で、計画ドキュメント作成時に警告が出るようにフック/CIと連携させる（将来的に pre-commit や既存の validate フローに組み込み予定）。
