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

Cycle 20 — 対話セッションの heartbeat 化（resume 二重起動の構造的根治）  (2026-06-13 22:20)
  Plan   : Cycle 19 の事故の根治。resume は「最終コミット時刻」だけを生存印にするため、
           長い1ターン中（未コミット）や起動直後（最終コミットが数時間前）の対話セッションを
           検知できず headless /evolve を二重起動する。受け入れ基準 = 生きている対話セッションが
           独立した活動印を更新し、resume はそれが新鮮なら起動を抑止 / 後方互換（印が無ければ
           従来通り）/ 緑・敵対レビュー通過。落とした候補: done 6本 prune / load_organizations 警告。
  Did    : work/session-heartbeat-20260613。設計を Workflow（3レンズ並列→統合, GO 判定）で固め、
           実装→レビュー Workflow（3レンズ→verdict）で硬化。
           - .claude/hooks/session-heartbeat.mjs 新設: ~/.pantheon/evolve_session.heartbeat を
             atomic(tmp→rename)で touch、best-effort・常に exit 0。SessionStart + 全ツール
             PostToolUse('*', async) で更新。
           - .claude/settings.json: SessionStart に2つ目 / PostToolUse に matcher '*' 追加。
           - scripts/evolve_resume.ps1: commit ゲートの後に mtime ゲート（Test-Path 内＝後方互換）。
             **内容は読まず mtime のみ**（torn-read で ConvertFrom-Json→$ErrorActionPreference=Stop
             中断、を回避）。生の double 比較で境界厳密化。
           - tests/test_evolve_resume_session_heartbeat.py（8本）: フック writer + PS ゲート判定
             （fresh→skip / 不在・stale→proceed, powershell-gated）。
  Check  : 全8テスト pass / ruff 緑 / PS ParseFile 0 / BOM 保持 / 4 DryRun シナリオ実証 /
           test-triage GREEN（1108 passed・基線2のみ・回帰0）。
           レビュー所見対応: ①PS ゲート無テスト→PS判定テスト3本追加（最重要）②crash した headless
           resume が自分の再起動を最大90分マスク→headless 子は PANTHEON_EVOLVE_HEADLESS=1 で
           marker を書かない（健全 headless は pid ロックで重複防止／marker=「対話のみ」）③[int]
           四捨五入→生 double 比較。④グローバル marker の cross-repo 結合（現状安全・sibling Org に
           フック無し）と⑤cold-start サブ秒残留窓は記録のみ（次へ）。
  Act    : （merge 後に追記）固定化: 「mtime のみ読む heartbeat は torn-read/単位/TZ のリスク群を
           一掃」「無コンソール経路は観測口を残す」「resume が起動する子は自分用の生存印を書かない」。
  Next   : marker を cwd/リポジトリ別名で repo スコープ化（cross-repo 結合の解消）/
           done ブランチ6本の prune / load_organizations の silent-drop 警告ログ。

Cycle 19 — 窓なしランチャの回帰防止テスト固定＋並走セッション事故の収束  (2026-06-13 21:20)
  Plan   : Cycle 18 の窓なしランチャは「壊れても無音で回帰する」（窓が再び出る/フォーカス
           奪取が復活する）クラスで、単体テストが無かった穴を埋める。受け入れ基準 =
           CREATE_NO_WINDOW 契約・コマンド構築・cwd・戻り値伝播・失敗時ログを固定 / 緑 /
           レビュー通過。落とした候補: done 6本の prune / load_organizations 警告ログ
           （次サイクルへ）。
  Did    : work/launcher-regression-test-20260613。tests/test_evolve_resume_launcher.py（7本）
           — CREATE_NO_WINDOW(0x08000000)/-File ps1/-StaleMinutes/cwd=repo/既定90/戻り値伝播/
           ps1不在=1+ログ/spawn失敗=1+ログ/powershell パス解決。差し替えは monkeypatch のみ
           （共有 subprocess.run 汚染回避）。
  Check  : 7 passed / ruff 緑 / 全体コレクション 1102 健全 / merge gate 通過。
           code-reviewer APPROVE-WITH-NITS → 🟢2件（cwd 検証・spawn失敗分岐）を取り込み。
  Act    : merged ✅（09a8d10..2c8489f）。**事故と収束（重要・固定化）**: Cycle 18 のテスト中、
           未コミット（heartbeat 古）状態で毎時タスクが 21:01 に自然発火し、headless /evolve
           （pid 14068）が起動して私と同じ作業ツリーを編集（このテストファイルを monkeypatch 版へ
           改良＝皮肉にも net positive だった）。git は無傷（rogue はブランチ作成もコミットも
           できず Stop 前に停止）。killswitch を立て→lock/ログから pid 特定→当該ツリーのみ
           taskkill /T→lock 掃除→killswitch 解除で正常運用復帰。教訓: resume タスクの検証時は
           先に `.disabled` を立てるか先にコミットして heartbeat を新鮮にする。
  Next   : interactive /evolve セッションの heartbeat 化（resume との二重起動を根絶）/
           done ブランチ6本の prune / load_organizations の silent-drop 警告ログ。

