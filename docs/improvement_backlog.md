# RepoCorp AI — 改善バックログ（100件チェックリスト）

このドキュメントは横断監査で発見した改善課題を、カテゴリ別・優先度つきでチェックリスト化したもの。
各イテレーションで「ベストプラクティスを調査 → 解決 → テスト緑 → チェック」を繰り返す。

凡例: 優先度 **P0**(緊急/安全) / **P1**(高) / **P2**(中) / **P3**(低)。`[x]` 解決済み。

> 進め方: `python -m pytest tests/ -q` と `npm --prefix web/frontend run test` と `ruff check .` を常に緑に保つ。

---

## A. セキュリティ

- [x] A1 (P0) uvicorn 既定が `host="0.0.0.0"`（全IF公開）→ 既定 `127.0.0.1`、公開は `REPOCORP_HOST` 明示時のみ。**[完了 Iter1]**
- [x] A2 (P1) API に認証が無い → 任意のローカルトークン認証（`REPOCORP_API_TOKEN`/`api_auth_token`、`X-RepoCorp-Token`/Bearer、既定無効、health除外）。**[完了 Iter11]**
- [x] A3 (P1) CORS が `allow_methods/headers=["*"]` ＋ credentials → 必要最小限に絞る。**[完了 Iter1]**
- [x] A4 (P1) 機微API/WS に CSRF/Origin 検証が無い → Host 許可リスト(TrustedHost) + WS Origin 検証。**[完了 Iter1]**
- [ ] A5 (P1) APIキーが gui_settings.json に平文（0600のみ）→ 暗号化/キーチェーン保存の選択肢。
- [x] A6 (P0) 例外メッセージ等にキー/秘匿値が漏れ得る → 秘匿値マスキング用ログフィルタ＋`_redact_secrets`。**[完了 Iter1]**
- [x] A7 (P1) Core改善/承認の監査ログ（誰が・何を）が無い → execution_history に actor 記録。**[完了 Iter8]**
- [x] A8 (P1) リクエストボディのグローバルサイズ上限が無い → ミドルウェアで上限（Content-Length 判定→413、`REPOCORP_MAX_BODY_BYTES` 既定10MiB）。**[完了 Iter11]**
- [x] A9 (P2) WS（chat/updates/terminal）の接続数・アイドルタイムアウトが無い → updates に接続上限（`REPOCORP_WS_MAX_CONNECTIONS` 既定50, 超過は1013）、terminal は C1 GC で回収。**[完了 Iter20]**（chat 上限/アイドル切断は後続）
- [x] A10 (P2) `.env` 実体の取り扱い・`.env.example` の鍵名整合を確認/文書化 → `.env.example` に運用系 env を追記、`docs/security.md` に整合表。**[完了 Iter20]**
- [x] A11 (P3) GitHub トークン最小権限スコープのガイドが無い → `docs/security.md` に Fine-grained/Classic PAT の最小権限ガイド。**[完了 Iter20]**
- [x] A12 (P1) 依存脆弱性スキャン（pip-audit / npm audit）が無い → CI に追加。**[完了 H6/H7 で実現: CI audit ジョブ + `make audit`]**

## B. LLM プロバイダー層

- [x] B1 (P1) `LLMConfig.from_env()` が env のみ参照（gui_settings 無視）→ `LLMConfig.from_settings()` を追加（client の解決ロジックに委譲、env>settings）。**[完了 Iter12]**
- [x] B2 (P0) provider 呼び出しにタイムアウトが無い（無限ハング）→ `call_with_retry` で全 generate に timeout。**[完了 Iter2]**
- [x] B3 (P1) リトライ/指数バックオフが無い（429/5xx/瞬断）→ `call_with_retry` 共通ラッパ。**[完了 Iter2]**
- [x] B4 (P1) ネイティブ JSON モード未使用 → capabilities 連動で response_format / mime。**[完了 Iter10]**（Anthropic の tool 強制は後続）
- [ ] B5 (P2) streaming が tools 非対応（全 provider stream が tools 無視）→ 対応 or 明示。
- [ ] B6 (P2) reasoning_effort（o系 / Claude thinking）未配線 → capabilities 連動で渡す。
- [x] B7 (P1) トークン使用量/コストの記録・GUI 表示が無い → `UsageTracker` + `/api/usage` + Settings カード。**[完了 Iter5]**
- [x] B8 (P2) 長文の汎用トリム戦略が無い（max_tokens 超でエラー）→ `core/llm/trim.py`（`trim_messages`: system/直近温存・中間削除・最大本文末尾省略）。**[完了 Iter23]**
- [x] B9 (P1) provider 固有エラーの正規化が無い（生例外が UI に出る）→ `LLMError` 正規化。**[完了 Iter2]**
- [x] B10 (P1) `/api/providers/{p}/models` が同期 SDK 呼び出しでループブロック → `to_thread`。**[完了 Iter2]**
- [x] B11 (P2) `get_default_llm_client` がリクエスト毎に provider 生成 → `(provider, key, model)` キーでキャッシュ（`reset_provider_cache`）。**[完了 Iter12]**
- [x] B12 (P1) 5 プロバイダの契約テスト（generate/stream/tool/json 正規化）が薄い → `tests/test_llm_provider_contract.py` で拡充。**[完了 Iter12]**

