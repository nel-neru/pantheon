---
name: repocorp-llm-foundation
description: RepoCorp AI 改善プロジェクトの現在状態スナップショット（アーキ確立→WebGUI→自己改善→ターミナル/モード→100件改善ループ）
metadata: 
  node_type: memory
  type: project
  originSessionId: eba7f14c-f146-4c27-8f44-cb0ac2502252
---

## プロジェクト
RepoCorp AI（`/Users/masaoka/Downloads/repocorp_ai`）= 開発者が自己成長型AI組織を作り、CLI/WebGUI/自律デーモンでコード分析→改善提案→承認→自己改善を回すプラットフォーム。目標は「APIキーさえあればどのLLMでも全機能」かつ「WebGUIからCore自身を自律改善」。

## 確立済みアーキテクチャ（Phase 1–4 完了）
- **LLM抽象 `core/llm/`**: `LLMProvider`(anthropic/openai/groq/github_models/gemini) + `client.py`(同期ブリッジ`LLMClient`/`get_default_llm_client`/`get_configured_llm_provider`) + `tool_schema.py`(tool中立化) + `json_extract.py` + `capabilities.py` + `model_registry.py` + `retry.py`(`LLMError`/`call_with_retry`=timeout+指数バックオフ) + `usage.py`(`UsageTracker`)。全 generate は retry でラップ＆usage記録。
- **2平面の設定**: ビルド時=`AGENTS.md`(正典)+各ツールへのリダイレクト(CLAUDE.md/GEMINI.md/.cursor/.github)。実行時=`skills/*.yaml`+`agents/definitions/*.yaml`+`core/llm`。`skills//agents//commands/` は RepoCorp 実行時概念で `.claude/` とは無関係。
- **WebGUI**: React(`web/frontend`, dist が正典, 旧 web/static は `web/legacy/` へ退避)。10+1画面（+ターミナル）。Settings に provider capabilities/モデル/実行モード/トークン使用量。
- **自己改善**: `agents/core_improvement_agent.py`(LLM編集→`SafeChangeExecutor`でテスト検証/反復/複数ファイル原子適用→検証済みdiff, 既定validate_only) → `POST /api/core/improve` → `ImprovementProposal`(PolicyEngineでCore変更=human_required) → 承認は既存フロー(検証済みcontentをサイドカーから直接適用)。UI: `components/CoreImprovePanel.tsx`。
- **実行モード(API/CLI)**: `core/execution/cli_registry.py`(claude/codex/gemini/aider/opencode, PATH検出) + gui_settings.execution_mode/cli_tool + `/api/execution/modes`。
- **cmux再現ターミナル**: `web/terminal.py`(PTY, localhost限定+Host許可リスト+Origin検証, BEL通知, gitブランチ, atexit終了) + `/api/terminal/sessions` + `/ws/terminal/{id}` + `components/TerminalView.tsx`(xterm.js) + `pages/TerminalPage.tsx`(縦タブ/状態/青リング/CLI起動)。実シェル prompt 実機確認済。

## Phase 5: 100件改善ループ（進行中）
- 生きたチェックリスト＝**`docs/improvement_backlog.md`**（A:セキュリティ〜J:観測性、優先度付き、各項目に解決手段、進捗ログに研究知見と検証結果）。方針「deep-research→ベストプラクティス実装→pytest/vitest/ruff緑→チェック」を反復。
- **完了 70/100**: Iter1-9（A1,A3,A4,A6,C2,D5,J1,J8/B2,B3,B9,B10/H1,H6,H7/F4,F5,F12/B7/E1,E9,E10,D8,G5,I1,I2/D4,D6/A7,J7,I3/G1,G2,G8）, Iter10(B4), Iter11(A8/A2/A12), Iter12(B1/B11/B12・F1), Iter13(J2/J3/J4/D10・E5監査), Iter14(C1/C5/C11/C3), Iter15(E3), Iter16(F6/F9/F11), Iter17(F7 cov70%/H2/H8/H10), Iter18(I4/I5/I7/I8 docs), Iter19(F2 e2e承認PR), Iter20(A9 WS上限/A10/A11/G7), Iter21(F10 CLIスモーク), Iter22(J5 ログローテ)。新規: `core/llm/json_mode.py`, `core/logging_config.py`, `core/metrics/request_metrics.py`。共有 `core/io_utils.atomic_write_text`。
- **B4 ネイティブJSONモード(Iter10)**: capabilities `supports_json_mode` を openai/groq/github_models/gemini で True 化。各 `generate()` に `json_mode` 引数（OpenAI互換=`response_format` json_object＋"json"語補完, Gemini=`response_mime_type`, Anthropic=受理のみ＝堅牢抽出継続）。`generate_json` は capabilities 連動でネイティブ要求し例外時は通常生成へフォールバック（純上積み）。同期 `LLMClient.generate_json` も provider 経路へ統一。
- セキュリティ研究知見: localhost bind不十分(DNSリバインディング)→Host許可リスト(`TrustedHostMiddleware`); WS=CSWSH→Origin検証; keyring=OSネイティブ(A5後続)。

## 検証コマンド / 制約
- `python -m pytest tests/ -q`（現在 **881 passed**, カバレッジ76%）/ `npm --prefix web/frontend run test`（**85**）/ `ruff check .`（**0**）/ `make verify` / `make cov`（F7: --cov-fail-under=70）。
- 新規環境変数（任意）: `REPOCORP_API_TOKEN`（A2認証）, `REPOCORP_MAX_BODY_BYTES`（A8, 既定10MiB）, `REPOCORP_LOG_FORMAT=json`/`REPOCORP_LOG_LEVEL`（J2）。新エンドポイント `GET/DELETE /api/metrics`（J4）, 全応答に `X-Request-ID`（J3）。
- 規約: 新規.pyは`from __future__ import annotations`; `datetime.utcnow()`禁止; テストは`tests/`; Web変更は404/SPA挙動維持＋HelpPage更新; LLMは`core/llm`経由(特定SDK直結禁止)。
- 安全則: エージェント`__init__`既定は不変(キー無し=stub維持)、注入は呼び出し側。`get_default_llm_client`はキー無しでNone。サーバは`settings=_load_gui_settings()`を渡す。この開発機には github_models キーが実在。

## 残 30 件（2026-06-03 時点）
- **自動化可・低リスク（継続中）**: B5(stream+tools=設計上の制約を明文化), B6(reasoning_effort 配線), B8(長文トリム), C4(cwd方針 doc), D2/D7/D9/D11/D12(監査+小修正), E6/E7/E8(監査), J6(error hook 任意), I6(OpenAPI examples).
- **要スコープ判断（ユーザー確認）**: D1(broad except 60ファイル=段階的), G3/G6/G4/G11/G12(フロント a11y 横断監査=vitest要), H3(mypy 段階導入=既存型エラー多数), H4(eslint=既存lint多数), F3(jest-axe). 
- **大型/自動検証困難（要スコープ判断 or 実機）**: C6/C12(CLIワークスペース統合), C7/C8/C9(cmux分割/埋込/socket), A5(keyring), E2/E4(WS統一/検索index), G9(xterm SR), G10(i18n), 5provider 実機検証, B4後続(Anthropic tool強制JSON)。
計画書: `~/.claude/plans/ai-api-core-core-webgui-ai-immutable-alpaca.md`。