Cycle 18 — 定期実行のフォーカス奪取を根絶（窓なし自動再開）  (2026-06-13 21:02)
  Plan   : ユーザー実害報告 — 毎時の "Pantheon Evolve Resume" タスクが powershell.exe
           （コンソールサブシステム）を直接起動するため、起動のたびに可視コンソール窓が
           前面化しフォーカス（とマウス）を奪い、全画面ゲームが裏画面へ落ちる。高レバレッジ
           （24h 自律基盤の運用品質に直結）・高確信・完全可逆。受け入れ基準 = 毎時タスクが
           窓を一切出さずに評価チェーンを回す / claude 再開経路を壊さない / 基線維持 +
           レビュー通過。落とした候補: VBScript ラッパ（MS が非推奨化を進行中）/ schtasks の
           Hidden 設定（窓フラッシュは消えない）/ 「ログオン不要」実行（資格情報が必要・制約違反）。
  Did    : work/evolve-resume-hidden-20260613。scripts/evolve_resume_launcher.py 新設
           （pythonw.exe＝GUIサブシステム＝窓なし、watchdog と同じ windowless 実行体から
           powershell を CREATE_NO_WINDOW で spawn）。install_evolve_resume_task.ps1 を
           pythonw+launcher 登録へ変更（-PythonW param、launcher/pythonw 存在検証）。
           evolve_resume.ps1 は不変。レビュー指摘で launcher 側 spawn 失敗を ps1 と同じ
           ~/.pantheon/evolve_resume.log へ一行残す観測性を追加（無コンソール下の唯一の診断口）。
  Check  : ライブタスクを再登録し実機検証 — pythonw→launcher→(窓なし)powershell→ps1 が
           LastTaskResult=0x0 で完走、窓は一切出ず。killswitch 経路でも exit 0・skip ログ確認。
           test-triage GREEN（既知2失敗のみ・新規回帰0、1093 passed）/ ruff 緑 /
           docstring の \e 無効エスケープ SyntaxWarning を raw 文字列化で根絶。
           code-reviewer APPROVE-WITH-NITS（critical 無し）→ 観測性 nit を取り込み済み。
           注: テスト中、未コミット（heartbeat 古）状態で schtasks /Run したため一度 headless
           claude が起動 → 競合回避のため即 stop + lock 掃除（正常運用では auto-commit が
           heartbeat を新鮮に保ち skip されるため非再現）。
  Act    : （merge 結果はマージ後に追記）学び＝固定化: 「タスクスケジューラから窓を出さず
           console アプリを回す正解は pythonw(GUI)→CREATE_NO_WINDOW。-WindowStyle Hidden は
           フラッシュが残る」。無コンソール経路は必ずファイルログに観測口を残す。
  Next   : done ブランチ6本の --prune 掃除 / load_organizations の silent-drop に警告ログ /
           resume と対話セッションの二重起動ガード（interactive session も heartbeat 化）。

