---
description: 全デーモン（improvement/content/trend/watchdog）の稼働状態・heartbeat・レート制限を一覧する
---

# /daemon-status — 24h 自律基盤の状態を見る

全デーモンの health（pid 生死 × heartbeat 鮮度 × desired state）と、プロセス横断の
レート制限ゲート状態をまとめて表示する。

```powershell
.\.venv\Scripts\python.exe main.py daemons status
```

読み方:

- `[OK]` 健康（heartbeat 新鮮）/ `[HANG]` 生存だが heartbeat 途絶（watchdog の restart 対象）/
  `[DEAD]` enabled なのに死亡（watchdog が起動する）/ `[OFF]` 無効
- 先頭に `[!] レート制限中 — <reset> に自動再開予定` が出ていれば、全デーモンが pause→
  reset 時刻に自動 resume する（「制限解除されたら再開」の実体）。

関連操作:

- 起動/停止: `main.py daemons start|stop <name|all>`（desired state も更新）
- enable/disable のみ: `main.py daemons enable|disable <name>`（プロセスに触れない）
- 自動復旧の常駐登録: `main.py daemons watchdog install`（ONLOGON＋5分ガード、PC 再起動後も復帰）
- 実測トークン/クォータ: `GET /api/usage/summary`（5h/7d 窓＋governor 状態）