## C. ターミナル / 実行モード

- [x] C1 (P1) アイドルセッションの自動 GC が無い（プロセス残留）→ `TerminalManager.gc()`（exited は exited_ttl、購読者0の running は idle_ttl で回収。list/create で機会的実行、env で TTL 上書き）。**[完了 Iter14]**
- [x] C2 (P0) サーバ終了時に PTY を確実に kill する shutdown フックが無い → `atexit` で TerminalManager.shutdown。**[完了 Iter1]**
- [x] C3 (P2) スクロールバック上限はあるが、購読者0時の挙動を明確化 → 監査済み: 購読者0でも `_SCROLLBACK_CAP` で上限維持しつつ蓄積、再 attach 時に replay。**[完了 Iter14: 監査]**
- [ ] C4 (P2) ターミナル cwd が PROJECT_ROOT 外も許す → 既定/許可方針の明確化。
- [x] C5 (P2) Windows 未対応（PTY）→ POSIX import を任意化し `_PTY_AVAILABLE` 判定、`create()` で明示エラー。**[完了 Iter14: 明示メッセージ。ConPTY 対応は将来]**
- [ ] C6 (P1) CLI ワークスペースの出力を「タスク結果」として取り込む統合（残課題）。
- [ ] C7 (P2) cmux の分割ペイン未実装。
- [ ] C8 (P3) cmux の埋め込みブラウザ＋スクリプト API 未実装。
- [ ] C9 (P2) cmux の socket API / `notify` フック（waiting 通知の正式化）未実装。
- [ ] C10 (P2) 再接続時のサイズ同期/初回 fit タイミング改善。
- [x] C11 (P3) セッションのリネーム不可 → `rename()` + `PATCH /api/terminal/sessions/{id}`。**[完了 Iter14]**
- [ ] C12 (P1) 実行モード=CLI 時に Core改善等を CLI ワークスペースへ振り分ける統合。

## D. 正しさ / 堅牢性

- [ ] D1 (P1) broad `except Exception`（60ファイル）の一部がエラー握り潰し → ログ必須・絞り込み。
- [ ] D2 (P2) `_run_sync` のスレッド毎ループ生成のオーバーヘッド/整合性検証。
- [ ] D3 (P2) goal pipeline の同期 invoke が長時間ブロック → async 化検討。
- [x] D4 (P1) `.repocorp/*.json` の並行書き込み競合 → `atomic_write_text`(tmp+os.replace) で原子化。**[完了 Iter7]**
- [x] D5 (P0) JSON 保存が非原子的（クラッシュで破損）→ `_atomic_write_text`(tmp+os.replace)。**[完了 Iter1]**
- [x] D6 (P2) 日時の一貫性（`utcnow` 禁止）を全体再確認。**[完了 Iter7: 監査+回帰テスト]**
- [ ] D7 (P3) 短縮 UUID（[:8]/[:12]）の衝突可能性。
- [x] D8 (P2) proposal id 前方一致が複数マッチし得る → 完全一致優先。**[完了 Iter6]**
- [ ] D9 (P2) WS 例外時のクリーンアップ漏れ可能性。
- [x] D10 (P2) `asyncio.gather` で 1 例外が全体を落とす箇所 → 監査済み: 全 gather サイト(pre_task/multi_org)は worker 内で例外捕捉、multi_org は CancelledError を意図的に伝播。**[完了 Iter13: 監査]**
- [ ] D11 (P3) パス正規化のエッジ（symlink/大文字小文字）。
- [ ] D12 (P2) 設定マージの deepcopy 漏れによる共有 state 変異。

## E. パフォーマンス

