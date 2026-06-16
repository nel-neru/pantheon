# Evolution — 次フェーズ候補バックログ & 監査カバレッジ台帳

> **目的**: `/evolve` の自動再開が「近傍候補は枯渇」を**毎回ゼロから再発見**する非効率（Cycle 30/31/32 で
> 反復観測）を断ち切る。ここは (A) どのバグクラス/サブシステムが「検証済みクリーン」かの台帳と、
> (B) 小スライスが尽きたあとに着手すべき**より大きな候補**のキューを置く。
> planning hygiene 準拠の一時ドキュメント（恒久化したら `docs/design/` へ統合・本ファイルは整理）。
>
> **使い方（次の resume へ）**: `/evolve` 開始時の「現在地把握」でこのファイルを読む。
> §A に載っている候補は**再探索しない**（変更があった疑いがあるときだけ再検証）。
> §B から1つ選んで単一スライスに切って着手する。1サイクル終えたらこの台帳も更新する。

---

## §A. 監査カバレッジ台帳（検証済みクリーン — 再探索不要）

最終更新: Cycle 32（2026-06-16）。各項目は「その時点で実コードを読んで確認」した結果。

| 領域 / バグクラス | 状態 | 根拠（最後に確認したサイクル） |
|---|---|---|
| 状態 load の silent-drop（`except: continue`） | ✅ 観測化済 | Cycle 29: `core/platform/state.py` の `warn_skipped_state_file` を `core/state/manager.py` の5経路へ |
| trends/content の silent-drop | ✅ 観測化済 | Cycle 30: `trends/store.py` `_iter_raw` / `content_jobs.py` `_load_raw`・`list_jobs` |
| メトリクスの除算ゼロ | ✅ ガード済 | Cycle 32: `live_metrics`・`balanced_growth`・`group_balance`・`growth_history` すべて empty/len ガード |
| scheduler の naive datetime 比較 | ✅ ガード済 | Cycle 32: `content_jobs.is_due` / `publish_jobs.is_due` とも try/except（r4 由来）。`growth_history._build_x_values` も naive→UTC 補正 |
| 頭脳層の mutable default / 危険な max・min・[0] | ✅ 該当なし | Cycle 32: `orchestration`/`goals`/`intelligence` を grep |
| web/server.py のセキュリティ | ✅ 堅牢 | Cycle 32: token guard（`compare_digest`）+ パストラバーサル guard（`resolve`+`relative_to`、3経路）+ SPA fallback は固定 index.html |
| claude CLI 不在/失敗時の degradation | ✅ 堅牢 | Cycle 32: `ClaudeUnavailableError`/`ClaudeRateLimitedError`・Timeout/OSError ハンドリング・web で明示メッセージ・`/api` status |
| 提案順序の決定性 | ✅ 解決済 | Cycle 31: `get_all/get_pending_improvement_proposals` は created_at 降順。Pydantic ISO の文字列ソート＝時系列 |
| atelier GUI ページの派生ロジック | ✅ 回帰テスト追加 | Cycle 32: Observatory（degradation/daemon ラベル）+ Pantheon（filter）。スモーク→意味あるテストへ |
| atelier オンボーディング: claude 認証状態の可視化 | ✅ 実装済 | Cycle 34: `ClaudeStatusBanner`（`/api/platform/status` の `has_llm===false` 時のみ全ページ警告＋Handbook 誘導・fail-safe） |
| publishing 投稿前バリデーション（preview＋live 両経路） | ✅ 実装済 | Cycle 35: `base._preview` が空コンテンツを弾き X は280字超を警告。Cycle 36: 共有 `_is_empty_content`/`EMPTY_CONTENT_ERROR` で note/wordpress の `_publish_live` にも空ガード（ブラウザ未起動・preview≥live を一様化）。wp live の回帰テストも新設 |
| .claude/ の CC ベストプラクティス整合 | ✅ 整合 | Cycle 31: trend-watcher 照合（Fable 5 heavy・Opus 4.8 trailer・選択的 MCP・秘密なし） |
| 基盤 state JSON 書き込みの原子性 | ✅ 実装済 | Cycle 37: `core/persistence.atomic_write_text`（mkstemp+os.replace+失敗時 cleanup）を `core/state/manager.py`（8 site）・`core/platform/state.py`（3 site）の非アトミック書き込みへ適用。torn write（クラッシュ/並行書き込みでの切り詰め）を防止し silent-drop の元凶を構造的に断つ。回帰テスト `tests/test_persistence.py`（8本: 原子性/孤児.tmp不残/失敗時の元ファイル無傷/read-modify-write 往復） |

