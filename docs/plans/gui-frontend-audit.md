# web/frontend GUI 監査・改善 状態リスト（マッピング駆動）

- 生成: 2026-06-14 / 出典: workflow gui-frontend-audit (run w3bnm8rn9, 49 agents)
- 対象GUI: **web/frontend (legacy / 既定UI)**
- 進捗: **25/42 完了**（done/verified）。状態凡例: `[x]`=完了/検証済 `[~]`=着手中 `[ ]`=未着手 `[-]`=見送り
- **このファイルが改善の正本**。各変更を着手→完了→検証で状態遷移させながら実装する。
- 機械可読の進捗は `gui-frontend-audit-state.json`（本ファイルと対・JSONが正本）。
- 由来: 全21画面の要素インベントリ→6軸（必要性/妥当性/機能性/利便性/拡張性/保守性）厳格評価→横断監査→重複排除した優先度付き計画（Workflow `gui-frontend-audit`）。

## 総評

現状の web/frontend は「堆積型」の典型で、刷新ではなく作り直しに近い再設計が要る。最も深刻なのは安全境界の崩壊で、外部SNS実投稿(publish run)・ジョブ/タスク/接続/セッションの破壊操作・一括承認/却下が軒並み無確認ワンクリックで走り、「公開=人手ゲート」という製品思想とUIが正面から矛盾している(P0)。情報設計も破綻しており、20項目フラットのサイドバーは認知限界を大きく超え、承認インボックス/あなたのタスク/通知センターという3つの「要対応」導線が概念的に重複、収益化パイプライン(スタジオ/予約/引き渡し/収益)は分断、Studioは保存もできない孤島になっている。横断的にはErrorBoundary皆無・WS多重接続・401導線欠如・日付/数値/status色/ボタン変種/page-header/タブの実装分裂・inline style規約違反・未定義CSS変数が積み上がり、テストはapi全モックで「見せかけUI」と契約ズレを構造的に検出できない。死蔵データ(last_detail/payload詳細/priority/created_at等)と死んだ導線(承認/詳細へ飛べない読み取り専用リスト)が全画面に散在する。妥協せず、削除・統合・共通化・確認ゲート整備・IA再設計を一気に行うべき段階にある。

## ナビ/IA 再設計方針

navItems をフラット20項目から NavGroup[]（type NavGroup = { label: string; items: NavItem[] }）へ再設計し、レンダリングで既存 .sidebar-section-label をグループ毎に出力する（CSSは新規不要、折りたたみ時はラベルを display:none 済み→代わりに .sidebar-group-divider を出す分岐を数行追加）。推奨5グループ・グループ内は頻度/ワークフロー順:

(1)『はじめに』= ダッシュボード(最上段に昇格・『ホーム/ダッシュボード』へ改名)→ 初回セットアップ(2番目に降格、可能なら platform status で完了後は非表示)。ロゴ+ブランドは <NavLink to=\"/dashboard\"> で包みホーム導線化。

(2)『要対応(Action Center)』= 承認インボックス(各項目に未処理件数バッジ)。/human-tasks は /api/inbox の human_task kind に集約、/notifications はナビ削除しBellポップオーバー(未読プレビュー+『すべて見る』)に一本化。3重の心的モデルを1つへ(C006/C007)。

(3)『組織と提案』= 組織 → 改善提案(/inbox?kind=proposal の詳細 or 組織詳細パネルへ降格) → エージェント。実行ドメイン(セッション/ボード)もここに寄せるか(5)へ。

(4)『収益化(Monetization)』= スタジオ → コンテンツ予約 → 引き渡し → 収益 をワークフロー順に連続配置。Studio は下書きビューアとして Content/Inbox の publish から開ける接続を前提(C020)。

(5)『システム/高度な設定』(折りたたみ可)= 連携設定(旧プラットフォーム接続・ダッシュボードの『プラットフォーム』とラベル衝突するため改名) → マーケットプレイス → Atlas(リポジトリ地図、開発者向け) → セッション → 作業ボード → データ管理 → 設定 → ヘルプ。

合わせて: ラベル整理(『プラットフォーム』→『ダッシュボード』、『Atlas』→『Atlas(リポジトリ地図)』、『プラットフォーム接続』→『連携設定』)、折りたたみ時の全項目 title/Tooltip 付与(C005)、アイコン重複(Boxes/Blocks)の見直し、AGENTS.md の新Webページ手順に『追加時は適切なグループへ、末尾フラット追加禁止』を明記して堆積を防止。これによりトップ可視領域が高頻度の(1)〜(4)に絞られ、ナビ項目は20→17程度に縮小する。

## 変更チェックリスト（42件・ウェーブ順）

### W0 — 共通基盤（部品/lib/CSS）  (3/8)

- [~] **C002** `[P0]` `<add>` risk=medium — 全破壊/不可逆操作に統一確認ダイアログ(ConfirmDialog)を導入 _(状態: in_progress)_
  - 対象: `web/frontend/src/components/ConfirmDialog.tsx`, `web/frontend/src/pages/InboxPage.tsx`, `web/frontend/src/pages/HumanTasksPage.tsx`, `web/frontend/src/pages/ConnectionsPage.tsx`, `web/frontend/src/pages/ContentSchedulePage.tsx`, `web/frontend/src/pages/BoardPage.tsx`, `web/frontend/src/pages/ProposalsPage.tsx`, `web/frontend/src/pages/OrgsPage.tsx`
  - 軸: necessity, validity, maintainability, convenience
  - 根拠: necessity/validity/maintainability: publish取消(DELETE)・公開を確認・content-job削除・task キャンセル・接続切断・アイコンリセット・workspace片道移行・一括承認/却下が無確認で即実行され、確認手段もwindow.confirm/独自Modal/無確認と分裂。OrgsPageのtype-to-confirm Modalを Radix Dialog ベースの共通 ConfirmDialog(単純確認/名前一致確認の2モード)へ抽出し全破壊操作で再利用。Escape/フォーカストラップ/初期フォーカス/aria-modalも一括担保。
  - テスト影響: 破壊操作テストが確認経由に変わり全面更新。ConfirmDialogの単体テスト(Esc/フォーカストラップ/名前一致)を新規追加。
- [x] **C008** `[P1]` `<add>` risk=low — アプリ全体をErrorBoundaryで包みスキーマdrift耐性を確保 _(状態: done)_
  - 対象: `web/frontend/src/main.tsx`, `web/frontend/src/App.tsx`, `web/frontend/src/components/ErrorBoundary.tsx`, `web/frontend/src/pages/MarketplacePage.tsx`, `web/frontend/src/pages/RevenuePage.tsx`, `web/frontend/src/pages/HandoffsPage.tsx`
  - 軸: validity, maintainability
  - 根拠: validity/maintainability: ErrorBoundaryが皆無で、API応答の形ズレ(null/欠落/型違い)で.map/.join/JSON.stringifyが例外→全画面ホワイトアウト。全テストがapi全モックで理想形のみ返すためdriftは検出不能。ルートErrorBoundary(フォールバック+再読み込み)を導入し、危険な配列/オブジェクトアクセスに既定値ガード(?? []/Array.isArray)を入れ、想定外形のレンダー耐性テストを追加。
  - テスト影響: ErrorBoundaryの単体テストと、空/null/型違いレスポンスでのページ非クラッシュテストを新規追加。