- [x] E1 (P1) JS バンドル ~790KB（xterm）→ 動的 import / manualChunks で分割。**[完了 Iter6]**
- [ ] E2 (P2) ポーリング過多（terminal 4s 等）→ WS 統一 / 間隔最適化。
- [x] E3 (P1) `_load_all_proposals` が全 org 全ファイルを毎回読む（N+1）→ (org,件数,最大mtime) シグネチャでキャッシュ（追加/削除/上書きで自動無効化、`_invalidate_proposals_cache`）。**[完了 Iter15]**
- [ ] E4 (P2) `/api/search` が全 org 横断スキャン → インデックス。
- [x] E5 (P1) モデル一覧 API 同期呼び出しブロック（B10 と連動）→ `get_provider_models` は全 provider `asyncio.to_thread` 化済み。**[完了 B10/Iter2]**
- [ ] E6 (P3) 大量提案リストの仮想化が無い。
- [ ] E7 (P3) codebase indexer のキャッシュ無効化戦略。
- [ ] E8 (P2) execution_history 全件読み書き → 効率化。
- [x] E9 (P1) git 操作（branch/commit/PR）が同期で API ブロック → `to_thread`。**[完了 Iter6: ImprovementExecutor]**
- [x] E10 (P2) 静的アセットのキャッシュヘッダ未設定。**[完了 Iter6: immutable]**

## F. テスト

- [x] F1 (P1) provider 契約テスト（generate/stream/tool/json）拡充。**[完了 Iter12: B12 と同一 `tests/test_llm_provider_contract.py`]**
- [x] F2 (P1) e2e（goal→proposal→approve→PR）統合テスト → `tests/test_e2e_approve_pr.py`（実 PSM で提案→承認→PR成功/実行失敗/file_path無し）。goal→proposal は test_e2e、検証済み変更は test_core_improve_approval が補完。**[完了 Iter19]**
- [ ] F3 (P2) フロント a11y テスト（axe）。
- [x] F4 (P1) ターミナル WS 異常系テスト（切断/巨大出力/不正制御）。**[完了 Iter4: resize/input/不正制御]**
- [x] F5 (P1) CoreImprove 承認→直接適用の統合テスト。**[完了 Iter4]**
- [x] F6 (P2) PolicyEngine 境界網羅テスト → `tests/test_policy_boundaries.py`（優先度/カテゴリ/ファイルパターン/サイズ上限/helpers/YAML roundtrip）。**[完了 Iter16]**
- [x] F7 (P1) カバレッジ計測と CI ゲート → pytest-cov + `--cov-fail-under=70`（現状76%）、CI/`make cov`/pyproject [tool.coverage]。**[完了 Iter17]**
- [ ] F8 (P2) 並行性テスト（同時セッション/書き込み）。
- [x] F9 (P2) `json_extract` のファズ/プロパティテスト → `tests/test_json_extract_property.py`（固定シード乱数で 300+ 構造を生成しノイズ包み round-trip）。**[完了 Iter16]**
- [x] F10 (P2) CLI サブコマンドのスモークテスト網羅 → `tests/test_cli_smoke.py`（全サブコマンド `--help` 正常終了 + HANDLERS 健全性）。**[完了 Iter21]**
- [x] F11 (P2) WS updates ブロードキャストテスト → `tests/test_update_hub.py`（配信/接続管理/stale 除去）。**[完了 Iter16]**
- [x] F12 (P1) 既知バグ回帰テスト（例: pre_task の asyncio 欠落）。**[完了 Iter4]**

## G. アクセシビリティ / UX

- [x] G1 (P1) フォーカス管理（メニュー/検索/ドロップダウンのトラップ・復帰）。**[完了 Iter9: 検索 Esc/外クリック]**
- [x] G2 (P1) ARIA ロール/ラベル網羅（menu/listbox/live region）。**[完了 Iter9: 検索 combobox/listbox]**
- [ ] G3 (P1) キーボード操作（Tab/Esc/矢印）。
- [ ] G4 (P2) コントラスト WCAG AA（muted/バッジ）。
- [x] G5 (P2) `prefers-reduced-motion`（terminal-ring 等）対応。**[完了 Iter6]**
- [ ] G6 (P1) ローディング/空/エラー状態の一貫性（全ページ監査）。
- [x] G7 (P2) トーストの `aria-live` 通知 → `sonner`（Toaster）がアクセシブルな aria-live live-region を内蔵（実質達成）。**[完了 Iter20: 監査]**
- [x] G8 (P1) 検索ドロップダウンのキーボードナビ（↑↓Enter）。**[完了 Iter9]**
- [ ] G9 (P3) ターミナル（xterm）のスクリーンリーダー配慮。
- [ ] G10 (P3) i18n 基盤（現状日本語固定）。
- [ ] G11 (P2) レスポンシブのエッジ（極小画面/ターミナルタブ）。
- [ ] G12 (P2) フォームの `aria-describedby` でエラー紐付け。

