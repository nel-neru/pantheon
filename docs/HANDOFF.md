# HANDOFF — 引き継ぎ（別デバイス/別セッション用）

> このファイルは **デバイス間移行・セッション引き継ぎの単一の入口**です。
> Claude Code のメモリ（`~/.claude/.../memory/`）はデバイス依存で移行しないため、
> その内容と進捗・再開点をすべてここ（リポジトリ内）に固定しています。

最終更新: 2026-06-03

## 0. まず読む順番

1. [`AGENTS.md`](../AGENTS.md) — プロジェクト正典（概要・規約・テスト手順）
2. **この `docs/HANDOFF.md`** — 現在地と再開方法
3. [`docs/improvement_backlog.md`](improvement_backlog.md) — **生きた100件チェックリスト＋進捗ログ**（作業の本体）
4. [`docs/development/state-snapshot.md`](development/state-snapshot.md) — プロジェクト状態スナップショット（旧メモリの内容）
5. [`docs/development/plan.md`](development/plan.md) — 3フェーズ計画と Phase 1–4 完了記録
6. [`docs/architecture.md`](architecture.md) — アーキテクチャと「エージェントの2平面」

## 1. 新しいデバイスでのセットアップ

全作業はブランチ **`phase5-improvements-handoff`**（コミット `8166c25`〜）にあります。移行は次のどちらか。

**A) git bundle 経由（GitHub 不要・推奨）** — リポジトリ全履歴を 1 ファイルに固めてあります:

```bash
# 1) ~/Downloads/repocorp_ai-handoff.bundle を別デバイスにコピー（USB/クラウド等）
# 2) 別デバイスで:
git clone repocorp_ai-handoff.bundle repocorp_ai
cd repocorp_ai                       # HEAD = phase5-improvements-handoff
git checkout phase5-improvements-handoff
```

**B) GitHub 経由** — `nel-neru/repocorp_ai`（**private**）にブランチを push 済み:

```bash
# nel-neru アカウントでアクセス権があること（private）。SSH または gh 認証。
git clone https://github.com/nel-neru/repocorp_ai.git repocorp_ai && cd repocorp_ai
git checkout phase5-improvements-handoff
# 別デバイスで gh 認証: gh auth login  /  HTTPS なら gh auth setup-git
```

**共通（取得後）:**

```bash
python -m venv .venv && source .venv/bin/activate    # 任意
make install        # Python(-e .[dev,web]+ruff+pytest-cov) と frontend 依存
make build          # web/dist（正典UI）を生成（dist は .gitignore のため各デバイスで要ビルド）
make verify         # lint + test + build + fe-test（CI 同等）
make cov            # カバレッジゲート（--cov-fail-under=70, 現状76%）
```

API キーは `.env`（git 管理外）または Web GUI の Settings に設定（[`docs/security.md`](security.md) 参照）。
この開発機には `GITHUB_TOKEN`（github_models）キーが実在していました（別デバイスには無い前提で）。

## 2. 現在地（Phase 5: 100件改善ループ）

- **進捗: 70/100 完了**。直近セッションで **Iteration 10〜22** を実施（B4 ネイティブJSON〜J5 ログローテ）。
- 全イテレーションで **pytest / ruff / vitest を緑に維持**。
- 検証スナップショット: `pytest` **881 passed**（カバレッジ76%）/ `vitest` **85**/ `ruff` **0**。
- 完了項目の詳細は [`docs/improvement_backlog.md`](improvement_backlog.md) の各 `[x]` と末尾「進捗ログ」を参照（Iteration 単位で何を・なぜ・検証結果まで記録）。

### このセッションで追加された主なもの
- 新規モジュール: `core/llm/json_mode.py`（B4）, `core/llm/trim.py`（B8）, `core/logging_config.py`（J2/J3/A6集約）, `core/metrics/request_metrics.py`（J4）。
- 新規テスト: `test_llm_json_mode` / `test_llm_provider_contract` / `test_observability` / `test_proposals_cache` / `test_policy_boundaries` / `test_json_extract_property` / `test_update_hub` / `test_e2e_approve_pr` / `test_cli_smoke` / `test_llm_trim`。
- 新規 docs: `docs/security.md` / `docs/troubleshooting.md` / `docs/cli_tools.md` / `CONTRIBUTING.md` / `CHANGELOG.md`。
- 新規環境変数（任意）: `REPOCORP_API_TOKEN`(A2), `REPOCORP_MAX_BODY_BYTES`(A8), `REPOCORP_LOG_FORMAT=json`/`REPOCORP_LOG_LEVEL`/`REPOCORP_LOG_FILE`/`REPOCORP_LOG_MAX_BYTES`/`REPOCORP_LOG_BACKUPS`(J2/J5), `REPOCORP_WS_MAX_CONNECTIONS`(A9), `REPOCORP_TERMINAL_IDLE_TTL`/`REPOCORP_TERMINAL_EXITED_TTL`(C1)。すべて `.env.example` に記載。
- 新規エンドポイント: `GET/DELETE /api/metrics`(J4), `PATCH /api/terminal/sessions/{id}`(C11)。全応答に `X-Request-ID`(J3)。

## 3. 再開点（重要 — ここから続ける）