Cycle 17 — atelier Inbox に Publishing セクション（収益化フローの新 GUI parity）  (2026-06-12 22:43)
  Plan   : 新フラッグシップ GUI（atelier）の Inbox が提案+handoff のみで publishing チェーン
           （投稿待ち/公開確認待ち）が完全欠落 — legacy でしか収益化フローを回せない状態の解消。
           Cycle 15/16 で完成済みの API をそのまま使う parity = 高レバレッジ・高確信度・可逆。
           受け入れ基準 = queued→投稿/取消、handed_off→公開を確認 が atelier で完結 /
           vitest+build 緑 / レビュー通過。落とした候補: wordpress Phase 2（資格情報設計が
           無人運転に不適）/ 実機 E2E（ユーザー同席要）/ CLI confirm parity（GUI が主経路）。
  Did    : work/atelier-publish-inbox-20260612。frontend-dev に委譲: Inbox.tsx に第3セクション
           Publishing（/api/inbox 30s ポーリング、kind=publish フィルタ、busy-key
           pub:{id}:{action}）、handed_off には /run が 409 するボタンを出さない設計、
           4 つ目の Stat。types.ts に InboxItem/InboxPayload。テストは fetch モック
           （api ラッパと URL 構築まで実走）で 9 本。
  Check  : code-reviewer APPROVE-WITH-NITS だが **major 1 件**: busy-key 非対称 — 取消
           (DELETE) in-flight 中も 投稿 が押せて同一ジョブに並行 run/delete が走り得る
           （バックエンドの 409/404 防御で被害は限定、だが busy 機構の目的そのもの）→
           disabled を working に広げ + in-flight を保留 Promise で観察する回帰テスト追加。
           最終: atelier 24/24 + build 緑 / merge gate 通過。
  Act    : merged ✅。学び: 複数アクションを持つカードの busy 制御は「自ボタンのみ lock」が
           罠 — 同一エンティティへの全 mutating アクションを相互排他にする（レビューが
           2 サイクル連続で frontend の状態管理バグを実害確定している — 省略不可の網）。
  Next   : 接続ページの atelier parity 判断 / 24h 基盤・トレンドの健全性監査（flow-audit）/
           wordpress Phase 2 設計メモ（実装はユーザー同席時）。

Cycle 16 — プラットフォーム接続 GUI ページ（/connections）  (2026-06-12 22:33)
  Plan   : Cycle 10/11/13/15 の Next に毎回積み残していた接続 GUI。API 3 本
           （list/login/disconnect）は実装済みで GUI だけ欠落 = レバレッジ高・確信度高・可逆。
           受け入れ基準 = 接続状態一覧 + 接続（ヘッドフルログイン起動→ポーリング完了検知）+
           切断が GUI で完結 / vitest + build 緑 / レビュー通過。落とした候補: 実機 E2E
           （ユーザー同席要）/ wordpress Phase 2・atelier 残ページ（1 サイクルに収まらない）。
  Did    : work/connections-gui-20260612。frontend-dev subagent に委譲: ConnectionsPage.tsx
           （3s ポーリング+120s タイムアウト、poller は useRef Map+unmount 掃除+多重起動ガード、
           capability はハードコードせず API の status/detail をそのまま表示）、/connections
           ルート+nav（Plug、インボックスの隣）、テスト 7 本（fake timers は
           shouldAdvanceTime + advanceTimers で userEvent と両立）。
  Check  : code-reviewer APPROVE-WITH-NITS（poller リーク/stale closure/URL エンコード/XSS/
           契約一致を全検証）→ 確定 minor 1 件反映: ポーリング中バッジを render から
           ref 参照→state ミラーに（タイムアウト経路はsetState を伴わずバッジ残留するため）。
           提案 1 件も採用: ポーリング完了検知の happy path テスト追加。
           最終: vitest 98/98 + build 緑 / merge gate の backend テストも通過。
  Act    : merged ✅（--delete-branch）。学び: 「ref を render で読む」は変更が描画に反映
           されない時限バグ — 表示に使う進行状態は state にミラーする（rules/frontend.md は
           既にこの語彙だが、レビューで毎回掴まえるのが現実的な網）。
  Next   : atelier への接続/確認フロー parity 判断 / wordpress Phase 2 REST /
           24h 基盤の硬化（roadmap B/C トラック）。