> ⚠️ 台帳の前提が崩れる変更（対象ファイルの編集・リファクタ）が入ったら、その行だけ再検証する。
> 台帳は「いつ・何を根拠に」確認したかを残すので、git log と突き合わせて陳腐化を判定できる。

---

## §B. 次に着手すべき大きめ候補（小スライスが尽きた今、ここから選ぶ）

小スライスの正確性/堅牢性候補は §A のとおり枯渇。以下は**より大きい・要設計・一部は有人**の高価値候補。
それぞれ「なぜ価値があるか / 1サイクルで切れる最初のスライス / リスク・前提」を付す。

### B-1. Publishing 実機 E2E ハードニング（収益化の最終1マイル）  🟡 一部出荷（Cycle 35–36）
- **価値**: note/X/WordPress の `_publish_live(assisted)` は実装済だが**実機 E2E 未検証**。公開製品の核。
- ~~**最初のスライス（無人で安全）**: dry-run/プレビュー経路・投稿前バリデーション~~
  → **Cycle 35 で出荷済**（preview の空拒否＋X 文字数警告＋回帰テスト）。
- ~~**live の空コンテンツ検証**（preview≥live を一様化）~~ → **Cycle 36 で出荷済**（note/wordpress の
  `_publish_live` に共有空ガード・ブラウザ未起動・wp live 回帰テスト新設）。
- **次のスライス（残り）**: 実機 E2E（**実投稿は有人時のみ**・承認ゲートを越える実 POST は無人運転で
  行わない）。無人で進められるのは失敗時エラー面・セッション期限切れ検知などの追加ハードニングまで。
- **リスク**: 実投稿は不可逆・外部公開。資格情報に触れない。Playwright MCP で UI 駆動は可。

### B-2. 初回起動 / オンボーディング UX（"誰もが欲しがる"の入口）  🟡 一部出荷（Cycle 34）
- **価値**: 新規公開ユーザーが最初に触れる体験。`core/ui/setup_wizard.py` は存在するが、
  atelier GUI 側の first-run 導線（claude 未認証時の案内・最初の Org 作成への誘導）が手薄。
- ~~**最初のスライス**: atelier で claude status を読んで未認証/不在時に明示パネルを出す~~
  → **Cycle 34 で出荷済**（`ClaudeStatusBanner`、`has_llm===false` 時のみ全ページ警告＋Handbook 誘導）。
- **次のスライス（残り）**: 組織がゼロのときの「最初の Organization を作る」誘導（empty-state CTA →
  `pantheon org create` 相当 or `/api` 経由の作成フロー）。初回ウィザード（`setup_wizard.py`）の GUI 露出。
- **リスク**: 低〜中（作成フローは書き込み操作を含むので Confirm
  や明示同意が要る）。GUI スライスは frontend-dev へ委譲。

### B-3. atelier の運用ビュー拡充（daemon/usage の専用面）
- **価値**: Observatory は要約のみ。24h 自律基盤の運用者向けに daemon 制御・usage 履歴・rate-limit
  状況の専用ビューがあると "self-evolving org" の可観測性が上がる。
- **最初のスライス**: 既存 `/api/daemons/status`・`/api/usage/summary` を使う読み取り専用の詳細パネル1枚。
- **リスク**: daemon の start/stop を GUI から叩く場合は破壊操作＝ConfirmDialog 必須・要慎重設計。読み取りのみなら低。

### B-4. 監査の網を細かくして基準を上げる（メタ）
- **価値**: §A で粗い網は通過。次は**プロパティ/ファズ的テスト**や**並行性**（複数デーモン同時稼働時の
  state 競合）など、これまでの単体監査が拾えない層へ網を細かくする。
- **最初のスライス**: 1つのサブシステム（例: state manager の並行 read/write）に絞った競合テスト。
- **リスク**: 中（並行テストはフレークになりやすい — 決定的に書く）。
- **follow-up（Cycle 37 由来）**: 既存のコピペ・アトミック書き込み（`content_jobs.py`/`publish_jobs.py`/
  `business_store.py` の簡易 `.json.tmp` パターンは**失敗時に孤児 .tmp を残す**）を共有
  `core/persistence.atomic_write_text`（堅牢版・失敗時 cleanup）へ寄せて DRY 化。あわせて残る直接
  `write_text`/`json.dump` の書き込み site（daemon が書く store 等）を監査し、torn write クラスを完全に閉じる。

---

## 運用メモ
- このバックログは `/evolve` 専用。実装が進んだら該当 §B 項目を消し、確定した不変条件は `docs/design/` へ。
- §A は「やらないことリスト」として機能する（churn 防止）。
</content>
