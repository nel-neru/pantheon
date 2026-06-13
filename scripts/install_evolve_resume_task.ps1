# /evolve 自動再開チェックを Windows タスクスケジューラに登録する。
#
#   - "Pantheon Evolve Resume" : 毎時実行。リポジトリの最終コミットが閾値より古ければ
#     `claude -p` で /evolve を headless 再開する（判定は scripts\evolve_resume.ps1）。
#
# これにより 5h レート制限などで /evolve セッションが停止しても、制限解除後
# 最大1時間以内に自動再開される。PC 再起動後も（ログオンしていれば）有効。
# 管理者権限は不要（現在ユーザーのタスクとして登録）。
#
# ウィンドウ抑止: アクションは powershell を直接呼ばず pythonw.exe（GUI サブシステム
# ＝窓を持たない。watchdog と同じ windowless 実行体）経由で
# scripts\evolve_resume_launcher.py を起動し、そこから powershell を CREATE_NO_WINDOW
# で spawn する。これで毎時起動時にコンソール窓が前面化してフォーカス（とマウス）を
# 奪う問題（全画面ゲームが裏画面へ落ちる）を根絶する。
#
# 使い方:  powershell -ExecutionPolicy Bypass -File scripts\install_evolve_resume_task.ps1
# 一時停止: ~/.pantheon/evolve_resume.disabled を作成
# 解除:    powershell -ExecutionPolicy Bypass -File scripts\uninstall_evolve_resume_task.ps1
param(
    [int]$StaleMinutes = 90,
    [string]$PythonW = ""
)
$ErrorActionPreference = "Stop"

$repo = Split-Path -Parent $PSScriptRoot
$script = Join-Path $repo "scripts\evolve_resume.ps1"
if (-not (Test-Path $script)) { throw "スクリプトが見つかりません: $script" }
$launcher = Join-Path $repo "scripts\evolve_resume_launcher.py"
if (-not (Test-Path $launcher)) { throw "ランチャが見つかりません: $launcher" }
if (-not $PythonW) { $PythonW = Join-Path $repo ".venv\Scripts\pythonw.exe" }
if (-not (Test-Path $PythonW)) {
    throw "pythonw.exe が見つかりません: $PythonW （-PythonW で明示指定してください）"
}

# 窓なし起動: pythonw.exe -> evolve_resume_launcher.py -> (CREATE_NO_WINDOW) powershell
$tr = "`"$PythonW`" `"$launcher`" $StaleMinutes"

# 毎時タスク（watchdog と同様、:00 を避けた開始時刻で負荷の同時集中を避ける）
$start = (Get-Date).AddMinutes(5).ToString("HH:mm")
schtasks /Create /F /TN "Pantheon Evolve Resume" /SC HOURLY /ST $start /TR $tr | Out-Null
Write-Host "[OK] タスク 'Pantheon Evolve Resume' (毎時, 初回 $start) を登録しました。"
Write-Host ""
Write-Host "確認:   schtasks /Query /TN `"Pantheon Evolve Resume`""
Write-Host "ログ:   ~/.pantheon/evolve_resume.log"
Write-Host "一時停止: New-Item ~/.pantheon/evolve_resume.disabled"
Write-Host "解除:   powershell -ExecutionPolicy Bypass -File scripts\uninstall_evolve_resume_task.ps1"
