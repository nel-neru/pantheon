# /evolve ループの自動再開チェック（タスクスケジューラから毎時呼ばれる）。
#
# 問題: /evolve を回す Claude Code セッションが 5h レート制限などで停止すると、
# 制限解除後に誰も再点火しない（セッション内の起床予約は制限中に死ぬ）。
# 解決: リポジトリの最終コミット時刻を heartbeat として使い（auto-commit フックが
# 毎ターン commit するため、生きているセッションがあれば必ず新しい）、
# 閾値より古ければ `claude -p` で headless に /evolve を再開する。
# claude 自体がまだ制限中なら失敗してすぐ終わり、次の毎時実行が再試行する
# ＝ 制限解除後、最大1時間以内に自動再開される。
#
# 使い方:   powershell -ExecutionPolicy Bypass -File scripts\evolve_resume.ps1 [-DryRun]
# 無効化:   ~/.pantheon/evolve_resume.disabled を作る（タスクを残したまま一時停止）
# 解除:     scripts\uninstall_evolve_resume_task.ps1
param(
    [int]$StaleMinutes = 90,
    [string]$ClaudeBin = "",
    [switch]$DryRun
)
$ErrorActionPreference = "Stop"

$repo = Split-Path -Parent $PSScriptRoot
$pantheonHome = Join-Path $env:USERPROFILE ".pantheon"
$logPath = Join-Path $pantheonHome "evolve_resume.log"
$lockPath = Join-Path $pantheonHome "evolve_resume.lock"
$disablePath = Join-Path $pantheonHome "evolve_resume.disabled"
New-Item -ItemType Directory -Force $pantheonHome | Out-Null

function Write-Log([string]$msg) {
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $msg"
    Add-Content -Path $logPath -Value $line -Encoding utf8
    Write-Host $line
}

# --- キルスイッチ ---
if (Test-Path $disablePath) {
    Write-Log "skip: $disablePath が存在（無効化中）"
    exit 0
}

# --- 多重起動ガード（前回の headless 実行がまだ生きていれば何もしない） ---
# ただし lock が閾値の2倍より古ければ「生きているが進んでいない」(permission 待ち等の
# ハング) とみなして旧プロセスを止め、再開を続行する（永久 wedge の防止）。
if (Test-Path $lockPath) {
    $oldPid = (Get-Content $lockPath -ErrorAction SilentlyContinue | Select-Object -First 1) -as [int]
    $lockAgeMin = [int](((Get-Date) - (Get-Item $lockPath).LastWriteTime).TotalMinutes)
    if ($oldPid -and (Get-Process -Id $oldPid -ErrorAction SilentlyContinue)) {
        if ($lockAgeMin -lt (2 * $StaleMinutes)) {
            Write-Log "skip: 前回の再開プロセス (pid=$oldPid, lock ${lockAgeMin}分前) が実行中"
            exit 0
        }
        Write-Log "stale-lock: pid=$oldPid が ${lockAgeMin}分 >= $(2 * $StaleMinutes)分 進捗なし → 停止して再開する"
        try { Stop-Process -Id $oldPid -Force -ErrorAction Stop } catch {}
    }
    Remove-Item $lockPath -Force -ErrorAction SilentlyContinue
}

# --- heartbeat: リポジトリの最終コミットからの経過分 ---
$git = "C:\Program Files\Git\cmd\git.exe"
if (-not (Test-Path $git)) {
    $gitCmd = Get-Command git -ErrorAction SilentlyContinue
    if (-not $gitCmd) {
        Write-Log "skip: git が見つかりません（repo=$repo）"
        exit 0
    }
    $git = $gitCmd.Source
}
$lastCommitEpoch = & $git -C $repo log -1 --format=%ct 2>$null
if (-not $lastCommitEpoch) {
    Write-Log "skip: git log が取得できません（repo=$repo）"
    exit 0
}
$ageMinutes = [int](((Get-Date) - ([DateTimeOffset]::FromUnixTimeSeconds([long]$lastCommitEpoch).LocalDateTime)).TotalMinutes)
if ($ageMinutes -lt $StaleMinutes) {
    Write-Log "skip: 最終コミット ${ageMinutes}分前 < 閾値 ${StaleMinutes}分（セッション活動中とみなす）"
    exit 0
}

# --- claude CLI の解決（Pantheon と同じ優先順: 明示指定 > PANTHEON_CLAUDE_BIN > PATH > 既知の場所） ---
if (-not $ClaudeBin) { $ClaudeBin = $env:PANTHEON_CLAUDE_BIN }
if (-not $ClaudeBin) {
    $cmd = Get-Command claude -ErrorAction SilentlyContinue
    if ($cmd) { $ClaudeBin = $cmd.Source }
}
if (-not $ClaudeBin) { $ClaudeBin = Join-Path $env:USERPROFILE ".local\bin\claude.exe" }
if (-not (Test-Path $ClaudeBin)) {
    Write-Log "error: claude CLI が見つかりません（PANTHEON_CLAUDE_BIN を設定してください）"
    exit 1
}

$prompt = "/evolve 自動再開（evolve_resume.ps1 から）: 前回のセッションが中断している。docs/plans/evolution-log.md と git 状態（現在ブランチ・未コミット・未マージの work ブランチ）を確認し、中断点から PDCA サイクルを再開せよ。不変の制約（work ブランチ運用・テストゲート・敵対的レビュー・claude CLI のみ・資格情報に触れない）は /evolve 本文どおり。"

# headless では permission プロンプトに誰も答えられないため、編集系を自動許可する
# （Bash 等は .claude/settings.local.json の allow リストでカバー）。出力形式は
# 製品の生成経路（core/runtime/claude_code.py）と同じ json に揃える。
# 注意: PS5.1 の Start-Process -ArgumentList は空白を含む配列要素を自動クォート
# しない（実証済み）ため、プロンプトは手動でクォートした1本の文字列で渡す。
# $prompt に二重引用符を含めないこと（含めるとここが壊れる）。
$argLine = "-p `"$prompt`" --output-format json --permission-mode acceptEdits"

if ($DryRun) {
    Write-Log "dry-run: 最終コミット ${ageMinutes}分前 >= ${StaleMinutes}分 → 再開対象。実行コマンド: `"$ClaudeBin`" $argLine (cwd=$repo)"
    exit 0
}

# 実行ごとにタイムスタンプ付きログ（前回分の上書き・ファイルロック衝突を回避）。14日より古い分は掃除。
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$outLog = Join-Path $pantheonHome "evolve_resume.$stamp.out.log"
$errLog = Join-Path $pantheonHome "evolve_resume.$stamp.err.log"
Get-ChildItem $pantheonHome -Filter "evolve_resume.*.log" -ErrorAction SilentlyContinue |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-14) } |
    Remove-Item -Force -ErrorAction SilentlyContinue

Write-Log "resume: 最終コミット ${ageMinutes}分前 >= ${StaleMinutes}分 → headless /evolve を起動（bin=$ClaudeBin）"
try {
    $proc = Start-Process -FilePath $ClaudeBin -ArgumentList $argLine -WorkingDirectory $repo -WindowStyle Hidden -RedirectStandardOutput $outLog -RedirectStandardError $errLog -PassThru
} catch {
    Write-Log "error: 起動に失敗しました（次の毎時実行が再試行します）: $_"
    exit 1
}
Set-Content -Path $lockPath -Value $proc.Id -Encoding ascii
Write-Log "resume: 起動済み pid=$($proc.Id) log=$outLog（制限中なら即失敗し、次の毎時実行が再試行する）"
