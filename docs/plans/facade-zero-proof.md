# 見せかけUI・偽データ・非機能 = 0 の証明（web/frontend）

- 日付: 2026-06-14 / 対象: **web/frontend（既定 legacy GUI）**。`web/atelier` は別GUIで本証明の対象外。
- 主張: **(A) 見せかけUI=0**（存在しないAPIを叩く/押しても何も起きない/形状不一致で無言で死ぬ要素が無い）、**(B) 偽データ=0**（ハードコードのダミーを実データとして見せる箇所が無い）、**(C) 非機能=0**（名乗る機能が実バックエンドで実際に動く）。
- 方法論: 「エージェントが0と言った」だけに依らず、**機械的証拠 ＋ 実機 end-to-end ＋ 探して直して再探索（loop-until-dry）** で立証。

## 証拠

### 1. 網羅的フロント↔バック契約（恒久テスト）— (A)
`tests/test_frontend_contract.py`（pytest・CIで常時実行）:
- `test_no_frontend_api_call_hits_missing_route`: web/frontend の **全 `api()` 呼び出し 105件（ユニーク84）** を静的走査し、各 {method, 正規化パス} が実在の FastAPI ルートに対応することを保証。**missing=0 / 動的パス=0**。
- `test_frontend_critical_routes_exist`: 破壊/外部送信/承認系の主要ルートを明示リストで保証。
- → 「存在しないエンドポイントを叩く見せかけ」は0、かつ将来も契約ドリフトで失敗して気づける。

### 2. 実機 end-to-end プローブ — (B)(C)
実 ASGI アプリ(`web.server.app`)を新規の実ホームに対して TestClient で動かし、**実ハンドラ・実ストア・実状態**を経由（モック非経由）して **22/22 PASS**:
- 初期化→`/api/platform/status` が実データ（組織数・スコア・env）。
- **書き込み往復＝実状態変化を観測**: 人間タスク 作成→`/api/inbox`出現→完了→消滅／通知 作成→未読+1→既読→未読-1／**人手ゲート公開** handed_off→inbox確認待ち→confirm→published 確定。
- `/api/orchestration/analyze` がフラット構造(`recommended_agents`)を返す（下記 facade 修正の裏取り）。
- フロントが使う read エンドポイント 13本が実レスポンス。

### 3. マーカー/スタブ走査 — (A)(B)
- 出荷フロント(web/frontend/src, 非テスト) の `TODO/FIXME/未実装/coming soon/準備中/dummy/lorem/モックデータ` grep = **0**（唯一の hit はテスト基盤 mocks.ts のコメントで非出荷）。
- `web/server.py` の `NotImplementedError/stub/未実装` = **0**。
- バックエンド全体の `NotImplementedError`/未実装 は **すべて Phase 2 の意図的境界**（実収益API・完全自動の外部公開）。これらが GUI から「動く」と提示されていないかを相互参照（下記）。

### 4. 多面 facade ハント（敵対的検証・loop-until-dry）— (A)(B)(C)
全画面×全バックエンド領域を Explore エージェントで走査し、各疑いを別エージェントが実コードで敵対的検証:
- **R1 = 0**（ただし「人手ゲート隣接」を過剰に正当化して見逃しあり）。
- **grep 相互参照** で Phase2 未実装能力の GUI 露出を発見。
- **R2（校正済・研ぎ澄まし）= 2件確定 → 修正**。
- **R3（修正後・再走査）= 0 → DRY 収束**。

### 5. フルスイート
- backend `pytest tests/` = **1357 passed**（既知 Windows chmod 2件のみ＝回帰なし）。
- frontend = **tsc クリーン・31ファイル/384 passed**。

## 発見し修正した本物の facade（透明性）
1. **ContentSchedulePage の自動投稿** — `publish_mode=auto`「承認したら自動投稿／予約時刻に自動投稿されます」を提示していたが、外部公開アダプタ(note/x/wordpress)は「auto は未実装（Phase 2）」。動かない能力を動くUIとして提示＝facade。→ **auto 選択肢と『（自動）』バッジを除去**し、実際に動く assisted のみを提示。
2. **AgentsPage のオーケストレーション分析** — `/api/orchestration/analyze` はフラット構造を返すのにフロント型が `routing.analysis.*` のネスト前提で、推奨エージェントが**常に表示されない**（形状不一致による無言の機能不全）。テストも誤った形状をモックして露見を隠していた。→ **フロント型を実レスポンス（フラット）に一致**させ、テストも実形状に修正（推奨エージェントが実際に表示される）。

## 正当な境界（facade ではない）
- 外部への最終送信は **人手ゲート**が製品仕様（PUB-AUTO / 「下書き工場＝公開は人手」）。承認→投稿待ち→人手で公開確定の導線は実際に動く（§2 で実証）。自動送信しないこと自体は仕様。
- 実収益API連携・完全自動公開は Phase 2（未接続）。**GUIはこれらを動く機能として一切提示していない**（§3/§4 で確認）。
- 実状態が現時点で空（組織0件等）でも、実バックエンドから取得していれば偽データではない（空状態表示は正当）。

## 再検証方法
- `python -m pytest tests/test_frontend_contract.py` … 契約（見せかけ呼び出し=0）。
- 実機プローブは `web.server.app` を新規 PANTHEON_HOME に対して TestClient で叩く（本文書 §2 の手順）。
- backend/frontend フルスイートは [[../../CLAUDE.md]] のコマンドどおり。
