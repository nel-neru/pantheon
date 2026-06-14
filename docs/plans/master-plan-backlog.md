# Master Plan 実行 backlog（v1.1 を完璧に実現するための出荷サイクル一覧）

このファイルは `Pantheon_Master_Development_Plan_v1.0.md`（v1.1）の §3〜§8・§12 を
**1サイクル=1出荷**の小さな実装単位へ分解した「done の唯一の定義」。AIエージェントが
上から順に実装・テスト・マージしていく。完了したら `status` を更新し、計画書本体にも反映する。

**凡例**: status = ⬜ 未着手 / 🔻 着手中 / ✅ 完了（main 統合済み）
**human-gate**: 実アカウント/資格情報/入金/実投稿の最終送信/クラウド配布/main マージ など人間専用。
これらは「手前まで実装し承認キューへ積む」= AI は実装、実行は人間。

---

## Phase 0（基盤）— 完了

- ✅ P0.A 計画 v1.1 再ベースライン + Fable 配線
- ✅ P0.B 収益 手動入力GUI + 月次レポート
- ✅ P0.C publish-live（note/X 既存 + WordPress assisted）+ 全アダプタ テスト
- ✅ P0.D 2階層プラグイン（事業部プラグイン）+ GUIマーケットプレイス

## Phase 1（収益ループ完成）

- ✅ P1.1 収益0 org に具体的な収益化事業部の ADD_DIVISION 提案（HQ）
- ✅ P1.2 収益インテリジェンス（`revenue_intelligence.analyze_revenue` + `/api/metrics/revenue/intelligence`
  + RevenuePage 収益トレンドカード。MoM/トレンド/翌月予測）
- ✅ P1.3 収益駆動の提案キュー（`revenue_impact_rank` + `/api/inbox` が収益インパクト→優先度で
  並べ替え・付与、InboxPage に「収益」バッジ）
- ✅ P1.4 Human Member タスク管理（`core/humans/human_tasks` HumanTask/Store/enqueue +
  `/api/human-tasks` CRUD + HumanTasksPage `/human-tasks` + publishing handed_off→公開確認タスク自動起票）
- 🟩 P1.5 ポートフォリオ資源配分（コア✅ `core/metrics/portfolio.recommend_allocation`：ROI で
  invest/monetize/optimize/grow_audience 振り分け＋テスト。HQ提案/GUI 配線は後続 WIRE-A）

## Phase 2（自己拡大）

> 並列ワークフロー（wf_4acbfaf7）で P2.1〜P2.4 + P1.5 の **コア（純粋ロジック/ストア+テスト）を出荷済み**。
> API/HQ/daemon/GUI への**配線は後続の直列サイクル WIRE-A/B** で行う（既存ファイル改修を伴うため）。

- ✅ P2.1 トレンド→新規事業提案（コア✅ `core/trends/business_proposal.trend_to_business_proposal` +
  `is_business_worthy`。**承認ゲート配線は WIRE-B で完了**）
- 🟩 P2.2 会社プラグイン manifest（コア✅ `config/company_plugins.yaml` + `core/orchestration/company_plugins`
  ローダ＋テスト。**install→完全な org 起動フローは P2.2b＝次の本丸**、GUI は WIRE-B）
- 🟩 P2.3 Self-Evolution / Playbook（コア✅ `core/intelligence/playbook` Entry/Store/採点/top＋テスト。
  生成・参照経路への配線は後続）
- 🟩 P2.4 複数org連携最適化（コア✅ `core/hierarchy/handoff_optimizer.recommend_handoffs`＋テスト。
  HQ提案/handoff 自動起票への配線は WIRE-A）
- ✅ P2.5 Trend 硬化（コア✅ `core/trends/trend_dedup.py` dedupe_trends/rank_trends。
  **配線完了**: `runner.collect_and_store` が採点後・保存前に `_dedupe_items`（trend_dedup）で
  url 正規化/title の near-dup を最高スコア1件へ畳み込む＝store の hash 完全一致 dedup を補完
  （summary.deduped 追加）。runner dedup テスト追加）
