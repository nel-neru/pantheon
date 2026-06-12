# /evolve 自動再開チェックを Windows タスクスケジューラに登録する。
#
#   - "Pantheon Evolve Resume" : 毎時実行。リポジトリの最終コミットが閾値より古ければ
#     `claude -p` で /evolve を headless 再開する（判定は scripts\evolve_resume.ps1）。
#
# これにより 5h レート制限などで /evolve セッションが停止しても、制限解除後
# 最大1時間以内に自動再開される。PC 再起動後も（ログオンしていれば）有効。
# 管理者権限は不要（現在ユーザーのタスクとして登録）。
#
# 使い方:  powershell -ExecutionPolicy Bypass -File scripts\install_evolve_resume_task.ps1
# 一時停止: ~/.pantheon/evolve_resume.disabled を作成
# 解除:    powershell -ExecutionPolicy Bypass -File scripts\uninstall_evolve_resume_task.ps1
param(
    [int]$StaleMinutes = 90
)
$ErrorActionPreference = "Stop"

$repo = Split-Path -Parent $PSScriptRoot
$script = Join-Path $repo "scripts\evolve_resume.ps1"
if (-not (Test-Path $script)) { throw "スクリプトが見つかりません: $script" }

$tr = "powershell -NoProfile -ExecutionPolicy Bypass -File `"$script`" -StaleMinutes $StaleMinutes"

# 毎時タスク（watchdog と同様、:00 を避けた開始時刻で負荷の同時集中を避ける）
$start = (Get-Date).AddMinutes(5).ToString("HH:mm")
schtasks /Create /F /TN "Pantheon Evolve Resume" /SC HOURLY /ST $start /TR $tr | Out-Null
Write-Host "[OK] タスク 'Pantheon Evolve Resume' (毎時, 初回 $start) を登録しました。"
Write-Host ""
Write-Host "確認:   schtasks /Query /TN `"Pantheon Evolve Resume`""
Write-Host "ログ:   ~/.pantheon/evolve_resume.log"
Write-Host "一時停止: New-Item ~/.pantheon/evolve_resume.disabled"
Write-Host "解除:   powershell -ExecutionPolicy Bypass -File scripts\uninstall_evolve_resume_task.ps1"