ユーザー指示: **「残りの全項目（大型機能含む）を実装する」**。低リスク項目＋フロントa11y＋ツール＋大型機能をすべて完了させる方針。
直近は **Iteration 23（LLM残り）の途中**で中断:
- ✅ B8（長文トリム）: `core/llm/trim.py` ＋ `tests/test_llm_trim.py` 完了（utility 提供）。
- ⏳ **B6（reasoning_effort 配線）**: 未着手。`json_mode`(B4) と同様に `generate()` に `reasoning_effort` を opt-in で配線（OpenAI o系=`reasoning_effort`、Anthropic=`thinking`）。capabilities 連動＋失敗時フォールバックで安全に。
- ⏳ **B5（streaming + tools）**: 未着手。各 provider の `stream()` は tools 非対応。「明示（docstring/capabilities に制約を記載）」で対応予定。

### 残り 30 件（カテゴリ別 / [`improvement_backlog.md`](improvement_backlog.md) が正）
- **LLM**: B5, B6, B8(済) — B5/B6 が残り。
- **堅牢性（監査＋小修正）**: D1(broad except 60ファイル=段階的), D2, D7, D9, D11, D12。
- **パフォーマンス**: E2(WS統一/ポーリング), E4(検索index), E6(仮想化), E7(indexerキャッシュ), E8(history効率化)。
- **フロント a11y**: G3(キーボード), G4(コントラスト), G6(状態一貫性), G9(xterm SR), G10(i18n基盤), G11(レスポンシブ), G12(aria-describedby)。
- **テスト**: F3(jest-axe)。
- **DX**: H3(mypy 段階導入), H4(eslint+prettier), H5(依存lock), H9(frontend pre-commit)。
- **ドキュメント**: I6(OpenAPI examples/terminal)。
- **観測性**: J6(エラー集約フック 任意)。
- **大型機能**: C6/C12(CLIワークスペース深統合), C7(cmux分割ペイン), C8(cmux埋込ブラウザ), C9(cmux socket API)。
- **実機検証**: 5プロバイダ実機検証（実APIキー要・課金。github_models 以外は要キー。契約テストはモックで網羅済み=B12/F1）。
- **B4後続**: Anthropic の tool 強制 JSON（現状 Anthropic は堅牢抽出にフォールバック）。

### 進め方（確立済みの方法論 — 踏襲すること）
各イテレーションで「**調査 → ベストプラクティス実装 → pytest/vitest/ruff 緑 → バックログにチェック＋進捗ログ追記**」を反復。
1イテレーション = 関連2〜4項目。本番コード変更後は必ず `python -m pytest tests/ -q` と `ruff check .`、フロント変更時は `npm --prefix web/frontend run test` と build を緑に。

## 4. 検証コマンド / 現在値

| ゲート | コマンド | 現在値 |
|---|---|---|
| backend | `python -m pytest tests/ -q` | 881 passed |
| coverage | `make cov`（`--cov-fail-under=70`） | 76% |
| lint | `ruff check .` | 0 |
| frontend | `npm --prefix web/frontend run test` | 85 |
| build | `npm --prefix web/frontend run build` | OK |
| 一括 | `make verify` | — |

## 5. 安全則・設計制約（厳守）

- 新規 `.py` は `from __future__ import annotations` で開始。`datetime.utcnow()` 禁止 → `datetime.now(timezone.utc)`。
- **LLM 呼び出しは必ず `core/llm` 経由**（特定 SDK 直結禁止）。既定 `get_default_llm_client()`、構造化出力 `generate_json`。
- エージェントの `__init__` 既定は不変（キー無し=stub 維持）。注入は呼び出し側のみ。`get_default_llm_client()` はキー無しで `None`。サーバは `settings=_load_gui_settings()` を渡す。
- Web/API 変更時は 404/SPA 挙動を維持（catch-all は未知の `/api/*`・`/ws/*` に 404）。UI ページ追加時は `HelpPage.tsx` と vitest を更新。
- `skills/` `agents/` `commands/` は RepoCorp の**実行時概念**で Claude Code の `.claude/` とは無関係（[`docs/architecture.md`](architecture.md) の「2平面」）。

## 6. git / 移行手順

- 全作業（159ファイル）は **ブランチ `phase5-improvements-handoff` にコミット済み**（`main` は旧 `63fdfeb` のまま）。
- **GitHub `nel-neru/repocorp_ai`（private）にブランチを push 済み**。別デバイスでは nel-neru でアクセスし `git checkout phase5-improvements-handoff`（§1-B）。`gh` は `na-masaoka`/`nel-neru` で認証済み（push は nel-neru で実施。private のため na-masaoka からは見えない点に注意）。
- **オフライン移行用に git bundle も用意**: `~/Downloads/repocorp_ai-handoff.bundle`（全履歴入り、§1-A）。GitHub と等価。
- `web/dist`・`.repocorp/`・`.env`・`.claude/`・`scratch_dot_repocorp/` は `.gitignore` 対象（移行先で再生成 or 各自設定）。
- 旧メモリ実体（`~/.claude/.../memory/repocorp-llm-foundation.md`）は移行不要（内容は [`state-snapshot.md`](development/state-snapshot.md) に固定済み）。新デバイスでは本 HANDOFF を起点に作業を再開できます。
