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

Cycle 9 — trend-watcher 査定: 適用すべき確定変更なし  (2026-06-12 09:40)
  Plan   : 毎回先送りしていた「CC ベストプラクティス採用」カテゴリ。trend-watcher で
           .claude/ 設定の更新提案を収集し、検証済みのものだけ適用する方針。
  Did    : trend-watcher が6提案を返したが敵対的査定で大半を棄却:
           (1)「Fable は Haiku より低コスト」は事実誤認（Fable 5 は Opus 上位の最上位
           モデル）→ 棄却。有効な核は「agent の model: に fable が指定可能になった」事実
           のみで、code-reviewer/debugger の opus→fable 昇格はコスト判断つきの将来候補。
           (2) /goal・security-guidance plugin は本ハーネスで未確認の伝聞 → 見送り。
           (3) nested sub-agents は既に .claude/workflows/ で運用中 → 新規性なし。
           設定変更ゼロ（強引に出荷しない判断もログに残す）。
  Check  : n/a（変更なし）
  Act    : 学び: haiku ティアの trend-watcher は伝聞とコスト系の誤った断定を混ぜてくる —
           モデル/価格の主張は必ず一次情報で検証してから適用する。
  Next   : exe 配布時の PyInstaller datas に web/atelier/dist 追加 / _publish_live /
           atelier 残ページ移植 / code-reviewer・debugger の fable 昇格判断。

Cycle 8 — atelier を pantheon serve から配信（--ui atelier）  (2026-06-12 09:35)
  Plan   : 新 GUI を dev server 無しで使える導線。サブパス配信は Vite base/Router 再ビルドが
           必要で壊れやすいため「配信 dist の差し替え」方式。受け入れ基準 = 既定 legacy 不変 /
           --ui atelier で atelier 配信（未ビルド時は警告して legacy fallback）/ 単体テスト /
           明示 404 維持 / 実機 smoke。落とした候補: trend-watcher / _publish_live。
  Did    : work/atelier-serve-20260612。web/server.py に _resolve_serve_dir()（PANTHEON_UI 判定・
           fallback 警告）+ assets mount の条件を _serve_dir 基準に修正。serve/up 両コマンドに
           --ui（web.server import 前に環境変数へ反映）。テスト3本。docs（CLAUDE.md / atelier
           README）。**副発見の fix-forward**: PS5.1 Start-Process -ArgumentList は空白含む配列
           要素を自動クォートしない（argdump で実証）→ Cycle 7 の evolve_resume.ps1 の claude
           起動が引数分割で壊れていた → 手動クォート1本文字列に修正＋AGENTS.md に規約固定化。
           Cycle 7 レビューの「配列形式は自動クォートされる」判断は誤りだった（dry-run 検証は
           引数マーシャリングまで届かない、という教訓）。
  Check  : test_web_server 92 passed（基線2のみ）/ lint 緑 / 実機 smoke: PANTHEON_UI=atelier で
           「Pantheon Atelier」index 配信 + /api 明示 404 維持を確認 / クォート修正も argdump で
           実証。code-reviewer APPROVE-WITH-NITS（非ブロッキング2件: プロンプト禁止文字
           コメント拡大=対応済み / exe 化時の PyInstaller datas=follow-up 記録）。
  Act    : merged ✅。memory atelier-gui に serve 導線を記録。固定化: AGENTS.md に
           Start-Process 非クォート規約。
  Next   : trend-watcher で CC 設定更新（→ Cycle 9）/ _publish_live / atelier 残ページ移植。