## H. DX / CI / ツール

- [x] H1 (P0) GitHub Actions CI（pytest+ruff+vitest+build）が無い → `.github/workflows/ci.yml`。**[完了 Iter3]**
- [x] H2 (P1) ruff を pre-commit に組込（現状 GUI テスト/Help のみ）→ `scripts/hooks/pre-commit` でステージ .py を `ruff check`。**[完了 Iter17]**
- [ ] H3 (P2) mypy 段階導入。
- [ ] H4 (P2) frontend eslint + prettier。
- [ ] H5 (P2) 依存の再現性（`~=` 緩い）→ 制約 / lock。
- [x] H6 (P1) pip-audit / npm audit を CI に。**[完了 Iter3: 非ブロック audit ジョブ]**
- [x] H7 (P2) Makefile（test/lint/serve/build 一括）→ `make verify`。**[完了 Iter3]**
- [x] H8 (P2) CONTRIBUTING.md / 開発セットアップ → `CONTRIBUTING.md`（セットアップ/Makefile/規約/PRフロー）。**[完了 Iter17]**
- [ ] H9 (P3) pre-commit に frontend 軽量チェック。
- [x] H10 (P3) CHANGELOG / バージョニング → `CHANGELOG.md`（Keep a Changelog 準拠）。**[完了 Iter17]**

## I. ドキュメント

- [x] I1 (P1) REST API ドキュメント更新（core/improve, execution/modes, terminal, usage, health）。**[完了 Iter6]**
- [x] I2 (P1) architecture.md に Phase2-5 反映。**[完了 Iter6]**
- [x] I3 (P2) README に terminal/modes セットアップ。**[完了 Iter8]**
- [x] I4 (P2) docs/agents 更新（CoreImprovementAgent 等）→ `docs/agents/README.md` に CoreImprovementAgent 行追加。**[完了 Iter18]**
- [x] I5 (P1) セキュリティ運用ガイド（localhost/トークン/キー管理）→ `docs/security.md`。**[完了 Iter18]**
- [ ] I6 (P3) OpenAPI tags/examples 整備（terminal）。
- [x] I7 (P2) トラブルシューティング拡充（CLI 未検出/PTY/WS）→ `docs/troubleshooting.md`。**[完了 Iter18]**
- [x] I8 (P3) cli_registry の CLI 導入手順 → `docs/cli_tools.md`。**[完了 Iter18]**

## J. 観測性 / 運用

- [x] J1 (P1) `/api/health`（liveness/readiness）。**[完了 Iter1]**
- [x] J2 (P2) 構造化ログ（JSON / レベル統一）→ `core/logging_config.py`（`JsonLogFormatter`/`configure_logging`、`REPOCORP_LOG_FORMAT=json`）。**[完了 Iter13]**
- [x] J3 (P2) リクエスト/相関 ID → `request_id_var` + `_request_context` ミドルウェア（`X-Request-ID` 入出力、ログ自動付与）。**[完了 Iter13]**
- [x] J4 (P2) メトリクス（処理時間/LLM 呼数/トークン）→ `core/metrics/request_metrics.py` + `GET/DELETE /api/metrics`（LLM 呼数/トークンは B7 UsageTracker）。**[完了 Iter13]**
- [x] J5 (P3) daemon ログローテーション → `REPOCORP_LOG_FILE` 指定時に `RotatingFileHandler`（`REPOCORP_LOG_MAX_BYTES`/`REPOCORP_LOG_BACKUPS`）。**[完了 Iter22]**
- [ ] J6 (P3) エラー集約フック（任意 Sentry 等）。
- [x] J7 (P1) 監査ログ（A7 と連動）。**[完了 Iter8]**
- [x] J8 (P0) グレースフルシャットダウン（PTY は atexit で完了。WS/daemon は後続）。**[完了 Iter1: PTY]**

---

## 進捗ログ