- ✅ **P2.2b 会社プラグイン install フロー（本丸・組織のプラグイン化）**: `install_company_plugin`
  で manifest→完全な Organization 起動（事業部名から型/スキル推定で Division/Team/Agent 生成・
  Humanタスク自動起票・初期KPI返却）+ `GET /api/company-plugin-manifests` + `POST /api/company-plugins/{id}/install`
  + マーケットプレイス「この会社を作成」ボタン。backend 3 + API 1 + frontend 2 テスト。
- ✅ **WIRE-A 収益コアの配線**: `build_portfolio_proposals` を `GET /api/hq/portfolio`（OutcomeStore から
  org_stats を集計→提案）に配線し、RevenuePage に「ポートフォリオ提案（HQ）」カードを表示。backend+frontend テスト。
- ✅ **WIRE-B 自己拡大の配線**: `core/trends/business_pipeline.scan_business_proposals`
  （TrendStore→`trend_to_business_proposal`→`new_business` ImprovementProposal 承認ゲート、冪等・score 0..10↔0..1 橋渡し）
  ＋ `POST/GET /api/hq/business-proposals[/scan]` ＋ trend daemon サイクルに組込み（summary.business_proposals）
  ＋ CLI `pantheon trends business-scan` ＋ MarketplacePage「新規会社候補（トレンド発）」カード。
  backend 7 + API 1 + frontend 2 テスト。company manifest→マーケットGUI は P2.2b で済。

## §6 プラグインテンプレ化（§6.2 / §7.4）

- ✅ **PT-1 プラグインテンプレ框組み**: `core/orchestration/plugin_templates.py`（§6.2 CATEGORY_PRESETS
  audience/monetization/full_funnel/operations/content + `scaffold_division_plugin`/`scaffold_company_plugin`）＋13テスト。
- ✅ **PT-2 カタログ拡張**: ①`load_division_plugins` を**テンプレ形対応**に拡張（department を書かず
  id/label/category だけのエントリを `scaffold_division_plugin` で自動展開＝「テンプレ化」）。
  ②`config/division_plugins.yaml` を §7.4 準拠で **21 事業部**へ拡充（audience/monetization/content/operations 各5
  ＋full_funnel：YouTube/TikTok/SEO/Newsletter/デジプロ/講座/電子書籍/サブスク/広告/スケジューラ/競合監視/AB/CRM 等）。
  ③scaffold→YAML CLI `pantheon plugin scaffold-division --id --label --category [--write]`（--write でカタログ追記・冪等）。
  loader 展開3 + scaffold CLI 1 テスト。

## §5 Workspace モデル（git からの脱却）

- ✅ **WS-0 Workspace モデル v0（repo-optional org）**: `Organization.management_mode`（repo|workspace）と
  `workspace_path` を導入。`data_location`/`is_managed` で repo 無しでも妥当に管理。
  `get_org_state_manager` は data_location 配下を使用。**会社プラグイン install は workspace モード（git 不要）で
  org を起動**。`/api/organizations` に mode/workspace_path を露出。既存 repo 紐付き org（Meta 等）は非破壊。
  → 収益モデル会社は git リポジトリ不要のアプリ内データとして管理される（あなたの質問への回答を実体化）。
- ✅ **WS-1 既存 org の移行ツール**: コア✅ `core/orchestration/org_migration.py`
  （plan_repo_to_workspace_migration / migrate_repo_org_to_workspace、**git なし・削除なしのモデル変換**）。
  **配線完了**: CLI `pantheon org migrate-to-workspace --name [--dry-run]`、API `GET .../migration-plan`・
  `POST .../migrate-to-workspace`（workspace_root は設定→platform_home/workspaces フォールバック）、
  org 詳細 API に management_mode/workspace_path/data_location 露出、OrgsPage 詳細に「workspace へ移行」ボタン。
  backend 2 + CLI 2 + API 2 + frontend 1 テスト。実データ移動は意図的に範囲外（来歴として repo パス保持）。
