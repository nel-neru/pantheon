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

# --- Optional code signing ------------------------------------------------- #
# Signing is OPTIONAL and OFF unless a certificate is provided via environment
# variables. This lets unsigned dev builds work while supporting signed release
# builds (Windows Smart App Control / SmartScreen block unsigned exes).
#   PANTHEON_SIGN_THUMBPRINT  - SHA1 thumbprint of a cert already in the store, OR
#   PANTHEON_SIGN_CERT        - path to a .pfx file (+ PANTHEON_SIGN_PASSWORD)
#   PANTHEON_SIGN_TIMESTAMP   - RFC3161 timestamp URL (default: DigiCert)
function Get-SignTool {
    $st = (Get-Command signtool -ErrorAction SilentlyContinue)
    if ($null -ne $st) { return $st.Source }
    $sdkRoots = @(
        "${env:ProgramFiles(x86)}\Windows Kits\10\bin",
        "$env:ProgramFiles\Windows Kits\10\bin"
    )
    foreach ($root in $sdkRoots) {
        if (Test-Path $root) {
            $found = Get-ChildItem -Path $root -Recurse -Filter signtool.exe -ErrorAction SilentlyContinue |
                Where-Object { $_.FullName -match 'x64' } |
                Sort-Object FullName -Descending | Select-Object -First 1
            if ($null -ne $found) { return $found.FullName }
        }
    }
    return $null
}

function Test-SigningConfigured {
    return [bool]($env:PANTHEON_SIGN_THUMBPRINT -or $env:PANTHEON_SIGN_CERT)
}

function Invoke-Sign($Path) {
    if (-not (Test-SigningConfigured)) { return $false }
    $signtool = Get-SignTool
    if ($null -eq $signtool) {
        Write-Warning "signtool.exe not found (install the Windows SDK). Skipping signing of $Path."
        return $false
    }
    $ts = if ($env:PANTHEON_SIGN_TIMESTAMP) { $env:PANTHEON_SIGN_TIMESTAMP } else { 'http://timestamp.digicert.com' }
    $signArgs = @('sign', '/fd', 'SHA256', '/tr', $ts, '/td', 'SHA256')
    if ($env:PANTHEON_SIGN_THUMBPRINT) {
        $signArgs += @('/sha1', $env:PANTHEON_SIGN_THUMBPRINT)
    } else {
        $signArgs += @('/f', $env:PANTHEON_SIGN_CERT)
        if ($env:PANTHEON_SIGN_PASSWORD) { $signArgs += @('/p', $env:PANTHEON_SIGN_PASSWORD) }
    }
    $signArgs += $Path
    & $signtool @signArgs
    if ($LASTEXITCODE -ne 0) { throw "signtool failed for $Path" }
    return $true
}

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

# --- 2b. Optional code signing (exe) --------------------------------------- #
Write-Step "Code signing (optional)"
if (Invoke-Sign $Exe) {
    Write-Host "[OK] Signed: $Exe" -ForegroundColor Green
} else {
    Write-Host "Code signing not configured; shipping unsigned exe."
    Write-Host "  To sign, set PANTHEON_SIGN_THUMBPRINT (cert in store) or PANTHEON_SIGN_CERT (.pfx) + PANTHEON_SIGN_PASSWORD."
}

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
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"   # winget user-scope install
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
    if (Invoke-Sign $Setup) { Write-Host "[OK] Signed installer." -ForegroundColor Green }
    Write-Host "[OK] Installer: $Setup" -ForegroundColor Green
} else {
    Write-Warning "Installer output not found (check OutputDir/OutputBaseFilename in pantheon.iss)."
}