- [x] **C016** `[P1]` `<fix>` risk=low — 未定義CSS変数の是正とdanger/primaryトークン統一 _(状態: done)_
  - 対象: `web/frontend/src/pages/DataPage.tsx`, `web/frontend/src/index.css`
  - 軸: validity, maintainability
  - 根拠: validity/maintainability: index.cssは--color-accent/--color-red定義だが--color-danger(DataPage L295)と--color-primary(index.css L989)が未定義で色が当たらず、DataPageの履歴クリアがbtn-ghost灰のまま(他の破壊操作は赤btn-danger)。L295のinline styleを廃しbtn-danger化、L989を--color-accentに修正。var(--color-を@theme定義と突合する簡易チェックをビルド前に入れる。
  - テスト影響: 軽微。破壊ボタンのclassテストを追加可。
- [~] **C021** `[P2]` `<refactor>` risk=medium — status/priority/levelのバッジ色・ラベルをlib/labelsに一元化 _(状態: in_progress)_
  - 対象: `web/frontend/src/lib/labels.ts`, `web/frontend/src/lib/utils.ts`, `web/frontend/src/pages/DashboardPage.tsx`, `web/frontend/src/pages/SessionsPage.tsx`, `web/frontend/src/pages/AgentsPage.tsx`, `web/frontend/src/pages/HandoffsPage.tsx`, `web/frontend/src/pages/BoardPage.tsx`, `web/frontend/src/pages/InboxPage.tsx`
  - 軸: validity, maintainability, convenience
  - 根拠: validity/maintainability: statusBadgeがDashboard/Sessions/Agents/Handoffs/Boardで独自定義され同じpendingがyellow/neutralと食い違い、priorityBadgeも共通版とInbox版でlow/medium既定が逆。値も英語生表示(running/pending/high/low)で和訳画面と非対称。statusLabel/priorityLabel/levelLabelとbadgeマップをlib/labelsに集約し全badgeをそれ経由に、想定値の全集合と既定色を1箇所で定義。
  - テスト影響: 各ページのbadge表示テストを共通ラベル前提へ更新。labelsの単体テスト追加。
- [~] **C022** `[P2]` `<refactor>` risk=low — 日付/時刻フォーマットをlib/utilsに統一(ロケール無しtoLocaleString全廃) _(状態: in_progress)_
  - 対象: `web/frontend/src/lib/utils.ts`, `web/frontend/src/pages/ContentSchedulePage.tsx`, `web/frontend/src/pages/AtlasPage.tsx`, `web/frontend/src/pages/DashboardPage.tsx`, `web/frontend/src/pages/ConnectionsPage.tsx`, `web/frontend/src/pages/NotificationsPage.tsx`, `web/frontend/src/pages/InboxPage.tsx`
  - 軸: validity, convenience, maintainability
  - 根拠: validity/convenience: 共通formatDateがあるのにDataPage/Orgsのみ使用、他は5系統(秒までフル/独自formatConnectedAt/ロケール無し/生ISO)に分裂し『6/14 09:00』『2026/6/14 9:00:00』『2026-06-14T...』が混在。NotificationsとInboxは生ISO表示。formatDateTime(ja-JP)をutilsに追加し全独自実装と生表示を置換、相対表示+title絶対時刻に。ロケール無しtoLocaleString()は全廃。
  - テスト影響: 日時表示テストを共通フォーマット前提へ更新。
- [~] **C023** `[P2]` `<refactor>` risk=low — page-header/loading/empty-stateを共通コンポーネント化 _(状態: in_progress)_
  - 対象: `web/frontend/src/components/PageHeader.tsx`, `web/frontend/src/components/LoadingCard.tsx`, `web/frontend/src/components/EmptyState.tsx`, `web/frontend/src/index.css`, `web/frontend/src/pages/ContentSchedulePage.tsx`, `web/frontend/src/pages/DataPage.tsx`, `web/frontend/src/pages/HelpPage.tsx`, `web/frontend/src/pages/AtlasPage.tsx`
  - 軸: maintainability, validity, convenience
  - 根拠: maintainability/validity: page-header構造が3系統(div.page-title/+subtitle/+page wrapper+h1)、.page-subtitleはCSS未定義で3ページ未スタイル、loadingがspinnerカードと素テキストで割れ、empty-stateもアイコンサイズ24/28とinline padding混在。PageHeader/LoadingCard/EmptyState共通部品へ集約し.page-subtitleをindex.cssに定義、見出し構造とアイコン配置を統一。
  - テスト影響: 各ページのヘッダ/loading/empty取得テストが共通部品で安定化。
- [x] **C033** `[P2]` `<refactor>` risk=low — スコアバー/しきい値/status色の二重定義を共通ScoreBarへ集約 _(状態: done)_
  - 対象: `web/frontend/src/components/ScoreBar.tsx`, `web/frontend/src/pages/OrgsPage.tsx`, `web/frontend/src/pages/DashboardPage.tsx`, `web/frontend/src/pages/AgentsPage.tsx`, `web/frontend/src/index.css`
  - 軸: maintainability, validity
  - 根拠: maintainability/validity: スコアバーが一覧(ScoreTooltip: score-high/mid/low)と詳細(healthClass: good/warning/critical)でしきい値・色語彙が二重定義され乖離、自律スコアは一覧バー有り・詳細数値のみで不整合、health-fillのwidthがinline style。単一ScoreBarコンポーネント(共通しきい値/配色/凡例)に集約し一覧/詳細で共有、widthはCSS変数化。
  - テスト影響: ScoreBar単体テスト。各ページのスコア表示テストを共通部品前提へ更新。
- [~] **C038** `[P3]` `<refactor>` risk=low — 数値整形/更新ボタン呼称/タブUIの分裂を統一 _(状態: in_progress)_
  - 対象: `web/frontend/src/lib/utils.ts`, `web/frontend/src/pages/RevenuePage.tsx`, `web/frontend/src/pages/AtlasPage.tsx`, `web/frontend/src/pages/DashboardPage.tsx`, `web/frontend/src/pages/AgentsPage.tsx`, `web/frontend/src/pages/DataPage.tsx`, `web/frontend/src/components/Tabs.tsx`, `web/frontend/src/components/RefreshButton.tsx`
  - 軸: validity, maintainability, convenience
  - 根拠: validity/maintainability: 数値整形がja-JP千区切り/ロケール無し/桁数バラバラで混在、更新ボタンが『更新』『再読み込み』で揺れ可視テキストとaria-labelも不一致、タブが tab-bar/data-tabs/help-tabs の3系統(ARIA有無不揃い)。formatNumber/formatYen/formatScoreをutilsに集約、Refreshボタンを部品化し呼称を『更新』に統一しaria一致、共通Tabs(role=tablist/tab+aria-selected)へ移行。
  - テスト影響: DataPage等の『再読み込み』name取得テストを『更新』へ更新。共通Tabs/Refreshのテスト追加。

### W1 — P0 安全ゲート（破壊/外部送信の確認）  (1/2)

- [x] **C001** `[P0]` `<fix>` risk=medium — 外部公開(publish run)とdry-run/confirmに確認ゲートを必須化 _(状態: verified)_
  - 対象: `web/frontend/src/pages/InboxPage.tsx`, `POST /api/publish-jobs/{id}/run`, `POST /api/publish-jobs/{id}/confirm`, `web/frontend/src/pages/__tests__/InboxPage.test.tsx`
  - 軸: necessity, validity, functionality
  - 根拠: necessity/validity: kind==='publish'の『投稿』がPOST /publish-jobs/{id}/runを無確認ワンクリックで発火し、note/X/WordPressへ取り消し不能な外部公開を実行する。『公開=人手ゲート』という製品の安全境界(CLAUDE.md/PUB-AUTO)と真っ向から矛盾し、最も損害の大きい操作が最も軽いガードになっている逆転。媒体名・本文要約・予約時刻を出すRadix AlertDialog確認を必須化し、preview(dry-run)→approveの二段導線にする。
  - テスト影響: InboxPage.test の『投稿で run を叩く』テストが確認ダイアログ経由に変わるため要更新。確認→実行/キャンセルのテストを追加。
- [~] **C003** `[P0]` `<fix>` risk=medium — HumanTasks/Board/Dashboard/Settings等の確認なし破壊操作を是正 _(状態: in_progress)_
  - 対象: `web/frontend/src/pages/HumanTasksPage.tsx`, `web/frontend/src/pages/BoardPage.tsx`, `web/frontend/src/pages/DashboardPage.tsx`, `web/frontend/src/pages/ProposalsPage.tsx`, `web/frontend/src/pages/SettingsPage.tsx`
  - 軸: necessity, validity, functionality
  - 根拠: necessity/validity: HumanTasksの『完了』(不可逆・高リスク最終確認の場でこそ無確認は設計矛盾)、Boardのrunningタスクキャンセル(backendがPENDINGのみ許可するため必ず失敗する死んだ破壊操作)、Dashboardのinit(再初期化)/daemon stop、Proposals一括承認(コード適用を伴う)、SettingsのloadError中DEFAULT上書き保存。C002のConfirmDialogで確認を入れ、Boardのキャンセルはpendingのみに条件を絞る。
  - テスト影響: 各破壊操作テストを確認経由に更新。Boardはrunning行でキャンセル不可になることのテストを追加。

### W2 — IA/ナビ再設計・承認/通知統合  (3/4)

- [x] **C004** `[P1]` `<refactor>` risk=medium — サイドバーIAをグループ化データ構造へ再設計(NavGroup[]) _(状態: done)_
  - 対象: `web/frontend/src/App.tsx`, `web/frontend/src/index.css`, `AGENTS.md`
  - 軸: necessity, validity, convenience, extensibility
  - 根拠: necessity/validity/convenience: navItemsが20項目フラットで唯一の見出し『ワークスペース』が全項目を覆う=セクション分けの体を成さず、ミラーズ7±2の約3倍で毎回線形スキャン。優先度づけ皆無で初回1回の『初回セットアップ』が最上段を恒久占有。NavGroup={label,items}配列に再設計し既存.sidebar-section-labelで5グループ(はじめに/要対応/組織と提案/収益化/システム)を出力、グループ内は頻度・ワークフロー順。折りたたみ時はラベル代替にグループ区切り線を出す。
  - テスト影響: ナビ描画テストがあれば構造変更で要更新。グループ見出し出力のテストを追加。
- [x] **C005** `[P1]` `<fix>` risk=low — 折りたたみ時の全ナビ判別不能を是正(title/Tooltip付与) _(状態: done)_
  - 対象: `web/frontend/src/App.tsx`
  - 軸: convenience, validity
  - 根拠: convenience/validity: 折りたたみ時に全NavLinkのラベルをnullで消すのにtitle属性もツールチップも一切無く、20アイコンだけでは判別不能=折りたたみが実質使用不能(P0級の利便性破壊)。各NavLinkにtitle={item.label}またはRadix Tooltipを付与。トグルのラベル『ナビゲーション』も動作を表さず改名。
  - テスト影響: 軽微。折りたたみ時のtitle/aria存在テストを追加可。
- [x] **C006** `[P1]` `<merge>` risk=high — 承認系3画面(/inbox・/proposals・/human-tasks)を/inbox承認ハブに統合 _(状態: done)_
  - 対象: `web/frontend/src/pages/InboxPage.tsx`, `web/frontend/src/pages/ProposalsPage.tsx`, `web/frontend/src/pages/HumanTasksPage.tsx`, `web/frontend/src/App.tsx`, `/api/inbox`, `/api/proposals`, `/api/human-tasks`
  - 軸: necessity, maintainability, convenience
  - 根拠: necessity/maintainability: 3導線が『溜まった承認を捌く』単一ジョブを分割し、どこを見れば全部終わるか判別不能。Inboxは既にproposal承認で同一API(approve/reject)を呼びProposalsはサブセット。/api/inboxにhuman_task kindを足して集約、proposalの詳細(diff/approval_notes/一括)はInbox行展開へ取り込み、/proposalsと/human-tasksをナビから外す。承認分岐ロジックが1箇所に集約され重複解消。
  - テスト影響: 大。3ページのテストを統合構成へ再編。/api/inboxにhuman_task追加のバックエンド/契約テストが必要。
- [~] **C007** `[P1]` `<merge>` risk=medium — 通知をライブ(トースト)と永続(/notifications)に役割分離しBellを一本化 _(状態: in_progress)_
  - 対象: `web/frontend/src/App.tsx`, `web/frontend/src/pages/NotificationsPage.tsx`, `/api/notifications`, `web/frontend/src/hooks/usePlatformUpdates.ts`
  - 軸: necessity, validity, maintainability
  - 根拠: necessity/validity/maintainability: 同一WSイベントがトースト+Bellポップオーバー+通知ページ+通知センターナビの最大4面で多重露出し語彙(success/info/error vs done/live/error)も不一致。Bellは未読概念が無く件数バッジが『未読』を詐称・pendingを『live』と誤表示。Bellを/api/notifications未読プレビューに置換しWS直結を廃止、WSはトースト専用、通知センターナビは削除(20→19)。statusラベルは保留/処理中/完了等に統一。
  - テスト影響: App.tsxのBell/トーストテストとNotificationsのバッジテストを更新。pending表示の文言テストを追加。

### W3 — グローバル堅牢化（WS/401/非同期/オフライン）  (3/5)

- [x] **C009** `[P1]` `<refactor>` risk=medium — usePlatformUpdatesを単一WS Providerに集約(多重接続/重複配信を解消) _(状態: done)_
  - 対象: `web/frontend/src/hooks/usePlatformUpdates.ts`, `web/frontend/src/App.tsx`, `web/frontend/src/components/OrchestraView.tsx`, `web/frontend/src/pages/InboxPage.tsx`, `web/frontend/src/pages/ContentSchedulePage.tsx`, `web/frontend/src/pages/SessionsPage.tsx`, `web/frontend/src/test/setup.ts`
  - 軸: validity, maintainability
  - 根拠: validity/maintainability: hookが呼び出し毎にnew WebSocketを張り、App+OrchestraView+Inbox+ContentSchedule+Sessionsの5箇所で画面ごとに複数接続が発生。各インスタンスが別events stateと別3s再接続を持ち、同一イベントがN重処理→再取得多重発火。Context Providerで1本のWSを共有し各ページは購読のみ。WSスタブを配信可能に拡張して接続数/重複のテストを追加。
  - テスト影響: WS no-opスタブを配信可能スタブへ拡張。購読系ページの再取得トリガテストを更新・追加。
- [x] **C010** `[P1]` `<add>` risk=low — 401集中ハンドリングとSettingsのAPIトークン入力UIを追加 _(状態: done)_
  - 対象: `web/frontend/src/lib/token.ts`, `web/frontend/src/lib/api.ts`, `web/frontend/src/pages/SettingsPage.tsx`, `web/frontend/src/App.tsx`
  - 軸: necessity, functionality
  - 根拠: necessity/functionality: PANTHEON_API_TOKEN運用時、token.tsはURLクエリ取り込みのみでアプリ内の入力/更新/クリアUIが無く(setApiTokenは未呼び出しの死蔵)、api.tsは401でErrorを投げるだけ。未認証/期限切れユーザーは各ページが赤エラーを出すだけで復帰手段が分からず詰む。api.tsに401集中ハンドリング(未認証→トークン入力誘導)を入れ、SettingsにAPIトークンフィールド(setApiToken連携・マスク・クリア)を追加。
  - テスト影響: 401応答時の誘導テストとトークン設定/クリアのSettingsテストを追加。
- [~] **C011** `[P1]` `<fix>` risk=low — ContentSchedule等のエラー/空状態欠落を是正し非同期状態を統一 _(状態: in_progress)_
  - 対象: `web/frontend/src/pages/ContentSchedulePage.tsx`, `web/frontend/src/pages/HumanTasksPage.tsx`, `web/frontend/src/pages/NotificationsPage.tsx`, `web/frontend/src/components/AsyncBoundary.tsx`
  - 軸: validity, convenience, maintainability
  - 根拠: validity/convenience: ContentScheduleはPromise.allSettledで失敗を握りつぶしerror/再試行UIが皆無→API失敗時に空カードで無言。他は三項チェーンとloading/error独立判定で分岐形式も分裂。全ページにAlertTriangle空状態+再試行を必須化し、共通AsyncBoundary(loading/error/empty)へ寄せる。
  - テスト影響: ContentScheduleにエラー状態テストを新規追加。共通AsyncBoundaryの単体テスト。
- [~] **C027** `[P2]` `<improve>` risk=low — 再取得時の全画面spinner置換によるチラつきを解消(quiet再取得) _(状態: in_progress)_
  - 対象: `web/frontend/src/pages/InboxPage.tsx`, `web/frontend/src/pages/HumanTasksPage.tsx`, `web/frontend/src/pages/NotificationsPage.tsx`, `web/frontend/src/pages/OrgsPage.tsx`, `web/frontend/src/pages/MarketplacePage.tsx`, `web/frontend/src/pages/AtlasPage.tsx`, `web/frontend/src/pages/SessionsPage.tsx`, `web/frontend/src/pages/BoardPage.tsx`
  - 軸: convenience, validity
  - 根拠: convenience: 多くのページで更新/操作後の非quiet load()がリスト全体をspinnerへ置換し既存表示が消えてチラつく(Inbox/HumanTasks/Notifications/Orgs/Marketplace/Atlas/Sessions/Board/Handoffs)。初回マウントのみフルローディング、再取得はquiet=trueで既存保持+控えめインジケータ/skeletonへ統一。
  - テスト影響: 軽微。quiet再取得で既存リストが保持されるテストを追加可。
- [x] **C035** `[P2]` `<add>` risk=low — ライブ更新切断バナーとオフライン昇格表示の追加 _(状態: done)_
  - 対象: `web/frontend/src/App.tsx`, `web/frontend/src/hooks/usePlatformUpdates.ts`, `web/frontend/src/pages/InboxPage.tsx`, `web/frontend/src/pages/SessionsPage.tsx`, `web/frontend/src/components/OrchestraView.tsx`
  - 軸: validity, convenience
  - 根拠: validity/convenience: WS依存ページ(Inbox/Sessions/Orchestra)はポーリング廃止でWS断時にデータが静かに陳腐化するが警告無し。ヘッダは3s再接続ループで永遠に『再接続中』のまま恒久断にエスカレーションせず誤認を招く。共有Provider(C009)上で切断バナー『表示が古い可能性』を出し、一定回数失敗で『オフライン』へ昇格。
  - テスト影響: 切断状態のバナー表示/オフライン昇格テストを追加。

### W4 — Dashboard＋画面別機能修正  (10/13)

- [x] **C012** `[P1]` `<merge>` risk=medium — Dashboardの重複カードを統合(約11枚→7枚) _(状態: done)_
  - 対象: `web/frontend/src/pages/DashboardPage.tsx`
  - 軸: necessity, maintainability, convenience
  - 根拠: necessity/maintainability: ヘルス×3・組織数×3・LLM状態×3・更新ボタン×3・/api/tasksカード×2の重複。platform-status+health-scoreを1カードに統合、metric-platform-health/health-score-monitor-text/system-info-kv-llm/platform-llm-badgeを削除、execution-monitor+task-queueをタスク1カードに統合し更新ボタンを1つへ。組織数の真実をorganizations.lengthに一本化。
  - テスト影響: Dashboard要素テストを統合後構成へ更新。削除カードのテストを除去。
- [x] **C013** `[P1]` `<fix>` risk=medium — Dashboard累計メトリクスのlimit=40依存を是正(サーバ集計化orラベル正直化) _(状態: done)_
  - 対象: `web/frontend/src/pages/DashboardPage.tsx`, `/api/execution-history`, `web/server.py`
  - 軸: validity, functionality
  - 根拠: validity: 総提案数/承認率/改善速度/velocityがexecution-history limit=40窓に依存し『累計』を僭称。承認率は分母0で0%表示が実績ゼロと却下多数を区別不能。サーバ集計エンドポイントへ切替えるか、無理なら『直近40件の…』へ正直化し分母0は『データなし/—』に。velocityは手書きSVGをやめrecharts/共通チャートへ。
  - テスト影響: 集計表示テストを更新。サーバ集計を足す場合はバックエンドテストを追加。
- [x] **C017** `[P1]` `<fix>` risk=low — ナビ依存の死んだリストにアクション/遷移を付与(承認・詳細導線) _(状態: done)_
  - 対象: `web/frontend/src/pages/MarketplacePage.tsx`, `web/frontend/src/pages/RevenuePage.tsx`, `web/frontend/src/pages/OrgsPage.tsx`, `web/frontend/src/pages/HandoffsPage.tsx`, `web/frontend/src/pages/DashboardPage.tsx`
  - 軸: functionality, necessity, convenience
  - 根拠: functionality/necessity: Marketplaceの新規会社候補・Revenueのportfolio提案・Orgs詳細の未対応提案リストが読み取り専用で承認/会社化/詳細へ進めず(routeフィールド未使用)。Dashboard handoff一覧も承認へ飛べない。各行に『承認インボックスで開く』/該当画面リンクを付与しpriority降順ソートも実装、死んだ示唆を行動の起点にする。
  - テスト影響: 各行の遷移/起票テストを追加。
- [x] **C018** `[P1]` `<fix>` risk=low — install-division-button等の『成功が反映されない』非一貫挙動を修正 _(状態: done)_
  - 対象: `web/frontend/src/pages/MarketplacePage.tsx`
  - 軸: functionality, validity
  - 根拠: functionality/validity: install-divisionが成功後にload()を呼ばず画面が更新されない(installCompany/scanは更新する)ため、成功トーストを見ても結果が反映されず再押下で二重追加を誘発=『壊れて見える』(P0級)。成功後にload()または局所更新を必ず行い、対象org取り違え防止に確認も挟む。
  - テスト影響: 追加成功後の再取得/反映テストを追加。
- [x] **C019** `[P2]` `<improve>` risk=low — ContentScheduleループ間隔のハードコード(interval:600)を可変化+可視化 _(状態: done)_
  - 対象: `web/frontend/src/pages/ContentSchedulePage.tsx`
  - 軸: validity, functionality, convenience
  - 根拠: validity/functionality: ジョブ側は1時間〜1週間選べるのにループ巡回間隔だけinterval:600固定・非表示でブラックボックス。実行間隔セレクトを開始ボタン近くに用意し送信値を可変化、最低でも『10分ごとに巡回』をUI明示。job-run-nowの連打防止(行単位disabled+スピナー)も追加。
  - テスト影響: 間隔送信値とrun連打防止のテストを追加。
- [ ] **C020** `[P2]` `<merge>` risk=medium — 収益化パイプラインのナビ連続配置とStudio/Content接続(または統合)
  - 対象: `web/frontend/src/App.tsx`, `web/frontend/src/pages/StudioPage.tsx`, `web/frontend/src/pages/ContentSchedulePage.tsx`, `web/frontend/src/pages/InboxPage.tsx`, `web/frontend/src/lib/contentFormat.ts`
  - 軸: necessity, convenience, extensibility
  - 根拠: necessity/convenience: スタジオ/コンテンツ予約/引き渡し/収益が分散配置でワークフロー(生成→予約→引き渡し→収益)として連続せず、Studioは保存もAPI呼び出しも無い孤島でContentが生成した下書きと相互に流し込めない。『収益化』グループに連続配置し、Studioを承認待ち下書きを読み込む下書きビューアとして/content・/inboxのpublishから開けるよう接続。接続しないなら単独ナビは廃しContent詳細に内包。
  - テスト影響: Studioに下書き読み込みテストを追加。ナビ統合に伴う遷移テスト更新。
- [~] **C026** `[P2]` `<improve>` risk=low — 死蔵データの活用と生値露出の是正(last_detail/payload/created_at/ref等) _(状態: in_progress)_
  - 対象: `web/frontend/src/pages/ContentSchedulePage.tsx`, `web/frontend/src/pages/HandoffsPage.tsx`, `web/frontend/src/pages/HumanTasksPage.tsx`, `web/frontend/src/pages/AtlasPage.tsx`, `web/frontend/src/pages/SessionsPage.tsx`, `web/frontend/src/pages/AgentsPage.tsx`
  - 軸: functionality, necessity
  - 根拠: functionality/necessity: last_detail(失敗原因)・handoff payload整形/policy_reason/materialized_ref・HumanTask.ref/作成日時・KnownIssue.detail・subsystem.paths・exit_code異常強調・open/totalカウントが取得済みなのに未表示で診断/判断が不能。失敗時detail表示・主要キーの定義リスト化・ref/作成日時表示・件数バッジ活用を行い、生JSONはRAW折りたたみへ降格。
  - テスト影響: 失敗detail表示・件数バッジ等の表示テストを追加。
- [x] **C029** `[P2]` `<fix>` risk=low — Studio Xスレッド閾値バグ修正と出口(コピー/エクスポート)・永続化 _(状態: done)_
  - 対象: `web/frontend/src/pages/StudioPage.tsx`, `web/frontend/src/lib/contentFormat.ts`
  - 軸: functionality, validity, convenience
  - 根拠: functionality/validity: 文字数バッジ/状態がcount>280基準なのに実分割は接尾辞ぶん上限を縮め275〜280字で『緑・1ツイート』と実2分割が矛盾。判定をthread.length基準に統一。読み取り専用で各ツイート/全件/記事のコピー導線が無く目的未達→コピー/エクスポートを追加。title/bodyがuseStateのみでリロード消失→localStorage自動保存・復元。
  - テスト影響: 閾値境界(275-280字)の分割一致テスト・コピー/永続化テストを追加。
- [~] **C030** `[P2]` `<improve>` risk=medium — Onboardingのエラー/空状態追加・MarketplaceとのテーブルDRY化・初回出し分け _(状態: in_progress)_
  - 対象: `web/frontend/src/pages/OnboardingPage.tsx`, `web/frontend/src/pages/MarketplacePage.tsx`, `web/frontend/src/components/CompanyManifestTable.tsx`, `web/frontend/src/pages/__tests__/OnboardingPage.test.tsx`, `web/frontend/src/App.tsx`
  - 軸: necessity, maintainability, convenience
  - 根拠: necessity/maintainability: OnboardingとMarketplaceが同一API/型/installフローでerror/再試行/KPI列まで重複しOnboardingは劣化版。step2失敗で空テーブルのまま行き止まり(完了disabled)。共通CompanyManifestTableへ抽出、error/empty/KPI列を追加し、組織0件等で『初回のみ』ナビ出し分け/自動リダイレクトを検討。
  - テスト影響: Onboardingの失敗/空/step3/disabledゲートテストを追加。共有テーブルのテスト。
- [x] **C031** `[P2]` `<merge>` risk=low — Dashboard組織一覧をサマリ縮小し正は/orgsに一本化 _(状態: done)_
  - 対象: `web/frontend/src/pages/DashboardPage.tsx`, `web/frontend/src/pages/OrgsPage.tsx`
  - 軸: maintainability, necessity
  - 根拠: maintainability/necessity: Dashboardの組織一覧テーブルが/orgsの読み取り専用サブセットで同一概念(健康/提案数)を二重メンテ。Dashboardは『弱い/強い組織トップN+全件は/orgsへ』のサマリに縮小、フル一覧の正は/orgsに統一。ナビは役割が違うため両方残す。
  - テスト影響: Dashboard組織テーブルのテストをサマリ前提へ更新。
- [x] **C032** `[P2]` `<fix>` risk=medium — OrgsPage行カードのボタン入れ子アンチパターンと詳細パネルa11y是正 _(状態: done)_
  - 対象: `web/frontend/src/pages/OrgsPage.tsx`
  - 軸: validity, maintainability, convenience
  - 根拠: validity/maintainability: 行全体role=button内に編集/削除ボタンを内包する入れ子アンチパターン、詳細スライドパネルがrole=dialog/aria-modal/フォーカストラップ/Esc/初期フォーカス欠如(独自実装)、OrgIconがDate.now()で常時キャッシュ破棄。詳細トリガをChevronボタンに限定し行のrole=buttonを廃止、パネルをRadix Dialog化、アイコンversionは更新時のみbump。
  - テスト影響: 詳細パネルのEsc/フォーカス、行操作の分離テストを追加・更新。
- [x] **C034** `[P2]` `<fix>` risk=low — 入力検証・冪等性の強化(ナレッジ名/組織repoパス/会社重複/収益org) _(状態: done)_
  - 対象: `web/frontend/src/pages/DataPage.tsx`, `web/frontend/src/pages/OrgsPage.tsx`, `web/frontend/src/pages/MarketplacePage.tsx`, `web/frontend/src/pages/RevenuePage.tsx`, `web/frontend/src/pages/BoardPage.tsx`
  - 軸: validity, functionality
  - 根拠: validity/functionality: ナレッジ作成が空チェックのみで拡張子/パストラバーサル/重複未検証、organization repoパスが無検証自由入力で孤児/誤ルーティング誘発、同一テンプレ重複作成の警告無し、Revenue組織名がdatalist自由入力でtypoで別組織記録、Board組織名/種別も無検証自由入力。クライアント前検証+確認+選択式化(存在しないorgは警告)で防ぐ。
  - テスト影響: 不正名/重複/未知org送信時の検証テストを追加。
- [x] **C036** `[P2]` `<improve>` risk=low — config/分析の生JSONダンプを構造化表示+Raw折りたたみ+コピー化 _(状態: done)_
  - 対象: `web/frontend/src/pages/AgentsPage.tsx`
  - 軸: convenience, maintainability
  - 根拠: convenience/maintainability: 設定ビューア/分析結果が生JSONダンプでエンドユーザー向けでなく、しかも結果が画面外の別カードに出て『何も起きない』視線断絶、推奨エージェントもraw ID表示で誰か不明・ジャンプ導線無し。主要フィールドを構造化表示+RawはコピーボタンつきでprogressLogクラス流用をやめ、結果は行内展開/モーダル化し自動スクロール、推奨はname解決+該当行リンク。
  - テスト影響: 構造化表示/コピー/ジャンプのテストを追加。

### W5 — 一貫性/a11y/i18n/テスト/デッドコード  (5/10)

- [x] **C014** `[P1]` `<improve>` risk=high — ポリシー/モデル構成/プロンプトの生JSON手編集を構造化エディタ化 _(状態: done)_
  - 対象: `web/frontend/src/pages/SettingsPage.tsx`, `/api/settings`
  - 軸: validity, necessity, functionality
  - 根拠: validity/necessity: 安全境界に直結するpolicy_rules(auto_approve/human_required/auto_reject)がスキーマ検証なしの生JSONで、誤記で空条件保存が可能。prompt_templatesはString()で配列/オブジェクトを黙殺破壊、model_configsも型未検証。固定キー前提の構造化フォーム+JSONスキーマ検証へ作り替え、生JSONはRAWトグル裏に退避。空条件警告も出す。
  - テスト影響: Settings保存テストを構造化エディタ前提へ再編。スキーマ検証失敗のテストを追加。
- [x] **C015** `[P1]` `<fix>` risk=low — 数値設定の相互/範囲検証を追加(soft<=hard・0-23・min/max) _(状態: done)_
  - 対象: `web/frontend/src/pages/SettingsPage.tsx`, `web/frontend/src/pages/NotificationsPage.tsx`
  - 軸: validity, functionality
  - 根拠: validity: quota soft>hardでも保存可、quiet_hours/window_hoursがHTML min/maxのみでJS検証なく範囲外値をPUTしデータ破壊。NotificationsのquietHours入力も0-23 clamp/NaNガード無し。保存前にsoft<=hard・0-23・>=1を検証し不正時はインラインエラー+該当フィールドへフォーカス、保存ボタンにdirty追跡。
  - テスト影響: 範囲外/相互不整合入力で保存ブロックされるテストを追加。
- [~] **C024** `[P2]` `<fix>` risk=low — inline style廃止とボタン変種統一(frontend規約準拠) _(状態: in_progress)_
  - 対象: `web/frontend/src/pages/ProposalsPage.tsx`, `web/frontend/src/pages/AgentsPage.tsx`, `web/frontend/src/pages/SessionsPage.tsx`, `web/frontend/src/pages/NotificationsPage.tsx`, `web/frontend/src/pages/RevenuePage.tsx`, `web/frontend/src/pages/BoardPage.tsx`, `web/frontend/src/pages/DataPage.tsx`, `web/frontend/src/index.css`
  - 軸: validity, maintainability
  - 根拠: validity/maintainability: frontend.md禁止のinline styleが多数(Proposals差分のハードコードhex #7ee787等でテーマ非追従、Agents/Sessions/Notifications/Revenue/Board/Data)。grid/カードもTailwind直書きとindex.cssユーティリティの二重基準。破壊/取消ボタンもbtn-danger↔btn-ghost↔btn-secondaryで危険シグナル不一致。差分色を.diff-add/.diff-del等クラス化、width等をユーティリティ化、ボタン変種(破壊=danger/主=primary/副=secondary/補助=ghost)を規定しfrontend.mdに明記。
  - テスト影響: 視覚回帰中心。クラス指定テストを一部追加可。
- [~] **C025** `[P2]` `<fix>` risk=medium — 検索/通知ポップオーバー/モーダルのa11y契約整備 _(状態: in_progress)_
  - 対象: `web/frontend/src/App.tsx`, `web/frontend/src/pages/OrgsPage.tsx`, `web/frontend/src/pages/DataPage.tsx`, `web/frontend/src/components/ConfirmDialog.tsx`
  - 軸: validity, convenience
  - 根拠: validity/convenience: 全体検索がrole=listbox宣言なのに子にrole=option/矢印キー/Enter/Escape/aria-activedescendant無し(ARIA契約違反)、通知ポップオーバーにdialog属性・フォーカストラップ無し、Orgs/DataのモーダルもEscape/フォーカストラップ/初期フォーカス欠如(DataはRadix未使用の素div)。Radix Combobox/Popover/Dialogへ置換しキーボード/aria/Escを一括担保。Ctrl/Cmd+K検索フォーカスも追加。
  - テスト影響: 検索キーボード操作・モーダルEsc/フォーカストラップのa11yテストを追加。
- [~] **C028** `[P2]` `<improve>` risk=medium — Atlas依存グラフSVGのアクセシビリティ/スケール改善 _(状態: in_progress)_
  - 対象: `web/frontend/src/pages/AtlasPage.tsx`
  - 軸: validity, functionality, convenience
  - 根拠: validity/functionality: 円環固定レイアウト+ホバー専用ハイライトでノード増に破綻、ズーム/パン無し、role=imgで子のtext/円がスクリーンリーダ不可視、固定760x520でレスポンシブ非対応、キーボード/タッチ非対応。ノードを<button>/tabindex化しフォーカスハイライト・viewBox維持でwidth100%可変・テキスト代替(隣接リスト)を併設、規模超過時はフォースレイアウトへ。
  - テスト影響: グラフのキーボード操作/aria代替テストを追加。
- [x] **C037** `[P3]` `<delete>` risk=low — デッドコード削除(streamSSE/setApiToken)とドキュメントdrift修正 _(状態: done)_
  - 対象: `web/frontend/src/lib/api.ts`, `web/frontend/src/test/mocks.ts`, `web/frontend/src/lib/token.ts`, `.claude/rules/frontend.md`
  - 軸: maintainability
  - 根拠: maintainability: streamSSEはapi.tsからexportされるが本番呼び出し皆無(テストmockのみ)で対応する/api/goals/stream・/api/analyze/streamもフロント未配線の両側デッドウェイト。setApiTokenも未呼び出し(C010で配線するなら例外)。frontend.mdが存在しないuseWebSocketを参照するdriftもある。SSE機能を使わないなら削除、使うなら配線。
  - テスト影響: mocks.tsのstreamSSEモック行削除。SSE関連テストがあれば除去。
- [ ] **C039** `[P3]` `<fix>` risk=low — 日本語UIへの英語ラベル混入を是正(Select All/tools/dry-run等)
  - 対象: `web/frontend/src/pages/ProposalsPage.tsx`, `web/frontend/src/pages/AgentsPage.tsx`, `web/frontend/src/pages/SessionsPage.tsx`, `web/frontend/src/pages/SettingsPage.tsx`, `web/frontend/src/pages/InboxPage.tsx`, `web/frontend/src/lib/labels.ts`
  - 軸: validity, convenience
  - 根拠: validity/convenience: 日本語UIにSelect All/{n} tools/schema/legacy/driver/dry-runや列挙生値(running/pending/revenue/sales)が残り言語が不統一。ユーザー可視ラベルは日本語化(『すべて選択』『ツール』)、列挙値はlib/labels(C021)経由で和訳、driver/schema等の内部識別子を英語のまま残すなら方針をルール化し一貫適用。
  - テスト影響: ラベル文字列でのテスト取得箇所を和訳後文言へ更新。
- [x] **C040** `[P3]` `<fix>` risk=low — Help網羅性のナビ1:1化・収益セクション追加・事実誤り修正・コピー/リンク化 _(状態: done)_
  - 対象: `web/frontend/src/pages/HelpPage.tsx`, `web/frontend/src/App.tsx`
  - 軸: validity, necessity
  - 根拠: validity/necessity: acc-pages-helpが『APIキー取得先』と記載しAPIキー不使用という製品事実と自己矛盾(P1事実誤り)。/revenue『収益』のヘルプ欠落・wmux/board混載で目次がナビと非対応、ドリフト検出テストも無し。CodeBlockのコマンド/URLがコピー不可・非リンク。事実誤り削除、収益セクション追加、pageSectionsとNAVの差分検出vitest追加、CodeBlockにコピー/anchorを付与。
  - テスト影響: NAVとpageSectionsのドリフト検出テストを新規追加。
- [x] **C041** `[P3]` `<improve>` risk=low — prefers-reduced-motion対応とルート遷移時フォーカス/スクロール _(状態: done)_
  - 対象: `web/frontend/src/index.css`, `web/frontend/src/App.tsx`
  - 軸: validity, convenience
  - 根拠: validity/convenience: アニメーション/トランジション27箇所にprefers-reduced-motionガードが皆無で動き酔い配慮欠落。ルート遷移時のmainフォーカス移動・スクロール先頭リセットも無い。index.css末尾にreduced-motionメディアクエリを追加、Outlet遷移時にフォーカス/スクロールをリセット。
  - テスト影響: 軽微。reduced-motion適用の視覚確認中心。
- [ ] **C042** `[P3]` `<add>` risk=low — フロント/バック契約テストとWS実挙動スモークを追加(見せかけUI検出)
  - 対象: `web/frontend/src/test/mocks.ts`, `web/frontend/src/test/setup.ts`, `web/frontend/src/lib/api.ts`, `web/server.py`
  - 軸: maintainability, validity
  - 根拠: maintainability/validity: 全ページがapiを全モックし理想形のみ返すため、ボタンが意味ある副作用を起こすか・叩く{method,path}がweb/server.py実ルートと一致するか・WS多重接続/重複が検出できない。主要破壊/外部送信フロー(publish run・handoff approve・org delete)の{method,path}を実ルートallowlistと突合する軽量契約テスト、最低1ページMSWで401/500/形違いを通すスモークを追加。
  - テスト影響: 契約テスト/MSWスモークを新規追加。既存テストへの影響は限定的。

## 削除対象（17件）

- [ ] ナビ項目 nav-notifications(通知センター): ツールバーBell+ポップオーバーと完全重複。削除しBellに一本化(C007)
- [ ] ナビ項目 nav-proposals(改善提案): /inbox承認ハブへ統合しトップレベルから削除、詳細は/inbox?kind=proposal(C006)
- [ ] ナビ項目 nav-human-tasks(あなたのタスク): /api/inbox の human_task kindへ集約しナビから削除(C006)
- [ ] Dashboard metric-platform-health: group_health_scoreの三重表示。削除しゲージ1箇所へ(C012)
- [ ] Dashboard platform-llm-badge: LLM状態の三重掲示。削除しsystem-info-cardへ集約(C012)
- [ ] Dashboard health-score-monitor-text(N件の組織を監視中): total_organizations三重目の飾り。削除(C012)
- [ ] Dashboard system-info-kv-llm: ヘッダsystem-info-badgeとllmReady二重表示。削除(C012)
- [ ] Dashboard execution-monitor-refresh / task-queue-refresh: 同一refreshTasksの重複ボタン。統合し片方削除(C012)
- [ ] Dashboard health-score-card: 単一フィールド表示のためだけのカード。platform-status-cardへ移設し削除(C012)
- [ ] ContentSchedule daemon-pid-text: エンドユーザーに無価値なPID常時表示。削除/詳細退避(C026)
- [ ] AgentsPage agent-card-schema-badge: 内部メタschema_versionの表面常時表示。表面から削除しビューア詳細へ(C036)
- [ ] lib/api.ts streamSSE と test/mocks.ts の streamSSE モック行: 本番呼び出し皆無のデッドコード(C037)
- [ ] lib/token.ts setApiToken: 未呼び出しの死蔵(C010でトークン入力UIに配線しない場合は削除)(C037)
- [ ] HelpPage acc-pages-help内の『APIキー取得先』記述: API不使用と矛盾する事実誤り。削除(C040)
- [ ] Studio/Content の重複『下書き工場・外部公開しない』境界説明とStudio単独ナビ(接続しない場合): Content詳細へ内包しナビから削除(C020)
- [ ] SettingsPage driver-badge の表面常時表示: 診断専用。詳細折りたたみへ退避(表面から削除)
- [ ] AppShell live-status-indicator の常時『リアルタイム接続中』文言: 正常時ノイズ。ドットのみ/非表示に降格(切断時のみ文言)

## 画面別 総合判定（21画面）

| 画面 | route | 総合 | 主な問題 |
|---|---|---|---|
| AppShell | `(global shell)` | overhaul | P0: 折りたたみ時に全ナビラベルを消すのに title/ツールチップが無く20アイコンの判別不能=折りたたみが実質使用不能（sidebar-collapse-toggle / 全 nav-*）；P1: 通知件数バッジが『未読』を詐称（既読化されず減らない＋WSのみでリロード消失）し利用者を誤誘導、pending を『… |
| OnboardingPage | `/onboarding` | overhaul | MarketplacePage と中核機能が重複（同一API・同一型・同一installフロー・エラー文言までリテラル重複）。共通コンポーネント化されておらず保守が二重化し、Onboarding 側は KPI 列と error/再試行 state を欠く劣化版になっている；『作成』が確認なしで実 Organizatio… |
| DashboardPage | `/dashboard` | overhaul | 重複の山: ヘルス×3・組織数×3・LLM状態×3・更新ボタン×3・/api/tasksカード×2。merge/delete で約11枚→7枚に圧縮すべき；破壊操作に確認が無い: header-init-button(POST /api/init) と daemon-stop-button(稼働停止) は規約違反、Al… |
| InboxPage | `/inbox` | overhaul | P0: publish の『投稿』(実外部投稿 POST /run)が確認ダイアログ無しの単一クリックで外部公開される — PUB-AUTO 人手ゲート方針違反；P0/P1: publish の『取消』(DELETE=復元不可)と『公開を確認』(実公開確定)もノーガードで誤クリックが致命的 |
| NotificationsPage | `/notifications` | overhaul | 静音時間入力(quiet_hours_start/end)が 0-23 のclamp/NaNガード無しで範囲外値をPUT送信—データ整合性の即時修正対象(P1)；通知行から組織/提案など発生元への遷移導線が皆無で、通知が行動につながらない死んだ表示になっている |
| HumanTasksPage | `/human-tasks` | overhaul | 完了ボタンが不可逆操作を確認なしで即実行（P0）— 高リスク承認/実投稿の最終確認という目的と真っ向から矛盾。Radix確認ダイアログ必須。；判断文脈の欠落 — HumanTask.ref・作成日時・優先度/リスクが未表示で、人間がタイトルだけで承認させられる。安全ゲートが実質無効化。 |
| ConnectionsPage | `/connections` | keep | 切断ボタンが確認ダイアログなしで即 DELETE され、誤クリックで storage_state セッションが消失(再ログイン必須)— Radix AlertDialog 等で確認必須 (P1)；ログイン待機ポーリングが120秒タイムアウトや失敗時に無通知で消えるため、ユーザーが接続の成否を判断できない — タイムアウ… |
| OrgsPage | `/orgs` | overhaul | 詳細パネルと全モーダルにフォーカストラップ/Esc/初期フォーカス/aria-labelledby が無く、行カードはボタン入れ子のアクセシビリティ・アンチパターン（Radix Dialog 化＋詳細トリガの単一ボタン化で是正）；workspace移行とアイコンリセットが確認なし単一クリックの破壊操作（片道のworks… |
| MarketplacePage | `/marketplace` | overhaul | install-division-button: 成功時にload()を呼ばず画面が更新されない非一貫挙動(P0)。二重追加を誘発し『壊れて見える』。成功後の再取得 or 局所更新が必須。；会社作成/事業部追加という実体生成・変更操作が確認ダイアログ無しで即実行。install-companyは他行同時押下の余地もあり… |
| ProposalsPage | `/proposals` | overhaul | 一括却下・個別却下・一括承認が確認/Undo なしで不可逆実行される（CLAUDE.md の破壊操作禁止方針に違反, P0/P1）；batch ボタンの disabled が actionId==='approve'/'reject' で相互排他になっておらず、承認進行中に却下が押せる競合操作（P1） |
| HandoffsPage | `/handoffs` | overhaul | 却下・承認（claude生成を伴う高コスト/不可逆）に確認ダイアログが無く誤操作のガードゼロ（P1）；『本文のみ生成』が成功後にリスト再取得せず結果が画面に反映されない＝死んだフィードバック導線（P1） |
| StudioPage | `/studio` | overhaul | P1 閾値バグ: 文字数バッジ/状態テキストが count>280 基準なのに実分割は接尾辞ぶん上限を縮めるため、275〜280字で『緑・1ツイート』表示と実際の2件分割が矛盾する（判定を thread.length 基準に統一）；P1 出口導線ゼロ: 分割ツイート・記事プレビューが全て読み取り専用で、コピー/エクスポ… |
| ContentSchedulePage | `/content` | overhaul | 削除が確認ダイアログなしの即時DELETE(P0): 誤クリックでジョブが無警告消失。Radix AlertDialog かundo付きトーストを必須化；ループ駆動間隔が interval:600 でハードコード(P1): ジョブ側は1時間〜1週間選べるのにループ全体の巡回間隔だけ固定・非表示でブラックボックス化。可変… |
| RevenuePage | `/revenue` | overhaul | ポートフォリオ提案(portfolio-card/proposal-row)が読み取り専用で行動導線ゼロ・priority未使用。提案→起票/遷移のアクションを必須化し priority 降順ソートを実装(P1)。；trend-card と monthly-report-card がデータ不足/0件で無音消滅し、機能の… |
| AgentsPage | `/agents` | overhaul | 設定を見る/表示の結果が画面外の別カードに出て『何も起きない』ように見える視線断絶（モーダルor行内展開＋自動スクロールで是正、P2）；推奨エージェントが raw ID 表示で誰か分からず、分析→実体への導線が死んでいる（name解決＋ジャンプリンク化、P2） |
| AtlasPage | `/atlas` | overhaul | 依存グラフSVGが円環固定レイアウト+ホバー専用ハイライト: ノード増で破綻、ズーム/パン無し、キーボード/タッチ非対応、role=imgで子のラベルがスクリーンリーダ不可視(P1)；タブが未完成のWAI-ARIA Tabs(tabpanelロール/矢印キー/URL同期なし)で、再読込のたびにatlasごと消える設計に… |
| SessionsPage | `/sessions` | overhaul | session-stop-button: 確認ダイアログ無しの破壊操作（誤クリックで稼働中エージェントを即停止／二重送信可能）— P0；agent-log-panel: openLog 時の1回取得スナップショットで自動追従せず『ライブ監視』を満たさない＋停止/削除済みセッション選択時の stale 表示 — P1 |
| BoardPage | `/board` | overhaul | running タスクのキャンセルXが backend と矛盾し必ず失敗する死んだ破壊操作（確認ダイアログも無し）— P0；『レビュー』カラムが実体 failed の誤ラベルでレビュー操作も無い／done と cancelled を同列同色で混在 — P0/P2 |
| DataPage | `/data` | overhaul | 新規作成ダイアログが自前実装でアクセシビリティ不備（Radix Dialog 未使用＝規約違反、フォーカストラップ/Escape/role 欠如）；破壊操作（履歴全削除・ファイル削除）が window.confirm 依存でアプリのトースト/ダイアログUIと不整合、確認UIが混在 |
| SettingsPage | `/settings` | overhaul | モデル構成/プロンプト/ポリシールールが生JSON手編集（スキーマ検証なし）——ポリシーは安全境界に直結し誤記で空条件保存が可能、prompt_templatesはString()でデータ黙殺。構造化エディタ＋スキーマ検証へ作り替え必須(P1)；loadError(DEFAULTフォールバック)中に保存ボタンを押すと既… |
| HelpPage | `/help` | overhaul | acc-pages-help が『API キー取得先』と記載しAPIキー不使用という製品事実と自己矛盾(P1事実誤り)；ライブナビの /revenue『収益』のヘルプ欠落・wmux/board混載で目次がナビと1:1非対応、ドリフト検出テストも無し(P1網羅性+保守性) |