- 2026-06-01: バックログ作成（100件）。イテレーション開始。
- 2026-06-01: **Iteration 1（P0 セキュリティ/堅牢性）完了** — A1, A3, A4, A6, C2, D5, J1, J8。
  - deep-research（FastAPI+PTY ローカルツールのセキュリティ）に基づき実装。主要知見:
    - 127.0.0.1 バインドは必要だが不十分（DNS リバインディング／0.0.0.0 経由）→ **Host ヘッダ許可リスト**（`TrustedHostMiddleware`）を追加。出典: [DEF CON 27 DNS Rebinding](https://media.defcon.org/), [NCC Singularity](https://github.com/nccgroup/singularity)。
    - WebSocket は SOP 非対象＝CSWSH（ハンドシェイクの CSRF）→ **サーバ側 Origin 検証**が定石。出典: [PortSwigger CSWSH](https://portswigger.net/web-security/websockets/cross-site-websocket-hijacking), [IncludeSecurity 2025](https://blog.includesecurity.com/2025/04/cross-site-websocket-hijacking-exploitation-in-2025/)。
    - xterm.js の demo/attach addon は本番不可 → 独自ブリッジで実装済。出典: [xterm.js security](https://xtermjs.org/docs/guides/security/)。
    - シークレットは OS ネイティブストア（keyring 経由）が推奨（A5 後続）。出典: [keyring](https://keyring.readthedocs.io/), [OWASP Secrets Mgmt](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)。
  - 検証: pytest 744 / ruff 0 / 新規 `tests/test_security_hardening.py`。
- 2026-06-01: **Iteration 2（B/LLM層 信頼性）完了** — B2, B3, B9, B10。
  - `core/llm/retry.py` を新設: `LLMError`（provider/status/retryable 付き正規化例外）, `classify_exception`, `call_with_retry`（タイムアウト＋指数バックオフ）。
  - 4 provider（anthropic/openai/groq/github_models/gemini）の `generate` を `call_with_retry` で包み、一時障害(429/5xx/timeout/conn)のみリトライ。
  - `/api/providers/{p}/models` の同期 SDK 呼び出しを `asyncio.to_thread` 化（イベントループ非ブロック, B10）。
  - 検証: pytest 751 / ruff 0 / 新規 `tests/test_llm_retry.py`（成功/リトライ/恒久エラー即時/上限/タイムアウト/分類）。
- 2026-06-01: **Iteration 3（H/DX・CI）完了** — H1, H6, H7。
  - `.github/workflows/ci.yml`: python(ruff+pytest) / frontend(build+vitest) / audit(pip-audit+npm audit, 非ブロック) の 3 ジョブ。
  - `Makefile`: install/test/lint/fix/build/fe-test/serve/verify/audit。`make verify` で CI 同等チェック一括。
  - 検証: CI YAML 妥当 / `make lint` 緑 / pytest 751 / ruff 0。
- 2026-06-01: **Iteration 4（F: テスト拡充）完了** — F4, F5, F12（本番コード変更なし）。
  - F5: Core 自己改善の承認→検証済み変更が実行タスクへそのまま渡る統合テスト（`tests/test_core_improve_approval.py`）。
  - F12: 回帰テスト（`tests/test_regressions.py`）— pre_task の asyncio 欠落・主要モジュール import スモーク・apply_changes 存在。
  - F4: ターミナル WS の resize/input 制御＋不正入力耐性（`tests/test_terminal.py` 追加）。
  - 検証: pytest 766 / ruff 0。
- 2026-06-01: **Iteration 5（B7: トークン使用量）完了**。
  - `core/llm/usage.py`（`UsageTracker`: provider/model 別 calls/prompt/completion/total 集計, スレッドセーフ, best-effort 記録）。
  - 全4provider の `generate` で `record_usage` を呼び、`GET/DELETE /api/usage` で公開・リセット。Settings に「トークン使用量」カード（provider 別 + 合計 + リセット）。
  - 検証: pytest 770 / vitest 80 / ruff 0 / build OK / 新規 `tests/test_llm_usage.py`。
- 2026-06-01: **Iteration 6（E/D/G/I 混成）完了** — E1, E9, E10, D8, G5, I2。
  - E1: vite `manualChunks`（xterm/react-vendor/charts 分割）＋ `chunkSizeWarningLimit` → 790KB 警告解消。
  - E9: `ImprovementExecutorAgent` の git 操作を `asyncio.to_thread` 化（イベントループ非ブロック）。
  - E10: ハッシュ付き `/assets/*` に `Cache-Control: immutable`（ミドルウェア）。
  - D8: 提案 ID は完全一致を優先し前方一致にフォールバック（誤マッチ低減）。
  - G5: `prefers-reduced-motion` 尊重（terminal-ring 等のアニメ抑制）。
  - I2: `docs/architecture.md` に Phase 2–5 の追加コンポーネントを反映。
  - 検証: pytest 771 / vitest 80 / ruff 0 / build（バンドル分割確認）。
  - I1 も同バッチで完了: `docs/api/rest_api.md` に health/usage/execution/modes/core-improve/terminal を追記。**完了 26/100。**
- 2026-06-01: **Iteration 7（D: 永続化堅牢性）完了** — D4, D6。
  - D4: 共有 `core/io_utils.atomic_write_text`（tmp+os.replace）を新設し、`core/state/manager.py`(7箇所) と `core/platform/state.py`(3箇所) の JSON 書込を原子化。server も同実装へ委譲（DRY）。クラッシュ時の torn write を防止。
  - D6: 本番コードに naive `datetime.utcnow()` が無いことを監査し、回帰防止テストを追加。
  - 検証: pytest 775 / ruff 0 / 新規 `tests/test_iter7_persistence.py`。**完了 28/100。**
- 2026-06-02: **Iteration 8（A7/J7 監査ログ + I3 README）完了**。
  - A7/J7: 実行イベントに `actor` を追加（既定 system、承認/却下/Core改善/組織作成・削除は user）。`ExecutionHistoryItemResponse`・正規化・`_record_execution_event`・`/api/execution-history` に反映。
  - I3: README に Web GUI / ターミナル / 実行モード / Core自己改善 / 使用量 を追記。
  - 検証: pytest 778 / ruff 0 / 新規 `tests/test_audit_log.py`。**完了 31/100。**
- 2026-06-02: **Iteration 9（G: アクセシビリティ）完了** — G1, G2, G8。
  - 検索を `components/GlobalSearch.tsx` に切り出し、combobox/listbox ロール・`aria-expanded`/`aria-activedescendant`/`aria-selected`(G2)、↑↓/Enter/Esc キーボード操作(G8)、フォーカス外クリック/Escで閉じる(G1) を実装。App.tsx を簡素化。
  - 検証: vitest 85（新規 `GlobalSearch.test.tsx`）/ build OK / pytest 778。**完了 34/100。**
- 2026-06-03: **Iteration 10（B4: ネイティブJSONモード）完了**。
  - 新設 `core/llm/json_mode.py`（`OPENAI_JSON_RESPONSE_FORMAT`/`GEMINI_JSON_MIME_TYPE`/`ensure_json_keyword`）。OpenAI の json_object モードは messages に "json" を要求するため、無ければ system 指示を補う。
  - `capabilities.py` の `supports_json_mode` を openai/groq/github_models/gemini で True 化（Anthropic はネイティブ response_format 無し→堅牢抽出継続、tool 強制は後続）。
  - 各 provider の `generate()` に `json_mode` を追加配線: OpenAI 互換は `response_format={"type":"json_object"}`、Gemini は `generation_config.response_mime_type="application/json"`。Anthropic は受理のみ（SDK へ漏らさない）。
  - `LLMProvider.generate_json`（base）は capabilities 連動でネイティブ要求し、**例外時は通常生成へフォールバック**（純粋な上積み）。最終 parse は `extract_json_object` のまま。同期 `LLMClient.generate_json` も `agenerate_json`→provider 経路へ統一（DRY）。
  - 研究知見: OpenAI/Groq/GitHub Models(Azure) は `response_format` の json_object をサポート（messages に "json" 必須）。Gemini は `response_mime_type`。Anthropic はネイティブ JSON モードが無く tool 強制/prefill が定石（リスク回避のため本イテレーションは堅牢抽出を維持）。
  - 検証: pytest **789 passed**（新規 `tests/test_llm_json_mode.py` 11件）/ vitest 85 / ruff 0。Settings の provider capabilities に JSON チップが反映。**完了 35/100。**
- 2026-06-03: **Iteration 11（A: API セキュリティ強化）完了** — A8, A2, A12。
  - A8: `_enforce_body_size_limit` ミドルウェア（Content-Length 判定→413、`REPOCORP_MAX_BODY_BYTES` 既定10MiB、本文読込前に拒否）。
  - A2: `_enforce_api_token` ミドルウェア（任意のローカルトークン認証。`REPOCORP_API_TOKEN` > `gui_settings.api_auth_token`、`X-RepoCorp-Token` か `Authorization: Bearer`、`hmac.compare_digest` 定数時間比較、**既定無効**で挙動不変、`/api/*` のみ・health/OPTIONS/非API除外）。WS は Origin 検証(A4)済みのため本回は対象外。
  - A12: H6（CI の pip-audit/npm audit ジョブ）+ H7（`make audit`）で既に実現済みのため統合チェック。
  - 検証: pytest **797 passed**（`tests/test_security_hardening.py` に8件追加）/ ruff 0。**完了 38/100。**
- 2026-06-03: **Iteration 12（B: LLM層強化）完了** — B1, B11, B12, F1。
  - B1: `LLMConfig.from_settings(settings)` を追加。client の `resolve_*`（env>settings）に委譲し選択プロバイダーのキーを `api_keys` へ。`from_env` は不変（単体テスト保護）。
  - B11: `get_configured_llm_provider` を `(provider, key, model)` キーでキャッシュ。設定変更は別キー＝自然に無効化。`reset_provider_cache()` を公開。
  - B12/F1: `tests/test_llm_provider_contract.py` — 5プロバイダの generate 契約（messages整形/tool中立化/tool_calls正規化/json_mode配線/usage記録）をフェイククライアントで固定。
  - 検証: pytest **816 passed**（+19: 契約11 + client4 + 既存）/ ruff 0。**完了 42/100。**
- 2026-06-03: **Iteration 13（J: 観測性）完了** — J2, J3, J4（+ D10/E5 監査）。
  - J2: `core/logging_config.py`（`JsonLogFormatter` 1行1JSON+相関ID、`SecretRedactingFilter`/`redact_secrets` を A6 から集約、`configure_logging` は `REPOCORP_LOG_FORMAT=json` 時のみ root を JSON 化＝既定 text 不変）。`web/server.py` は再エクスポートで後方互換。
  - J3: `request_id_var`（ContextVar）+ `_request_context` 最外周ミドルウェア（受信 `X-Request-ID` 踏襲/生成、応答へ返却、ログ自動付与）。
  - J4: `core/metrics/request_metrics.py`（requests/errors/avg_duration_ms/by_status をスレッドセーフ集計）+ `GET/DELETE /api/metrics`。LLM 呼数/トークンは B7 UsageTracker が担当。
  - 監査: D10（全 gather は worker で例外捕捉、multi_org は CancelledError を意図伝播）、E5（モデル一覧は B10 で to_thread 済み）。
  - 検証: pytest **826 passed**（新規 `tests/test_observability.py` 11件）/ ruff 0。rest_api.md 更新。**完了 47/100。**
- 2026-06-03: **Iteration 14（C: ターミナル堅牢性）完了** — C1, C5, C11（+ C3 監査）。
  - C1: `TerminalManager.gc()`（exited は `exited_ttl`=300s、購読者0の running は `idle_ttl`=3600s で kill+回収。`last_activity`/`touch()` を write/subscribe/resize/出力で更新。list()/create() で機会的GC。`REPOCORP_TERMINAL_IDLE_TTL`/`_EXITED_TTL` で上書き）。
  - C5: POSIX (`fcntl`/`termios`) import を try/except 化し `_PTY_AVAILABLE` 判定。`create()` で Windows 明示エラー、`resize()` もガード（ConPTY は将来）。
  - C11: `TerminalSession.rename()` + `TerminalManager.rename()` + `PATCH /api/terminal/sessions/{id}`（`TerminalRenameRequest`）。
  - C3: 監査—購読者0でも `_SCROLLBACK_CAP` 上限で蓄積し再 attach 時 replay（現状で正しい）。
  - 検証: pytest **833 passed**（`tests/test_terminal.py` に7件追加）/ ruff 0。**完了 51/100。**
- 2026-06-03: **Iteration 15（E: パフォーマンス）完了** — E3。
  - E3: `_load_all_proposals` を (org名, 件数, 最大mtime) シグネチャでキャッシュ。追加/削除は件数、上書きは mtime(ns 解像度) で検出し JSON 再パースを回避。唯一の呼出元 `_search_results` は読み取り専用のため安全。`_invalidate_proposals_cache()` を用意。
  - 検証: pytest **835 passed**（新規 `tests/test_proposals_cache.py` 2件）/ ruff 0。**完了 52/100。**
- 2026-06-03: **Iteration 16（F: テスト拡充）完了** — F6, F9, F11（本番コード変更なし）。
  - F6: `tests/test_policy_boundaries.py` — auto_reject>human_required>auto_approve>default の優先順位、優先度/カテゴリ/ファイルパターン/サイズ上限の境界、helpers、custom YAML roundtrip。
  - F9: `tests/test_json_extract_property.py` — 固定シード乱数で多様なネスト構造を生成し、コードフェンス/前後ノイズで包んでも復元する round-trip（300+ ケース）。
  - F11: `tests/test_update_hub.py` — UpdateHub の配信・接続管理・送信失敗接続の自動除去。
  - 検証: pytest **854 passed**（+19）/ ruff 0。**完了 55/100。**
- 2026-06-03: **Iteration 17（H/F: DX・CI）完了** — F7, H2, H8, H10。
  - F7: pytest-cov を dev extras に追加。CI pytest に `--cov --cov-fail-under=70`（現状 76%）、`make cov`、pyproject `[tool.coverage]`。
  - H2: `scripts/hooks/pre-commit` にステージ済み `.py` の `ruff check`（ruff 不在時はスキップ）。
  - H8: `CONTRIBUTING.md`（セットアップ/Makefile 一覧/規約/PRフロー）。H10: `CHANGELOG.md`（Keep a Changelog 準拠）。
  - 検証: pytest 854 passed（カバレッジ 76.06% ≥ 70 ゲート通過）/ ruff 0 / hook 構文 OK。**完了 59/100。**
- 2026-06-03: **Iteration 18（I: ドキュメント）完了** — I4, I5, I7, I8（本番コード変更なし）。
  - I5: `docs/security.md`（公開設定/認証/キー管理/入力保護/監査チェックリスト）。I7: `docs/troubleshooting.md`（LLM/CLI未検出/PTY/WS/401・413/ログ）。
  - I8: `docs/cli_tools.md`（外部CLI導入と検出）。I4: `docs/agents/README.md` に CoreImprovementAgent 行追加。
  - 検証: docs のみ（pytest/ruff 不変）。**完了 63/100。**（I6=OpenAPI examples は P3、tags は付与済みのため残置）
- 2026-06-03: **Iteration 19（F2: e2e 承認→PR）完了**。
  - `tests/test_e2e_approve_pr.py`: 実 PlatformStateManager 上で提案→承認エンドポイント→（FakeOrchestrator で git/LLM 差替）。成功時 pr_url/branch を返し done、実行失敗時 failed(500)、file_path 無しは 400。goal→proposal は `test_e2e.py`、検証済み変更受け渡しは `test_core_improve_approval.py` が補完し F2 の鎖を構成。
  - 検証: pytest **857 passed**（+3）/ ruff 0。**完了 64/100。**
- 2026-06-03: **Iteration 20（A/G: WS上限・セキュリティ文書・トースト）完了** — A9, A10, A11, G7。
  - A9: `UpdateHub` に同時接続上限（`REPOCORP_WS_MAX_CONNECTIONS` 既定50, 0=無制限）。超過は `close(1013)` で拒否。terminal はC1 GC。
  - A10: `.env.example` に運用系 env（HOST/ALLOWED_HOSTS/CORS/API_TOKEN/MAX_BODY_BYTES/WS_MAX/LOG_FORMAT/TERMINAL TTL）を追記。`docs/security.md` に整合表。
  - A11: `docs/security.md` に GitHub PAT 最小権限ガイド（Fine-grained: Contents/PR の RW のみ）。
  - G7: `sonner` がアクセシブル aria-live を内蔵（監査で確認）。
  - 検証: pytest **859 passed**（UpdateHub +2）/ ruff 0。**完了 68/100。**
- 2026-06-03: **Iteration 21（F10: CLIスモーク）完了**。
  - `tests/test_cli_smoke.py`: `build_parser()` の全サブコマンド `--help` が SystemExit 0、`HANDLERS` 全 callable、代表コマンド存在を検証（副作用なし）。
  - 検証: pytest **880 passed**（+21）/ ruff 0。**完了 69/100。**
- 2026-06-03: **Iteration 22（J5: ログローテーション）完了**。
  - `configure_logging` を拡張: `REPOCORP_LOG_FILE` 指定時に `RotatingFileHandler`（既定 5MiB×3 世代、`REPOCORP_LOG_MAX_BYTES`/`REPOCORP_LOG_BACKUPS`）。text/json 両対応。
  - 検証: pytest **881 passed**（+1）/ ruff 0。**完了 70/100。**
- 2026-06-03: **Iteration 23（LLM残り）着手 + 引き継ぎ整備**。
  - B8: `core/llm/trim.py`（`trim_messages`/`estimate_tokens`）＋ `tests/test_llm_trim.py`。**完了**。
  - B6（reasoning_effort 配線）/ B5（streaming+tools 明示）は **未着手**（次の再開点）。
  - **デバイス移行のための引き継ぎ固定**: `docs/HANDOFF.md`（単一の入口）、`docs/development/plan.md`（計画書コピー）、`docs/development/state-snapshot.md`（旧メモリ内容）を作成。`AGENTS.md` から HANDOFF へ導線。`.gitignore` に `.claude/` `scratch_dot_repocorp/` 追加。全作業をコミット＆push。
  - 検証: pytest **885 passed**（B8 +4）/ ruff 0。**完了 71/100。**