Cycle 15 — handed_off の公開確認フロー（出口側を配線、中断から再開）  (2026-06-12 22:21)
  Plan   : handed_off 意味論の出口側 — 人間が実公開した後に published へ確定し、そこで初めて
           成果 posts を記録する確認ステップ。これが無いと handed_off は dead end（成果が永遠に
           0 のまま・inbox からも消える）。受け入れ基準 = confirm で published+成果記録が厳密
           1 回 / 非 handed_off は 409 / 再ハンドオフ防止 / GUI から確認可能。
           ※前セッションが実装途中でレート制限中断 → evolve_resume.ps1（Cycle 7 の成果）経由で
           自動再開し、Check フェーズから続行。
  Did    : work/handedoff-confirm-20260612。runner.confirm_handed_off()（status ゲート +
           OutcomeStore.record の新フラグ dedupe_on_source=True でジョブ固有 source
           "publish-confirm:<job_id>" の冪等記録 = 並行/再送でも二重計上しない防御の深層化）。
           POST /api/publish-jobs/{id}/confirm（404/409 明示）。/run は handed_off に 409
           （API 直叩きの再ハンドオフ＝二重下書き防止。dry_run は無害なので許可）。
           /api/inbox に handed_off を「公開確認待ち」として集約（status フィールド追加）。
           InboxPage: handed_off は 投稿/プレビュー の代わりに「公開を確認」ボタン+バッジ。
           テスト: backend 6 本 + frontend 2 本。
  Check  : test-triage GREEN（1093 passed / 基線 chmod 2 件のみ）/ frontend 91/91 + build 緑 /
           ruff 緑。code-reviewer APPROVE（成果は確認時のみ・厳密 1 回・due_jobs 再進入なし・
           承認ゲート不変・明示 404 維持・WS live 更新・result_url 永続化を実コードで全件検証。
           所見は対応不要 nit 3 件: operation 欠落は /run と同型 / O(n) dedupe は既存パターン
           準拠 / 非アトミック mark_status は既存全呼出と同許容で source-dedupe が backstop）。
  Act    : merged ✅（7b7e42d..06d96b4 push、ブランチ削除）。これで収益化チェーンが一周:
           生成→承認→assisted ハンドオフ→人間公開→確認→成果記録。学び: 「人間に引き渡す」
           status を導入したら、必ず**人間が完了を報告する出口**も同時に設計する（さもなくば
           正直さのための status が成果の計上漏れに変わる）。evolve_resume.ps1 による中断→
           自動再開→merge の全行程が実地で機能した（Cycle 7 への投資が回収された初の実例）。
  Next   : 実機 E2E（ユーザー同席、docs/publishing.md）/ プラットフォーム接続 GUI ページ /
           atelier 残ページ移植 / wordpress Phase 2。

Cycle 14 — exe に atelier dist を同梱（Cycle 8 follow-up 完済）  (2026-06-12 12:50)
  Plan   : 記録済み残債の最小候補。--ui atelier が exe（PyInstaller onedir）で legacy に
           fallback してしまう穴を 1 タプルで閉じる。受け入れ基準 = spec 構文 OK +
           同梱先と server.py の resource_path 契約の一致 + レビュー。
  Did    : work/pyinstaller-atelier-dist-20260612。packaging/pantheon.spec の datas に
           (web/atelier/dist, web/atelier/dist) を追加（既存 exists フィルタで未ビルド時は
           自然に外れ、serve の警告つき fallback と整合）。docstring に atelier ビルド手順1行。
  Check  : spec compile() OK / ATELIER_DIST_DIR=resource_path("web","atelier","dist") と
           完全一致を確認。code-reviewer APPROVE（所見ゼロ — dist に .map/秘密なしも確認済み）。
  Act    : merged（結果は下記追記）。Cycle 8 レビュー由来の follow-up はこれで完済。
  Next   : 実機 E2E（note セレクタ + X intent、docs/publishing.md）/ 接続 GUI ページ /
           atelier 残ページ移植。

