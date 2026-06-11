# Pantheon 完全ガイド（人間用）

このドキュメントは「Pantheon をゼロから起動して使いこなす」ための、人間向けの完全ガイドです。
インストールから、人間用可視化サイト（Web GUI）の使い方、CLI 早見表、典型ワークフロー、
トラブルシュートまでを 1 枚にまとめています。

> 開発者向けの規約・テスト基準は [`README.md`](../README.md) / [`AGENTS.md`](../AGENTS.md) /
> [`CLAUDE.md`](../CLAUDE.md) を参照してください。本ガイドは「使う人」向けです。

---

## 目次

1. [Pantheon とは](#1-pantheon-とは)
2. [前提: Claude Code CLI](#2-前提-claude-code-cli)
3. [導入の3通り](#3-導入の3通り)
4. [起動する](#4-起動する)
5. [人間用可視化サイト（Web GUI）の歩き方](#5-人間用可視化サイトweb-gui-の歩き方)
6. [CLI コマンド早見表](#6-cli-コマンド早見表)
7. [典型ワークフロー](#7-典型ワークフロー)
8. [データはどこに保存される？](#8-データはどこに保存される)
9. [トラブルシューティング](#9-トラブルシューティング)
10. [自分でビルド／配布する](#10-自分でビルド配布する)

---

## 1. Pantheon とは

**個人開発者が自分専用の「自己成長型 AI 組織（Organization）」を立ち上げ、コードの分析・改善提案・
承認・適用・自己改善のサイクルを回すためのプラットフォーム**です。実体は次の3層構成です。

- **CLI**（`pantheon` / `Pantheon.exe`）— すべての操作の入口。
- **Web GUI（FastAPI + React）** — 「人間用可視化サイト」。ダッシュボード・依存グラフ・Kanban・
  チャットなど 13 ページ。`pantheon serve` で起動し `http://localhost:7860` で開きます。
- **自律実行パイプライン** — 分析→提案→承認→適用と、定期実行するデーモン。

すべての AI 生成は**ローカルの `claude` CLI（Claude Code）経由**で行われ、**API キーは使いません**。

---

## 2. 前提: Claude Code CLI

Pantheon の「考える」部分（コード分析・チャット・改善適用など）は、外部の **`claude` CLI** に
委譲します。これは Pantheon に同梱できない外部ツールなので、**別途インストールと初回ログインが必要**です。

```powershell
claude          # 初回のみ実行してログイン（以後は認証情報が再利用される）
```

- 確認: `claude --version` が動けば OK。
- 入っているか不安なときは Pantheon 側で `Pantheon.exe doctor`（または `pantheon doctor`）で診断できます。
- **claude が無くても、GUI・ダッシュボード・各種閲覧機能は動きます。**生成系の操作だけが claude を要求します。

> 任意で `PANTHEON_CLAUDE_BIN` 環境変数に `claude` バイナリのパスを指定して上書きできます。

---

## 3. 導入の3通り

### (A) インストーラで入れる（いちばん簡単・配布相手向け）

1. `Pantheon-Setup.exe` を実行する。
2. ウィザードに従ってインストール（管理者権限は不要）。スタートメニューに **Pantheon** が登録されます。
3. 初回起動前に [`claude` の用意](#2-前提-claude-code-cli) を済ませてください。

> Python も Node.js も不要。必要なものは exe にすべて同梱されています（生成に使う `claude` を除く）。

### (B) 配布フォルダを直接実行（ポータブル）

ビルド済みの `dist/Pantheon/` フォルダをそのままコピーし、`Pantheon.exe` をダブルクリックするだけ。
インストール不要で持ち運べます。

### (C) ソースから動かす（開発者向け）

```powershell
git clone https://github.com/nel-neru/pantheon.git
cd pantheon
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1          # 拒否される場合: Set-ExecutionPolicy -Scope Process RemoteSigned
python -m pip install --upgrade pip
python -m pip install -e ".[dev,web]"
```

以後 `pantheon <command>` が使えます（venv を有効化しない場合は `.\.venv\Scripts\pantheon.exe <command>`）。

---

## 4. 起動する

### いちばん簡単: ダブルクリック

`Pantheon.exe` を**ダブルクリック**（または引数なしで実行）すると、**Web GUI が起動し、
既定ブラウザが自動で `http://localhost:7860` を開きます**。表示されるコンソールにはサーバの
ログと URL が出ます。閉じるとサーバも止まります。

### ターミナルから（CLI も同じ実行体で使える）

```powershell
Pantheon.exe                       # 引数なし → GUI 起動＋ブラウザ自動オープン
Pantheon.exe serve                 # 明示的に GUI 起動（http://localhost:7860）
Pantheon.exe serve --port 8080     # ポート変更
Pantheon.exe serve --no-browser    # ブラウザを自動で開かない
Pantheon.exe chat                  # CLI チャット
Pantheon.exe analyze --org-name "MyApp"
Pantheon.exe --help                # 全コマンド一覧
```

ソース実行（C）の場合は `Pantheon.exe` を `pantheon` に読み替えてください。

### 開発モード（ホットリロード）

フロントエンドを編集しながら使う場合のみ:

```powershell
pantheon serve --port 8000         # ターミナル1: バックエンド/API
cd web/frontend; npm run dev       # ターミナル2: Vite (http://localhost:5173)
```

Vite の dev サーバは `/api` と `/ws` を `http://localhost:8000` にプロキシします。

---

## 5. 人間用可視化サイト（Web GUI）の歩き方

`http://localhost:7860` を開くと、左サイドバーから 13 ページに移動できます（既定は「チャット」）。

| ページ | ルート | 何ができるか |
|---|---|---|
| **チャット** | `/chat` | 自然言語で AI 組織に依頼。`/help` `/analyze` `/goal` 等のスラッシュコマンドも使える。入口に最適 |
| **組織** | `/orgs` | Organization の作成・編集・削除。対象リポジトリと目的を登録 |
| **分析** | `/analyze` | リポジトリを分析し、改善提案を生成。最大ファイル数を指定、ログがライブ表示 |
| **ゴール** | `/goals` | 「達成したいこと」を自然言語で入力して自律実行。履歴も確認 |
| **改善提案** | `/proposals` | 生成された提案をレビュー。ステータス/カテゴリ/優先度で絞り、**承認・却下** |
| **エージェント** | `/agents` | 登録済み Specialist Agent とスキル、オーケストレーション推奨を一覧 |
| **Atlas** | `/atlas` | リポジトリの**依存グラフ・使用フロー・CLI コマンド木・API ルートマップ・サブシステム**を可視化 |
| **セッション** | `/sessions` | 各エージェントの実行状態・終了コード・claude 出力ログをライブ確認 |
| **作業ボード** | `/board` | キュー/実行中/レビュー/完了 の Kanban。人間がタスクを起票・キャンセル |
| **プラットフォーム** | `/dashboard` | 全体のヘルス/バランススコア、組織一覧、**デーモンの起動・停止** |
| **データ管理** | `/data` | ゴール履歴の確認・クリア、`knowledge/` ファイルの閲覧・編集・作成・削除 |
| **設定** | `/settings` | LLM プロバイダ表示、デーモンの実行間隔/最大ファイル数、保存先情報 |
| **ヘルプ** | `/help` | アプリ内ガイド（本ガイドの要約版）。概要 / 各画面 / 設定・CLI・トラブルの3タブ |

上部バーには、全体検索（組織・エージェント・提案・ゴール）、リアルタイム接続状態、通知、
ダーク/ライト切替があります。OpenAPI ドキュメントは `http://localhost:7860/docs`。

---

## 6. CLI コマンド早見表

`Pantheon.exe <command>`（ソース実行なら `pantheon <command>`）。`--help` を付けると各コマンドの詳細が出ます。

| コマンド | 用途 |
|---|---|
| `init` | グローバルプラットフォームを初期化（最初に1回） |
| `org add --name N --repo PATH --purpose "..."` | Organization（対象リポジトリ）を登録 |
| `org list` / `org show --org-name N` / `org remove --org-name N` | 組織の一覧・詳細・削除 |
| `analyze --org-name N` | リポジトリを分析して改善提案を生成 |
| `proposals --org-name N` | 改善提案の一覧 |
| `proposal show <id>` / `proposal reject <id>` / `proposal apply <id>` | 提案の詳細・却下・適用 |
| `approve <id> --org-name N` | 提案を承認して適用フェーズへ |
| `query` | 提案などを条件で問い合わせ |
| `chat` | 自然言語チャット（最初のおすすめ） |
| `serve [--host H] [--port P] [--no-browser]` | Web GUI を起動 |
| `atlas` | Repository Atlas を生成（CLI 出力） |
| `doctor [--fix]` | 健康診断（claude 検出など）。`--fix` で自動修復 |
| `platform status` / `platform run-all` | 全組織横断のダッシュボード / 改善サイクル一括実行 |
| `platform config` / `platform config set K V` / `platform logs` | 設定の表示・更新・ログ |
| `platform backup` / `platform restore` | プラットフォーム状態のバックアップ・復元 |
| `daemon start` / `daemon stop` / `daemon status` | 自律改善デーモンの起動・停止・状態 |
| `goal run` / `goal status` | 自然言語ゴールの実行・状態 |
| `agent list` / `agent status` | エージェント一覧・稼働状況 |
| `orchestration analyze \| history \| capabilities \| self-review` | オーケストレーションの分析・履歴・能力・自己レビュー |
| `hq diagnose \| propose \| apply \| outcomes` | 本社（プラットフォーム自身）の診断・提案・適用・結果 |
| `session start \| list \| show \| stop \| resume \| doctor` | エージェントセッションの管理 |
| `version` | バージョン表示 |

---

## 7. 典型ワークフロー

```powershell
# 0) 事前準備（初回のみ）
claude                                      # claude にログイン
Pantheon.exe init                           # プラットフォーム初期化

# 1) 対象リポジトリを組織として登録
Pantheon.exe org add --name "MyApp" --repo C:\path\to\app --purpose "ECサイト改善"

# 2) 分析して改善提案を作る
Pantheon.exe analyze --org-name "MyApp"

# 3) 提案を確認して承認・適用
Pantheon.exe proposals --org-name "MyApp"
Pantheon.exe approve <proposal-id> --org-name "MyApp"
```

GUI で進める場合は **チャット**で「MyApp のコードをレビューして」のように頼むか、
**分析 → 改善提案（承認）→ プラットフォーム**の順に画面を移動します。

---

## 8. データはどこに保存される？

- **グローバル状態**: `~/.pantheon/`（全組織横断。`platform.json`、`state.db`、`chat_sessions/`、
  `gui_settings.json`、デーモンの `daemon.pid` / `daemon.log` など）
- **リポジトリ固有**: `<対象リポジトリ>/.pantheon/`（その repo の提案・決定履歴）

exe 化しても保存先は変わりません（ユーザーホーム配下）。アンインストールしても `~/.pantheon` は
残るので、設定や履歴は保持されます。

---

## 9. トラブルシューティング

| 症状 | 対処 |
|---|---|
| 生成系コマンドが「Claude Code CLI が必要」で止まる | `claude` をインストールし一度 `claude` を実行してログイン。`Pantheon.exe doctor` で確認 |
| ポート 7860 が使用中 | `Pantheon.exe serve --port 8080` のように別ポートで起動 |
| ブラウザが自動で開かない | 表示された URL（`http://localhost:7860`）を手動で開く。`--no-browser` を付けていないか確認 |
| GUI は出るが分析・チャットが失敗 | ほぼ claude 未ログイン。`claude` 実行で認証を確認 |
| **「スマート アプリ コントロールがブロックしました」/「Windows によって PC が保護されました」** | 未署名 exe を Windows 11 の SAC / SmartScreen が止めています。下の [SAC / SmartScreen でブロックされる](#sac--smartscreen-でブロックされる) を参照 |
| PowerShell で実行ポリシー拒否（ソース実行時） | `Set-ExecutionPolicy -Scope Process RemoteSigned` |
| GitHub への PR 作成が失敗 | `git` のインストールと `GITHUB_TOKEN` の設定を確認（PR 機能のみ必要） |
| 設定を取得できない / 画面が出ない | サーバを再起動（`Pantheon.exe serve`）。`Pantheon.exe doctor --fix` も試す |

> 開発者向け補足: Windows では `chmod` 由来の**既知2テスト失敗**があり回帰ではありません（詳細は `CLAUDE.md`）。

### SAC / SmartScreen でブロックされる

PyInstaller で作った `Pantheon.exe` は**コード署名されていない**ため、Windows 11 の
**スマート アプリ コントロール（SAC）**や **SmartScreen** が「未知のアプリ」として実行を止めることがあります
（メッセージ例:「スマート アプリ コントロールがこのアプリの一部をブロックしました」「Windows によって PC が保護されました」）。

対処は状況に応じて次のいずれか。

1. **自分のマシンで今すぐ使いたいだけ**: exe を作らず、ソース実行の launcher を使う。
   `claude` を動かしている開発機なら、これがいちばん簡単で安全です。

   ```powershell
   .\.venv\Scripts\pantheon.exe serve     # python.exe 経由なので SAC に止められない
   #  または  python main.py serve
   ```

   この `pantheon.exe`（venv 内）は signed な `python.exe` を起動するだけなので SAC の対象外です。
   デスクトップにこのコマンドのショートカットを置けば「ダブルクリック起動」も実現できます。

2. **SmartScreen だけの場合（SAC オフ）**: ダウンロードファイル由来の警告なら、exe を右クリック →
   プロパティ → 「許可する（ブロックの解除）」、または PowerShell で `Unblock-File .\Pantheon.exe`。
   実行時の SmartScreen 青画面は「詳細情報」→「実行」で続行できます。
   （**SAC が「オン」の場合はこの方法では解除できません** — 3 か 4 が必要）。

3. **SAC をオフにする**: 設定 → プライバシーとセキュリティ → Windows セキュリティ →
   アプリとブラウザーの制御 → 「スマート アプリ コントロール」→ オフ。
   ⚠️ **一度オフにすると、Windows をクリーンインストールするまで再びオンにできません。**
   セキュリティを下げる操作なので、自分の開発機に限って判断してください。

4. **配布するなら exe をコード署名する（本命）**: 署名済みの実行体は SAC / SmartScreen に信頼されます。
   詳細は [10 章の「配布時のコード署名」](#配布時のコード署名) を参照。

---

## 10. 自分でビルド／配布する

リポジトリには、ワンクリック exe とインストーラを作るための一式が `packaging/` にあります。

```powershell
# 前提: ソース導入(C)済み + Node.js(フロントビルド用)
powershell -ExecutionPolicy Bypass -File packaging\build.ps1
```

このスクリプトは順に実行します。

1. **フロントエンドビルド**: `web/frontend` で `npm run build` → `web/dist`
2. **exe 生成**: PyInstaller（`packaging/pantheon.spec`）で `dist/Pantheon/Pantheon.exe`（onedir）
3. **インストーラ生成**: Inno Setup（`packaging/pantheon.iss`）で `dist/Pantheon-Setup.exe`

オプション:

- `-SkipFrontend` … `web/dist` が既にある場合、フロントビルドを省略
- `-SkipInstaller` … exe フォルダまでで停止（インストーラを作らない）

Inno Setup（`iscc`）が見つからない場合は exe フォルダまでで停止します。導入は:

```powershell
winget install JRSoftware.InnoSetup
```

### 配布時のコード署名

PyInstaller の出力は**未署名**なので、配布相手の Windows 11 では SAC / SmartScreen に止められます
（[9 章の SAC 対処](#sac--smartscreen-でブロックされる) 参照）。広く配るなら**コード署名証明書**で
署名するのが本命です。

- 署名対象は `dist/Pantheon/Pantheon.exe`（インストーラも作るなら `dist/Pantheon-Setup.exe`）。
- コマンド例（証明書を持っている場合）:

  ```powershell
  signtool sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 ^
    /f mycert.pfx /p <password> dist\Pantheon\Pantheon.exe
  ```

- 証明書の種類による違い: **OV 証明書**は SmartScreen の評価が貯まるまで警告が残ることがあります。
  **EV 証明書**は最初から信頼されやすく、SAC の通過も安定します。
- 自分の開発機だけで使うなら署名は不要です（[9 章](#sac--smartscreen-でブロックされる) の方法 1〜3）。

> 署名を `build.ps1` に組み込みたい場合は、PyInstaller の後・Inno Setup の前に `signtool sign ...` の
> ステップを追加します（証明書のパス／パスワードは環境変数や引数で渡す）。

### 仕組みのメモ（なぜ exe 一個で動くか）

- 同梱した読み取り専用リソース（`web/dist`・`config`・`skills`・`knowledge`・`agents/definitions`・
  Atlas 用ソース）は、`core/paths.py` の `resource_path()` が exe 化時に `sys._MEIPASS` 配下を返す
  ことで解決されます。
- 引数なし起動で GUI、`--daemon-run` で自分自身を再実行してデーモン化する分岐は `main.py` にあります。
- 生成に使う `claude` だけは外部依存のため同梱されません（[2章](#2-前提-claude-code-cli) 参照）。