Cycle 7 — レート制限解除後の /evolve 自動再開（ユーザー要望）  (2026-06-12 09:15)
  Plan   : 「5hレート制限解除後に自動再開されない」へのOSレベル対処。受け入れ基準 =
           再開判定スクリプト（fresh/stale/disabled 3分岐検証）+ schtasks 登録 + レビュー + merge。
           セッション内の暫定網として CronCreate（毎時:17、session-only と判明）も併設。
  Did    : work/evolve-auto-resume-20260612。scripts/evolve_resume.ps1（最終コミット時刻を
           heartbeat に使う: auto-commit フックが毎ターン commit するため生きたセッションが
           あれば必ず新しい。90分超で claude -p headless 再開、pid lock + disabled キルスイッチ）、
           install/uninstall_evolve_resume_task.ps1（毎時タスク）。タスク登録・PANTHEON_CLAUDE_BIN
           を setx で恒久化（watchdog 起動のデーモンも claude へ到達可能に）。
           付随発見: (1) settings.local.json env.PATH の ${PATH} がハーネスで展開されず
           セッション PATH が激狭だった（git/claude/powershell 不可視の根因）→明示列挙に修正
           (2) 日本語 .ps1 は UTF-8 BOM 必須（PS5.1 が cp932 誤読でパース崩壊）
           (3) このセッション自体が約4時間レート制限停止していた（263分前コミットで実証）
  Check  : dry-run 3分岐（fresh=skip / stale=再開対象 / disabled=skip）+ claude.exe --version 疎通。
           レビューと merge はこの後（結果は追記）。
  Act    : schtasks 'Pantheon Evolve Resume' 稼働開始。学び: 「auto-commit の毎ターン commit」は
           セッション生存の heartbeat として再利用できる。
  Next   : atelier serve 導線 / trend-watcher で CC 設定更新 / _publish_live（承認ゲート付き）。

Cycle 6 — Organization load の silent-drop を観測可能に  (2026-06-12 05:20)
  Plan   : 壊れた組織 JSON が黙って消える堅牢性の穴（Cycle 3 で発見）。受け入れ基準 =
           警告ログ + 他組織は読める + テスト。落とした候補: serve 導線。
  Did    : work/org-load-warn-20260612。platform/state.py に warn_skipped_org_file
           （path+mtime デデュープ: 常時ポーリング環境で警告洪水を防ぎ初回のみ WARNING）、
           per-repo 側 RepoStateManager にも同ヘルパを配線（レビュー所見）。テスト2本更新。
  Check  : 31 passed / lint 緑。code-reviewer APPROVE（hot path 洪水と sibling 整合の
           提案2件 → 両方対応）。
  Act    : merged ✅（7737bd9..）。学び: 耐性のための握りつぶしは「観測可能な握りつぶし」にする。
  Next   : evolve 自動再開（→ Cycle 7 で実施）/ serve 導線。

Cycle 5 — 順序フレーク2件の根治（基線 2 件=chmod のみへ）  (2026-06-12 05:05)
  Plan   : test_get_improvement_history（単体でも 25-35% 失敗へ悪化）と
           test_backup_manager_cleanup_old（12-15%）の根治。受け入れ基準 = 20回反復+全件で安定
           pass、基線記述からフレーク2件を削除。落とした候補: serve 導線 / silent-drop 警告。
  Did    : work/flaky-test-rootfix-20260612。debugger agent の根因特定: どちらも壁時計
           タイムスタンプ文字列を一意キーに使い、Windows の ~1-16ms クロック刻み内の連続呼出で
           衝突する製品バグ（テストの不変条件は正しい）。self_improvement_cycle.py の cycle_id に
           uuid4 8桁サフィックス、backup_manager.py のバックアップ名に既存時カウンタ付与。
           基線記述 7箇所からフレーク2件を削除（落ちたら回帰扱いに厳格化）。
  Check  : 反復 20/20 pass（修正前 25-35%/12-15% 失敗）。対象3ファイル 61 passed。
           全件 test-triage + レビューは実行済み（結果はマージ後追記）。
  Act    : （マージ後追記）
  Next   : atelier serve 導線 / load_organizations silent-drop 警告 / trend-watcher で
           CC 設定の最新動向取り込み。