Cycle 13 — X 実投稿 Phase 1: web intent で assisted ハンドオフ  (2026-06-12 12:25)
  Plan   : 収益化チェーンの残り主要アダプタ。note（Cycle 11）と同型の assisted ハンドオフを
           X に展開。受け入れ基準 = フェイク検証で緑 / handed_off 意味論・不変条件の維持 /
           note との共通部（keepalive）の重複排除。落とした候補: PyInstaller datas / 接続 GUI。
  Did    : work/x-publish-live-20260612。XPublisher._publish_live: **web intent URL
           （x.com/intent/post?text=urlencoded）でプリフィル** — 公開エンドポイントのため
           contenteditable fill よりUI 変更に強い。body 優先・空は起動前に正直な失敗・280字超は
           detail 警告（len() は粗い近似と明記、自動分割 Phase 2）。adapters/handoff.py 新設で
           keepalive を note/X 共有化（プロセス全体・横断の単一リストと意図を明記）。
           docs/publishing.md に X 追記。**プロセス反省**: ブランチ作成を忘れ main 上で編集
           （未コミットだったため checkout -b で無害に是正。Stop hook の防御も健在だった）。
  Check  : test-triage GREEN（1086 passed / 基線 chmod 2 件のみ）/ ruff 緑。code-reviewer
           APPROVE-WITH-NITS（不変条件・quote() エンコーディング・URL 長・handoff 移設の
           回帰なしを実証検証済み）→ nits 3 件反映: len() 近似コメント / keepalive の
           横断設計コメント / 共有契約の直接ユニットテスト追加。
  Act    : merged（結果は下記追記）。学び: プラットフォームが公開している intent/share URL が
           あるなら、セレクタ自動化より先にそれを使う（壊れにくさが段違い）。
  Next   : 実機 E2E（note+X まとめて docs/publishing.md 手順）/ 接続 GUI ページ /
           PyInstaller datas（web/atelier/dist）。

Cycle 12 — branch_status --prune の偽成功報告を根治  (2026-06-12 11:45)
  Plan   : Cycle 11 後の掃除で発覚した確定バグ。git() ラッパ（失敗時も stdout 返却・表示系には
           正しい設計）を削除操作に流用していたため、`git branch -d` の拒否（ローカルが自分の
           upstream より先行）を「削除:」と誤報告 — 本日 2 回の prune で 6 本が実は消えていなかった。
           Cycle 2 で直した「静かな誤報告」クラスの残存。受け入れ基準 = 削除成否の正確な報告 +
           安全な範囲でのみ -D フォールバック + 実走検証。
  Did    : work/prune-false-success-20260612。deleteBranch()（execFileSync 直接・stderr 返却・
           LC_ALL=C でメッセージをロケール非依存化）。-D 昇格は3条件ゲート: MAIN===origin/main ∧
           fetch 成功（fetchOrigin() 新設で成否を実記録）∧ stderr が "not fully merged"
           （worktree 使用中等を力業で踏み抜かない）。失敗は exitCode=1 + 理由表示。
           リモート削除ヒントは通常 -d で消せたものだけに表示。
  Check  : 実走 4 通り（正常系 0 件・通常 -d・合成 upstream 未同期→-D 昇格・LC_ALL 後再確認）。
           code-reviewer 1st ラウンド REQUEST-CHANGES（-D の安全性論証は origin/main 照合と
           fetch 成功が前提なのに未保証 = critical 2 件）→ 全件反映 → 2nd ラウンド APPROVE
           （git 実メッセージの再現確認付き。ロケール所見は LC_ALL=C で対応）。
  Act    : merged（結果は下記追記）。学び・固定化: 「表示系の寛容なラッパ」を**成否が結果そのものの
           操作（削除等）に流用しない**。-D/-f 系の安全性論証は「何と照合した done か」「その照合先は
           新鮮か」まで明示してゲートする。
  Next   : 実機 E2E（docs/publishing.md）/ X _publish_live / 接続 GUI ページ / PyInstaller datas。

