# Pantheon watchdog の Windows タスクスケジューラ登録を解除する。
# 実行中の watchdog プロセス自体は `pantheon daemons stop watchdog` で停止すること。
#
# 使い方:  powershell -ExecutionPolicy Bypass -File scripts\uninstall_watchdog_task.ps1
#          （または `pantheon daemons watchdog uninstall`）
$ErrorActionPreference = "Continue"

foreach ($tn in @("Pantheon Watchdog", "Pantheon Watchdog Guard")) {
    schtasks /End /TN $tn 2>$null | Out-Null
    schtasks /Delete /F /TN $tn 2>$null | Out-Null
    Write-Host "[OK] タスク '$tn' を削除しました（存在しなかった場合は無視）。"
}
Write-Host "実行中の watchdog を止めるには: pantheon daemons stop watchdog"
