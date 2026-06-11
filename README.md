# Pantheon

開発者が自分専用の自己成長型 AI Organization を作り、CLI / Web / 自律実行パイプラインで改善を回せるプラットフォームです。

> **使う人向けの完全ガイドは [`docs/GUIDE.md`](docs/GUIDE.md)。** 起動方法・人間用可視化サイト（Web GUI）の歩き方・
> CLI 早見表・トラブルシュートを 1 枚にまとめています。
>
> **exe 一個で起動したい場合**は `packaging/build.ps1` でワンクリック exe（`dist/Pantheon/Pantheon.exe`）と
> インストーラ（`dist/Pantheon-Setup.exe`）を生成できます（[`docs/GUIDE.md` の 10 章](docs/GUIDE.md#10-自分でビルド配布する)）。
> `Pantheon.exe` はダブルクリックで Web GUI が起動し、ブラウザが自動で開きます。

## できること

- `pantheon` CLI で Organization を作成・分析・承認
- FastAPI ベースの Web UI / API を起動
- YAML 定義から Agent / Skill / 組織テンプレートを読み込み
- 自律改善ループで提案を収集・実行

## インストール

リポジトリ直下で **仮想環境 (venv)** を作って依存をインストールします。
有効化すると `python` / `pip` / `pantheon` がそのまま使えます。

Windows (PowerShell):

```powershell
git clone https://github.com/nel-neru/pantheon.git
cd pantheon
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1          # 以後 python / pantheon が使えます
                                       # 実行を拒否される場合: Set-ExecutionPolicy -Scope Process RemoteSigned
python -m pip install --upgrade pip
python -m pip install -e ".[dev,web]"
```

macOS / Linux:

```bash
git clone https://github.com/nel-neru/pantheon.git
cd pantheon
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev,web]"
```

> venv を有効化しない場合は、実体パスで呼べます（例: `.\.venv\Scripts\pantheon.exe --help`、`.\.venv\Scripts\python.exe -m pytest`）。
> `requirements.txt` を使う場合は `python -m pip install -r requirements.txt` でも可です。

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

> **venv を有効化済み・リポジトリ直下にいる前提**です（上の「インストール」参照）。
> 有効化していない場合は `pantheon` を `.\.venv\Scripts\pantheon.exe`、`python` を `.\.venv\Scripts\python.exe` に読み替えてください。

```powershell
python scripts\validate_config.py     # 設定の検証（任意）
pantheon init                          # 初回セットアップ（1回だけ）
pantheon org add --name "MyApp" --repo C:\path\to\app --purpose "ECサイト改善"
pantheon analyze --org-name "MyApp"
pantheon proposals --org-name "MyApp"
pantheon serve                         # Web UI を起動
```

git の pre-commit フックも入れる場合（任意・POSIX シェルが必要。Windows では **Git Bash / WSL** で実行）:

```bash
bash scripts/install_hooks.sh
```

- CLI は `pantheon --help` で確認できます
- Web UI は通常 `http://localhost:7860`
- OpenAPI は `http://localhost:7860/docs`

## pre-commit フック

`bash scripts/install_hooks.sh` で `git commit` 時の pre-commit フックを `.git/hooks/pre-commit` に配置します（POSIX シェル製のため、Windows では **Git Bash / WSL** から実行してください。PowerShell の `bash` 単体では動きません）。

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

venv を有効化していれば:

```bash
python -m pytest tests/ -q --tb=short
```

未有効化なら実体パスで（Windows）:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\ -q --tb=short
```

> Windows では path-separator と `chmod` 由来の **6 件が既知の失敗**（回帰ではありません）。詳細は `CLAUDE.md` / `AGENTS.md` を参照。

## コントリビュート / ライセンス / セキュリティ

- 貢献方法・開発環境・ブランチ運用: [`CONTRIBUTING.md`](CONTRIBUTING.md)
- 脆弱性の報告・セキュリティ特性: [`SECURITY.md`](SECURITY.md)
- ライセンス: [MIT](LICENSE)