Cycle 11 — note 実投稿 Phase 1: assisted ハンドオフ（handed_off 意味論）  (2026-06-12 11:05)
  Plan   : Cycle 10 の接続フローに続き、最重要タスク _publish_live の note 実装。受け入れ基準 =
           接続済みセッションでエディタに流し込み「最終公開は人間」までフェイク検証で緑 /
           assisted live 成功は published と区別する handed_off（成果に数えない）/
           承認ゲート+mode ガード回帰テスト全維持。落とした候補: X アダプタ / 接続 GUI ページ。
  Did    : work/note-publish-live-20260612。NotePublisher._publish_live（auto=未実装の正直な失敗、
           未接続=connect 誘導、assisted=storage_state 復元→エディタ fill→**ブラウザ開いたまま
           ハンドオフ**。セレクタ/URL は実機検証待ちとしてモジュール定数に隔離）。
           PublishResult.handed_off + PUBLISH_JOB_STATUSES に handed_off（is_due は queued のみ＝
           再実行されない）。runner: handed_off は OutcomeEvent 未記録（未公開を収益に数えない）・
           監査ログには記録。WS は publish_handed_off（InboxPage は type.startsWith('publish') で
           live 更新が機能）。PlaywrightLauncher に storage_state 復元。docs/publishing.md 新設
           （運用手順+実機 E2E チェックリスト）。
  Check  : test-triage GREEN（1078 passed / 基線 chmod 2 件のみ）/ ruff 緑。code-reviewer
           APPROVE-WITH-NITS（不変条件: 承認なしジョブ生成なし・assisted は自動経路から発火せず・
           handed_off は terminal、を全て検証済み）→ 所見2件反映: (1) _HANDOFF_KEEPALIVE の
           無制限成長 → 次回ハンドオフ時に is_alive() で死んだ残骸を close+prune（人間使用中には
           触れない、テスト追加） (2) Timeout 時は「セッション期限切れの可能性」と明示。
           残リスク（正直に記録）: NOTE_BODY_SELECTOR は最初の contenteditable にマッチするため
           実機で誤ノード流し込みの可能性 — E2E チェックリスト項目4で検証する。
  Act    : merged ✅（9bcbd6b..91e4118 push 済み）。学び: 「下書き流し込み成功」と「公開」を status で
           区別する handed_off 意味論は、収益指標の正直さ（未公開を数えない）と自動再実行防止を同時に解決。
  Next   : 実機 E2E（ユーザー同席時、docs/publishing.md 手順）/ X _publish_live / 接続 GUI ページ。

Cycle 10 — ヘッドフルログイン接続フロー（Track E コア）  (2026-06-12 10:35)
  Plan   : publishing を「下書き工場」から実投稿チェーンへ進める第一歩。_publish_live の前提
           となる接続フロー（SessionStore.is_connected が常に false の構造的欠落）を先に埋める。
           受け入れ基準 = `pantheon publish connect note` でヘッドフル起動→手動ログイン→
           storage_state 保存→connections が connected、フェイク注入テストで緑。
           落とした候補: _publish_live 直行（接続なしでは E2E 不能）/ PyInstaller datas / atelier 残ページ。
  Did    : work/publish-connect-20260612。core/publishing/connect.py 新設（interactive_login:
           遅延 import、セッション cookie 名+発行ドメインのポーリング検知、launcher= フェイク注入、
           例外を投げず ConnectResult で正直に返す契約）。commands/publish.py（connect/status/
           disconnect、choices ハードコード+同期強制テスト）。web/server.py の login スタブを
           背景タスク起動に昇格（_login_tasks 多重起動防止+done callback で自己掃除、wordpress=
           unsupported、明示 404 維持）。tests/conftest.py に PANTHEON_NO_BROWSER=1 セッション
           ガード（playwright 導入環境でも suite が実ブラウザを起動しない）。
  Check  : test-triage GREEN（1071 passed / 基線 chmod 2 件のみ）/ ruff 緑 / CLI smoke
           （status 一覧+connect の正直な失敗）。code-reviewer APPROVE-WITH-NITS →
           確定所見3件を全て修正: (1) state.json はログイン済み cookie=実質ベアラ秘密 →
           0o600/dir 0o700（best-effort、settings ファイルと同基準） (2) cookie 名だけの
           一致は他ドメイン同名 cookie を誤検知 → 発行ドメイン照合を追加+負のテスト
           (3) _login_tasks の完了エントリを done callback で identity ガード付き pop。
  Act    : merged ✅（a405bd2..9bcbd6b push 済み、done ブランチ 6 本 prune）。
           学び: 「資格情報を保存しない」設計でも storage_state は
           ベアラ秘密 — 秘密相当ファイルは保存経路で必ず 0o600 基準に合わせる。
           実機 E2E（実ログイン）は無人ループでは行わずユーザー同席時に委ねる、を明文化。
  Next   : note _publish_live（assisted、handed_off 意味論）→ Cycle 11 / X _publish_live /
           接続 GUI ページ。

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