- ⬜ **WS-2 SQLite ストア（§5.2）**: JSON 正準 → SQLite（workspaces/organizations/... テーブル）へ段階移行。

## Phase 3（アプリ化・UX）

- ✅ P3.1 **PyInstaller ビルド硬化 + smoke**: `scripts/check_build_spec.py`（spec の datas 同梱漏れ・
  重要リソース実体・動的 hiddenimports・resource_path 解決を静的検査、致命時 exit 1）+ `tests/test_build_spec.py`（3）。
  最頻事故「リポジトリに足したリソースを datas に入れ忘れ→exe で欠落」を CI で捕捉。（実配布署名は human-gate）
- ✅ P3.2 **初回ウィザード**: `OnboardingPage` `/onboarding`（3 ステップ: 説明→manifest 選択で会社を
  1クリック起動→完了。既存 `/api/company-plugin-manifests`・`/install` を利用＝副業ポートフォリオ自動構築）
  + ナビ追加 + OrgsPage 初回 welcome に CTA。frontend 2 テスト。
- ✅ P3.3 **通知センター / Always-On**: `core/notifications/NotificationCenter`（既存 append-only
  `notifications.jsonl` を正準ログに、別ファイルの既読 id 集合で既読/未読を非破壊管理 + 設定
  min_level/静音時間帯 + `should_push` ゲート）+ API（GET/POST/read/read-all/settings）+
  NotificationsPage `/notifications`（一覧・既読・一括既読・設定）+ ナビ。backend 11 + API 2 + frontend 3 テスト。
- 🔒 P3.4 クラウド版（オプション）: ホスティング/配布は **human-gate**（インフラ・課金）。設計メモのみ AI 可。

## Phase 4（究極形態）

- ✅ P4.1 **完全自律経営デモ**: `core/hierarchy/portfolio_pipeline.py`（決定論・LLM 非依存）
  ＝目標額→`compute_revenue_gap`（OutcomeStore 実績 vs 目標/予測）→`build_target_plan`
  （`build_portfolio_proposals` ＋ ギャップ符号で収益打ち手を強調＋リーチ不足時に new_business エスカレーション）
  →`scan_portfolio_proposals`（承認ゲート ImprovementProposal を冪等起票。dedupe_key は収益値非依存）。
  CLI `pantheon goal plan <target> [--preview]`、API `POST /api/hq/portfolio/scan`・`GET /api/hq/portfolio/plan`、
  RevenuePage「自律経営プラン（月収益目標）」カード。backend 8 + API 1 + frontend 1 テスト。
- ✅ P4.2 **新事業ジャンル自動発見**: `core/trends/untapped_genre.py`（決定論・LLM 非依存・集合演算）
  ＝store ジャンル − 既存 org の industry_genre（slug 正規化・既定 general 除外）→ 未開拓高スコアジャンルを
  `trend_to_business_proposal` 再利用で new_business 提案として**ジャンル単位冪等**で起票。CLI `pantheon trends untapped [--preview]`、
  API `POST /api/hq/untapped-genres/scan`・`GET /api/hq/untapped-genres`、trend daemon サイクルに組込（summary.untapped_genres）、
  MarketplacePage「未開拓ジャンルをスキャン」ボタン。backend 7 + API 1 + frontend 1 テスト。
- 🔒 P4.3 コミュニティ機能 / P4.4 税務・会計補助: 外部サービス/法務が絡むため **human-gate**（設計のみ AI 可）。

## 横断・検証

- ✅ X.1 **完全性クリティック（第1巡 実施済み）**: 敵対的 completeness-critic ワークフロー（30 agent・
  4監査次元 §1/§5・§6/§7・§3/§4/§8・§9〜§12 → 各ギャップを refute 検証）で計画 §1〜§14 vs 現実を突合。
  **17 件の真ギャップを確定**し下記「Phase 5」へ追記（X.1 は dry ではない＝forward-scoped 工程が残存と判明）。
  以後 N サイクルごとに再実行する運用。
