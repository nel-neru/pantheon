# plans/

このディレクトリは **実装前・進行中の一時的な計画段階ドキュメント** を置く場所です
（kickoff / 調査メモ / ロードマップ / フェーズ別の実装計画など）。

**ルール（AGENTS.md の Planning Document Hygiene に明文化）**:

- 進行中の計画・調査・キックオフなどの一時ドキュメントは `docs/plans/` に集約する。
- `docs/design/` などの恒久ドキュメントフォルダを汚さない。
- このディレクトリの内容は一時的である。
- 実装完了後:
  1. 重要な決定・設計は `docs/design/`、`docs/architecture.md` など恒久ドキュメントへ統合する。
  2. このディレクトリ内のファイルは削除するか `docs/archive/plans/` へアーカイブする（ゴミを残さない）。
- 検証: `python scripts/check_planning_docs.py`（`docs/design/` への計画ドキュメント誤配置を検知。
  `docs/` の .md 編集時に PostToolUse フック `check-planning-docs.mjs` が自動実行）。

## 現在のアクティブな計画

**なし。** 直近の Group Structure & Monetization 計画は実装完了・main 反映済みのため整理済みです:

- 恒久的な決定・アーキテクチャ・残存する将来課題 → **`docs/design/group-monetization.md`**
- 完了した計画段階ドキュメント（研究シード・推論過程） → **`docs/archive/plans/`** にアーカイブ

新しいフェーズ/取り組みを始めるときは、ここ（`docs/plans/`）にキックオフ等の一時ドキュメントを
追加し、完了したら上記の手順で恒久ドキュメントへ統合・アーカイブしてください。
