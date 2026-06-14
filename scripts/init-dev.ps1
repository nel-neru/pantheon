# Pantheon - initialize the DEV environment (one-time).
#
# Creates an isolated dev platform home at ~/.pantheon-dev and bootstraps it.
# Safe to re-run (pantheon init is idempotent). Never touches the user env (~/.pantheon).
$ErrorActionPreference = "Stop"
$env:PANTHEON_HOME = Join-Path $HOME ".pantheon-dev"
$root = Split-Path -Parent $PSScriptRoot
Write-Host "[Pantheon] init DEV env at $env:PANTHEON_HOME"
& "$root\.venv\Scripts\python.exe" "$root\main.py" init