- ✅ X.2 **§12 成功指標の検証 run**: `tests/test_success_metrics_e2e.py`（クリーン tmp_path で Phase 0 §12 を
  端から端まで駆動し pass・決定論・claude CLI 非依存）。会社プラグイン起動/手動収益記録→月次レポート/
  Meta-Overseer 提案→計画→基本実行/CLI 非依存性 の4 E2E。計画書 §12 の現況注記を実態へ更新。
- ✅ **HYGIENE-1 リポジトリ衛生監査（2026-06-14）**: 多角監査ワークフロー（21 agent・docs/dead-code/garbage/packaging/plugin）
  で 13 確定。修正: packaging spec に `scripts/`（watchdog .ps1）同梱漏れ＋check_build_spec へ追加（HIGH）／
  namespace package 化していた core/{metrics,models,orchestration,quality,state} に `__init__.py`（collect_submodules 0→検出）／
  dead code 削除（web/server.py `FALLBACK_MODELS`・`_PROVIDER_KEY_MAPPING`・`_get_provider_api_key`／main.py の同等
  vestigial 群）／tmp/ のレビュー成果物4件を git 管理から除外＋`tmp/` を .gitignore／docs 整合（AGENTS.md/daemon-status.md に
  revenue daemon 追記・README の既知失敗を 6→2 に修正）。回帰なし（1334 passed）。
- 継続: 各サイクルでテストゲート + 敵対的レビュー + 計画書/該当 memory の更新（自己更新ルール）。

## Phase 5（X.1 が surfaced した「真の自律化」残工程）

> X.1 第1巡（2026-06-14）で確定。Phase 0〜4 で**部品（純粋コア）と承認ゲート経路**は揃ったが、
> 「24/7 で常駐し、寝てる間に勝手に回る」最終形には**配線・常駐化・自動収集・実投稿**が残る。
> 多くは Phase 1〜2 horizon の forward-scoped。実投稿/実配布は **human-gate**。

- ✅ **AUTO-1 常駐エンジンの daemon 化（§1.2/§1.3/§8）**: Meta-Overseer を 24/7 常駐化。
  (a) revenue daemon（`RevenueScheduler`＝`analyze_revenue` 常時＋target>0 で `scan_portfolio_proposals`→承認キュー、
  `daemon_registry` 登録・runner・frozen flag・heartbeat。**並列 /evolve セッションが出荷**）、
  (b) **HQ 経営会議 cadence ＋可視化（本サイクルで追加）**: `RevenueScheduler.run_cycle` を拡張し target>0 で
  `HQInterventionProposer.propose_all`（決定論・冪等）も実行＋`NotificationCenter` へサイクル要約通知
  （§12「寝てる間に改善が進んでた」）。idle 安全契約（target<=0 は無起票・無通知）を維持。revenue 7 テスト。
- 🔒 **PUB-AUTO Phase2 完全自動投稿（§1.1 原則3・HIGH）**: 全アダプタが auto モード未実装で
  `process_due_publish_jobs` が無人投稿できない＝「寝てる間に出力」未達。実送信は **human-gate**だが、
  X(REST)/WordPress(REST) の auto 経路の実装手前まで AI 可。
- ✅ **WIRE-MEM Self-Evolution + Layered Memory（§8 P2/§9・P2.3 配線）**: `core/intelligence/memory_bank.MemoryBank`
  （PlaybookStore を統一する Layered Memory ファサード・決定論/冪等/LLM 非依存）を新設し dead store を解消。
  **recall 配線**: `BaseAgent.apply_skills_to_prompt` が有用度上位 Playbook をプロンプト末尾へ注入（空なら無変更）。
  **capture 配線**: `BaseAgent._save_execution_knowledge` が成功実行を Playbook へ冪等蓄積（title 正規化で重複増殖防止）。
  API `GET/POST /api/memory/playbook`。memory 10 + API 1 テスト。
  （補足: `AgentKnowledgeAccumulator` との完全統合は将来課題＝今回は統一エントリ点 MemoryBank と Playbook 経路を配線）。
