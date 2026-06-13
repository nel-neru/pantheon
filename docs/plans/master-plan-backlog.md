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

- 🟩 P2.1 トレンド→新規事業提案（コア✅ `core/trends/business_proposal.trend_to_business_proposal` +
  `is_business_worthy`＋テスト。承認ゲート→org 生成の配線は WIRE-B）
- 🟩 P2.2 会社プラグイン manifest（コア✅ `config/company_plugins.yaml` + `core/orchestration/company_plugins`
  ローダ＋テスト。**install→完全な org 起動フローは P2.2b＝次の本丸**、GUI は WIRE-B）
- 🟩 P2.3 Self-Evolution / Playbook（コア✅ `core/intelligence/playbook` Entry/Store/採点/top＋テスト。
  生成・参照経路への配線は後続）
- 🟩 P2.4 複数org連携最適化（コア✅ `core/hierarchy/handoff_optimizer.recommend_handoffs`＋テスト。
  HQ提案/handoff 自動起票への配線は WIRE-A）
- ⬜ P2.5 **Trend Monitor 本格運用の硬化**: trend daemon の収集→採点→変換の網羅と重複排除を強化 + テスト。
- ✅ **P2.2b 会社プラグイン install フロー（本丸・組織のプラグイン化）**: `install_company_plugin`
  で manifest→完全な Organization 起動（事業部名から型/スキル推定で Division/Team/Agent 生成・
  Humanタスク自動起票・初期KPI返却）+ `GET /api/company-plugin-manifests` + `POST /api/company-plugins/{id}/install`
  + マーケットプレイス「この会社を作成」ボタン。backend 3 + API 1 + frontend 2 テスト。
- ⬜ **WIRE-A 収益コアの配線**: portfolio/handoff_optimizer を HQ 提案・GUI（ポートフォリオ/連携推奨）へ接続。
- ⬜ **WIRE-B 自己拡大の配線**: business_proposal→承認ゲート、company manifest→マーケットGUI 表示。✅ 一部完了（manifest→install→マーケットGUI は P2.2b で済）。

## §5 Workspace モデル（git からの脱却）

- ✅ **WS-0 Workspace モデル v0（repo-optional org）**: `Organization.management_mode`（repo|workspace）と
  `workspace_path` を導入。`data_location`/`is_managed` で repo 無しでも妥当に管理。
  `get_org_state_manager` は data_location 配下を使用。**会社プラグイン install は workspace モード（git 不要）で
  org を起動**。`/api/organizations` に mode/workspace_path を露出。既存 repo 紐付き org（Meta 等）は非破壊。
  → 収益モデル会社は git リポジトリ不要のアプリ内データとして管理される（あなたの質問への回答を実体化）。
- ⬜ **WS-1 既存 org の移行ツール**: 既存の external repo（affiliate/note/sns）の中身を workspace へ取り込み、
  git 依存を外す移行コマンド（**削除ではなく移行**）。
- ⬜ **WS-2 SQLite ストア（§5.2）**: JSON 正準 → SQLite（workspaces/organizations/... テーブル）へ段階移行。

## Phase 3（アプリ化・UX）

- ⬜ P3.1 **PyInstaller ビルド硬化 + smoke**: spec の同梱漏れ点検、ビルド/起動 smoke の自動チェック。
  受け入れ: ビルド検証スクリプト or テスト + ドキュメント。（実配布署名は human-gate）
- ⬜ P3.2 **初回ウィザード**: GUI 初回起動で「副業ポートフォリオ自動構築」へ誘導（org/事業部プラグイン選択）。
  受け入れ: ウィザード画面 + 既存 API 連携 + テスト。
- ⬜ P3.3 **通知センター / Always-On**: WS イベントを集約する通知 UI + 設定（時間帯/頻度）。
  受け入れ: 通知ストア + GUI + 設定 + テスト。
- 🔒 P3.4 クラウド版（オプション）: ホスティング/配布は **human-gate**（インフラ・課金）。設計メモのみ AI 可。

## Phase 4（究極形態）

- ⬜ P4.1 **完全自律経営デモ**: 「月XX円目標で最適運用して」を `abstract_goal_pipeline` に接続し、
  目標→Meta-Overseer がポートフォリオ施策を立案・実行（人間ゲートは承認キュー）。受け入れ: 目標入力→計画→
  提案群生成のデモ経路 + テスト。
- ⬜ P4.2 **新事業ジャンル自動発見**: trends から未開拓ジャンルを発見し新会社提案（P2.1 の発展）。
- 🔒 P4.3 コミュニティ機能 / P4.4 税務・会計補助: 外部サービス/法務が絡むため **human-gate**（設計のみ AI 可）。

## 横断・検証

- ⬜ X.1 **完全性クリティック**: N サイクルごとに「計画 §1〜§14 vs 現実」を突き合わせ、抜けを本 backlog へ追記
  （loop-until-dry）。
- ⬜ X.2 **§12 成功指標の検証 run**: クリーンな環境で §12 を実際に pass させる E2E 的チェックを整備。
- 継続: 各サイクルでテストゲート + 敵対的レビュー + 計画書/該当 memory の更新（自己更新ルール）。

---

**収束条件（＝完璧に実現）**: 上記 ⬜ がすべて ✅、🔒 は実装済み+承認キュー積み or 人間実施済み、
X.1 が dry、X.2 が pass。そのとき計画書の全節が出荷済み現実に対応する。
