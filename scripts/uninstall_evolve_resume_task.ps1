# "Pantheon Evolve Resume" タスクをタスクスケジューラから解除する。
#
# 使い方:  powershell -ExecutionPolicy Bypass -File scripts\uninstall_evolve_resume_task.ps1
$ErrorActionPreference = "Continue"

schtasks /Delete /F /TN "Pantheon Evolve Resume" 2>$null | Out-Null
Write-Host "[OK] タスク 'Pantheon Evolve Resume' を解除しました（存在しなかった場合も成功扱い）。"