- 🟩 **REV-COLLECT 外部API収益自動収集（§8 P1/§9）= 枠組み出荷**: `core/metrics/revenue_collectors/`
  （`RevenueCollector` 基底＋note/X/ASP アダプタ＋`run_revenue_collection` オーケストレータ）。接続済みは
  `OutcomeStore.record(dedupe_on_source)` で冪等記録、未接続は「接続してください」人間タスクを一度だけ起票。
  CLI `pantheon revenue collect` ＋ API `POST /api/revenue/collect`。collectors 4 + API 1 テスト。
  **実 API 認証・取得は human-gate**（`~/.pantheon/revenue_credentials/<source>.json` を接続後に各アダプタの
  `fetch` を実装＝Phase 2）。それまで手動入力/CSV が fallback。残: 実 API 実装・daemon 巡回への組込。
- 🟩 **TPL-SEED テンプレ標準シード（§6.1/§6.2）**: 会社プラグイン install を実体化。
  ①`Organization.initial_kpis` フィールド追加＋install で永続化＋org 詳細/一覧 API 露出＋OrgsPage「初期KPI」表示
  （= KPI ダッシュボードの素地・§6.1）。②`plugin_templates.self_improvement_seed_division`（週次レビュー Agent を持つ
  org_evolution 事業部）を全社に標準搭載（§6.2）。**WIRE-MEM（成功施策→Playbook 蓄積）＋AUTO-1（HQ エスカレーション）と噛み合い、
  立ち上げ初日から自己改善ループを持つ**。backend（company/templates）＋frontend テスト。
  残: 群統合（新会社を portfolio_advisor へ自動リンク）・専用 HQ Agent の明示生成は後続。
- ⬜ **WS-2 SQLite ストア（§5.2・再掲）**: workspaces/organizations/.../revenue_records/execution_logs/app_settings
  を §5.2 設計で実装し JSON 正準→SQLite へ段階移行（**保存層移行でリスク高・着手前に要確認**）。
- 🟩 **SET-EXPOSE 設定露出（§4 P2-5/P3-12）**: トークンクォータ上限と通知設定を統一アプリ設定へ露出。
  `quota_governor.save_rules`（token_quota.yaml writer・部分更新/soft≤hard 保証/不正値無視）＋ `/api/settings`
  GET/PUT に `token_quota`・`notification_settings` を追加（通知は NotificationCenter へ委譲）＋ SettingsPage
  「リソース制御・通知」カード（クォータ窓/ソフト・ハード上限/通知最小レベル/静音時間帯）。
  quota writer 4 + 設定 API 1 + frontend 1 テスト。残: 承認閾値/提案積極性は現状 policy_rules JSON で編集可
  （構造化コントロール化は将来）。
- ✅ **PT-3 §7.4 カタログ拡幅**: 事業部カタログ 21→**25**。content に `note_paid_article`（有料記事**作成**特化・
  販売側 note_monetization と別＝§7.4 #2）。full_funnel に差別化 department を持つ残3バリアント
  （`funnel_short_video_digital` 短尺→デジタル商品 / `funnel_content_multiplatform` コンテンツ→複数PF同時収益化 /
  `funnel_ai_note_affiliate` AI生成→note+アフィ複合＝§7.4 #4）。マーケットプレイスは自動列挙。division-plugins 2 テスト追加。

---

**収束条件（＝完璧に実現）**: Phase 0〜5 の ⬜ がすべて ✅、🔒 は実装済み+承認キュー積み or 人間実施済み、
X.1 が dry（再実行で新規ギャップ 0）、X.2 が pass。そのとき計画書の全節が出荷済み現実に対応する。
**現況**: Phase 0〜4＋§5 WS-0/1＋§6 PT-1/2 完了。Phase 5（真の常駐自律化）が X.1 で surfaced され残存。
