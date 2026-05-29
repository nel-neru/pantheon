# RepoCorp AI

開発者が自分専用の自己成長型 AI Organization を作り、CLI / Web / 自律実行パイプラインで改善を回せるプラットフォームです。

## できること

- `repocorp` CLI で Organization を作成・分析・承認
- FastAPI ベースの Web UI / API を起動
- YAML 定義から Agent / Skill / 組織テンプレートを読み込み
- 自律改善ループで提案を収集・実行

## インストール

```bash
git clone https://github.com/nel-neru/repocorp_ai.git
cd repocorp_ai
python -m pip install --upgrade pip
python -m pip install -e ".[dev,web]"
```

`requirements.txt` を使う場合は次でも可です。

```bash
python -m pip install -r requirements.txt
```

## 初期設定

```bash
cp .env.example .env
```

`.env` には少なくとも 1 つの LLM プロバイダーのキーを入れてください。

- Anthropic: `ANTHROPIC_API_KEY`
- OpenAI: `OPENAI_API_KEY`
- Groq: `GROQ_API_KEY`
- Gemini: `GOOGLE_API_KEY`

GitHub 連携や PR 作成を使う場合は `GITHUB_TOKEN` も設定します。

## クイックスタート

```bash
bash scripts/install_hooks.sh
python scripts/validate_config.py
repocorp init
repocorp org add --name "MyApp" --repo /absolute/path/to/app --purpose "ECサイト改善"
repocorp analyze --org-name "MyApp"
repocorp proposals --org-name "MyApp"
repocorp serve
```

- CLI は `repocorp --help` で確認できます
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