Cycle 4 — publishing パイプライン（6コミット +2552行）の statale ブランチ統合  (2026-06-12 04:45)
  Plan   : 滞留2日の work/web-gui-publishing-20260610（生成→承認→投稿の一気通貫、/inbox /studio
           /revenue、PublishJob、auto/assisted モード）へ main 17マージ分を取り込み統合。
           受け入れ基準 = 統合後 backend 新基線+frontend 緑 / 承認ゲート不変条件の維持を
           レビューで確認 / merge_to_main 成功。落とした候補: serve 導線 / フレーク根治。
  Did    : merge-tree プローブで衝突3件と事前確認 → main をブランチへマージ。衝突解決:
           content_scheduler は main の A-1 設計（gate pause→自動resume）を採用、content_runner は
           _publish_block と downgrade= を両立、tsbuildinfo は untrack+gitignore（*.tsbuildinfo を
           ルートに追加）で根治。レビュー所見対応: runner.process_due_publish_jobs に
           PUBLISH_MODE_AUTO ガード+回帰テスト（assisted は自動実行経路から絶対に発火しない）、
           /proposals?org= ルートの quote() 統一（8箇所）、InboxPage の WS ライブ更新+preview の
           無駄リロード抑止、splitIntoThread の接尾辞 reserve を桁安定までループ（999→1000 境界）。
  Check  : backend 1051 passed / 失敗は基線3件のみ（chmod2+フレーク1）。frontend 89/89 + build 緑。
           Workflow レビュー（4次元×反証検証、16 agents）: critical/major 0、確定 minor 5件→全修正。
  Act    : merged ✅（e8d2978..59a0660）。memory gui-publishing-subsystem / roadmap を更新。
           学び: (1) stale ブランチは merge-tree --write-tree で無侵襲に衝突プローブしてから着手
           (2) 自動投稿経路の mode ガードは「daemon 側にあるから helper は不要」ではなく
           全経路に置く（防御の深層化）。
  Next   : test_get_improvement_history フレーク根治（単体でも失敗に悪化の報告あり）/
           atelier serve 導線 / load_organizations silent-drop 警告。

Cycle 3 — Windows パス区切り基線4件の根治  (2026-06-12 04:25)
  Plan   : 既知基線6件のうち path-separator 起因4件を根治し基線を 2 件（chmod のみ）へ縮小。
           受け入れ基準 = 4テスト pass（POSIX 互換維持）+ 基線符号化9箇所の同期 + 新規失敗ゼロ。
           なぜ今: 基線の複雑さが毎回の merge ゲート・triage を歪めている（今日 test-triage が
           基線リスト照合を誤った遠因）。落とした候補: publishing ブランチ取り込み / serve 導線。
  Did    : work/windows-path-baseline-20260612。repo_reader / dependency_graph /
           improvement_executor の相対パスを as_posix() 正規化（消費者はテストのみと確認済み）。
           test_save_and_load_organization は '/tmp' ハードコード→tmp_path に（意図=永続化往復）。
           基線記述 9箇所を 6→2 件へ同期、python.md ルールに as_posix 規約を固定化。
           付随: ruff format . が未整形112ファイルを再整形 → fix と style を**2コミットに分割**
           （412a68d fix / 878557e style）。以後 'ruff format .' は no-op。
  Check  : 対象4ファイル 72/72 pass。全件 test-triage GREEN（1023 passed、新基線どおり）。
           code-reviewer APPROVE（全消費者・永続化・ゲート・CI 検証済み）。follow-up 2件
           （codebase_indexer の as_posix 化 / ci.yml コメント）も対応。
  Act    : merged ✅（9cbb66d..e8d2978）。memory pantheon-test-baseline を新基線（chmod 2件）に
           更新。固定化: python.md に as_posix 規約、test-triage agent に「基線リストは
           リテラル一致・記憶で推論しない」を明記。
  Next   : work/web-gui-publishing-20260610 の取り込み判断 / atelier serve 導線 /
           load_organizations の silent-drop（検証失敗 JSON を黙って捨てる）に警告ログ。

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
