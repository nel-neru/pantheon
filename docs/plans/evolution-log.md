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

Cycle 2 — scripts の git 解決を fail-fast 化  (2026-06-12 04:00)
  Plan   : branch_status.mjs が git 不在環境（PowerShell セッション）で ENOENT を握りつぶし
           「全ブランチ 0」と誤報告する確定バグの修正。受け入れ基準 = git 無し PATH でも
           標準インストール先から自動解決して正常動作、それも無ければ exit 2 で明確に中止。
           落とした候補: パス区切り基線4件の根治 / 順序フレーク根治 / atelier serve 導線。
  Did    : work/scripts-git-fail-fast-20260612。scripts/lib/git_exec.mjs 新設（解決順:
           $PANTHEON_GIT → PATH → Git for Windows 標準パス、見つからなければ fail-fast）。
           branch_status.mjs / merge_to_main.mjs / new_work_branch.mjs に適用。
           branch_status の git() は ENOENT のみ fail-fast（コマンド失敗時の stdout 返却は維持）。
           あわせて settings.local.json（gitignored）の env.PATH に C:\Program Files\Git\cmd を
           追加（このマシンはシステム PATH に git が無いことが判明）。
  Check  : 4通り検証 — Bash 正常系（done 17/active 1 正しく分類）/ git 無し PATH で
           フォールバック成功 / PANTHEON_GIT 不正で exit 2 / 元の PowerShell 再現も正常化。
           レビュー所見と対応は下記 Check 欄追記参照。
  Act    : （merge 結果はマージ後に追記）学び: 「外部コマンド呼び出しの catch-all は
           ENOENT を必ず区別する」— 静かな誤報告は派手なクラッシュより危険。
  Next   : パス区切り基線4件の根治（基線縮小）/ work/web-gui-publishing-20260610 の
           取り込み判断（6 コミット先行で滞留中）/ done ブランチ 17 本の --prune 掃除。

Cycle 1 — atelier GUI を main へ landing  (2026-06-12 03:55)
  Plan   : 前セッション完成・22件監査済みの web/atelier 新 GUI（実コード約3.8k行）+
           /evolve コマンド自体が origin/main 未統合のまま checkpoint commit に滞留して
           いたため、検証→最終レビュー→統合を最優先。受け入れ基準 = build/vitest 緑・
           backend 基線維持・merge_to_main 成功。落とした候補: scripts の git バグ修正
           （Cycle 2 へ）/ パス区切り基線根治。
  Did    : work/hooks-skills-refresh-20260611（既存 checkpoint の landing のため新枝なし）。
           レビュー所見対応として web/atelier/.gitignore に *.tsbuildinfo 追加 + 2ファイル untrack。
  Check  : atelier npm run build 緑 / vitest 15/15 緑 / backend 全件 = 既知6件のみ failed・
           1021 passed（真の回帰ゼロ。test-triage agent は test_save_and_load_organization を
           新規回帰と誤判定したが CLAUDE.md 基線に明記済み — agent の基線リスト照合ミス）。
           code-reviewer 最終スポットレビュー = APPROVE-WITH-NITS（token/WS/Inbox 競合/
           URL スキーム/proxy/リーク全て確認済み、唯一の minor = tsbuildinfo 追跡 → 対応済み）。
  Act    : merged ✅（182aeac..267b2af を push）。memory atelier-gui を main 統合済みに更新。
           学び: auto-commit checkpoint にしか存在しない完成物は最優先で landing する。
  Next   : scripts git fail-fast（→ Cycle 2 実施）/ 基線縮小 / atelier serve 導線。
