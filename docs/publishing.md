# Publishing — ブラウザ投稿基盤の使い方と実機検証

生成→承認→投稿の最後の区間（実ブラウザ投稿）の運用手順。設計の全体像は
`core/publishing/` の各モジュール docstring を参照。

## 前提（1回だけ）

```powershell
.\.venv\Scripts\python.exe -m pip install playwright
.\.venv\Scripts\playwright.exe install chromium
```

Playwright 未導入でも Pantheon は壊れない（接続/投稿が「未導入」と正直に失敗するだけ）。
テスト中は `tests/conftest.py` が `PANTHEON_NO_BROWSER=1` を設定するため実ブラウザは決して起動しない。

## プラットフォーム接続（手動ログイン）

```powershell
pantheon publish connect note      # ヘッドフルブラウザが開く → 自分でログイン → 自動検知して保存
pantheon publish status            # 接続状態の一覧
pantheon publish disconnect note   # セッション state を削除
```

- 保存されるのは Playwright の storage_state（cookie 等）のみ:
  `~/.pantheon/browser_sessions/<platform>/state.json`（0o600/dir 0o700 best-effort）。
  パスワードを Pantheon が受け取る・保存することはない。
- Web からは `POST /api/publishing/connections/{platform}/login`（背景タスク起動、
  完了は `GET /api/publishing/connections` に反映）。
- wordpress は接続フロー対象外（Phase 2 で REST API 接続を予定）。

## assisted 投稿（Phase 1: note）

/inbox で承認済み投稿ジョブを「投稿」実行すると:

1. 保存済みセッションで note エディタが開き、タイトル/本文が流し込まれる
2. **ブラウザは開いたまま**になる — 内容を確認して、人間が「公開」を押す（最終送信は人間、が契約）
3. ジョブ status は `handed_off` になる（`published` とは区別。未公開のものは
   成果指標 posts に数えない。`due_jobs` にも二度と乗らない）

auto モード（完全自動公開）は note では未実装（Phase 2）。assisted はどの自動実行経路
（daemon / `process_due_publish_jobs`）からも発火しない。

## 実機 E2E チェックリスト（ユーザー同席時に1回）

セレクタ/エディタ URL は note 側の UI 変更で壊れうるため
`core/publishing/adapters/note.py` のモジュール定数に隔離してある。CI では検証不能なので、
初回は以下を実機確認する:

1. `pantheon publish connect note` → ログイン → 「ログインを検知し…保存しました」が出るか
2. `pantheon publish status` で note が connected か
3. /inbox から assisted ジョブを実行 → エディタが開くか（`NOTE_EDITOR_URL` の検証）
4. **タイトルが「記事タイトル」欄に、本文が本文エリアに入っているか**
   （`NOTE_BODY_SELECTOR = 'div[contenteditable="true"]'` は最初の contenteditable に
   マッチするため、誤ノードに入る可能性が既知リスク。ズレたら note.py の定数を修正）
5. 人間が「公開」→ ジョブが `handed_off` のまま（公開の自動確認は Phase 2）

壊れていた場合に直すのは note.py の定数 3 つ（URL / タイトル / 本文セレクタ）だけ。
