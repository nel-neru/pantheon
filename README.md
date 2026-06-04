# Pantheon

開発者が自分専用の自己成長型 AI Organization を作り、CLI / Web / 自律実行パイプラインで改善を回せるプラットフォームです。

## できること

- `pantheon` CLI で Organization を作成・分析・承認
- FastAPI ベースの Web UI / API を起動
- YAML 定義から Agent / Skill / 組織テンプレートを読み込み
- 自律改善ループで提案を収集・実行

## インストール

```bash
git clone https://github.com/nel-neru/pantheon.git
cd pantheon
python -m pip install --upgrade pip
python -m pip install -e ".[dev,web]"
```

`requirements.txt` を使う場合は次でも可です。

```bash
python -m pip install -r requirements.txt
```

## 初期設定

Pantheon は **API キーを使いません**。すべての生成はローカルの `claude` CLI（Claude Code）経由で実行されます。初回のみ `claude` で認証してください。

```bash
claude        # 初回のみ: ログイン（以後は認証情報が再利用されます）
```

任意の上書き設定が必要な場合のみ `.env` を作成します（詳細は `.env.example`）。

```bash
cp .env.example .env
```

- `PANTHEON_CLAUDE_BIN` — `claude` バイナリのパス/名前の上書き（既定: `claude`）
- `PANTHEON_DEFAULT_MODEL` — ヘッドレス生成のモデル指定（空なら claude の既定）
- `GITHUB_TOKEN` — GitHub 連携や PR 作成を使う場合のみ

## クイックスタート

```bash
bash scripts/install_hooks.sh
python scripts/validate_config.py
pantheon init
pantheon org add --name "MyApp" --repo /absolute/path/to/app --purpose "ECサイト改善"
pantheon analyze --org-name "MyApp"
pantheon proposals --org-name "MyApp"
pantheon serve
```

- CLI は `pantheon --help` で確認できます
- Web UI は通常 `http://localhost:7860`
- OpenAPI は `http://localhost:7860/docs`

## pre-commit フック

`bash scripts/install_hooks.sh` で `git commit` 時の pre-commit フックを `.git/hooks/pre-commit` に配置します。

このフックでは主に次をチェックします。

- GUI ページ追加時のテスト不足
- UI 変更時の `HelpPage.tsx` 更新漏れ

## ドキュメント

- `docs/api/cli_reference.md`
- `docs/api/rest_api.md`
- `docs/development/conventions.md`
- `docs/development/adding_new_features.md`
- `docs/agents/README.md`

## 検証

```bash
python -m pytest tests/ -q --tb=short
```
