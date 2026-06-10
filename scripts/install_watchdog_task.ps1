# Pantheon watchdog を Windows タスクスケジューラに登録する。
#
#   - "Pantheon Watchdog"       : ログオン時に起動（ユーザーコンテキスト）
#   - "Pantheon Watchdog Guard" : 5 分ごとに起動を試みる保活タスク
#     （単一インスタンスは runner 側の pid ファイルで保証されるため多重起動しない）
#
# これにより PC 再起動（＋ログオン）後に watchdog が自動復帰し、watchdog が
# enabled.json の desired state に従って各 daemon を復元する。
# 管理者権限は不要（現在ユーザーのタスクとして登録）。
#
# 使い方:  powershell -ExecutionPolicy Bypass -File scripts\install_watchdog_task.ps1
#          （または `pantheon daemons watchdog install`）
param(
    [string]$PythonW = ""
)
$ErrorActionPreference = "Stop"

$repo = Split-Path -Parent $PSScriptRoot
if (-not $PythonW) { $PythonW = Join-Path $repo ".venv\Scripts\pythonw.exe" }
if (-not (Test-Path $PythonW)) {
    throw "pythonw.exe が見つかりません: $PythonW （-PythonW で明示指定してください）"
}
$runner = Join-Path $repo "core\_watchdog_runner.py"
if (-not (Test-Path $runner)) { throw "runner が見つかりません: $runner" }
$tr = "`"$PythonW`" `"$runner`""

# ログオン時トリガー（環境によっては非管理者で失敗するため、失敗してもガードタスクで代替）
try {
    schtasks /Create /F /TN "Pantheon Watchdog" /SC ONLOGON /TR $tr | Out-Null
    Write-Host "[OK] タスク 'Pantheon Watchdog' (ONLOGON) を登録しました。"
} catch {
    Write-Warning "ONLOGON タスクの登録に失敗しました（ガードタスクのみで運用します）: $_"
}

schtasks /Create /F /TN "Pantheon Watchdog Guard" /SC MINUTE /MO 5 /TR $tr | Out-Null
Write-Host "[OK] タスク 'Pantheon Watchdog Guard' (5分間隔) を登録しました。"

# 今すぐ起動（登録直後から監視を開始）
try {
    schtasks /Run /TN "Pantheon Watchdog Guard" | Out-Null
    Write-Host "[OK] watchdog を起動しました。ログ: ~/.pantheon/watchdog.log"
} catch {
    Write-Warning "即時起動に失敗しました（次回のガードタスク実行時に起動します）: $_"
}

Write-Host ""
Write-Host "確認:   schtasks /Query /TN `"Pantheon Watchdog Guard`""
Write-Host "状態:   pantheon daemons status"
Write-Host "解除:   powershell -ExecutionPolicy Bypass -File scripts\uninstall_watchdog_task.ps1"
