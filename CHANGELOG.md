# Changelog

本プロジェクトの主要な変更履歴。形式は [Keep a Changelog](https://keepachangelog.com/) に準拠し、
バージョニングは [SemVer](https://semver.org/) を目安とする。

## [Unreleased]

横断監査バックログ（[`docs/improvement_backlog.md`](docs/improvement_backlog.md)）に基づく改善イテレーション。

### Added
- ネイティブ JSON モード（B4）: provider capabilities 連動で `response_format` / `response_mime_type` を要求し、失敗時は堅牢抽出にフォールバック（`core/llm/json_mode.py`）。
- 任意のローカル API トークン認証（A2, 既定無効）と、リクエストボディサイズ上限（A8）。
- 構造化ログ（J2, `REPOCORP_LOG_FORMAT=json`）/ 相関ID（J3, `X-Request-ID`）/ リクエストメトリクス（J4, `GET /api/metrics`）。
- ターミナル: アイドルセッションの自動 GC（C1）、ワークスペースのリネーム（C11, `PATCH /api/terminal/sessions/{id}`）、Windows 非対応の明示（C5）。
- `LLMConfig.from_settings()`（B1）、provider インスタンスのキャッシュ（B11）。
- カバレッジゲート（F7, `--cov-fail-under=70`）、pre-commit の ruff lint（H2）、`CONTRIBUTING.md`（H8）。

### Changed
- 全提案の横断ロードをシグネチャでキャッシュし N+1 を解消（E3）。
- 秘匿値マスキング（A6）を `core/logging_config.py` に集約（後方互換のため `web/server.py` にエイリアス）。

### Tests
- プロバイダー契約テスト（B12/F1）、PolicyEngine 境界（F6）、`json_extract` プロパティ（F9）、UpdateHub ブロードキャスト（F11）。

## 基盤（Phase 1–4, 〜2026-05）

- LLM 抽象 `core/llm/`（5 プロバイダー、同期ブリッジ、retry、usage、capabilities、model_registry、tool 中立化）。
- WebGUI（React 正典）、Core 自己改善ランタイム、cmux 風埋め込みターミナル、API/CLI 実行モード。

[Unreleased]: https://github.com/nel-neru/repocorp_ai/commits/main
