<#
.SYNOPSIS
    Build Pantheon into a one-click exe + installer.

.DESCRIPTION
    1. Build the frontend (web/frontend) into web/dist
    2. Use PyInstaller to produce the onedir exe dist/Pantheon/Pantheon.exe
    3. If Inno Setup (iscc) is available, produce dist/Pantheon-Setup.exe

    NOTE: This script is intentionally ASCII-only. Windows PowerShell 5.1 reads
    .ps1 files as the system ANSI codepage unless they carry a UTF-8 BOM, so any
    non-ASCII text here would be mis-parsed. Keep messages in ASCII.

.PARAMETER SkipFrontend
    Skip the frontend build (use when web/dist already exists).

.PARAMETER SkipInstaller
    Skip the Inno Setup installer (stop after the exe folder).

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File packaging\build.ps1
#>
[CmdletBinding()]
param(
    [switch]$SkipFrontend,
    [switch]$SkipInstaller
)

$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $PSScriptRoot          # packaging/.. = repo root
$Python = Join-Path $Root '.venv\Scripts\python.exe'
$Spec = Join-Path $Root 'packaging\pantheon.spec'
$Iss = Join-Path $Root 'packaging\pantheon.iss'

function Write-Step($msg) { Write-Host "`n=== $msg ===" -ForegroundColor Cyan }

if (-not (Test-Path $Python)) {
    throw "venv python not found: $Python . First run: py -3.12 -m venv .venv; .\.venv\Scripts\Activate.ps1; pip install -e '.[dev,web]'"
}

# --- 1. Frontend build ----------------------------------------------------- #
if ($SkipFrontend) {
    Write-Step "Skipping frontend build"
} else {
    Write-Step "Building frontend (web/frontend -> web/dist)"
    $npm = (Get-Command npm -ErrorAction SilentlyContinue)
    if ($null -eq $npm) {
        throw "npm not found on PATH. Install Node.js, or use -SkipFrontend if web/dist already exists."
    }
    Push-Location (Join-Path $Root 'web\frontend')
    try {
        if (Test-Path 'package-lock.json') { npm ci } else { npm install }
        if ($LASTEXITCODE -ne 0) { throw "npm install failed." }
        npm run build
        if ($LASTEXITCODE -ne 0) { throw "npm run build failed." }
    } finally {
        Pop-Location
    }
}

if (-not (Test-Path (Join-Path $Root 'web\dist\index.html'))) {
    throw "web/dist/index.html not found. The frontend build is required (drop -SkipFrontend)."
}

# --- 2. PyInstaller -------------------------------------------------------- #
# NOTE: do NOT redirect a native command's stderr (e.g. 2>$null) here. Under
# Windows PowerShell 5.1 that wraps stderr lines into a terminating
# NativeCommandError when ErrorActionPreference=Stop. Check $LASTEXITCODE instead.
Write-Step "Preparing PyInstaller"
& $Python -m pip show pyinstaller | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing PyInstaller into the venv..."
    & $Python -m pip install --upgrade pyinstaller
    if ($LASTEXITCODE -ne 0) { throw "Failed to install PyInstaller." }
}

Write-Step "Building exe (PyInstaller onedir)"
Push-Location $Root
try {
    & $Python -m PyInstaller $Spec --noconfirm --clean
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed." }
} finally {
    Pop-Location
}

$ExeDir = Join-Path $Root 'dist\Pantheon'
$Exe = Join-Path $ExeDir 'Pantheon.exe'
if (-not (Test-Path $Exe)) { throw "Build output not found: $Exe" }
Write-Host "[OK] Executable: $Exe" -ForegroundColor Green

# --- 3. Inno Setup installer ----------------------------------------------- #
if ($SkipInstaller) {
    Write-Step "Skipping installer (exe folder is ready)"
    Write-Host "Distribution folder: $ExeDir"
    return
}

Write-Step "Building installer with Inno Setup"
$iscc = (Get-Command iscc -ErrorAction SilentlyContinue)
if ($null -eq $iscc) {
    $candidates = @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
    )
    foreach ($c in $candidates) { if (Test-Path $c) { $iscc = $c; break } }
}
if ($null -eq $iscc) {
    Write-Warning "Inno Setup (iscc) not found. Skipping installer."
    Write-Warning "  Install with: winget install JRSoftware.InnoSetup  (then re-run to produce Pantheon-Setup.exe)"
    Write-Host "Distribution folder (no installer): $ExeDir"
    return
}

$isccPath = if ($iscc -is [System.Management.Automation.CommandInfo]) { $iscc.Source } else { $iscc }
& $isccPath $Iss
if ($LASTEXITCODE -ne 0) { throw "Inno Setup compile failed." }

$Setup = Join-Path $Root 'dist\Pantheon-Setup.exe'
if (Test-Path $Setup) {
    Write-Host "[OK] Installer: $Setup" -ForegroundColor Green
} else {
    Write-Warning "Installer output not found (check OutputDir/OutputBaseFilename in pantheon.iss)."
}
