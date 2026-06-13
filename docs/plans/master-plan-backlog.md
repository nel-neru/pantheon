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
- ⬜ P1.3 **収益駆動の提案キュー**: インボックス/ProposalsPage で収益インパクト順に並べ、
  HQ 収益提案（P1.1）を優先表示。受け入れ: 提案に revenue_impact ヒントを付与し並び替え + テスト。
- ⬜ P1.4 **Human Member タスク管理**: Human Specialist をモデル化し、人間専用タスクを
  `~/.pantheon` のキューへ積む + GUI で一覧/完了報告。受け入れ: HumanTask モデル + store +
  API + 最小 GUI + テスト。publishing handed_off / 提案承認の既存出口と接続。
- ⬜ P1.5 **ポートフォリオ資源配分の提案**: Meta-Overseer が org 横断で収益/リーチを見て
  「どの org に投資/縮小」を提案。受け入れ: 横断サマリ + 配分提案生成 + テスト。

## Phase 2（自己拡大）

- ⬜ P2.1 **トレンド→新規事業（会社）提案**: trend を新収益モデル会社の提案へ変換し承認ゲート化
  （承認で `org create` 相当を実行）。受け入れ: trend→business-proposal 変換 + 承認→org 生成 + テスト。
- ⬜ P2.2 **会社プラグイン manifest 化 + マーケット強化**: `config/departments/*` を会社プラグイン
  manifest（初期KPI/週次レビュー種/Humanタスク）に格上げ、推奨組合せ表示。受け入れ: manifest スキーマ +
  ローダ + GUI 表示 + テスト。
- ⬜ P2.3 **Self-Evolution / Playbook**: `agent_knowledge` の上に統一 Playbook 抽象（蓄積・採点・適用）。
  受け入れ: Playbook モデル/ストア + 生成・参照経路 + テスト。
- ⬜ P2.4 **複数org連携最適化**: handoff の自動推奨（集客 org→収益化 org）。受け入れ: 連携推奨生成 + テスト。
- ⬜ P2.5 **Trend Monitor 本格運用の硬化**: trend daemon の収集→採点→変換の網羅と重複排除を強化 + テスト。

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
