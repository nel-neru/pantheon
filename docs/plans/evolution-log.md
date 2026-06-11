# Pantheon 自律進化ログ（/evolve）

`/evolve`（`.claude/commands/evolve.md`）の PDCA ループが、サイクルごとの記録を時系列で追記する場所です。
**planning hygiene 準拠の一時ドキュメント**: 節目で重要な決定・確立したベストプラクティスを恒久ドキュメント
（`docs/design/` 等）や memory へ統合し、本ファイルは肥大化したらアーカイブします（`docs/plans/README.md` 参照）。

各サイクルは次の形式で追記する:

```
Cycle N — <一言タイトル>  (YYYY-MM-DD HH:MM)
  Plan   : 選んだ 1 件 / 受け入れ基準 / なぜ今これか（落とした候補も一行）
  Did    : ブランチ名 / 触ったファイルと変更の要点
  Check  : test-triage / lint / build / レビュー所見と対応
  Act    : merged?（merge_to_main 成否）/ 記録した学び・固定化したベストプラクティス
  Next   : 次サイクルの候補（2〜3 個）
```

---

<!-- 以降、新しいサイクルを上から追記していく -->
