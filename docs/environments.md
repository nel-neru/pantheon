# Pantheon の実行環境（dev / user の完全分離）

Pantheon は **プラットフォームホーム**（状態の保存先ディレクトリ）を切り替えることで、
「開発用」と「ユーザーの実利用」の 2 環境を **データ完全分離** で運用する。切替は環境変数
`PANTHEON_HOME` 1 つ。未設定なら既定の `~/.pantheon`。

## 2 つの環境

| 環境 | 用途 | わかりやすい URL | `PANTHEON_HOME` | データ保存先 | ポート |
|---|---|---|---|---|---|
| **user（本番 / PROD）** | ユーザーが実際に Pantheon を使う本番データ（実 org・収益・コンテンツ） | **http://pantheon.localhost:7860** | **未設定** | `~/.pantheon` | 7860 |
| **dev（開発 / DEV）** | Pantheon 自体の開発・自己改善（Meta org）・evolve・実験 | **http://dev.pantheon.localhost:7870** | `~/.pantheon-dev` | `~/.pantheon-dev` | 7870 |

両者は別ディレクトリ・別ポート・別プロセスで、データは一切混ざらない。
正準ストア（組織・収益 `OutcomeStore`・Playbook・タスクキュー・GUI 設定・チャット履歴）は
すべて `get_platform_home()`（＝`PANTHEON_HOME` 尊重）配下に解決される。

### わかりやすい URL と環境バッジ

- **`*.localhost` は最新ブラウザ（Chrome/Edge/Firefox）が自動的に `127.0.0.1` へ解決する**
  （RFC 6761）。hosts ファイル編集も管理者権限も不要。サーバの束縛先は従来どおり `127.0.0.1`
  のままで、`http://pantheon.localhost:7860` / `http://dev.pantheon.localhost:7870` がそのまま使える
  （`http://localhost:7860` 等も併用可）。
- **GUI 右上に環境バッジを常時表示**: 本番は緑の `PROD`、開発は黄の `DEV`。さらに **DEV では画面
  最上部に黄色の帯**が出るため、本番との取り違えを物理的に防ぐ。判定は `/api/platform/status` の
  `environment` / `env_label`（`core.platform.state.resolve_environment()`）。
- 環境の判定順: ① `PANTHEON_ENV`（`production`/`development`）の明示指定 → ② `PANTHEON_HOME` の
  ディレクトリ名に `-dev` を含むか → ③ 既定は `production`。起動スクリプトは念のため `PANTHEON_ENV`
  も明示する。

## 使い方（Windows PowerShell）

```powershell
# 開発環境を初回セットアップ（一度だけ）
scripts\init-dev.ps1

# ユーザー環境を起動（本番データ・http://pantheon.localhost:7860）
scripts\serve-user.ps1

# 開発環境を起動（隔離データ・http://dev.pantheon.localhost:7870）
scripts\serve-dev.ps1
```

任意の `pantheon` CLI を dev 環境に向けて実行する場合:

```powershell
$env:PANTHEON_HOME = "$HOME\.pantheon-dev"
.\.venv\Scripts\python.exe main.py org list   # dev 環境の org を見る
Remove-Item Env:PANTHEON_HOME                  # ユーザー環境へ戻す
```

## 設計上の不変条件

- **テストは常に隔離**: pytest は `tmp_path` + `monkeypatch` で `get_platform_home` を差し替えるため、
  どちらの実環境のデータにも触れない。
- **ハードコード禁止**: `~/.pantheon` を直書きせず必ず `get_platform_home()` を使う
  （`SETTINGS_FILE` / `CHAT_SESSIONS_DIR` / タスクキュー等を含む）。環境分離を破るため。
- **プロセス起動時に確定**: 一部の module 定数（GUI 設定パス等）は import 時に `PANTHEON_HOME` を
  解決する。dev/user は別プロセスで起動時に環境変数が決まるため分離は保たれる。
