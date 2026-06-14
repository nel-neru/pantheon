# Pantheon の実行環境（dev / user の完全分離）

Pantheon は **プラットフォームホーム**（状態の保存先ディレクトリ）を切り替えることで、
「開発用」と「ユーザーの実利用」の 2 環境を **データ完全分離** で運用する。切替は環境変数
`PANTHEON_HOME` 1 つ。未設定なら既定の `~/.pantheon`。

## 2 つの環境

| 環境 | 用途 | `PANTHEON_HOME` | データ保存先 | 既定ポート |
|---|---|---|---|---|
| **user（実利用）** | ユーザーが実際に Pantheon を使う本番データ（実 org・収益・コンテンツ） | **未設定** | `~/.pantheon` | 7860 |
| **dev（開発）** | Pantheon 自体の開発・自己改善（Meta org）・evolve・実験 | `~/.pantheon-dev` | `~/.pantheon-dev` | 7870 |

両者は別ディレクトリ・別ポート・別プロセスで、データは一切混ざらない。
正準ストア（組織・収益 `OutcomeStore`・Playbook・タスクキュー・GUI 設定・チャット履歴）は
すべて `get_platform_home()`（＝`PANTHEON_HOME` 尊重）配下に解決される。

## 使い方（Windows PowerShell）

```powershell
# 開発環境を初回セットアップ（一度だけ）
scripts\init-dev.ps1

# ユーザー環境を起動（本番データ・http://localhost:7860）
scripts\serve-user.ps1

# 開発環境を起動（隔離データ・http://localhost:7870）
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
